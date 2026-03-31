"""
Hybrid retriever: pgvector dense search + pg_trgm sparse search, fused with RRF.

Usage:
    from prompt_flow.search.retriever import Retriever

    retriever = Retriever()
    results = await retriever.search("write a product requirements doc", top_k=10)

    # With metadata filters
    results = await retriever.search(
        "analyze customer churn",
        filters={"domain": ["business"], "primary_stage": "analyze"},
        top_k=10,
    )
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg2
import psycopg2.extras

from prompt_flow.config import DB_CONFIG

# --- Constants -----------------------------------------------------------

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
QUERY_PREFIX = "search_query: "
MAX_CHARS = 4_000

# Number of candidates to pull from each retrieval path before fusion
DENSE_CANDIDATES = 50
SPARSE_CANDIDATES = 50

# RRF rank constant — k=60 is the standard default
RRF_K = 60


# --- Data contracts ------------------------------------------------------

@dataclass
class SearchResult:
    prompt_id: str
    prompt_text: str
    rrf_score: float
    dense_rank: int | None        # rank in dense results (1-based), None if not retrieved
    sparse_rank: int | None       # rank in sparse results (1-based), None if not retrieved
    dense_sim: float | None       # cosine similarity (0–1)
    sparse_sim: float | None      # pg_trgm similarity (0–1)
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Embedding -----------------------------------------------------------

async def embed_query(text: str) -> list[float]:
    """Embed a search query using the nomic asymmetric query prefix."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": QUERY_PREFIX + text[:MAX_CHARS]},
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama embed error {resp.status_code}: {resp.text[:200]}")
        return resp.json()["embedding"]


# --- SQL helpers ---------------------------------------------------------

def _build_filter_clause(filters: dict[str, Any]) -> tuple[str, list]:
    """
    Build a WHERE clause fragment and parameter list from a filters dict.

    Supported filter keys:
        domain         list[str]  — any-of match on domain array column
        intent         list[str]  — any-of match
        task_type      list[str]  — any-of match
        primary_stage  str        — exact match
        complexity_min int        — complexity_level >= value
        complexity_max int        — complexity_level <= value
        status         str        — default 'active'
    """
    clauses: list[str] = ["status = %s"]
    params: list = [filters.get("status", "active")]

    for col in ("domain", "intent", "task_type"):
        vals = filters.get(col)
        if vals:
            clauses.append(f"{col} && %s::varchar[]")
            params.append(vals)

    if filters.get("primary_stage"):
        clauses.append("primary_stage = %s")
        params.append(filters["primary_stage"])

    if filters.get("complexity_min") is not None:
        clauses.append("complexity_level >= %s")
        params.append(filters["complexity_min"])

    if filters.get("complexity_max") is not None:
        clauses.append("complexity_level <= %s")
        params.append(filters["complexity_max"])

    return " AND ".join(clauses), params


# --- Retriever -----------------------------------------------------------

class Retriever:
    """
    Hybrid prompt retriever.

    Combines:
    - Dense retrieval  : pgvector HNSW cosine similarity on stored embeddings
    - Sparse retrieval : pg_trgm trigram similarity on prompt_text
    - Fusion           : Reciprocal Rank Fusion (RRF, k=60)
    """

    def __init__(self, db_config: dict | None = None) -> None:
        self._db_config = db_config or DB_CONFIG

    def _connect(self):
        return psycopg2.connect(**self._db_config)

    def _dense_search(
        self,
        cur,
        query_vec: list[float],
        filter_clause: str,
        filter_params: list,
        n: int,
    ) -> list[dict]:
        """Return top-n results by cosine similarity using pgvector HNSW."""
        vec_str = "[" + ",".join(map(str, query_vec)) + "]"
        sql = f"""
            SELECT
                prompt_id,
                prompt_text,
                intent, task_type, domain, primary_stage,
                complexity_level, status, models_tested, notes,
                1 - (embedding <=> %s::vector) AS dense_sim
            FROM prompts
            WHERE embedding IS NOT NULL
              AND {filter_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        cur.execute(sql, [vec_str] + filter_params + [vec_str] + [n])
        return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]

    def _sparse_search(
        self,
        cur,
        query: str,
        filter_clause: str,
        filter_params: list,
        n: int,
    ) -> list[dict]:
        """Return top-n results by pg_trgm trigram similarity."""
        sql = f"""
            SELECT
                prompt_id,
                prompt_text,
                intent, task_type, domain, primary_stage,
                complexity_level, status, models_tested, notes,
                similarity(prompt_text, %s) AS sparse_sim
            FROM prompts
            WHERE {filter_clause}
            ORDER BY sparse_sim DESC
            LIMIT %s
        """
        cur.execute(sql, [query] + filter_params + [n])
        return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]

    @staticmethod
    def _rrf_merge(
        dense_rows: list[dict],
        sparse_rows: list[dict],
        k: int = RRF_K,
    ) -> list[SearchResult]:
        """
        Merge two ranked lists using Reciprocal Rank Fusion.

        RRF score = 1/(k + rank_dense) + 1/(k + rank_sparse)
        Documents appearing in only one list still contribute their term.
        """
        # Build rank maps (1-based)
        dense_rank = {r["prompt_id"]: i + 1 for i, r in enumerate(dense_rows)}
        sparse_rank = {r["prompt_id"]: i + 1 for i, r in enumerate(sparse_rows)}

        # Index rows by prompt_id for metadata lookup
        all_rows: dict[str, dict] = {}
        for r in dense_rows:
            all_rows[r["prompt_id"]] = r
        for r in sparse_rows:
            all_rows.setdefault(r["prompt_id"], r)

        # Score every unique document
        all_ids = set(dense_rank) | set(sparse_rank)
        scored: list[SearchResult] = []
        for pid in all_ids:
            dr = dense_rank.get(pid)
            sr = sparse_rank.get(pid)
            rrf = (1 / (k + dr) if dr else 0.0) + (1 / (k + sr) if sr else 0.0)
            row = all_rows[pid]
            scored.append(
                SearchResult(
                    prompt_id=pid,
                    prompt_text=row["prompt_text"],
                    rrf_score=rrf,
                    dense_rank=dr,
                    sparse_rank=sr,
                    dense_sim=row.get("dense_sim") if dr else None,
                    sparse_sim=row.get("sparse_sim") if sr else None,
                    metadata={
                        "intent": row.get("intent") or [],
                        "task_type": row.get("task_type") or [],
                        "domain": row.get("domain") or [],
                        "primary_stage": row.get("primary_stage"),
                        "complexity_level": row.get("complexity_level"),
                        "status": row.get("status"),
                        "models_tested": row.get("models_tested") or [],
                        "notes": row.get("notes"),
                    },
                )
            )

        scored.sort(key=lambda r: r.rrf_score, reverse=True)
        return scored

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
        dense_candidates: int = DENSE_CANDIDATES,
        sparse_candidates: int = SPARSE_CANDIDATES,
    ) -> list[SearchResult]:
        """
        Hybrid search returning top_k results ranked by RRF.

        Args:
            query:             Natural language search query.
            filters:           Optional metadata filters (see _build_filter_clause).
            top_k:             Number of results to return after fusion.
            dense_candidates:  How many candidates to pull from vector search.
            sparse_candidates: How many candidates to pull from trigram search.

        Returns:
            List of SearchResult sorted by rrf_score descending.
        """
        filters = filters or {}
        filter_clause, filter_params = _build_filter_clause(filters)

        # Embed query and run DB searches concurrently
        query_vec, conn = await asyncio.gather(
            embed_query(query),
            asyncio.get_event_loop().run_in_executor(None, self._connect),
        )

        try:
            cur = conn.cursor()
            psycopg2.extras.register_default_jsonb(conn)

            dense_rows = await asyncio.get_event_loop().run_in_executor(
                None,
                self._dense_search,
                cur, query_vec, filter_clause, filter_params, dense_candidates,
            )
            sparse_rows = await asyncio.get_event_loop().run_in_executor(
                None,
                self._sparse_search,
                cur, query, filter_clause, filter_params, sparse_candidates,
            )
        finally:
            conn.close()

        results = self._rrf_merge(dense_rows, sparse_rows)
        return results[:top_k]
