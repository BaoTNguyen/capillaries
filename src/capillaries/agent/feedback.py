"""
Feedback submission and aggregation for the learning loop.
"""

from __future__ import annotations

import uuid

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG


class FeedbackHandler:
    """
    Handles feedback submission and updates quality priors.
    """

    def __init__(self, db_config: dict | None = None):
        self._db_config = db_config or DB_CONFIG

    def submit_feedback(
        self,
        trace_id: str,
        outcome: str,
        mode: str,
        prompt_id: str | None = None,
        skill_id: str | None = None,
        session_id: str | None = None,
        quality_score: float | None = None,
        failure_step: int | None = None,
        failure_reason: str | None = None,
        notes: str | None = None,
        prompt_modifications: list[dict] | None = None,
        per_step_feedback: list[dict] | None = None,
        situation_text: str | None = None,
        inferred_domain: list[str] | None = None,
        inferred_stage: str | None = None,
    ) -> dict:
        """Submit agent feedback.

        *prompt_id* may be a prompt UUID or a title. Callers get a UUID back
        from find()/route(), but the MCP surface has always accepted either
        and the column used to store either -- so it is normalised here rather
        than rejected, and stored as the UUID.
        """
        feedback_id = str(uuid.uuid4())
        prompt_id = self._as_prompt_uuid(prompt_id)

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skills.agent_feedback (
                        feedback_id, trace_id, session_id, mode, prompt_id, skill_id,
                        outcome, quality_score, failure_step, failure_reason, notes,
                        prompt_modifications, per_step_feedback, situation_text,
                        inferred_domain, inferred_stage
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        feedback_id,
                        trace_id,
                        session_id,
                        mode,
                        prompt_id,
                        skill_id,
                        outcome,
                        quality_score,
                        failure_step,
                        failure_reason,
                        notes,
                        prompt_modifications or [],
                        per_step_feedback or [],
                        situation_text,
                        inferred_domain,
                        inferred_stage,
                    ),
                )

                if skill_id:
                    self._update_skill_success_rate(cur, skill_id)

                conn.commit()

        return {"acknowledged": True, "feedback_id": feedback_id}

    def _as_prompt_uuid(self, value: str | None) -> str | None:
        """Resolve a title to its prompt_id; pass a UUID through unchanged."""
        if not value:
            return None
        try:
            uuid.UUID(str(value))
            return str(value)
        except (ValueError, AttributeError, TypeError):
            pass
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT prompt_id::text FROM prompts WHERE title = %s", (value,))
                row = cur.fetchone()
        # Unresolvable: store nothing rather than a value no join can match.
        return row[0] if row else None

    def _update_skill_success_rate(self, cur, skill_id: str) -> None:
        """Update skill success rate from recent feedback."""
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_runs,
                AVG(CASE
                    WHEN outcome = 'success' THEN 1.0
                    WHEN outcome = 'partial' THEN 0.5
                    WHEN outcome = 'failure' THEN 0.0
                    ELSE NULL
                END) AS success_rate
            FROM skills.agent_feedback
            WHERE skill_id = %s AND outcome != 'skipped'
            """,
            (skill_id,),
        )
        result = cur.fetchone()

        if result and result[0]:
            cur.execute(
                """
                UPDATE skills.skills
                SET success_rate = %s, total_runs = %s
                WHERE skill_id = %s
                """,
                (result[1], result[0], skill_id),
            )

    def refresh_quality_prior(self) -> None:
        """Refresh the materialized view for prompt quality priors."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY prompt_quality_prior")
                conn.commit()


def get_quality_prior(prompt_id: str, db_config: dict | None = None) -> float | None:
    """Get the Bayesian quality score for a prompt."""
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT bayesian_quality FROM prompt_quality_prior WHERE prompt_id = %s",
                (prompt_id,),
            )
            row = cur.fetchone()
            return row["bayesian_quality"] if row else None