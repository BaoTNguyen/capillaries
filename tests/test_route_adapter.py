from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import asyncio

from capillaries.agent import api
from capillaries.agent.route import AgentRouter, RouteResponse
from capillaries.find import FindResult


def test_agent_router_delegates_to_shared_find():
    result = FindResult(
        mode="single", confidence=0.95, title="Prompt", prompt_text="Do [THING].",
        prompt_id="prompt-1", domain=["business"], intent=["build"], task_type=["plan"],
    )
    with patch("capillaries.agent.route.find", new_callable=AsyncMock, return_value=result) as shared_find:
        response = asyncio.run(AgentRouter().route(
            "Build a business plan", domain=["business"], intent=["build"],
            context={"THING": "the work"}, source="public", modality="text",
        ))

    assert response.mode == "single"
    assert response.recommendation["prompt_text"] == "Do the work."
    assert shared_find.await_args.kwargs["filters"] == {"source": "public", "modality": "text"}
    assert shared_find.await_args.kwargs["skill_hints"] == {"domain": ["business"], "intent": ["build"]}


def test_http_route_does_not_run_the_retired_gate():
    response = RouteResponse(mode="none", confidence=0.42, trace_id="trace")
    router = SimpleNamespace(route=AsyncMock(return_value=response))
    with patch.object(api, "_get_router", return_value=router):
        payload = asyncio.run(api.route(api.RouteRequest(situation="Review the current operating plan.")))

    assert payload == {"mode": "none", "confidence": 0.42, "trace_id": "trace"}
    router.route.assert_awaited_once()


def test_agent_router_formats_shared_skill_result():
    result = FindResult(
        mode="skill", confidence=0.96, title="", prompt_text="",
        skill_id="skill-1", skill_name="Plan", skill_tag="plan", skill_summary="A plan.",
        steps=[{"step_order": 1, "prompt_id": "prompt-1", "prompt_text": "Do [THING]."}],
    )
    router = AgentRouter()
    router._create_session = lambda *_, **_kw: None
    with patch("capillaries.agent.route.find", new_callable=AsyncMock, return_value=result):
        response = asyncio.run(router.route("Build a plan", context={"THING": "the work"}))

    assert response.mode == "skill"
    assert response.skill["total_steps"] == 1
    assert response.skill["first_step"]["prompt_text"] == "Do the work."
