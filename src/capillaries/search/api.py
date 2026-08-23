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
import os
import re
from dataclasses import dataclass, field
from typing import Any

from capillaries.search.retriever import Retriever
from capillaries.search.reranker import Reranker, RankedResult
from capillaries.search.union import union_candidates_broad, fetch_by_ids
from capillaries.skills.recall import SkillRecall, SkillMatch

RETRIEVAL_CANDIDATES = 20
SKILL_CANDIDATES = 10
EXPANSION_CANDIDATES = 10
RERANKER_BATCH_SIZE = int(os.getenv("CAPILLARIES_RERANKER_BATCH_SIZE", "32"))
IMAGE_GEN_PREFIX = "image gen"
_IMAGE_GENERATION_QUERY = re.compile(
    r"\b(?:generate|render|produce|edit|animate)\s+"
    r"(?:(?:an?|the)\s+)?(?:[a-z-]+\s+){0,3}"
    r"(?:image|images|video|videos|visual|visuals|animation|animations)\b"
    r"|\b(?:image|images|video|videos|visual|visuals|animation|animations)\s+"
    r"(?:generation|generating|rendering|editing|animation)\b",
    re.IGNORECASE,
)

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


def _filter_image_gen_candidates(query: str, candidates: list) -> list:
    """Keep Image Gen workflows out of non-generative image/video requests."""
    if _IMAGE_GENERATION_QUERY.search(query):
        return candidates
    return [
        candidate for candidate in candidates
        if not candidate.title.lower().startswith(IMAGE_GEN_PREFIX)
    ]


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
        reranker_batch_size: int = RERANKER_BATCH_SIZE,
        skill_recall: bool = True,
        rerank_only: bool = False,
    ) -> None:
        self.retriever = Retriever()
        self.reranker = Reranker(batch_size=reranker_batch_size)
        self.recall = SkillRecall() if skill_recall else None
        from capillaries.search.context_filter import ContextFilter
        self._context_filter = ContextFilter()
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
        query_expansion: str | None = None,
        boost_prompt_ids: list[str] | None = None,
        agent_context: Any | None = None,
        context: Any | None = None,
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
            query_expansion: Optional extra text (e.g. recent conversation /
                         session insights from arteries) used for a SECOND
                         retrieval pass, unioned into the candidate pool. Never
                         touches reranking — every candidate, expansion-sourced
                         or not, is still scored against `query` alone. This
                         only widens what the reranker gets to see; it can't
                         make a bad candidate look relevant.
            context:     Optional MemoryFrame. Reorders the reranked pool via
                         ContextFilter before the prompt-vs-skill decision, so
                         both tiers see the same context signals.
            boost_prompt_ids: Optional prompt ids (e.g. arteries'
                         prior_retrievals) injected directly into the candidate
                         pool, bypassing retrieval entirely. Same rule: still
                         reranked against `query`, not given a free pass.

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

            # Context widening — additive only. Both paths can only add
            # candidates the plain query missed; they never remove or
            # reweight anything, and reranking below still scores everyone
            # against `query` alone.
            if query_expansion:
                seen = {c.prompt_id for c in prompt_candidates}
                expanded = await union_candidates_broad(
                    f"{query} {query_expansion}".strip(),
                    filters=filters, per_channel=EXPANSION_CANDIDATES,
                )
                prompt_candidates += [c for c in expanded if c.prompt_id not in seen]

            if boost_prompt_ids:
                seen = {c.prompt_id for c in prompt_candidates}
                boosted = fetch_by_ids(boost_prompt_ids)
                prompt_candidates += [c for c in boosted if c.prompt_id not in seen]

        prompt_candidates = _filter_image_gen_candidates(query, prompt_candidates)

        skill_candidates: list = []
        if self.recall is not None and prefer != "single":
            skill_candidates = self.recall.candidates(
                query, skill_hints if skill_hints is not None else filters,
                per_channel=SKILL_CANDIDATES,
            )

        all_candidates = prompt_candidates + skill_candidates
        ranked = self.reranker.rerank(query, all_candidates, top_k=top_k + len(skill_candidates))

        # Context applies to the POOL, not to the prompt branch of it. This
        # used to run in find.py inside _build_single_result, and
        # _build_skill_result returned before ever reaching it — so a winning
        # skill was decided with the MemoryFrame ignored. Both tiers already
        # share one reranked list, so reordering it here covers both.
        #
        # Reorders only. rerank_score is left untouched because the confidence
        # floor is a statement about semantic match, not about context.
        if context is not None:
            ranked = [f.result for f in self._context_filter.apply(ranked, context)]

        total = len(all_candidates)

        # Top-k candidates the ranker considered, regardless of which tier is
        # ultimately served — the ranking signal any optimizer needs
        # (STACK_READINESS §5.1: "without the candidates that weren't served,
        # the optimizer can't learn ranking"). harvest.py was the consumer and
        # is gone; the record still has to be written while it is observable.
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

        # Coverage gate: a skill only wins on its own merit if its summary
        # scored well AND multiple of its actual steps independently rank
        # well against the query — not summary relevance alone. This is
        # "does the query need X+Y+Z, or just X" (skills/coverage.py),
        # distinct from "is this skill's description relevant" (the rerank
        # comparison above). Skipped when `prefer='skill'` forces the skill
        # regardless — that's an explicit override, not a rank-based win.
        if winner is not None and winner.metadata.get("kind") == "skill" and prefer != "skill":
            if not self._coverage_confirms(winner, ranked):
                winner = next((r for r in ranked if r.metadata.get("kind") != "skill"), None)

        if prefer == "skill":
            skill_ranked = [r for r in ranked
                            if r.metadata.get("kind") == "skill" and r.metadata.get("steps")]
            if skill_ranked:
                winner = skill_ranked[0]

        if winner is not None and winner.metadata.get("kind") == "skill":
            match = self._build_skill_match(winner, model=model)
            self._log_skill_run(match)
            self._log_serving(query, "skill", match.skill_id, ranked_candidates,
                              agent_context)
            return SearchResponse(
                query=query,
                recommendation="skill",
                results=results,
                total_candidates=total,
                filters_applied=filters,
                skill_match=match,
            )

        self._log_serving(query, "single_prompt", results[0].prompt_id if results else None,
                           ranked_candidates, agent_context)
        return SearchResponse(
            query=query,
            recommendation="single_prompt",
            results=results,
            total_candidates=total,
            filters_applied=filters,
        )

    def _coverage_confirms(self, winner, ranked: list) -> bool:
        """Does evidence from the skill's own steps back up this win?

        `ranked` still contains skill candidates mixed in with prompts (the
        unified pool) — coverage only reasons about prompts, so it gets the
        prompt-only slice. "top_is_step" here means the single most relevant
        *prompt* to this query is one of this skill's own steps, which is
        the adapted meaning of coverage.py's original "top-ranked result"
        check now that skills and prompts share one ranked list.
        """
        from capillaries.skills.coverage import score_skills

        prompt_ranked = [r for r in ranked if r.metadata.get("kind") != "skill"]
        if not prompt_ranked:
            return False
        coverage_by_skill = {c.skill_id: c for c in score_skills(prompt_ranked)}
        cov = coverage_by_skill.get(winner.metadata["skill_id"])
        return cov is not None and cov.top_is_step

    def _build_skill_match(self, winner, model: str | None) -> SkillMatch:
        """Resolve a winning skill candidate's steps to full prompt content.

        Only called on the candidate the reranker actually picked — the other
        skill candidates in the pool never pay for step resolution.
        """
        meta = winner.metadata
        steps = self.recall._resolve_steps(
            meta["steps"], model=model, skill_id=meta["skill_id"])
        return SkillMatch(
            skill_id=meta["skill_id"],
            name=winner.title,
            tag=meta["tag"],
            version=meta["version"],
            summary=meta["summary"],
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
        self, query: str, served_kind: str, served_id: str | None, candidates: list[dict],
        agent_context: Any | None = None,
    ) -> None:
        """Best-effort serving log — never blocks or breaks retrieval."""
        try:
            from capillaries.optimize.serving import log_serving
            log_serving(
                query, served_kind, served_id, candidates,
                episode_id=getattr(agent_context, "episode_id", None),
                turn_id=getattr(agent_context, "turn_id", None),
            )
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
