"""
Skill recall: match an incoming query to an existing validated skill.

Combines full-text search on routing_description with semantic (embedding)
similarity for hybrid matching. Returns the best match above a confidence
threshold, or None if no skill fits well enough.

When recall succeeds, PromptSearch returns the skill's pre-validated steps
instead of running the full retrieval + rerank pipeline.

Usage:
    from prompt_flow.skills.recall import SkillRecall

    recall = SkillRecall()
    match = recall.search("write a go-to-market strategy")
    if match:
        print(match.skill_id, match.match_score)
        for step in match.steps:
            print(step["stage"], step["prompt_id"])
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
import psycopg2
import psycopg2.extras

from prompt_flow.config import DB_CONFIG, EMBED_URL, EMBED_MODEL

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_CHARS = 4_000

RECALL_THRESHOLD = 0.50

# Weights for combining FTS and semantic scores
FTS_WEIGHT = 0.4
SEMANTIC_WEIGHT = 0.6


@dataclass
class SkillMatch:
    """A recalled skill with its steps resolved to full prompt content."""
    skill_id: str
    name: str
    slug: str
    version: int
    routing_description: str
    match_score: float              # ts_rank — confidence this skill fits the query
    steps: list[dict]               # ordered: {prompt_id, stage, step_order,
                                    #           rationale, prompt_text, metadata}
    domain: list[str] = field(default_factory=list)
    intent: list[str] = field(default_factory=list)
    task_type: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_id":            self.skill_id,
            "name":                self.name,
            "slug":                self.slug,
            "version":             self.version,
            "routing_description": self.routing_description,
            "match_score":         round(self.match_score, 4),
            "domain":              self.domain,
            "intent":              self.intent,
            "task_type":           self.task_type,
            "steps": [
                {
                    "step_order": s["step_order"],
                    "stage":      s["stage"],
                    "prompt_id":  s["prompt_id"],
                    "rationale":  s.get("rationale"),
                    "prompt_text": s.get("prompt_text", ""),
                }
                for s in self.steps
            ],
        }


class SkillRecall:
    """
    Searches active skills by routing_description (FTS) and returns the
    best match above RECALL_THRESHOLD, or None.

    Instantiate once and reuse — no heavy model loading, just DB queries.
    """

    def __init__(self, db_config: dict | None = None) -> None:
        self._db_config = db_config or DB_CONFIG

    # ── Public API ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        threshold: float = RECALL_THRESHOLD,
    ) -> SkillMatch | None:
        """
        Find the best active skill for a query using hybrid FTS + semantic search.

        Args:
            query:     Natural language query from the caller.
            filters:   Optional domain/intent/task_type hints to boost matching.
            threshold: Minimum combined score to return a match.

        Returns:
            SkillMatch with resolved prompt content, or None.
        """
        filters = filters or {}

        fts_row = self._fts_search(query, filters)
        sem_row = self._semantic_search(query)

        best = self._merge_results(fts_row, sem_row)
        if best is None or best["match_score"] < threshold:
            return None

        steps = self._resolve_steps(best["steps"])
        return SkillMatch(
            skill_id=str(best["skill_id"]),
            name=best["name"],
            slug=best["slug"],
            version=best["version"],
            routing_description=best["routing_description"],
            match_score=best["match_score"],
            domain=list(best["domain"] or []),
            intent=list(best["intent"] or []),
            task_type=list(best["task_type"] or []),
            steps=steps,
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

    def _fts_search(
        self, query: str, filters: dict[str, Any]
    ) -> dict | None:
        """
        Full-text search on routing_description.
        Taxonomy overlap boosts the score by up to 0.2.
        """
        # Sanitize query for plainto_tsquery (handles special chars safely)
        safe_query = " ".join(query.split())

        taxonomy_boost = self._taxonomy_boost_sql(filters)

        sql = f"""
            SELECT
                skill_id, name, slug, version, routing_description,
                steps, domain, intent, task_type,
                ts_rank(
                    to_tsvector('english', routing_description),
                    plainto_tsquery('english', %s)
                ) {taxonomy_boost} AS match_score
            FROM skills.skills
            WHERE status = 'active'
              AND to_tsvector('english', routing_description)
                  @@ plainto_tsquery('english', %s)
            ORDER BY match_score DESC
            LIMIT 1
        """
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, [safe_query, safe_query])
                row = cur.fetchone()
                return dict(row) if row else None

    def _semantic_search(self, query: str) -> dict | None:
        """
        Embed the query and find the nearest skill by cosine similarity
        on skills.skills.routing_embedding.
        """
        try:
            query_vec = self._embed_query(query)
        except Exception:
            return None

        if query_vec is None:
            return None

        sql = """
            SELECT
                skill_id, name, slug, version, routing_description,
                steps, domain, intent, task_type,
                1 - (routing_embedding <=> %s::vector) AS semantic_sim
            FROM skills.skills
            WHERE status = 'active'
              AND routing_embedding IS NOT NULL
            ORDER BY routing_embedding <=> %s::vector
            LIMIT 1
        """
        vec_str = "[" + ",".join(map(str, query_vec)) + "]"
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, [vec_str, vec_str])
                row = cur.fetchone()
                return dict(row) if row else None

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

    @staticmethod
    def _merge_results(fts_row: dict | None, sem_row: dict | None) -> dict | None:
        """
        Combine FTS and semantic results into a single best match.

        If both found the same skill, blend scores.
        If they found different skills, pick the one with the higher weighted score.
        """
        if fts_row is None and sem_row is None:
            return None

        if fts_row is None:
            sem_row["match_score"] = sem_row["semantic_sim"] * SEMANTIC_WEIGHT
            return sem_row

        if sem_row is None:
            return fts_row

        fts_id = str(fts_row["skill_id"])
        sem_id = str(sem_row["skill_id"])
        fts_score = fts_row["match_score"]
        sem_score = sem_row["semantic_sim"]

        if fts_id == sem_id:
            fts_row["match_score"] = fts_score * FTS_WEIGHT + sem_score * SEMANTIC_WEIGHT
            return fts_row

        fts_weighted = fts_score * FTS_WEIGHT
        sem_weighted = sem_score * SEMANTIC_WEIGHT
        if fts_weighted >= sem_weighted:
            fts_row["match_score"] = fts_weighted
            return fts_row
        sem_row["match_score"] = sem_weighted
        return sem_row

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

    def _resolve_steps(self, steps_json: list | str) -> list[dict]:
        """
        Fetch prompt_text and metadata for each step from public.prompts.
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
                cur.execute(
                    """
                    SELECT title, prompt_text, domain, intent, task_type,
                           complexity_level, content_hash
                    FROM prompts
                    WHERE title = ANY(%s)
                    """,
                    (prompt_ids,),
                )
                prompt_data = {row["title"]: dict(row) for row in cur.fetchall()}

        resolved = []
        for step in sorted(steps, key=lambda s: s["step_order"]):
            p = prompt_data.get(step["prompt_id"], {})
            resolved.append({
                "step_order":  step["step_order"],
                "stage":       step["stage"],
                "prompt_id":   step["prompt_id"],
                "rationale":   step.get("rationale"),
                "pinned_hash": step.get("pinned_hash"),
                "prompt_text": p.get("prompt_text", ""),
                "metadata": {
                    "domain":          p.get("domain") or [],
                    "intent":          p.get("intent") or [],
                    "task_type":       p.get("task_type") or [],
                    "complexity_level": p.get("complexity_level"),
                    "content_hash":    p.get("content_hash"),
                },
            })
        return resolved
