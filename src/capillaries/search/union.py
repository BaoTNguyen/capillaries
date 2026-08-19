"""
Union-then-rerank: both channels' candidates, deduped, reordered by the
cross-encoder.

This replaces weighted RRF as the way the two channels are combined, and the
reason is measured rather than argued. Weighted fusion requires choosing a
ratio, and every ratio tried was either indefensible or unmeasurable: on the
clean benchmark 50/50 and 0.3/0.7 differ by 0.5 points, RRF already reaches
within 0.4 points of its own theoretical ceiling, and 0.85/0.15 was worse than
both. There is nothing to tune there.

Union has no ratio. It takes everything either channel found and lets the
reranker order it:

  golden (n=20)   vector alone 55.0% R@10 -> union+rerank 75.0%  (oracle 75.0%)
  notes  (n=261)  vector alone 24.9% R@10 -> union+rerank 27.2%  (oracle 28.4%)

Two honest limits on those numbers:

  * R@10 reaching the oracle is close to tautological — a union of two top-10
    lists is 10-20 candidates, so returning 10 recovers most of it whether or
    not the reranker is any good.
  * R@1 did NOT improve (golden 30.0% -> 30.0%, notes 9.2% -> 8.4%). The extra
    answers arrive at ranks 5-10. Since callers serve position 1, the reranker
    is the component that has to improve before this reaches a user.

So this is a recall change, not yet a precision one.
"""

from __future__ import annotations

from typing import Any

from capillaries.search.channels import keyword_search, vector_search
from capillaries.search.retriever import SearchResult

CHANNEL_TOP_K = 10       # per channel, before the union


async def union_candidates_broad(
    query: str,
    filters: dict[str, Any] | None = None,
    per_channel: int = 20,
) -> list[SearchResult]:
    """The serving path: union of dense and *broad* lexical, deduped.

    Uses the retriever's OR-based lexical search rather than
    channels.keyword_search. That is a deliberate reversal of an earlier
    judgement. Measured on the golden set, reranked identically:

        RRF -> 20 + rerank              R@10 90.0%   MRR 0.510
        union + OLD broad lexical       R@10 85.0%   MRR 0.447
        union + key-term keyword        R@10 70.0%   MRR 0.396

    The key-term extraction in channels.py has better precision and materially
    worse recall, and recall is what a first stage owes the reranker — the
    reranker can discard a bad candidate, but it cannot invent a missing one.
    Precision is the reranker's job, not the retriever's.

    The remaining 5-point gap to RRF is one query out of twenty. Union is used
    anyway: it has no ratio to tune, no `k` to fit, and degrades cleanly when a
    channel returns nothing — properties worth more than a single query on a
    benchmark this small.

    Dense retrieval reads `prompt_chunks` and retains each parent's best
    matching passage for the reranker. Lexical retrieval remains document-level
    because its terms can legitimately occur in different prompt sections.
    """
    import asyncio

    from capillaries.search.retriever import Retriever, _build_filter_clause

    retriever = Retriever()
    clause, params = _build_filter_clause(filters or {})

    loop = asyncio.get_event_loop()
    conn = await loop.run_in_executor(None, retriever._connect)
    try:
        cur = conn.cursor()
        lexical = retriever._sparse_search(cur, query, clause, params, 50)
    finally:
        conn.close()

    by_id: dict[str, SearchResult] = {}

    # Dense side reads prompt_chunks (best chunk wins, rolled up to parent) so
    # long prompts are matched section-by-section instead of as one averaged
    # vector. Lexical stays at document level — keywords don't dilute over
    # length, and chunk-level AND discards 35% of legitimate matches.
    for rank, h in enumerate(vector_search(query, top_k=per_channel,
                                           filters=filters), 1):
        by_id[h.prompt_id] = SearchResult(
            prompt_id=h.prompt_id, title=h.title, prompt_text="",
            rrf_score=0.0, dense_rank=rank, sparse_rank=None,
            dense_sim=h.score, sparse_sim=None,
            matched_chunk_id=h.chunk_id,
        )
    _fill_text(by_id)

    for rank, row in enumerate(lexical, 1):
        pid = row["prompt_id"]
        if pid in by_id:
            by_id[pid].sparse_rank = rank
            by_id[pid].sparse_sim = row.get("sparse_sim")
        elif len(by_id) < per_channel * 2:
            by_id[pid] = _from_row(row, sparse_rank=rank)

    return list(by_id.values())


def fetch_by_ids(prompt_ids: list[str]) -> list[SearchResult]:
    """Fetch specific prompts by id, bypassing dense/lexical retrieval entirely.

    For context-driven candidate injection (e.g. arteries' prior_retrievals):
    a prompt context already knows was relevant gets a chance to compete in
    the rerank even if this turn's raw query text wouldn't have retrieved it.
    Still reranked against the real query like everything else — this only
    widens the candidate pool, it doesn't grant a free pass.
    """
    if not prompt_ids:
        return []
    import psycopg2

    from capillaries.config import DB_CONFIG

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT prompt_id::text, title, prompt_text, summary, intent, task_type, "
                "       domain, status, notes "
                "FROM prompts WHERE prompt_id::text = ANY(%s) AND status = 'active'",
                (prompt_ids,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        SearchResult(
            prompt_id=row[0], title=row[1], prompt_text=row[2],
            rrf_score=0.0, dense_rank=None, sparse_rank=None,
            dense_sim=None, sparse_sim=None,
            metadata={
                "summary": row[3] or "",
                "intent": row[4] or [], "task_type": row[5] or [],
                "domain": row[6] or [], "status": row[7], "notes": row[8],
                "boosted": True,
            },
        )
        for row in rows
    ]


def _from_row(row: dict, dense_rank=None, sparse_rank=None) -> SearchResult:
    return SearchResult(
        prompt_id=row["prompt_id"], title=row["title"],
        prompt_text=row["prompt_text"], rrf_score=0.0,
        dense_rank=dense_rank, sparse_rank=sparse_rank,
        dense_sim=row.get("dense_sim"), sparse_sim=row.get("sparse_sim"),
        metadata={
            "summary": row.get("summary") or "",
            "intent": row.get("intent") or [],
            "task_type": row.get("task_type") or [],
            "domain": row.get("domain") or [],
            "status": row.get("status"),
            "notes": row.get("notes"),
        },
    )


def union_candidates(
    query: str,
    filters: dict[str, Any] | None = None,
    channel_top_k: int = CHANNEL_TOP_K,
) -> list[SearchResult]:
    """Candidates from both channels, deduped, ready for the reranker.

    Order here is arbitrary and deliberately so — the reranker assigns the real
    order. `dense_rank` / `sparse_rank` are populated only so callers and the
    serving log can see which channel contributed a result, which is the signal
    needed to decide later whether keeping both channels is still worth it.
    """
    vec = vector_search(query, top_k=channel_top_k, filters=filters)
    lex = keyword_search(query, top_k=channel_top_k, filters=filters)

    by_id: dict[str, SearchResult] = {}
    for rank, h in enumerate(vec, 1):
        by_id[h.prompt_id] = SearchResult(
            prompt_id=h.prompt_id, title=h.title, prompt_text="",
            rrf_score=0.0, dense_rank=rank, sparse_rank=None,
            dense_sim=h.score, sparse_sim=None,
            matched_chunk_id=h.chunk_id,
        )
    for rank, h in enumerate(lex, 1):
        existing = by_id.get(h.prompt_id)
        if existing is not None:
            existing.sparse_rank = rank
            existing.sparse_sim = h.score
        else:
            by_id[h.prompt_id] = SearchResult(
                prompt_id=h.prompt_id, title=h.title, prompt_text="",
                rrf_score=0.0, dense_rank=None, sparse_rank=rank,
                dense_sim=None, sparse_sim=h.score,
            )

    _fill_text(by_id)
    return list(by_id.values())


def _fill_text(by_id: dict[str, SearchResult]) -> None:
    """Load prompt_text for the union in one query.

    Both channels return identifiers rather than bodies — the reranker needs
    the text and nothing before it does, so it is fetched once here instead of
    being carried through retrieval.
    """
    if not by_id:
        return
    import psycopg2

    from capillaries.config import DB_CONFIG

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT prompt_id::text, title, prompt_text, summary, intent, task_type, "
                "       domain, status, notes "
                "FROM prompts WHERE prompt_id::text = ANY(%s)",
                (list(by_id),),
            )
            for row in cur.fetchall():
                r = by_id[row[0]]
                r.title = row[1]
                r.prompt_text = row[2]
                r.metadata = {
                    "summary": row[3] or "",
                    "intent": row[4] or [], "task_type": row[5] or [],
                    "domain": row[6] or [],
                    "status": row[7], "notes": row[8],
                }
            chunk_ids = [r.matched_chunk_id for r in by_id.values()
                         if r.matched_chunk_id]
            if chunk_ids:
                cur.execute(
                    "SELECT chunk_id::text, chunk_text FROM prompt_chunks "
                    "WHERE chunk_id::text = ANY(%s)",
                    (chunk_ids,),
                )
                chunks = dict(cur.fetchall())
                for result in by_id.values():
                    if result.matched_chunk_id:
                        result.matched_chunk_text = chunks.get(result.matched_chunk_id)
    finally:
        conn.close()
