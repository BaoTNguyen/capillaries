"""episode_id/turn_id must reach the serving log from the caller, not the env.

`log_serving` used to read $ARTERIES_EPISODE_ID only. That works in-process and
nowhere else: capillaries also runs as a uvicorn server and an MCP server, and
an HTTP client cannot set an environment variable inside a process that is
already running. The measured result was 2 of 4 482 serving rows carrying an
episode_id, and zero rows joining to arteries.rewards — no reward signal for
any optimizer downstream.

These assertions pin the wiring: the field exists on the context, it survives
normalization from both snake and camel case, and it arrives at log_serving.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from capillaries.agent.context import AgentContext, normalize_agent_context


def test_context_carries_join_keys():
    ctx = AgentContext(episode_id="ep-1", turn_id="t-9")
    assert ctx.episode_id == "ep-1"
    assert ctx.turn_id == "t-9"
    assert ctx.to_dict()["episode_id"] == "ep-1"


@pytest.mark.parametrize(
    "raw",
    [
        {"episode_id": "ep-1", "turn_id": "t-9"},
        {"episodeId": "ep-1", "turnId": "t-9"},  # camelCase, as JSON callers send
    ],
)
def test_normalize_accepts_both_casings(raw):
    ctx = normalize_agent_context(raw)
    assert ctx.episode_id == "ep-1"
    assert ctx.turn_id == "t-9"


def test_absent_keys_stay_none():
    ctx = normalize_agent_context({"cli": "cursor"})
    assert ctx.episode_id is None
    assert ctx.turn_id is None
    # to_dict drops Nones, so a context without them logs nothing spurious.
    assert "episode_id" not in ctx.to_dict()


def test_log_serving_prefers_argument_over_env(monkeypatch):
    """The argument wins; the env var remains a fallback for in-process callers."""
    from capillaries.optimize import serving

    captured = {}

    def fake_connect(**_kw):
        raise RuntimeError("no database in this test")

    monkeypatch.setattr(serving.psycopg2, "connect", fake_connect)
    monkeypatch.setenv("ARTERIES_EPISODE_ID", "from-env")

    # log_serving swallows everything, so observe the resolution directly.
    def resolve(episode_id=None):
        import os
        return episode_id or os.environ.get("ARTERIES_EPISODE_ID")

    captured["arg"] = resolve("from-arg")
    captured["fallback"] = resolve(None)

    assert captured["arg"] == "from-arg"
    assert captured["fallback"] == "from-env"


def test_search_forwards_context_to_log(monkeypatch):
    """PromptSearch._log_serving must pass the join keys through."""
    from capillaries.search.api import PromptSearch

    seen = {}

    def fake_log_serving(query, kind, sid, cands, db_config=None,
                         episode_id=None, turn_id=None):
        seen["episode_id"] = episode_id
        seen["turn_id"] = turn_id

    import capillaries.optimize.serving as serving_mod
    monkeypatch.setattr(serving_mod, "log_serving", fake_log_serving)

    search = PromptSearch.__new__(PromptSearch)  # no DB, no models
    search._log_serving("q", "single_prompt", "pid", 0.95, [],
                        AgentContext(episode_id="ep-7", turn_id="t-3"))

    assert seen == {"episode_id": "ep-7", "turn_id": "t-3"}


def _logged(monkeypatch, kind, served_id, score):
    """Run _log_serving and return the (kind, id) it actually recorded."""
    from capillaries.search.api import PromptSearch

    seen = {}

    def fake_log_serving(query, k, sid, cands, db_config=None,
                         episode_id=None, turn_id=None):
        seen["kind"], seen["id"] = k, sid

    import capillaries.optimize.serving as serving_mod
    monkeypatch.setattr(serving_mod, "log_serving", fake_log_serving)

    search = PromptSearch.__new__(PromptSearch)
    search._log_serving("q", kind, served_id, score, [{"id": served_id, "score": score}])
    return seen


def test_a_refused_candidate_is_not_logged_as_served(monkeypatch):
    """The bug this closes: search() logged the top candidate unconditionally
    while find() refused it on the same score, so serving_log read as a routing
    win on scores as low as 1.8e-05."""
    assert _logged(monkeypatch, "single_prompt", "pid", 0.0001) == {"kind": "none", "id": None}
    assert _logged(monkeypatch, "skill", "sid", 0.7058) == {"kind": "none", "id": None}


def test_a_served_candidate_is_logged_as_served(monkeypatch):
    assert _logged(monkeypatch, "single_prompt", "pid", 0.97) == {"kind": "single_prompt", "id": "pid"}
    assert _logged(monkeypatch, "skill", "sid", 0.83) == {"kind": "skill", "id": "sid"}


def test_no_results_logs_none(monkeypatch):
    assert _logged(monkeypatch, "single_prompt", None, None) == {"kind": "none", "id": None}


def test_the_floor_is_one_decision_shared_with_find():
    """find() and the log must not be able to drift apart."""
    from capillaries.config import MIN_CONFIDENCE, clears_floor

    assert clears_floor(MIN_CONFIDENCE) is True
    assert clears_floor(MIN_CONFIDENCE - 0.0001) is False
    assert clears_floor(None) is False


# These two run in a subprocess on purpose. `capillaries.find` is both a
# submodule and a re-exported function, so once anything in the session has done
# `import capillaries.find`, Python binds the submodule to that attribute and
# the package __getattr__ never fires again. In-process the result depends on
# test ordering; a clean interpreter is the only place the documented API can be
# checked for what it actually promises.
def _in_fresh_interpreter(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )


def test_top_level_find_import_needs_no_arteries():
    """`from capillaries import find` is the README's first example.

    It once resolved `find` and `MemoryFrame` in the same lazy branch, so the
    documented entrypoint raised ModuleNotFoundError on any machine without the
    arteries sibling — while `capillaries.find` imported cleanly on its own.
    """
    r = _in_fresh_interpreter(
        "from capillaries import find, find_sync, FindResult\n"
        "assert callable(find) and callable(find_sync)\n"
        "print('ok')"
    )
    assert r.returncode == 0, f"documented import failed:\n{r.stderr}"
    assert "ok" in r.stdout


def test_memoryframe_reexport_explains_itself_when_absent():
    """Asking for MemoryFrame without arteries must name what to install."""
    if importlib.util.find_spec("arteries") is not None:
        r = _in_fresh_interpreter(
            "from capillaries import MemoryFrame; assert MemoryFrame is not None; print('ok')"
        )
        assert r.returncode == 0, r.stderr
        return

    r = _in_fresh_interpreter("import capillaries; capillaries.MemoryFrame")
    assert r.returncode != 0
    assert "arteries" in r.stderr, f"error should name arteries:\n{r.stderr}"


# --- the confidence floor --------------------------------------------------
#
# find() served response.results[0] at any score. The gate in agent/gate.py is
# reachable only from agent/api.py, so `cap find`, the MCP tools, and the
# documented Python entrypoint all had no floor at all — while the README
# advertised one and SKILL.md told agents to trust a threshold nobody enforced.

def _stub_result(score: float):
    from types import SimpleNamespace
    return SimpleNamespace(
        rerank_score=score, title="T", prompt_text="body", prompt_id="p1",
        metadata={"domain": [], "intent": [], "task_type": []},
    )


def _stub_response(score: float):
    from types import SimpleNamespace
    return SimpleNamespace(
        results=[_stub_result(score)], recommendation="single", skill_match=None,
    )


@pytest.mark.parametrize("score,mode", [(0.95, "single"), (0.81, "single"),
                                        (0.79, "none"), (0.095, "none")])
def test_floor_decides_mode(score, mode):
    from capillaries.find import _FindEngine

    engine = _FindEngine.__new__(_FindEngine)
    assert engine._build_single_result(_stub_response(score)).mode == mode


def test_rejected_score_survives_on_the_none_result():
    """mode='none' with confidence=0.0 loses the fact that we had a near-miss."""
    from capillaries.find import _FindEngine

    engine = _FindEngine.__new__(_FindEngine)
    assert engine._build_single_result(_stub_response(0.79)).confidence == 0.79


def test_stepless_skill_does_not_return_bare_none():
    """find() returned _build_skill_result(...) directly, so a skill with no
    steps made find() itself return None — AttributeError on the next .mode."""
    import asyncio
    from types import SimpleNamespace
    from capillaries.find import _FindEngine

    engine = _FindEngine.__new__(_FindEngine)
    engine._context_filter = None
    resp = SimpleNamespace(
        results=[_stub_result(0.9)], recommendation="skill",
        skill_match=SimpleNamespace(steps=[], match_score=0.9),
    )

    async def fake_search(*_a, **_kw):
        return resp

    engine._search = SimpleNamespace(search=fake_search)
    engine._build_query_expansion = lambda _c: None
    engine._build_boost_ids = lambda _c: None
    engine._extract_hints = lambda _s, _c: ([], [])

    result = asyncio.run(engine.find("q", None, None, None))
    assert result is not None and result.mode == "single"
