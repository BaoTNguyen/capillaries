"""
PromptSearch — the single library endpoint for agent callers.

Wraps the hybrid retriever (pgvector HNSW + pg_trgm, RRF) and cross-encoder
reranker into one interface. Load once, call many times.

Usage (async):
    from prompt_flow.search.api import PromptSearch

    ps = PromptSearch()          # loads reranker model onto GPU once

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

# How many candidates to pull before reranking.
# Higher = better recall, slightly more rerank latency.
RETRIEVAL_CANDIDATES = 50


@dataclass
class SearchResponse:
    query: str
    results: list[RankedResult]
    total_candidates: int          # how many were retrieved before reranking
    filters_applied: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "total_candidates": self.total_candidates,
            "filters_applied": self.filters_applied,
            "results": [r.to_dict() for r in self.results],
        }


class PromptSearch:
    """
    Main library endpoint for prompt retrieval.

    Instantiate once per process — the reranker model is loaded onto GPU
    at construction time and reused across all subsequent calls.
    """

    def __init__(
        self,
        retrieval_candidates: int = RETRIEVAL_CANDIDATES,
        reranker_batch_size: int = 32,
    ) -> None:
        self.retriever = Retriever()
        self.reranker = Reranker(batch_size=reranker_batch_size)
        self._retrieval_candidates = retrieval_candidates

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> SearchResponse:
        """
        Search for the most relevant prompts for a given query.

        Args:
            query:   Natural language description of what you need.
            filters: Optional metadata constraints (see module docstring).
            top_k:   Number of results to return.

        Returns:
            SearchResponse with ranked results and score breakdowns.
        """
        filters = filters or {}

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
        )

    async def search_json(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> dict:
        """Same as search() but returns a plain dict ready for JSON serialization."""
        response = await self.search(query, filters=filters, top_k=top_k)
        return response.to_dict()


# --- Sync convenience wrapper -------------------------------------------
# Useful for callers that aren't in an async context.

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
    For production agents running in async contexts, prefer PromptSearch directly.

    Args:
        query:    Natural language search query.
        filters:  Optional metadata filters.
        top_k:    Number of results to return.
        as_json:  If True, returns a plain dict instead of SearchResponse.
    """
    ps = _get_default()
    coro = ps.search_json(query, filters, top_k) if as_json else ps.search(query, filters, top_k)
    return asyncio.run(coro)
