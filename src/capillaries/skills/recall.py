"""
Skill recall: retrieve candidate skills for a query, to be reranked
alongside prompt candidates by the caller (see search/api.py).

Combines full-text search on skills.skills.search_tsv (same mechanism as
prompts.search_tsv — see Retriever._to_or_tsquery / _sparse_search) with
semantic (embedding) similarity on routing_embedding.

Usage:
    from capillaries.skills.recall import SkillRecall

    recall = SkillRecall()
    candidates = recall.candidates("write a go-to-market strategy")
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG, EMBED_URL, EMBED_MODEL, QUERY_PREFIX

if TYPE_CHECKING:
    # capillaries.skills.__init__ imports this module; capillaries.search.api
    # imports SkillRecall back, so importing SearchResult eagerly here breaks
    # depending on which package a caller touches first. Import type-only.
    from capillaries.search.retriever import SearchResult

MAX_CHARS = 4_000


@dataclass
class SkillMatch:
    """A recalled skill with its steps resolved to full prompt content."""
    skill_id: str
    name: str
    tag: str
    version: int
    summary: str
    match_score: float              # cross-encoder rerank score, same scale as prompt results
    steps: list[dict]               # ordered: {prompt_id, step_order,
                                    #           rationale, prompt_text, metadata}
    domain: list[str] = field(default_factory=list)
    intent: list[str] = field(default_factory=list)
    task_type: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_id":            self.skill_id,
            "name":                self.name,
            "tag":                self.tag,
            "version":             self.version,
            "summary": self.summary,
            "match_score":         round(self.match_score, 4),
            "domain":              self.domain,
            "intent":              self.intent,
            "task_type":           self.task_type,
            "steps": [
                {
                    "step_order": s["step_order"],
                    "prompt_id":  s["prompt_id"],
                    "rationale":  s.get("rationale"),
                    "prompt_text": s.get("prompt_text", ""),
                }
                for s in self.steps
            ],
        }


class SkillRecall:
    """
    Retrieves candidate active skills for a query via hybrid FTS + semantic
    search — a pool for the caller to rerank, not a pre-decided best match.

    Instantiate once and reuse — no heavy model loading, just DB queries.
    """

    def __init__(self, db_config: dict | None = None) -> None:
        self._db_config = db_config or DB_CONFIG

    # ── Public API ────────────────────────────────────────────────────────

    def candidates(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        per_channel: int = 10,
    ) -> list[SearchResult]:
        """
        Top-N skills by FTS + top-N by semantic similarity, unioned like
        prompt retrieval — a pool of candidates for the caller to rerank
        alongside prompt candidates, rather than a single pre-decided best.

        FTS uses the same mechanism as prompts (search_tsv, OR-joined
        tsquery, ts_rank_cd) — see Retriever._to_or_tsquery/_sparse_search.

        Each result carries metadata["kind"] = "skill" and the raw (unresolved)
        steps JSON — steps are only resolved to full prompt text for whichever
        candidate the reranker actually picks, via `_resolve_steps`.
        """
        from capillaries.search.retriever import Retriever

        filters = filters or {}
        taxonomy_boost = self._taxonomy_boost_sql(filters)

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as plain_cur:
                # _to_or_tsquery indexes the row positionally (cur.fetchone()[0]),
                # so it needs a plain cursor — RealDictCursor rows aren't int-indexable.
                or_terms = Retriever._to_or_tsquery(plain_cur, query)

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                fts_rows = []
                if or_terms:
                    fts_sql = f"""
                        SELECT
                            skill_id, name, tag, version, summary,
                            steps, domain, intent, task_type,
                            ts_rank_cd(search_tsv, to_tsquery('english', %s), 1|4|32)
                                {taxonomy_boost} AS score
                        FROM skills.skills
                        WHERE status = 'active'
                          AND search_tsv @@ to_tsquery('english', %s)
                        ORDER BY score DESC
                        LIMIT %s
                    """
                    cur.execute(fts_sql, [or_terms, or_terms, per_channel])
                    fts_rows = cur.fetchall()

        try:
            query_vec = self._embed_query(query)
        except Exception:
            query_vec = None

        sem_rows: list[dict] = []
        if query_vec is not None:
            vec_str = "[" + ",".join(map(str, query_vec)) + "]"
            sem_sql = """
                SELECT
                    skill_id, name, tag, version, summary,
                    steps, domain, intent, task_type,
                    1 - (routing_embedding <=> %s::vector) AS score
                FROM skills.skills
                WHERE status = 'active'
                  AND routing_embedding IS NOT NULL
                ORDER BY routing_embedding <=> %s::vector
                LIMIT %s
            """
            with psycopg2.connect(**self._db_config) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # See retriever._dense_search: ef_search caps the index
                    # walk and status is filtered after it.
                    cur.execute("SET LOCAL hnsw.ef_search = %s",
                                (max(2 * per_channel, 100),))
                    cur.execute(sem_sql, [vec_str, vec_str, per_channel])
                    sem_rows = cur.fetchall()

        by_id: dict[str, SearchResult] = {}
        for rank, row in enumerate(fts_rows, 1):
            by_id[str(row["skill_id"])] = self._to_candidate(row, sparse_rank=rank, sparse_sim=row["score"])
        for rank, row in enumerate(sem_rows, 1):
            sid = str(row["skill_id"])
            if sid in by_id:
                by_id[sid].dense_rank = rank
                by_id[sid].dense_sim = row["score"]
            else:
                by_id[sid] = self._to_candidate(row, dense_rank=rank, dense_sim=row["score"])

        return list(by_id.values())

    @staticmethod
    def _to_candidate(
        row: dict, dense_rank: int | None = None, sparse_rank: int | None = None,
        dense_sim: float | None = None, sparse_sim: float | None = None,
    ) -> SearchResult:
        from capillaries.search.retriever import SearchResult
        return SearchResult(
            prompt_id=str(row["skill_id"]),
            title=row["name"],
            prompt_text=f"{row['name']}\n\n{row['summary']}",
            rrf_score=0.0,
            dense_rank=dense_rank, sparse_rank=sparse_rank,
            dense_sim=dense_sim, sparse_sim=sparse_sim,
            metadata={
                "kind": "skill",
                "skill_id": str(row["skill_id"]),
                "tag": row["tag"],
                "version": row["version"],
                "summary": row["summary"],
                "domain": list(row["domain"] or []),
                "intent": list(row["intent"] or []),
                "task_type": list(row["task_type"] or []),
                "steps": row["steps"],
            },
        )

    def log_run(
        self,
        skill_id: str,
        skill_version: int,
        status: str = "success",
        score: float | None = None,
        step_hashes: list[dict] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """
        Record a skill invocation in skills.skill_runs and update total_runs.
        Call this after a recalled skill is used — fire-and-forget is fine.
        """
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skills.skill_runs
                        (run_id, skill_id, skill_version, status, score,
                         step_hashes, started_at, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        skill_id,
                        skill_version,
                        status,
                        score,
                        json.dumps(step_hashes or []),
                        datetime.utcnow(),
                        duration_ms,
                    ),
                )
                cur.execute(
                    """
                    UPDATE skills.skills
                    SET total_runs = total_runs + 1,
                        last_run_at = CURRENT_TIMESTAMP
                    WHERE skill_id = %s
                    """,
                    (skill_id,),
                )

    # ── Internals ─────────────────────────────────────────────────────────

    def _embed_query(self, text: str) -> list[float] | None:
        """Synchronously embed a query via the embedding server."""
        resp = httpx.post(
            EMBED_URL,
            json={"input": QUERY_PREFIX + text[:MAX_CHARS], "model": EMBED_MODEL},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return None
        return resp.json()["data"][0]["embedding"]

    def _taxonomy_boost_sql(self, filters: dict[str, Any]) -> str:
        """
        Return a SQL fragment that adds a small score bonus when the skill's
        taxonomy overlaps with the caller's filters.
        Each matching dimension adds 0.05 (max +0.15 total).
        """
        boosts = []
        if filters.get("domain"):
            boosts.append(
                f"+ CASE WHEN domain && ARRAY{filters['domain']!r}::varchar[] THEN 0.05 ELSE 0 END"
            )
        if filters.get("intent"):
            boosts.append(
                f"+ CASE WHEN intent && ARRAY{filters['intent']!r}::varchar[] THEN 0.05 ELSE 0 END"
            )
        if filters.get("task_type"):
            boosts.append(
                f"+ CASE WHEN task_type && ARRAY{filters['task_type']!r}::varchar[] THEN 0.05 ELSE 0 END"
            )
        return " ".join(boosts)

    def _resolve_steps(
        self, steps_json: list | str, model: str | None = None,
    ) -> list[dict]:
        """
        Fetch prompt_text and metadata for each step from public.prompts.
        When *model* is provided, prefer optimized variants from prompt_variants.
        Returns steps sorted by step_order with prompt content merged in.
        """
        if isinstance(steps_json, str):
            steps = json.loads(steps_json)
        else:
            steps = steps_json or []

        if not steps:
            return []

        prompt_ids = [s["prompt_id"] for s in steps]

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Steps carry prompt UUIDs, so both lookups match on prompt_id.
                # They used to match on title against a UUID, which returned
                # nothing without erroring — every step fell back to empty text.
                # Keys are str()-ed because psycopg2 hands back uuid.UUID while
                # step["prompt_id"] is a string from JSON.
                cur.execute(
                    """
                    SELECT prompt_id, title, prompt_text, domain, intent,
                           task_type, content_hash
                    FROM prompts
                    WHERE prompt_id = ANY(%s::uuid[])
                      AND status = 'active'
                    """,
                    (prompt_ids,),
                )
                prompt_data = {str(row["prompt_id"]): dict(row)
                               for row in cur.fetchall()}

                variant_texts: dict[str, str] = {}
                if model:
                    cur.execute(
                        """
                        SELECT prompt_id, prompt_text
                        FROM prompt_variants
                        WHERE prompt_id = ANY(%s::uuid[])
                          AND model = %s
                          AND is_current = TRUE
                        """,
                        (prompt_ids, model),
                    )
                    variant_texts = {str(row["prompt_id"]): row["prompt_text"]
                                     for row in cur.fetchall()}

        resolved = []
        for step in sorted(steps, key=lambda s: s["step_order"]):
            pid = step["prompt_id"]
            p = prompt_data.get(pid, {})
            text = variant_texts.get(pid, p.get("prompt_text", ""))
            resolved.append({
                "step_order":  step["step_order"],
                "prompt_id":   pid,
                "rationale":   step.get("rationale"),
                "pinned_hash": step.get("pinned_hash"),
                "prompt_text": text,
                "metadata": {
                    "domain":          p.get("domain") or [],
                    "intent":          p.get("intent") or [],
                    "task_type":       p.get("task_type") or [],
                    "content_hash":    p.get("content_hash"),
                },
            })
        return resolved
