"""
Top-level retrieval API for the memory project (arteries).

Stateless retrieval function — arteries decides *when* to call,
this module handles *what* comes back. No LLM gate, no session
management, no opinions about timing.

Usage:
    from capillaries import find

    result = await find("build a cash flow model")

    # With memory context from arteries
    from capillaries.find import FindResult
    from arteries.memory_types import MemoryFrame

    result = await find("debug auth middleware", memory=memory_frame)

    result.prompt_text   # ready-to-use prompt content
    result.confidence    # rerank score (higher = more relevant)
    result.title         # human-readable name
    result.mode          # 'single' | 'skill' | 'none'

Sync wrapper:
    from capillaries import find_sync
    result = find_sync("build a cash flow model")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from capillaries.agent.context import AgentContext, normalize_agent_context
from arteries.memory_types import MemoryFrame
from capillaries.search.memory_filter import MemoryFilter

# Modality (prompt vs skill) is decided entirely inside PromptSearch: prompt
# and skill candidates are retrieved into one pool and reranked in one pass,
# so this module just trusts `response.recommendation` — it never re-decides
# with a second, separately-scored lookup.
MEMORY_FILTER_CANDIDATES = 5


@dataclass
class FindResult:
    """Single best retrieval result returned to arteries."""

    mode: str                           # 'single' | 'skill' | 'none'
    confidence: float                   # rerank or skill match score
    title: str = ""
    prompt_text: str = ""
    prompt_id: str = ""

    # Populated when mode == 'skill'
    skill_id: str | None = None
    skill_name: str | None = None
    skill_tag: str | None = None
    steps: list[dict] = field(default_factory=list)

    # Metadata for arteries to inspect
    domain: list[str] = field(default_factory=list)
    intent: list[str] = field(default_factory=list)
    task_type: list[str] = field(default_factory=list)
    agent_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "mode": self.mode,
            "confidence": round(self.confidence, 4),
            "title": self.title,
            "prompt_text": self.prompt_text,
            "prompt_id": self.prompt_id,
            "domain": self.domain,
            "intent": self.intent,
            "task_type": self.task_type,
        }
        if self.agent_context:
            d["agent_context"] = self.agent_context
        if self.mode == "skill":
            d["skill_id"] = self.skill_id
            d["skill_name"] = self.skill_name
            d["skill_tag"] = self.skill_tag
            d["steps"] = self.steps
        return d


_instance: _FindEngine | None = None


class _FindEngine:
    """Lazy-loaded singleton wrapping retrieval + reranking + skill recall."""

    def __init__(self) -> None:
        from capillaries.search.api import PromptSearch

        self._search = PromptSearch()
        self._memory_filter = MemoryFilter()

    async def find(
        self,
        situation: str,
        memory: MemoryFrame | None = None,
        prefer: str = "auto",
    ) -> FindResult:
        domain_hints, intent_hints = self._extract_hints(situation, memory)

        skill_hints: dict[str, list[str]] = {}
        if domain_hints:
            skill_hints["domain"] = domain_hints
        if intent_hints:
            skill_hints["intent"] = intent_hints

        # prompt-vs-skill is decided by one comparison, not an order of
        # attempts: prompt and skill candidates are retrieved into one pool
        # and reranked in one pass (see search/api.py). `prefer` lets a
        # caller force one path when it already knows which fits.
        top_k = MEMORY_FILTER_CANDIDATES if memory else 1
        resp = await self._search.search(
            situation, top_k=top_k, skill_hints=skill_hints or None, prefer=prefer,
        )

        if resp.recommendation == "skill" and resp.skill_match:
            return self._build_skill_result(resp.skill_match)

        single_result = self._build_single_result(resp, memory)
        if single_result:
            return single_result

        return FindResult(mode="none", confidence=0.0)

    def _extract_hints(
        self, situation: str, memory: MemoryFrame | None
    ) -> tuple[list[str], list[str]]:
        domain: list[str] = []
        intent: list[str] = []

        if memory:
            if memory.persistent.active_domains:
                domain = memory.persistent.active_domains
            if memory.evergreen.user_intent:
                intent = memory.evergreen.user_intent

        from capillaries.agent.inference import infer_from_situation

        inference = infer_from_situation(
            situation,
            explicit_domain=domain or None,
            explicit_intent=intent or None,
        )
        return inference.domain, inference.intent

    def _build_single_result(
        self, response, memory: MemoryFrame | None = None
    ) -> FindResult | None:
        if not response.results:
            return None

        if memory:
            filtered = self._memory_filter.apply(response.results, memory)
            best = filtered[0]
            top = best.result
        else:
            top = response.results[0]

        return FindResult(
            mode="single",
            confidence=top.rerank_score,
            title=top.title,
            prompt_text=top.prompt_text,
            prompt_id=top.prompt_id,
            domain=top.metadata.get("domain", []),
            intent=top.metadata.get("intent", []),
            task_type=top.metadata.get("task_type", []),
        )

    def _build_skill_result(self, match) -> FindResult | None:
        # A skill with no steps has nothing to serve — returning it hands the
        # caller prompt_text="". PromptSearch already filters these out as
        # ineligible candidates, so this is a defensive no-op in practice.
        if not match.steps:
            return None

        steps = []
        for step in match.steps:
            steps.append({
                "step_order": step["step_order"],
                "prompt_id": step["prompt_id"],
                "prompt_text": step.get("prompt_text", ""),
            })

        return FindResult(
            mode="skill",
            confidence=match.match_score,
            title=match.name,
            prompt_text=match.steps[0].get("prompt_text", "") if match.steps else "",
            skill_id=match.skill_id,
            skill_name=match.name,
            skill_tag=match.tag,
            steps=steps,
            domain=match.domain if hasattr(match, "domain") else [],
            intent=match.intent if hasattr(match, "intent") else [],
            task_type=match.task_type if hasattr(match, "task_type") else [],
        )


def _get_engine() -> _FindEngine:
    global _instance
    if _instance is None:
        _instance = _FindEngine()
    return _instance


async def find(
    situation: str,
    memory: MemoryFrame | None = None,
    prefer: str = "auto",
    agent_context: dict[str, Any] | AgentContext | None = None,
) -> FindResult:
    """
    Find the best prompt or skill for a situation.

    This is the primary API for the memory project. Arteries calls this
    after deciding that a retrieval is warranted — no gating logic here.

    Args:
        situation: Natural language description of what the user needs.
        memory:    MemoryFrame from arteries (optional). Used to extract
                   domain/intent hints from active context.
        prefer:    'auto' (default), 'single', or 'skill'.
                   'auto' retrieves both prompt and skill candidates into one
                   pool and reranks them together — whichever scores highest
                   wins.
        agent_context: Optional normalized agent/CLI metadata. It is returned
                       for telemetry and callers; retrieval remains CLI-neutral.

    Returns:
        FindResult with .mode, .confidence, .prompt_text, and metadata.
        Caller can pass result.prompt_id to optimize.resolve.resolve_prompt_text()
        for model-specific variants when needed.
    """
    engine = _get_engine()
    result = await engine.find(situation, memory, prefer)
    normalized = normalize_agent_context(agent_context)
    if normalized:
        result.agent_context = normalized.to_dict()
    return result


def find_sync(
    situation: str,
    memory: MemoryFrame | None = None,
    prefer: str = "auto",
    agent_context: dict[str, Any] | AgentContext | None = None,
) -> FindResult:
    """Synchronous wrapper for non-async callers."""
    return asyncio.run(find(situation, memory, prefer, agent_context))
