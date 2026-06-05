"""
FastAPI endpoints for agent integration layer.

Exposes /agent/route, /agent/step, /agent/feedback, /agent/catalog, /agent/discover.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from prompt_flow.agent.catalog import CatalogHandler, get_discover_response
from prompt_flow.agent.execute import SkillExecutor
from prompt_flow.agent.feedback import FeedbackHandler
from prompt_flow.agent.gate import (
    gate as run_gate,
    MemoryFrame,
    EphemeralMemory,
    PersistentMemory,
    EvergreenMemory,
    Insight,
    CachedRetrieval,
)
from prompt_flow.agent.generate import generate, generate_stream
from prompt_flow.agent.route import AgentRouter


router = APIRouter(prefix="/agent", tags=["agent"])


class RouteRequest(BaseModel):
    situation: str = Field(..., min_length=10, max_length=2000)
    domain: list[str] | None = Field(None, description="Domain hints")
    intent: list[str] | None = Field(None, description="Intent hints")
    complexity: int | None = Field(None, ge=1, le=5)
    prefer: str = Field(default="auto", description="'single', 'skill', or 'auto'")
    context: dict[str, Any] | None = Field(None, description="Structured context for template filling")
    session_id: str | None = Field(None, description="For continuing previous interaction")
    recent_turns: list[str] | None = Field(None, description="Recent conversation messages for gate context")
    memory: dict[str, Any] | None = Field(None, description="MemoryFrame from the memory project (ephemeral/persistent/evergreen tiers)")
    source: str = Field(default="private", description="'private' (default) or 'public' for demo prompts")
    modality: str = Field(default="text", description="'text', 'image', 'video' — filters by output modality")
    skip_gate: bool = Field(default=False, description="Bypass the gate and always search")
    execute: bool = Field(default=False, description="Run the retrieved prompt through an LLM and return the completion")
    model: str | None = Field(None, description="LLM model override for execution")
    stream: bool = Field(default=False, description="Stream the LLM response (only with execute=True)")


class StepRequest(BaseModel):
    session_id: str
    step_order: int = Field(..., ge=1)
    previous_output: str | None = Field(None, max_length=50000)
    variables: dict[str, str] | None = None
    action: str = Field(default="execute", description="'execute', 'skip', or 'abort'")
    skip_reason: str | None = None
    run: bool = Field(default=False, description="Run the step's prompt through an LLM and return the completion")
    model: str | None = Field(None, description="LLM model override")


class FeedbackRequest(BaseModel):
    trace_id: str
    outcome: str = Field(..., description="'success', 'partial', 'failure', or 'skipped'")
    quality_score: float | None = Field(None, ge=0, le=1)
    failure_step: int | None = None
    failure_reason: str | None = Field(None, description="'irrelevant', 'too_vague', 'too_specific', 'wrong_domain', 'outdated', 'template_unfillable', 'other'")
    notes: str | None = Field(None, max_length=2000)
    prompt_modifications: list[dict] | None = None
    session_id: str | None = None
    per_step_feedback: list[dict] | None = None


class CatalogRequest(BaseModel):
    view: str = Field(default="overview", description="'overview', 'domains', or 'skills'")
    domain_filter: str | None = None


_router: AgentRouter | None = None
_executor: SkillExecutor | None = None
_feedback_handler: FeedbackHandler | None = None
_catalog_handler: CatalogHandler | None = None


def _get_router() -> AgentRouter:
    global _router
    if _router is None:
        _router = AgentRouter()
    return _router


def _get_executor() -> SkillExecutor:
    global _executor
    if _executor is None:
        _executor = SkillExecutor()
    return _executor


def _get_feedback_handler() -> FeedbackHandler:
    global _feedback_handler
    if _feedback_handler is None:
        _feedback_handler = FeedbackHandler()
    return _feedback_handler


def _get_catalog_handler() -> CatalogHandler:
    global _catalog_handler
    if _catalog_handler is None:
        _catalog_handler = CatalogHandler()
    return _catalog_handler


class GenerateRequest(BaseModel):
    prompt_text: str = Field(..., min_length=1, max_length=50000, description="Fully resolved prompt to run")
    model: str | None = Field(None, description="LLM model name")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    system: str | None = Field(None, max_length=5000, description="Optional system message")
    stream: bool = Field(default=False, description="Stream the response token-by-token")


def _build_memory_frame(raw: dict[str, Any]) -> MemoryFrame:
    """Deserialize a JSON dict into a typed MemoryFrame."""
    eph_raw = raw.get("ephemeral", {})
    per_raw = raw.get("persistent", {})
    evg_raw = raw.get("evergreen", {})

    ephemeral = EphemeralMemory(
        recent_messages=eph_raw.get("recent_messages", []),
        topic_drift=float(eph_raw.get("topic_drift", 0.0)),
        turn_count=int(eph_raw.get("turn_count", 0)),
    )

    persistent = PersistentMemory(
        session_insights=[Insight(**i) for i in per_raw.get("session_insights", [])],
        prior_retrievals=[CachedRetrieval(**r) for r in per_raw.get("prior_retrievals", [])],
        active_domains=per_raw.get("active_domains", []),
    )

    evergreen = EvergreenMemory(
        user_intent=evg_raw.get("user_intent", []),
        recurring_domains=evg_raw.get("recurring_domains", []),
        ground_truth_insights=[Insight(**i) for i in evg_raw.get("ground_truth_insights", [])],
        last_retrieval_ts=evg_raw.get("last_retrieval_ts"),
        retrieval_confidence=evg_raw.get("retrieval_confidence"),
    )

    return MemoryFrame(ephemeral=ephemeral, persistent=persistent, evergreen=evergreen)


@router.post("/route", response_model=None)
async def route(req: RouteRequest) -> dict | StreamingResponse:
    """
    Primary entry point for agents. Runs a gate check first to decide whether
    the situation warrants a prompt search. If the gate says skip, returns
    immediately with mode="none".

    With execute=True, the retrieved prompt is also run through an LLM and
    the completion is included in the response (or streamed).
    """
    if not req.skip_gate:
        memory_frame = _build_memory_frame(req.memory) if req.memory else None
        gate_decision = await run_gate(
            message=req.situation,
            recent_turns=req.recent_turns,
            memory=memory_frame,
        )
        if not gate_decision.search:
            return {
                "mode": "none",
                "confidence": gate_decision.confidence,
                "reason": gate_decision.reason,
                "gate": gate_decision.to_dict(),
            }

    agent_router = _get_router()
    result = await agent_router.route(
        situation=req.situation,
        domain=req.domain,
        intent=req.intent,
        complexity=req.complexity,
        prefer=req.prefer,
        context=req.context,
        session_id=req.session_id,
        source=req.source,
        modality=req.modality,
    )
    response = result.to_dict()
    response["gate"] = {"search": True, "confidence": 1.0, "reason": "gate passed"}

    if not req.execute:
        return response

    prompt_text = _extract_prompt_text(result)
    if not prompt_text:
        return response

    if req.stream:
        async def _stream():
            import json as _json
            yield _json.dumps(response) + "\n---STREAM_START---\n"
            async for chunk in generate_stream(prompt_text, model=req.model):
                yield chunk
        return StreamingResponse(_stream(), media_type="text/plain")

    completion = await generate(prompt_text, model=req.model)
    response["completion"] = completion
    return response


@router.post("/generate", response_model=None)
async def run_generate(req: GenerateRequest) -> dict | StreamingResponse:
    """
    Run an arbitrary prompt through the LLM. Use this after /agent/route
    when you want manual control over what gets executed, or to re-run
    a prompt with different parameters.
    """
    if req.stream:
        return StreamingResponse(
            generate_stream(req.prompt_text, model=req.model, temperature=req.temperature, system=req.system),
            media_type="text/plain",
        )
    result = await generate(req.prompt_text, model=req.model, temperature=req.temperature, system=req.system)
    return result


def _extract_prompt_text(result) -> str | None:
    """Pull the resolved prompt text from a RouteResponse for execution."""
    if result.mode == "single" and result.recommendation:
        return result.recommendation.get("prompt_text")
    if result.mode == "skill" and result.skill:
        first = result.skill.get("first_step")
        if first:
            return first.get("prompt_text")
    return None


@router.post("/step")
async def execute_step(req: StepRequest) -> dict:
    """
    Execute a step in a multi-step skill workflow.
    """
    executor = _get_executor()
    result = await executor.execute_step(
        session_id=req.session_id,
        step_order=req.step_order,
        previous_output=req.previous_output,
        variables=req.variables,
        action=req.action,
        skip_reason=req.skip_reason,
    )

    return {
        "session_id": result.session_id,
        "status": result.status,
        "current_step": result.current_step,
        "progress": result.progress,
        "context_summary": result.context_summary,
        "next_step_preview": result.next_step_preview,
    }


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """
    Report whether a prompt or skill worked.
    """
    handler = _get_feedback_handler()
    return handler.submit_feedback(
        trace_id=req.trace_id,
        outcome=req.outcome,
        mode="single",
        quality_score=req.quality_score,
        failure_step=req.failure_step,
        failure_reason=req.failure_reason,
        notes=req.notes,
        prompt_modifications=req.prompt_modifications,
        per_step_feedback=req.per_step_feedback,
        session_id=req.session_id,
    )


@router.get("/catalog")
async def get_catalog(view: str = "overview", domain_filter: str | None = None) -> dict:
    """
    Browse available domains, skills, and statistics.
    """
    handler = _get_catalog_handler()
    return handler.get_catalog(view=view, domain_filter=domain_filter)


@router.get("/discover")
async def discover() -> dict:
    """
    Self-describing endpoint for agent discovery.
    """
    return get_discover_response()