"""
Skill recall: match an incoming query to an existing validated skill.

Searches skills.skills using full-text search on routing_description,
optionally boosted by taxonomy overlap. Returns the best match above a
confidence threshold, or None if no skill fits well enough.

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

import psycopg2
import psycopg2.extras

from prompt_flow.config import DB_CONFIG

# Minimum ts_rank score to accept a skill match.
# ts_rank values are small (typically 0.01–0.6); 0.05 filters noise
# while still catching genuine matches.
RECALL_THRESHOLD = 0.05


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
        Find the best active skill for a query.

        Args:
            query:     Natural language query from the caller.
            filters:   Optional domain/intent/task_type hints to boost matching.
            threshold: Minimum ts_rank score to return a match.

        Returns:
            SkillMatch with resolved prompt content, or None.
        """
        filters = filters or {}
        row = self._fts_search(query, filters)
        if row is None or row["match_score"] < threshold:
            return None

        steps = self._resolve_steps(row["steps"])
        return SkillMatch(
            skill_id=str(row["skill_id"]),
            name=row["name"],
            slug=row["slug"],
            version=row["version"],
            routing_description=row["routing_description"],
            match_score=row["match_score"],
            domain=list(row["domain"] or []),
            intent=list(row["intent"] or []),
            task_type=list(row["task_type"] or []),
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
                    SELECT prompt_id, prompt_text, domain, intent, task_type,
                           primary_stage, complexity_level, content_hash
                    FROM prompts
                    WHERE prompt_id = ANY(%s)
                    """,
                    (prompt_ids,),
                )
                prompt_data = {row["prompt_id"]: dict(row) for row in cur.fetchall()}

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
                    "primary_stage":   p.get("primary_stage"),
                    "complexity_level": p.get("complexity_level"),
                    "content_hash":    p.get("content_hash"),
                },
            })
        return resolved
