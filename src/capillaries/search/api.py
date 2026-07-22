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
    complexity_min  int         1–5
    complexity_max  int         1–5
    status          str         default "active"
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from capillaries.search.retriever import Retriever
from capillaries.search.reranker import Reranker, RankedResult
from capillaries.skills.recall import SkillRecall, SkillMatch

RETRIEVAL_CANDIDATES = 20

SINGLE_THRESHOLD = 0.3


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
    ) -> SearchResponse:
        """
        Find the most relevant prompts for a query.

        Decision order:
          1. If the top single prompt scores >= SINGLE_THRESHOLD → return it
          2. Else check for a matching validated skill → return skill

        Args:
            query:   Natural language description of what you need.
            filters: Optional metadata constraints (see module docstring).
            top_k:   Number of single-prompt results to return.
            model:   Active LLM model — selects per-model prompt variants in skills.

        Returns:
            SearchResponse with .recommendation indicating which tier matched.
        """
        filters = filters or {}

        # ── Retrieval ─────────────────────────────────────────────────────
        if self._rerank_only:
            candidates = self.retriever.fetch_all(filters=filters)
        else:
            candidates = await self.retriever.search(
                query,
                filters=filters,
                top_k=self._retrieval_candidates,
            )
        results = self.reranker.rerank(query, candidates, top_k=top_k)

        total = len(candidates)
        best_score = results[0].rerank_score if results else float("-inf")

        # Top-k candidates the ranker considered, regardless of which tier is
        # ultimately served — this is the ranking signal harvest.py needs
        # (STACK_READINESS §5.1: "without the candidates that weren't served,
        # the optimizer can't learn ranking").
        ranked_candidates = [
            {"id": r.prompt_id, "score": r.rerank_score} for r in results
        ]

        # ── Tier 1: single prompt good enough ─────────────────────────────
        if best_score >= SINGLE_THRESHOLD:
            self._log_serving(query, "single_prompt", results[0].prompt_id if results else None,
                               ranked_candidates)
            return SearchResponse(
                query=query,
                recommendation="single_prompt",
                results=results,
                total_candidates=total,
                filters_applied=filters,
            )

        # ── Tier 2: check for a matching skill ───────────────────────────
        if self.recall is not None:
            match = self.recall.search(query, filters, model=model)
            if match is not None:
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
