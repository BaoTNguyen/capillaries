"""
Hybrid retriever: pgvector dense search + BM25 sparse search, fused with RRF.

Usage:
    from capillaries.search.retriever import Retriever

    retriever = Retriever()
    results = await retriever.search("write a product requirements doc", top_k=10)

    # With metadata filters
    results = await retriever.search(
        "analyze customer churn",
        filters={"domain": ["business"]},
        top_k=10,
    )
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG, EMBED_URL, EMBED_MODEL, QUERY_PREFIX

# --- Constants -----------------------------------------------------------

MAX_CHARS = 4_000

# Number of candidates to pull from each retrieval path before fusion
DENSE_CANDIDATES = 50
SPARSE_CANDIDATES = 50

RRF_K = 50

# RRF weights. These are NOT on the serving path — `search/api.py` retrieves
# through `union.union_candidates_broad`, which unions both channels and lets
# the reranker order them, with no weighting anywhere. `Retriever.search()` and
# `_rrf_merge` below survive only as the comparison arm for benchmarks and
# tests; nothing in production reads these two numbers.
#
# So don't promote them to config: a tunable that changes no behaviour is worse
# than a constant. Delete both, along with search()/_rrf_merge, once the
# benchmarks in bench_channels.py no longer need something to compare against.
DENSE_WEIGHT = 0.5
SPARSE_WEIGHT = 0.5


# --- Data contracts ------------------------------------------------------

@dataclass
class SearchResult:
    prompt_id: str            # UUID (primary key)
    title: str                # human-readable name (Obsidian filename)
    prompt_text: str
    rrf_score: float
    dense_rank: int | None        # rank in dense results (1-based), None if not retrieved
    sparse_rank: int | None       # rank in sparse results (1-based), None if not retrieved
    dense_sim: float | None       # cosine similarity (0–1)
    sparse_sim: float | None      # pg_trgm similarity (0–1)
    matched_chunk_id: str | None = None
    matched_chunk_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Query expansion -----------------------------------------------------

ACRONYMS: dict[str, str] = {
    "GTM": "go-to-market",
    "B2B": "business-to-business",
    "B2C": "business-to-consumer",
    "D2C": "direct-to-consumer",
    "DTC": "direct-to-consumer",
    "SaaS": "software as a service",
    "PaaS": "platform as a service",
    "IaaS": "infrastructure as a service",
    "PLG": "product-led growth",
    "SLG": "sales-led growth",
    "CLG": "community-led growth",
    "ICP": "ideal customer profile",
    "TAM": "total addressable market",
    "SAM": "serviceable addressable market",
    "SOM": "serviceable obtainable market",
    "ARR": "annual recurring revenue",
    "MRR": "monthly recurring revenue",
    "NRR": "net revenue retention",
    "GRR": "gross revenue retention",
    "CAC": "customer acquisition cost",
    "LTV": "lifetime value",
    "CLTV": "customer lifetime value",
    "ACV": "annual contract value",
    "TCV": "total contract value",
    "AOV": "average order value",
    "ARPU": "average revenue per user",
    "ARPA": "average revenue per account",
    "CPA": "cost per acquisition",
    "CPL": "cost per lead",
    "CPC": "cost per click",
    "CPM": "cost per mille",
    "CTR": "click-through rate",
    "CVR": "conversion rate",
    "MQL": "marketing qualified lead",
    "SQL": "sales qualified lead",
    "PQL": "product qualified lead",
    "OKR": "objectives and key results",
    "KPI": "key performance indicator",
    "NPS": "net promoter score",
    "CSAT": "customer satisfaction",
    "CES": "customer effort score",
    "PMF": "product-market fit",
    "MVP": "minimum viable product",
    "POC": "proof of concept",
    "PRD": "product requirements document",
    "BRD": "business requirements document",
    "SOW": "statement of work",
    "SLA": "service level agreement",
    "ROI": "return on investment",
    "ROAS": "return on ad spend",
    "P&L": "profit and loss",
    "EBITDA": "earnings before interest taxes depreciation and amortization",
    "COGS": "cost of goods sold",
    "OPEX": "operating expenditure",
    "CAPEX": "capital expenditure",
    "QBR": "quarterly business review",
    "ABM": "account-based marketing",
    "SEO": "search engine optimization",
    "SEM": "search engine marketing",
    "CRM": "customer relationship management",
    "ERP": "enterprise resource planning",
    "ETL": "extract transform load",
    "API": "application programming interface",
    "SDK": "software development kit",
    "CI/CD": "continuous integration and continuous delivery",
    "ML": "machine learning",
    "LLM": "large language model",
    "RAG": "retrieval augmented generation",
    "GenAI": "generative artificial intelligence",
    "AI/ML": "artificial intelligence and machine learning",
    "NLP": "natural language processing",
    "RPA": "robotic process automation",
    "IOT": "internet of things",
    "IoT": "internet of things",
    "HIPAA": "health insurance portability and accountability act",
    "SOC": "system and organization controls",
    "GDPR": "general data protection regulation",
    "SSO": "single sign-on",
    "RBAC": "role-based access control",
    "MFA": "multi-factor authentication",
    "VPC": "virtual private cloud",
    "CDN": "content delivery network",
    "DNS": "domain name system",
}

_ACRONYM_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in sorted(ACRONYMS, key=len, reverse=True)) + r')\b'
)


def expand_acronyms(text: str) -> str:
    """Expand known acronyms in-place: 'GTM strategy' → 'GTM (go-to-market) strategy'."""
    def _replace(m: re.Match) -> str:
        acr = m.group(0)
        return f"{acr} ({ACRONYMS[acr]})"
    return _ACRONYM_PATTERN.sub(_replace, text)


# --- Embedding -----------------------------------------------------------

def assert_index_matches_model(cur, table: str = "prompts") -> None:
    """Refuse to search an index built by a different embedding model.

    Vectors from two models share a column but not a space; querying across
    them returns confident nonsense and raises nothing. That is exactly how
    every embedding in this database came to be garbage without anyone
    noticing (see docs/rework_actions.md). Cheap check, loud failure.
    """
    cur.execute(
        f"SELECT DISTINCT embedding_version FROM {table} WHERE embedding IS NOT NULL"
    )
    versions = {r[0] for r in cur.fetchall()}
    if not versions:
        return  # empty index; nothing to disagree with
    if versions != {EMBED_MODEL}:
        raise RuntimeError(
            f"{table} was embedded by {sorted(versions)} but the configured model "
            f"is {EMBED_MODEL}. Re-embed before searching: "
            f"python3 -m capillaries.db.migrate_embed_dim --apply && "
            f"python3 -m capillaries.db.embed --reembed"
        )


async def embed_query(text: str) -> list[float]:
    """Embed a search query with the retrieval instruction prefix."""
    expanded = expand_acronyms(text)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            EMBED_URL,
            json={"input": QUERY_PREFIX + expanded[:MAX_CHARS], "model": EMBED_MODEL},
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embed error {resp.status_code}: {resp.text[:200]}")
        return resp.json()["data"][0]["embedding"]


# --- SQL helpers ---------------------------------------------------------

def _build_filter_clause(filters: dict[str, Any]) -> tuple[str, list]:
    """
    Build a WHERE clause fragment and parameter list from a filters dict.

    Supported filter keys:
        domain         list[str]  — any-of match on domain array column
        intent         list[str]  — any-of match
        task_type      list[str]  — any-of match
        status         str        — default 'active'
    """
    clauses: list[str] = ["status = %s"]
    params: list = [filters.get("status", "active")]

    for col in ("domain", "intent", "task_type"):
        vals = filters.get(col)
        if vals:
            clauses.append(f"{col} && %s::varchar[]")
            params.append(vals)

    if filters.get("source"):
        clauses.append("source = %s")
        params.append(filters["source"])

    if filters.get("modality"):
        clauses.append("modality = %s")
        params.append(filters["modality"])

    return " AND ".join(clauses), params


# --- Retriever -----------------------------------------------------------

class Retriever:
    """
    Hybrid prompt retriever.

    Combines:
    - Dense retrieval  : pgvector HNSW cosine similarity on stored embeddings
    - Sparse retrieval : BM25-style full-text search on search_tsv (title/summary/body weighted)
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
                prompt_id::text, title,
                prompt_text, summary,
                intent, task_type, domain,
                status, notes,
                1 - (embedding <=> %s::vector) AS dense_sim
            FROM prompts
            WHERE embedding IS NOT NULL
              AND {filter_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        cur.execute(sql, [vec_str] + filter_params + [vec_str] + [n])
        return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]

    @staticmethod
    def _to_or_tsquery(cur, query: str) -> str:
        """Convert a query string to an OR-joined tsquery via PostgreSQL.

        Every token is quoted. Unquoted, a token carrying punctuation —
        `textkit/__init__.py`, `slugify('')`, a bare `&` — is read as tsquery
        *syntax* rather than a lexeme, and the whole search dies with "syntax
        error in tsquery". Real agent prompts are full of such tokens, so this
        is the common case, not an edge case. Pure-punctuation tokens are
        dropped outright: quoted, they would produce empty lexemes.
        """
        cur.execute(
            "SELECT array_to_string("
            "  array_agg(DISTINCT quote_literal(token)), ' | '"
            ") FROM ts_parse('default', %s) "
            "WHERE tokid != 12 "              # exclude whitespace tokens
            "  AND token ~ '[[:alnum:]]'",    # ...and anything with no lexeme in it
            [query],
        )
        # No lexemes at all (pure punctuation, e.g. "!!! ???"). "''" was returned
        # here before and is itself invalid tsquery; empty means "skip sparse".
        return cur.fetchone()[0] or ""

    def _sparse_search(
        self,
        cur,
        query: str,
        filter_clause: str,
        filter_params: list,
        n: int,
    ) -> list[dict]:
        """Return top-n results by BM25-style full-text search on search_tsv."""
        or_terms = self._to_or_tsquery(cur, query)
        if not or_terms:
            return []  # nothing searchable; dense retrieval still stands on its own
        sql = f"""
            SELECT
                prompt_id::text, title,
                prompt_text, summary,
                intent, task_type, domain,
                status, notes,
                ts_rank_cd(search_tsv, to_tsquery('english', %s), 1|4|32) AS sparse_sim
            FROM prompts
            WHERE search_tsv @@ to_tsquery('english', %s)
              AND {filter_clause}
            ORDER BY sparse_sim DESC
            LIMIT %s
        """
        cur.execute(sql, [or_terms, or_terms] + filter_params + [n])
        return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]

    @staticmethod
    def _rrf_merge(
        dense_rows: list[dict],
        sparse_rows: list[dict],
        k: int = RRF_K,
    ) -> list[SearchResult]:
        """
        Merge two ranked lists using weighted Reciprocal Rank Fusion.

        RRF score = w_dense/(k + rank_dense) + w_sparse/(k + rank_sparse)
        Documents appearing in only one list still contribute their term.
        """
        dense_rank = {r["prompt_id"]: i + 1 for i, r in enumerate(dense_rows)}
        sparse_rank = {r["prompt_id"]: i + 1 for i, r in enumerate(sparse_rows)}

        all_rows: dict[str, dict] = {}
        for r in dense_rows:
            all_rows[r["prompt_id"]] = r
        for r in sparse_rows:
            all_rows.setdefault(r["prompt_id"], r)

        # sorted(), not set order: dense and sparse are weighted equally, so the
        # doc at dense rank i ties exactly with the doc at sparse rank i, and
        # roughly half of every candidate list is in some tie. Set iteration
        # order for str keys varies per process (hash randomization) and the
        # sort below is stable, so ties used to resolve differently in every
        # process — same query, same data, different ranking.
        all_ids = sorted(set(dense_rank) | set(sparse_rank))
        scored: list[SearchResult] = []
        for pid in all_ids:
            dr = dense_rank.get(pid)
            sr = sparse_rank.get(pid)
            rrf = (
                (DENSE_WEIGHT / (k + dr) if dr else 0.0)
                + (SPARSE_WEIGHT / (k + sr) if sr else 0.0)
            )
            row = all_rows[pid]
            scored.append(
                SearchResult(
                    prompt_id=pid,
                    title=row["title"],
                    prompt_text=row["prompt_text"],
                    rrf_score=rrf,
                    dense_rank=dr,
                    sparse_rank=sr,
                    dense_sim=row.get("dense_sim") if dr else None,
                    sparse_sim=row.get("sparse_sim") if sr else None,
                    metadata={
                        "summary": row.get("summary") or "",
                        "intent": row.get("intent") or [],
                        "task_type": row.get("task_type") or [],
                        "domain": row.get("domain") or [],
                        "status": row.get("status"),
                                                "notes": row.get("notes"),
                    },
                )
            )

        # explicit tie-break on prompt_id: stable across processes and runs
        scored.sort(key=lambda r: (-r.rrf_score, r.prompt_id))
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
            assert_index_matches_model(cur)

            dense_rows = await asyncio.get_event_loop().run_in_executor(
                None,
                self._dense_search,
                cur, query_vec, filter_clause, filter_params, dense_candidates,
            )
            sparse_rows = await asyncio.get_event_loop().run_in_executor(
                None,
                self._sparse_search,
                cur, expand_acronyms(query), filter_clause, filter_params, sparse_candidates,
            )
        finally:
            conn.close()

        results = self._rrf_merge(dense_rows, sparse_rows)
        return results[:top_k]

    def fetch_all(self, filters: dict[str, Any] | None = None) -> list[SearchResult]:
        """Load all prompts matching filters (no embedding, no ranking)."""
        filters = filters or {}
        filter_clause, filter_params = _build_filter_clause(filters)

        conn = self._connect()
        try:
            cur = conn.cursor()
            sql = f"""
                SELECT prompt_id::text, title, prompt_text, summary,
                       intent, task_type, domain,
                       status, notes
                FROM prompts
                WHERE {filter_clause}
            """
            cur.execute(sql, filter_params)
            rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
        finally:
            conn.close()

        return [
            SearchResult(
                prompt_id=r["prompt_id"],
                title=r["title"],
                prompt_text=r["prompt_text"],
                rrf_score=0.0,
                dense_rank=None,
                sparse_rank=None,
                dense_sim=None,
                sparse_sim=None,
                metadata={
                    "summary": r.get("summary") or "",
                    "intent": r.get("intent") or [],
                    "task_type": r.get("task_type") or [],
                    "domain": r.get("domain") or [],
                    "status": r.get("status"),
                    "notes": r.get("notes"),
                },
            )
            for r in rows
        ]
