"""
PromptSearch — the single library endpoint for agent callers.

Wraps hybrid retrieval (pgvector HNSW + pg_trgm, RRF) and cross-encoder
reranking behind a two-tier recommendation:

  1. Single prompt  — top reranked result is strong enough on its own
  2. Existing skill — a validated skill from skills.skills matches the query

Callers see a SearchResponse with a `recommendation` field indicating
which tier was selected: 'single_prompt' or 'skill'.

Usage (async):
    from capillaries.search.api import PromptSearch

    ps = PromptSearch()

    results = await ps.search("write a go-to-market strategy")
    results = await ps.search(
        "analyze customer churn",
        filters={"domain": ["business"]},
        top_k=5,
    )

    # Dict output for JSON serialization (agent-friendly)
    payload = await ps.search_json("identify project risks", top_k=10)

Usage (sync wrapper, for non-async callers):
    from capillaries.search.api import search

    results = search("summarize a research paper", top_k=5)
    payload = search("summarize a research paper", as_json=True)

Filters (all optional):
    domain          list[str]   e.g. ["business", "strategy"]
    intent          list[str]   e.g. ["build", "improve"]
    task_type       list[str]   e.g. ["generate", "analyze"]
    status          str         default "active"
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from capillaries.search.retriever import Retriever
from capillaries.search.reranker import Reranker, RankedResult
from capillaries.search.union import union_candidates_broad
from capillaries.skills.recall import SkillRecall, SkillMatch

RETRIEVAL_CANDIDATES = 20
SKILL_CANDIDATES = 10

# SINGLE_THRESHOLD is gone. It compared a cross-encoder relevance score for a
# prompt (0-1, one model) against the decision "should a skill be served
# instead" — which is answered by SkillRecall's cosine against
# routing_embedding (a different model, a different scale). Crossing one
# threshold is not evidence about the other, and the constant was silently
# doing two unrelated jobs: "is anything good enough" and "which modality".
#
# Prompts and skills are retrieved into ONE candidate pool and reranked in ONE
# pass by the SAME cross-encoder. Whichever candidate — prompt or skill —
# lands at rank 1 wins; modality is the outcome of that single ranking, never
# a gate or an order-of-attempt in front of it.


@dataclass
class SearchResponse:
    query: str
    recommendation: str             # 'single_prompt' | 'skill'
    results: list[RankedResult]     # top single prompts (always populated)
    total_candidates: int
    filters_applied: dict[str, Any] = field(default_factory=dict)

    # Populated when recommendation == 'skill'
    skill_match: SkillMatch | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "query":            self.query,
            "recommendation":   self.recommendation,
            "total_candidates": self.total_candidates,
            "filters_applied":  self.filters_applied,
            "results":          [r.to_dict() for r in self.results],
        }
        if self.recommendation == "skill" and self.skill_match:
            d["skill"] = self.skill_match.to_dict()
        return d


class PromptSearch:
    """
    Main library endpoint for prompt retrieval.

    Instantiate once per process — the reranker is loaded onto GPU at
    construction time and reused across calls. SkillRecall is lightweight
    (DB queries only) and also reused.
    """

    def __init__(
        self,
        retrieval_candidates: int = RETRIEVAL_CANDIDATES,
        reranker_batch_size: int = 32,
        skill_recall: bool = True,
        rerank_only: bool = False,
    ) -> None:
        self.retriever = Retriever()
        self.reranker = Reranker(batch_size=reranker_batch_size)
        self.recall = SkillRecall() if skill_recall else None
        self._retrieval_candidates = retrieval_candidates
        self._rerank_only = rerank_only

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
        model: str | None = None,
        skill_hints: dict[str, Any] | None = None,
        prefer: str = "auto",
    ) -> SearchResponse:
        """
        Find the most relevant prompt or skill for a query.

        Prompt and skill candidates are retrieved into ONE pool and reranked
        in ONE pass by the same cross-encoder — whichever lands at rank 1
        wins. Modality is never decided by trying one first.

        Args:
            query:       Natural language description of what you need.
            filters:     Optional metadata constraints (see module docstring).
                         Also used as skill taxonomy hints if skill_hints is None.
            top_k:       Number of single-prompt results to return.
            model:       Active LLM model — selects per-model prompt variants in skills.
            skill_hints: Optional domain/intent hints to soft-boost skill
                         matching, kept separate from `filters` so they never
                         become a hard retrieval filter on prompts.
            prefer:      'auto' (default, unbiased comparison), 'single'
                         (skip skill candidates entirely), or 'skill' (force
                         the best-scoring eligible skill if any was retrieved).

        Returns:
            SearchResponse with .recommendation indicating which tier matched.
        """
        filters = filters or {}

        # ── Retrieval: both modalities, same step ────────────────────────
        # Union of dense + lexical, then rerank. Replaces weighted RRF: the
        # union has no ratio to tune and no `k` to fit, and every weighting
        # proposed in the rework failed to survive a clean benchmark.
        #
        # Measured cost on the golden set (n=20): R@10 85.0% vs RRF's 90.0% —
        # one query. Bought with the removal of two fitted constants. See
        # search/union.py for the full comparison.
        if self._rerank_only:
            prompt_candidates = self.retriever.fetch_all(filters=filters)
        else:
            prompt_candidates = await union_candidates_broad(
                query, filters=filters, per_channel=self._retrieval_candidates,
            )

        skill_candidates: list = []
        if self.recall is not None and prefer != "single":
            skill_candidates = self.recall.candidates(
                query, skill_hints if skill_hints is not None else filters,
                per_channel=SKILL_CANDIDATES,
            )

        all_candidates = prompt_candidates + skill_candidates
        ranked = self.reranker.rerank(query, all_candidates, top_k=top_k + len(skill_candidates))

        total = len(all_candidates)

        # Top-k candidates the ranker considered, regardless of which tier is
        # ultimately served — this is the ranking signal harvest.py needs
        # (STACK_READINESS §5.1: "without the candidates that weren't served,
        # the optimizer can't learn ranking").
        ranked_candidates = [
            {"id": r.prompt_id, "score": r.rerank_score} for r in ranked
        ]

        results = [r for r in ranked if r.metadata.get("kind") != "skill"][:top_k]

        # ── Rank decides — no order-of-attempt, no separate re-score ─────
        # A skill with no steps is unservable, so it's skipped as a candidate
        # rather than costing the whole modality the comparison.
        def _eligible(r) -> bool:
            return r.metadata.get("kind") != "skill" or r.metadata.get("steps")

        winner = next((r for r in ranked if _eligible(r)), None)

        if prefer == "skill":
            skill_ranked = [r for r in ranked
                            if r.metadata.get("kind") == "skill" and r.metadata.get("steps")]
            if skill_ranked:
                winner = skill_ranked[0]

        if winner is not None and winner.metadata.get("kind") == "skill":
            match = self._build_skill_match(winner, model=model)
            self._log_skill_run(match)
            self._log_serving(query, "skill", match.skill_id, ranked_candidates)
            return SearchResponse(
                query=query,
                recommendation="skill",
                results=results,
                total_candidates=total,
                filters_applied=filters,
                skill_match=match,
            )

        self._log_serving(query, "single_prompt", results[0].prompt_id if results else None,
                           ranked_candidates)
        return SearchResponse(
            query=query,
            recommendation="single_prompt",
            results=results,
            total_candidates=total,
            filters_applied=filters,
        )

    def _build_skill_match(self, winner, model: str | None) -> SkillMatch:
        """Resolve a winning skill candidate's steps to full prompt content.

        Only called on the candidate the reranker actually picked — the other
        skill candidates in the pool never pay for step resolution.
        """
        meta = winner.metadata
        steps = self.recall._resolve_steps(meta["steps"], model=model)
        return SkillMatch(
            skill_id=meta["skill_id"],
            name=winner.title,
            tag=meta["tag"],
            version=meta["version"],
            routing_description=meta["routing_description"],
            match_score=winner.rerank_score,
            domain=meta.get("domain", []),
            intent=meta.get("intent", []),
            task_type=meta.get("task_type", []),
            steps=steps,
        )

    async def search_json(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
        model: str | None = None,
    ) -> dict:
        """Same as search() but returns a plain dict for JSON serialization."""
        response = await self.search(query, filters=filters, top_k=top_k, model=model)
        return response.to_dict()

    def _log_skill_run(self, match: SkillMatch) -> None:
        """Log a skill recall without blocking the response."""
        try:
            self.recall.log_run(
                skill_id=match.skill_id,
                skill_version=match.version,
                status="success",
                score=match.match_score,
                step_hashes=[
                    {"prompt_id": s["prompt_id"],
                     "content_hash": s["metadata"].get("content_hash")}
                    for s in match.steps
                ],
            )
        except Exception:
            pass

    def _log_serving(
        self, query: str, served_kind: str, served_id: str | None, candidates: list[dict]
    ) -> None:
        """Best-effort serving log — never blocks or breaks retrieval."""
        try:
            from capillaries.optimize.serving import log_serving
            log_serving(query, served_kind, served_id, candidates)
        except Exception:
            pass


# ── Sync convenience wrapper ──────────────────────────────────────────────

_default_instance: PromptSearch | None = None


def _get_default() -> PromptSearch:
    global _default_instance
    if _default_instance is None:
        _default_instance = PromptSearch()
    return _default_instance


def search(
    query: str,
    filters: dict[str, Any] | None = None,
    top_k: int = 10,
    as_json: bool = False,
    model: str | None = None,
) -> SearchResponse | dict:
    """
    Synchronous search wrapper for non-async callers.

    Uses a module-level PromptSearch instance (loaded on first call).
    For production agents in async contexts, prefer PromptSearch directly.
    """
    ps = _get_default()
    if as_json:
        coro = ps.search_json(query, filters, top_k, model=model)
    else:
        coro = ps.search(query, filters, top_k, model=model)
    return asyncio.run(coro)
