"""
PromptSearch — the single library endpoint for agent callers.

Wraps hybrid retrieval (pgvector HNSW + pg_trgm, RRF) and cross-encoder
reranking behind a two-mode interface:

  Recall mode  — query matches an existing validated skill → return its
                 pre-validated steps directly (fast, no reranking)
  Build mode   — no skill match → run full retrieval + rerank pipeline

Callers see the same SearchResponse either way. Check response.source to
know which mode ran: 'recall' or 'retrieval'.

Usage (async):
    from prompt_flow.search.api import PromptSearch

    ps = PromptSearch()

    results = await ps.search("write a go-to-market strategy")
    results = await ps.search(
        "analyze customer churn",
        filters={"domain": ["business"], "primary_stage": "execute"},
        top_k=5,
    )

    # Dict output for JSON serialization (agent-friendly)
    payload = await ps.search_json("identify project risks", top_k=10)

Usage (sync wrapper, for non-async callers):
    from prompt_flow.search.api import search

    results = search("summarize a research paper", top_k=5)
    payload = search("summarize a research paper", as_json=True)

Filters (all optional):
    domain          list[str]   e.g. ["business", "strategy"]
    intent          list[str]   e.g. ["build", "improve"]
    task_type       list[str]   e.g. ["generate", "analyze"]
    primary_stage   str         one of: clarify, plan, execute, verify, reflect
    complexity_min  int         1–5
    complexity_max  int         1–5
    status          str         default "active"
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from prompt_flow.search.retriever import Retriever
from prompt_flow.search.reranker import Reranker, RankedResult
from prompt_flow.skills.recall import SkillRecall, SkillMatch

# How many candidates to pull before reranking.
RETRIEVAL_CANDIDATES = 50


@dataclass
class SearchResponse:
    query: str
    results: list[RankedResult]
    total_candidates: int
    filters_applied: dict[str, Any] = field(default_factory=dict)

    # Recall metadata — set when an existing skill was matched
    source: str = "retrieval"       # 'recall' | 'retrieval'
    skill_id: str | None = None
    skill_slug: str | None = None
    skill_name: str | None = None
    skill_match_score: float | None = None

    def to_dict(self) -> dict:
        d = {
            "query":            self.query,
            "source":           self.source,
            "total_candidates": self.total_candidates,
            "filters_applied":  self.filters_applied,
            "results":          [r.to_dict() for r in self.results],
        }
        if self.source == "recall":
            d["skill"] = {
                "skill_id":    self.skill_id,
                "slug":        self.skill_slug,
                "name":        self.skill_name,
                "match_score": self.skill_match_score,
            }
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
    ) -> None:
        self.retriever = Retriever()
        self.reranker = Reranker(batch_size=reranker_batch_size)
        self.recall = SkillRecall() if skill_recall else None
        self._retrieval_candidates = retrieval_candidates

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> SearchResponse:
        """
        Find the most relevant prompts for a query.

        Tries skill recall first. If a validated skill matches confidently,
        returns its steps directly. Otherwise runs full retrieval + rerank.

        Args:
            query:   Natural language description of what you need.
            filters: Optional metadata constraints (see module docstring).
            top_k:   Number of results to return (used in build mode;
                     recall mode returns all skill steps).

        Returns:
            SearchResponse. Check .source to know which mode ran.
        """
        filters = filters or {}

        # ── Recall mode ───────────────────────────────────────────────────
        if self.recall is not None:
            match = self.recall.search(query, filters)
            if match is not None:
                return self._recall_response(query, match, filters)

        # ── Build mode (fresh retrieval) ──────────────────────────────────
        candidates = await self.retriever.search(
            query,
            filters=filters,
            top_k=self._retrieval_candidates,
        )
        results = self.reranker.rerank(query, candidates, top_k=top_k)

        return SearchResponse(
            query=query,
            results=results,
            total_candidates=len(candidates),
            filters_applied=filters,
            source="retrieval",
        )

    async def search_json(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> dict:
        """Same as search() but returns a plain dict for JSON serialization."""
        response = await self.search(query, filters=filters, top_k=top_k)
        return response.to_dict()

    # ── Internals ─────────────────────────────────────────────────────────

    def _recall_response(
        self,
        query: str,
        match: SkillMatch,
        filters: dict[str, Any],
    ) -> SearchResponse:
        """Convert a SkillMatch into a SearchResponse and log the run."""
        results = [
            RankedResult(
                prompt_id=step["prompt_id"],
                prompt_text=step["prompt_text"],
                rerank_score=match.match_score,   # FTS confidence, not a rerank logit
                rrf_score=0.0,
                dense_rank=step["step_order"],     # repurposed as step position
                sparse_rank=None,
                dense_sim=None,
                sparse_sim=None,
                metadata={
                    **step["metadata"],
                    "stage":      step["stage"],
                    "step_order": step["step_order"],
                    "rationale":  step.get("rationale"),
                    "from_skill": True,
                },
            )
            for step in match.steps
        ]

        # Log the run without blocking the response
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
            pass  # run logging is best-effort

        return SearchResponse(
            query=query,
            results=results,
            total_candidates=len(results),
            filters_applied=filters,
            source="recall",
            skill_id=match.skill_id,
            skill_slug=match.slug,
            skill_name=match.name,
            skill_match_score=match.match_score,
        )


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
) -> SearchResponse | dict:
    """
    Synchronous search wrapper for non-async callers.

    Uses a module-level PromptSearch instance (loaded on first call).
    For production agents in async contexts, prefer PromptSearch directly.
    """
    ps = _get_default()
    coro = ps.search_json(query, filters, top_k) if as_json else ps.search(query, filters, top_k)
    return asyncio.run(coro)
