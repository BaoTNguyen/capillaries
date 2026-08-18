"""Normalized agent context accepted by Capillaries interfaces.

Arteries owns CLI-specific extraction. Capillaries only accepts a small,
CLI-neutral context object so MCP, HTTP, and Python callers can pass the same
metadata without teaching retrieval code about each agent surface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AgentContext:
    cli: str = "generic"
    event: str = "prompt"
    agent_id: str | None = None
    parent_agent_id: str | None = None
    agent_role: str = "parent"
    session_id: str | None = None
    cwd: str | None = None
    capabilities: dict[str, Any] | None = None
    # Join keys for the reward signal. Without them a serving_log row cannot be
    # matched to the episode it belonged to, and the outcome join returns
    # nothing — which is the state the log was in until these were threaded.
    episode_id: str | None = None
    turn_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, {}, [])}


def normalize_agent_context(raw: dict[str, Any] | AgentContext | None) -> AgentContext | None:
    if raw is None or raw == {}:
        return None
    if isinstance(raw, AgentContext):
        return raw
    return AgentContext(
        cli=str(raw.get("cli") or "generic").lower(),
        event=str(raw.get("event") or "prompt"),
        agent_id=_text(raw, "agent_id", "agentId"),
        parent_agent_id=_text(raw, "parent_agent_id", "parentAgentId"),
        agent_role=str(raw.get("agent_role") or raw.get("agentRole") or raw.get("role") or "parent"),
        session_id=_text(raw, "session_id", "sessionId"),
        cwd=_text(raw, "cwd", "working_directory", "project_dir", "projectDirectory"),
        capabilities=raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else None,
        episode_id=_text(raw, "episode_id", "episodeId"),
        turn_id=_text(raw, "turn_id", "turnId"),
    )


def with_agent_context(context: dict[str, Any] | None, agent_context: AgentContext | None) -> dict[str, Any] | None:
    if agent_context is None:
        return context
    merged = dict(context or {})
    merged.setdefault("agent_context", agent_context.to_dict())
    return merged


def _text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return None
