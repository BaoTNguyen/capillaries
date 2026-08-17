"""Auto-inactivation: move prompts and skills to inactive after 6 months of disuse."""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG


def inactivate_stale_prompts(
    db_config: dict | None = None, dry_run: bool = False
) -> list[str]:
    """Move active prompts with no direct usage in 6 months to inactive.

    Direct usage = a row in skills.agent_feedback where prompt_id matches
    and outcome != 'skipped'. Skill-mediated usage does not count.
    """
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            if dry_run:
                cur.execute("""
                    SELECT title FROM prompts
                    WHERE status = 'active'
                      AND title NOT IN (
                          SELECT DISTINCT prompt_id FROM skills.agent_feedback
                          WHERE prompt_id IS NOT NULL
                            AND created_at > NOW() - INTERVAL '6 months'
                            AND outcome != 'skipped'
                      )
                """)
                return [row[0] for row in cur.fetchall()]

            cur.execute("""
                UPDATE prompts SET status = 'inactive'
                WHERE status = 'active'
                  AND title NOT IN (
                      SELECT DISTINCT prompt_id FROM skills.agent_feedback
                      WHERE prompt_id IS NOT NULL
                        AND created_at > NOW() - INTERVAL '6 months'
                        AND outcome != 'skipped'
                  )
                RETURNING title
            """)
            titles = [row[0] for row in cur.fetchall()]
            conn.commit()
            return titles


def inactivate_stale_skills(
    db_config: dict | None = None, dry_run: bool = False
) -> list[dict]:
    """Move active skills with no runs in 6 months to inactive."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if dry_run:
                cur.execute("""
                    SELECT name, tag FROM skills.skills
                    WHERE status = 'active'
                      AND skill_id NOT IN (
                          SELECT DISTINCT skill_id FROM skills.skill_runs
                          WHERE started_at > NOW() - INTERVAL '6 months'
                      )
                """)
                return [dict(row) for row in cur.fetchall()]

            cur.execute("""
                UPDATE skills.skills SET status = 'inactive'
                WHERE status = 'active'
                  AND skill_id NOT IN (
                      SELECT DISTINCT skill_id FROM skills.skill_runs
                      WHERE started_at > NOW() - INTERVAL '6 months'
                  )
                RETURNING name, tag
            """)
            rows = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return rows
