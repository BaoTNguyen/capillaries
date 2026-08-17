"""
Memory-informed post-rerank filter.

Takes the top-N candidates from the cross-encoder reranker and re-scores
them using signals from the MemoryFrame that the reranker is blind to:
domain affinity, prior retrieval outcomes, user intent, and session insights.

The reranker handles semantic quality (query-document relevance).
This filter handles contextual fit (does this result match what we know
about the user's current and long-term work?).

Usage:
    from capillaries.search.memory_filter import MemoryFilter
    from arteries.memory_types import MemoryFrame

    mf = MemoryFilter()
    filtered = mf.apply(candidates, memory_frame)
    best = filtered[0]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from arteries.memory_types import MemoryFrame
from capillaries.search.reranker import RankedResult


DOMAIN_BOOST = 0.06
RECURRING_DOMAIN_BOOST = 0.03
INTENT_BOOST = 0.04
INSIGHT_DOMAIN_BOOST = 0.02
PRIOR_RETRIEVAL_PENALTY = -0.10
PRIOR_RETRIEVAL_UNUSED_THRESHOLD = 0.4


@dataclass
class FilteredResult:
    """RankedResult with memory adjustment applied."""

    result: RankedResult
    final_score: float
    memory_adjustment: float
    adjustment_reasons: list[str]


class MemoryFilter:
    """
    Post-rerank filter that applies MemoryFrame signals to candidate selection.

    Designed to be stateless — reads the frame, scores, returns. The memory
    project owns all mutation logic.
    """

    def apply(
        self,
        candidates: list[RankedResult],
        memory: MemoryFrame,
    ) -> list[FilteredResult]:
        """
        Re-score candidates using memory context and return sorted results.

        Each candidate's rerank_score is adjusted by additive bonuses/penalties
        derived from the MemoryFrame. The adjustment is intentionally small —
        memory breaks ties in the reranker's narrow band, it doesn't override
        strong semantic signals.
        """
        if not candidates:
            return []

        active = set(d.lower() for d in memory.persistent.active_domains)
        recurring = set(d.lower() for d in memory.evergreen.recurring_domains)
        intents = set(i.lower() for i in memory.evergreen.user_intent)
        insight_domains = self._extract_insight_domains(memory)
        penalized_prompts = self._build_penalty_map(memory)

        results = []
        for candidate in candidates:
            adjustment = 0.0
            reasons: list[str] = []

            candidate_domains = set(
                d.lower() for d in candidate.metadata.get("domain", [])
            )
            candidate_intents = set(
                i.lower() for i in candidate.metadata.get("intent", [])
            )

            if active and candidate_domains & active:
                overlap = candidate_domains & active
                adjustment += DOMAIN_BOOST
                reasons.append(f"active domain match: {overlap}")

            if recurring and candidate_domains & recurring:
                overlap = candidate_domains & recurring
                if not (candidate_domains & active):
                    adjustment += RECURRING_DOMAIN_BOOST
                    reasons.append(f"recurring domain match: {overlap}")

            if intents and candidate_intents & intents:
                overlap = candidate_intents & intents
                adjustment += INTENT_BOOST
                reasons.append(f"intent match: {overlap}")

            if insight_domains and candidate_domains & insight_domains:
                overlap = candidate_domains & insight_domains
                adjustment += INSIGHT_DOMAIN_BOOST
                reasons.append(f"session insight domain match: {overlap}")

            if candidate.prompt_id in penalized_prompts:
                penalty_reason = penalized_prompts[candidate.prompt_id]
                adjustment += PRIOR_RETRIEVAL_PENALTY
                reasons.append(f"prior retrieval penalty: {penalty_reason}")

            results.append(
                FilteredResult(
                    result=candidate,
                    final_score=candidate.rerank_score + adjustment,
                    memory_adjustment=adjustment,
                    adjustment_reasons=reasons,
                )
            )

        results.sort(key=lambda r: (r.final_score, r.result.rrf_score), reverse=True)
        return results

    def _extract_insight_domains(self, memory: MemoryFrame) -> set[str]:
        """Pull domain tags from session insights."""
        domains: set[str] = set()
        for insight in memory.persistent.session_insights:
            if insight.domain:
                domains.add(insight.domain.lower())
        return domains

    def _build_penalty_map(self, memory: MemoryFrame) -> dict[str, str]:
        """
        Build a map of prompt_ids that should be penalized.

        A prior retrieval with low relevance means the prompt was surfaced
        but the agent didn't use it — a signal it wasn't helpful.
        """
        penalized: dict[str, str] = {}
        for cached in memory.persistent.prior_retrievals:
            if cached.relevance < PRIOR_RETRIEVAL_UNUSED_THRESHOLD:
                penalized[cached.prompt_id] = (
                    f"surfaced for '{cached.situation}' but unused "
                    f"(relevance={cached.relevance:.2f})"
                )
        return penalized
