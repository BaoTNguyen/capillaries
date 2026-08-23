"""Auto-inactivation: move prompts and skills to inactive after 6 months of disuse."""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG

# Refuse to retire more than this share of the corpus in one pass.
#
# "No usage recorded" and "no usage happened" are indistinguishable from
# inside this query, and they call for opposite actions. skills.agent_feedback
# was not created by scripts/setup_db.py at all until recently, so the honest
# reading of an empty feedback table is a telemetry outage, not a corpus where
# every single prompt went unused -- and acting on it would inactivate
# everything, silently, in one statement.
MAX_INACTIVATION_FRACTION = 0.5


class InactivationRefused(RuntimeError):
    """Raised when a pass would retire an implausible share of the corpus."""


def _guard(kind: str, doomed: int, total: int, max_fraction: float) -> None:
    if total == 0 or not doomed:
        return
    fraction = doomed / total
    if fraction > max_fraction:
        raise InactivationRefused(
            f"refusing to inactivate {doomed}/{total} {kind} ({fraction:.0%} of the "
            f"corpus, limit {max_fraction:.0%}). This usually means usage telemetry "
            f"is missing rather than that the content is stale -- check that "
            f"skills.agent_feedback is being written. Pass max_fraction=1.0 to "
            f"override once you have confirmed it."
        )


def inactivate_stale_prompts(
    db_config: dict | None = None, dry_run: bool = False,
    max_fraction: float = MAX_INACTIVATION_FRACTION,
) -> list[str]:
    """Move active prompts with no direct usage in 6 months to inactive.

    Direct usage = a row in skills.agent_feedback where prompt_id matches
    and outcome != 'skipped'. Skill-mediated usage does not count.

    Raises InactivationRefused if the pass would retire more than
    *max_fraction* of active prompts -- see MAX_INACTIVATION_FRACTION.
    """
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM prompts WHERE status = 'active'")
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM prompts
                WHERE status = 'active'
                  AND prompt_id::text NOT IN (
                      SELECT DISTINCT prompt_id::text FROM skills.agent_feedback
                      WHERE prompt_id IS NOT NULL
                        AND created_at > NOW() - INTERVAL '6 months'
                        AND outcome != 'skipped'
                  )
            """)
            _guard("prompts", cur.fetchone()[0], total, max_fraction)

            if dry_run:
                cur.execute("""
                    SELECT title FROM prompts
                    WHERE status = 'active'
                      AND prompt_id::text NOT IN (
                          SELECT DISTINCT prompt_id::text FROM skills.agent_feedback
                          WHERE prompt_id IS NOT NULL
                            AND created_at > NOW() - INTERVAL '6 months'
                            AND outcome != 'skipped'
                      )
                """)
                return [row[0] for row in cur.fetchall()]

            cur.execute("""
                UPDATE prompts SET status = 'inactive'
                WHERE status = 'active'
                  AND prompt_id::text NOT IN (
                      SELECT DISTINCT prompt_id::text FROM skills.agent_feedback
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
    db_config: dict | None = None, dry_run: bool = False,
    max_fraction: float = MAX_INACTIVATION_FRACTION,
) -> list[dict]:
    """Move active skills with no runs in 6 months to inactive.

    Raises InactivationRefused on the same guard as prompts.
    """
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT count(*) AS n FROM skills.skills WHERE status = 'active'")
            total = cur.fetchone()["n"]
            cur.execute("""
                SELECT count(*) AS n FROM skills.skills
                WHERE status = 'active'
                  AND skill_id NOT IN (
                      SELECT DISTINCT skill_id FROM skills.skill_runs
                      WHERE started_at > NOW() - INTERVAL '6 months'
                  )
            """)
            _guard("skills", cur.fetchone()["n"], total, max_fraction)

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
