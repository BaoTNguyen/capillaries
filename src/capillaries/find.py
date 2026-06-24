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
    from capillaries.agent.memory_types import MemoryFrame

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

from capillaries.agent.memory_types import MemoryFrame
from capillaries.search.memory_filter import MemoryFilter

SINGLE_THRESHOLD = 0.3
SKILL_THRESHOLD = 0.50
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
    skill_slug: str | None = None
    steps: list[dict] = field(default_factory=list)

    # Metadata for arteries to inspect
    domain: list[str] = field(default_factory=list)
    intent: list[str] = field(default_factory=list)
    task_type: list[str] = field(default_factory=list)

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
        if self.mode == "skill":
            d["skill_id"] = self.skill_id
            d["skill_name"] = self.skill_name
            d["skill_slug"] = self.skill_slug
            d["steps"] = self.steps
        return d


_instance: _FindEngine | None = None


class _FindEngine:
    """Lazy-loaded singleton wrapping retrieval + reranking + skill recall."""

    def __init__(self) -> None:
        from capillaries.search.api import PromptSearch
        from capillaries.skills.recall import SkillRecall

        self._search = PromptSearch()
        self._skill_recall = SkillRecall()
        self._memory_filter = MemoryFilter()

    async def find(
        self,
        situation: str,
        memory: MemoryFrame | None = None,
        prefer: str = "auto",
    ) -> FindResult:
        domain_hints, intent_hints, complexity = self._extract_hints(situation, memory)

        skill_hints: dict[str, list[str]] = {}
        if domain_hints:
            skill_hints["domain"] = domain_hints
        if intent_hints:
            skill_hints["intent"] = intent_hints

        prefer_mode = prefer
        if prefer_mode == "auto":
            prefer_mode = "skill" if complexity >= 3 else "single"

        # Skill-preferred path: check skills first for complex situations
        if prefer_mode == "skill":
            skill_result = self._try_skill(situation, skill_hints)
            if skill_result:
                return skill_result

        # Single prompt retrieval
        single_result = await self._try_single(situation, memory)
        if single_result and single_result.confidence >= SINGLE_THRESHOLD:
            return single_result

        # Fallback: try skill if we haven't yet
        if prefer_mode != "skill":
            skill_result = self._try_skill(situation, skill_hints)
            if skill_result:
                return skill_result

        # Return best single even if below threshold, or none
        if single_result and single_result.confidence > 0.0:
            return single_result

        return FindResult(mode="none", confidence=0.0)

    def _extract_hints(
        self, situation: str, memory: MemoryFrame | None
    ) -> tuple[list[str], list[str], int]:
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
        return inference.domain, inference.intent, inference.complexity

    async def _try_single(
        self, situation: str, memory: MemoryFrame | None = None
    ) -> FindResult | None:
        top_k = MEMORY_FILTER_CANDIDATES if memory else 1
        response = await self._search.search(situation, top_k=top_k)
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

    def _try_skill(self, situation: str, hints: dict) -> FindResult | None:
        match = self._skill_recall.search(situation, hints)
        if match is None or match.match_score < SKILL_THRESHOLD:
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
            skill_slug=match.slug,
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
                   'auto' checks skills first for complex situations.

    Returns:
        FindResult with .mode, .confidence, .prompt_text, and metadata.
        Caller can pass result.prompt_id to optimize.resolve.resolve_prompt_text()
        for model-specific variants when needed.
    """
    engine = _get_engine()
    return await engine.find(situation, memory, prefer)


def find_sync(
    situation: str,
    memory: MemoryFrame | None = None,
    prefer: str = "auto",
) -> FindResult:
    """Synchronous wrapper for non-async callers."""
    return asyncio.run(find(situation, memory, prefer))
