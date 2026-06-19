"""Advisory cascade: flag dependent items when a prompt or skill is inactivated."""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG


def find_dependent_skills(prompt_title: str, db_config: dict | None = None) -> list[dict]:
    """Find active skills that reference the given prompt in their steps."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT s.skill_id, s.name, s.slug, step->>'step_order' AS step_order
                FROM skills.skills s,
                     jsonb_array_elements(s.steps) AS step
                WHERE s.status = 'active'
                  AND step->>'prompt_id' = %s
            """, (prompt_title,))
            return [dict(row) for row in cur.fetchall()]


def find_orphaned_prompts(skill_slug: str, db_config: dict | None = None) -> list[dict]:
    """Find prompts used only by the given skill and no other active skill."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                WITH skill_prompts AS (
                    SELECT step->>'prompt_id' AS prompt_id
                    FROM skills.skills,
                         jsonb_array_elements(steps) AS step
                    WHERE slug = %s
                ),
                other_skill_prompts AS (
                    SELECT DISTINCT step->>'prompt_id' AS prompt_id
                    FROM skills.skills,
                         jsonb_array_elements(steps) AS step
                    WHERE slug != %s AND status = 'active'
                )
                SELECT p.title, p.status
                FROM skill_prompts sp
                JOIN prompts p ON p.title = sp.prompt_id
                WHERE sp.prompt_id NOT IN (SELECT prompt_id FROM other_skill_prompts)
            """, (skill_slug, skill_slug))
            return [dict(row) for row in cur.fetchall()]
