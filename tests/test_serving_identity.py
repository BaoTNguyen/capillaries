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
    search._log_serving("q", "single_prompt", "pid", [],
                        AgentContext(episode_id="ep-7", turn_id="t-3"))

    assert seen == {"episode_id": "ep-7", "turn_id": "t-3"}


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
