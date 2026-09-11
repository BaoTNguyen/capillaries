"""Quarterly review surface: present inactive items with decision-support metadata."""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG


def review_inactive_prompts(db_config: dict | None = None) -> list[dict]:
    """Surface inactive prompts with metadata for quarterly review."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    p.title,
                    p.status,
                    p.domain,
                    p.intent,
                    p.task_type,
                    p.last_updated,
                    (
                        SELECT MAX(af.created_at)
                        FROM skills.agent_feedback af
                        WHERE af.prompt_id = p.prompt_id
                    ) AS last_direct_use,
                    (
                        SELECT COUNT(*)
                        FROM skills.agent_feedback af
                        WHERE af.prompt_id = p.prompt_id AND af.outcome != 'skipped'
                    ) AS total_runs,
                    (
                        SELECT pqp.success_rate
                        FROM prompt_quality_prior pqp
                        WHERE pqp.prompt_id = p.prompt_id
                    ) AS success_rate,
                    (
                        SELECT COUNT(*)
                        FROM skills.skills s,
                             jsonb_array_elements(s.steps) AS step
                        WHERE s.status = 'active'
                          AND step->>'prompt_id' = p.prompt_id::text
                    ) AS active_skill_count,
                    (
                        SELECT COUNT(*)
                        FROM golden_examples ge
                        WHERE ge.prompt_id = p.prompt_id
                    ) AS golden_example_count,
                    (
                        SELECT COUNT(*)
                        FROM prompt_variants pv
                        WHERE pv.prompt_id = p.prompt_id AND pv.is_current = TRUE
                    ) AS variant_count
                FROM prompts p
                WHERE p.status = 'inactive'
                ORDER BY last_direct_use ASC NULLS FIRST
            """)
            return [dict(row) for row in cur.fetchall()]


def review_inactive_skills(db_config: dict | None = None) -> list[dict]:
    """Surface inactive skills with metadata for quarterly review."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    s.name,
                    s.tag,
                    s.status,
                    s.last_run_at,
                    s.total_runs,
                    s.success_rate,
                    jsonb_array_length(s.steps) AS step_count,
                    (
                        SELECT COUNT(*)
                        FROM jsonb_array_elements(s.steps) AS step
                        JOIN prompts p ON p.prompt_id::text = step->>'prompt_id'
                        WHERE p.status = 'inactive'
                    ) AS inactive_prompt_count
                FROM skills.skills s
                WHERE s.status = 'inactive'
                ORDER BY s.last_run_at ASC NULLS FIRST
            """)
            return [dict(row) for row in cur.fetchall()]


def find_similar_active_prompts(
    prompt_title: str, top_k: int = 3, db_config: dict | None = None
) -> list[dict]:
    """Find the closest active prompts by embedding similarity."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SET LOCAL hnsw.iterative_scan = 'relaxed_order'")
            cur.execute("""
                SELECT title, 1 - (embedding <=> (
                    SELECT embedding FROM prompts WHERE title = %s
                )) AS similarity
                FROM prompts
                WHERE status = 'active'
                  AND title != %s
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> (
                    SELECT embedding FROM prompts WHERE title = %s
                )
                LIMIT %s
            """, (prompt_title, prompt_title, prompt_title, top_k))
            return [dict(row) for row in cur.fetchall()]
