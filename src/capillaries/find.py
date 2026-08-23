"""
Top-level retrieval API for the memory project (arteries).

Stateless retrieval function — arteries decides *when* to call,
this module handles *what* comes back. No LLM gate, no session
management, no opinions about timing.

There is one opinion: a confidence floor. Below MIN_CONFIDENCE the result is
mode="none" carrying the rejected score, rather than rank 1 served regardless.

Usage:
    from capillaries import find

    result = await find("build a cash flow model")

    # With context from arteries
    from capillaries.find import FindResult
    from arteries.memory_types import MemoryFrame

    result = await find("debug auth middleware", context=context_frame)

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
from typing import Any, TYPE_CHECKING

from capillaries.agent.context import AgentContext, normalize_agent_context
from capillaries.config import MIN_CONFIDENCE
from capillaries.search.context_filter import ContextFilter

if TYPE_CHECKING:
    # arteries owns this contract and is not on PyPI. Every use below is an
    # annotation, and `from __future__ import annotations` keeps those strings
    # at runtime — so capillaries imports fine without arteries installed, and
    # the memory-aware path fails at the point of use instead.
    from arteries.memory_types import MemoryFrame

# Modality (prompt vs skill) is decided entirely inside PromptSearch: prompt
# and skill candidates are retrieved into one pool and reranked in one pass,
# so this module just trusts `response.recommendation` — it never re-decides
# with a second, separately-scored lookup.
CONTEXT_FILTER_CANDIDATES = 5


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
    skill_summary: str | None = None
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
        self._context_filter = ContextFilter()

    async def find(
        self,
        situation: str,
        context: MemoryFrame | None = None,
        prefer: str = "auto",
        agent_context: AgentContext | None = None,
        filters: dict[str, Any] | None = None,
        skill_hints: dict[str, list[str]] | None = None,
    ) -> FindResult:
        domain_hints, intent_hints = self._extract_hints(situation, context)

        inferred_skill_hints: dict[str, list[str]] = {}
        if domain_hints:
            inferred_skill_hints["domain"] = domain_hints
        if intent_hints:
            inferred_skill_hints["intent"] = intent_hints
        if skill_hints:
            for key, values in skill_hints.items():
                inferred_skill_hints[key] = list(dict.fromkeys(
                    inferred_skill_hints.get(key, []) + values
                ))

        # prompt-vs-skill is decided by one comparison, not an order of
        # attempts: prompt and skill candidates are retrieved into one pool
        # and reranked in one pass (see search/api.py). `prefer` lets a
        # caller force one path when it already knows which fits.
        top_k = CONTEXT_FILTER_CANDIDATES if context else 1
        resp = await self._search.search(
            situation, filters=filters, top_k=top_k,
            skill_hints=inferred_skill_hints or None, prefer=prefer,
            query_expansion=self._build_query_expansion(context),
            boost_prompt_ids=self._build_boost_ids(context),
            agent_context=agent_context,
            context=context,
        )

        if resp.recommendation == "skill" and resp.skill_match:
            # Assigned, not returned: a skill match with no steps (or below the
            # floor) yields None here, and returning that handed callers a bare
            # None instead of a FindResult — an AttributeError on `.mode`.
            skill_result = self._build_skill_result(resp.skill_match)
            if skill_result:
                return skill_result

        single_result = self._build_single_result(resp, context)
        if single_result:
            return single_result

        return FindResult(mode="none", confidence=0.0)

    def _build_query_expansion(self, context: MemoryFrame | None) -> str | None:
        """Recent conversation + session insight text, for a second retrieval
        pass only (see PromptSearch.search's query_expansion) — never used
        for reranking, so a noisy or off-topic frame can't win on its own,
        only add candidates the reranker then judges against the real query.
        """
        if not context:
            return None
        parts = list(context.ephemeral.recent_messages[-3:])
        parts += [
            i.text for i in context.persistent.session_insights[:3]
            if i.confidence >= 0.5
        ]
        if not parts:
            return None
        return " ".join(parts)[:1000]

    def _build_boost_ids(self, context: MemoryFrame | None) -> list[str] | None:
        """Prompts arteries already knows were relevant to a similar past
        situation — injected as extra candidates (see
        PromptSearch.search's boost_prompt_ids), not served on trust.
        """
        if not context:
            return None
        promoted = sorted(
            (r for r in context.persistent.prior_retrievals if r.relevance >= 0.7),
            key=lambda r: r.relevance, reverse=True,
        )
        ids = [r.prompt_id for r in promoted[:5]]
        return ids or None

    def _extract_hints(
        self, situation: str, context: MemoryFrame | None
    ) -> tuple[list[str], list[str]]:
        domain: list[str] = []
        intent: list[str] = []

        if context:
            if context.persistent.active_domains:
                domain = context.persistent.active_domains
            if context.evergreen.user_intent:
                intent = context.evergreen.user_intent

        from capillaries.agent.inference import infer_from_situation

        inference = infer_from_situation(
            situation,
            explicit_domain=domain or None,
            explicit_intent=intent or None,
        )
        return inference.domain, inference.intent

    def _build_single_result(
        self, response, context: MemoryFrame | None = None
    ) -> FindResult | None:
        if not response.results:
            return None

        # Ordering already reflects the MemoryFrame: search() runs the
        # context filter over the whole reranked pool, before prompts and
        # skills are split. Re-applying it here would double-count.
        top = response.results[0]

        # The rejected score rides along on the none-result. A caller that wants
        # to log "we had something at 0.29" can; one that checks .mode cannot
        # accidentally serve it.
        if top.rerank_score < MIN_CONFIDENCE:
            return FindResult(mode="none", confidence=top.rerank_score)

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

        # Same floor as the single path. A skill wins by out-scoring prompts,
        # so an unfiltered weak skill match is the more likely bad serve of the
        # two: it arrives with steps attached and looks authoritative.
        if match.match_score < MIN_CONFIDENCE:
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
            skill_summary=match.summary,
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
    context: MemoryFrame | None = None,
    prefer: str = "auto",
    agent_context: dict[str, Any] | AgentContext | None = None,
    filters: dict[str, Any] | None = None,
    skill_hints: dict[str, list[str]] | None = None,
) -> FindResult:
    """
    Find the best prompt or skill for a situation.

    This is the primary API for the memory project. Arteries calls this
    after deciding that a retrieval is warranted — no gating logic here.

    Args:
        situation: Natural language description of what the user needs.
        context:   MemoryFrame from arteries (optional). Used to extract
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
    # Normalized before the search, not after: episode_id/turn_id ride along to
    # the serving log, which is what makes a serving row joinable to its reward.
    normalized = normalize_agent_context(agent_context)
    engine = _get_engine()
    result = await engine.find(
        situation, context, prefer, normalized, filters, skill_hints,
    )
    if normalized:
        result.agent_context = normalized.to_dict()
    return result


def find_sync(
    situation: str,
    context: MemoryFrame | None = None,
    prefer: str = "auto",
    agent_context: dict[str, Any] | AgentContext | None = None,
    filters: dict[str, Any] | None = None,
    skill_hints: dict[str, list[str]] | None = None,
) -> FindResult:
    """Synchronous wrapper for non-async callers."""
    return asyncio.run(find(situation, context, prefer, agent_context, filters, skill_hints))
