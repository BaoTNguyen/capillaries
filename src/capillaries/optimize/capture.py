"""Golden example capture for DSPy optimization."""

from __future__ import annotations

import uuid

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG


def _resolve_prompt_id(cur, prompt_title: str) -> str:
    cur.execute("SELECT prompt_id FROM prompts WHERE title = %s", (prompt_title,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Prompt not found: {prompt_title}")
    return str(row[0])


class ExampleCapture:
    """Capture and manage golden examples for DSPy optimization."""

    def __init__(self, db_config: dict | None = None):
        self._db_config = db_config or DB_CONFIG

    def capture_from_memory(
        self,
        prompt_title: str,
        input_text: str,
        output_text: str,
        context_text: str | None = None,
        model: str | None = None,
        conversation_id: str | None = None,
    ) -> str:
        """Ingest a golden example from the memory project feed."""
        return self._insert(
            prompt_title=prompt_title,
            input_text=input_text,
            output_text=output_text,
            context_text=context_text,
            source="memory_project",
            model=model,
            conversation_id=conversation_id,
        )

    def capture_external(
        self,
        prompt_title: str,
        input_text: str,
        output_text: str,
        model: str | None = None,
    ) -> str:
        """Add an external golden example (breaks circular optimization)."""
        return self._insert(
            prompt_title=prompt_title,
            input_text=input_text,
            output_text=output_text,
            source="external",
            model=model,
        )

    def capture_manual(
        self,
        prompt_title: str,
        input_text: str,
        output_text: str,
        model: str | None = None,
    ) -> str:
        """Add a manually curated golden example."""
        return self._insert(
            prompt_title=prompt_title,
            input_text=input_text,
            output_text=output_text,
            source="manual",
            model=model,
        )

    def capture_contrastive(
        self,
        prompt_title: str,
        input_text: str,
        good_output: str,
        bad_output: str,
        model: str | None = None,
    ) -> tuple[str, str]:
        """Add a contrastive pair (good + bad for the same input)."""
        pair_id = str(uuid.uuid4())
        good_id = self._insert(
            prompt_title=prompt_title,
            input_text=input_text,
            output_text=good_output,
            source="contrastive",
            model=model,
            pair_id=pair_id,
            is_negative=False,
        )
        bad_id = self._insert(
            prompt_title=prompt_title,
            input_text=input_text,
            output_text=bad_output,
            source="contrastive",
            model=model,
            pair_id=pair_id,
            is_negative=True,
        )
        return good_id, bad_id

    def list_examples(self, prompt_title: str) -> list[dict]:
        """List all golden examples for a prompt with source breakdown."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prompt_id = _resolve_prompt_id(cur, prompt_title)
                cur.execute("""
                    SELECT example_id, source, model,
                           is_negative, pair_id, created_at,
                           LEFT(input_text, 100) AS input_preview,
                           LEFT(output_text, 100) AS output_preview
                    FROM golden_examples
                    WHERE prompt_id = %s
                    ORDER BY created_at DESC
                """, (prompt_id,))
                return [dict(row) for row in cur.fetchall()]

    def source_distribution(self, prompt_title: str) -> dict:
        """Check the source distribution of examples for a prompt."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                prompt_id = _resolve_prompt_id(cur, prompt_title)
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE source != 'memory_project') AS external_count,
                        COUNT(*) FILTER (WHERE source = 'memory_project') AS memory_count,
                        COUNT(*) FILTER (WHERE source = 'external') AS pure_external_count,
                        COUNT(*) FILTER (WHERE source = 'contrastive') AS contrastive_count,
                        COUNT(*) FILTER (WHERE source = 'manual') AS manual_count
                    FROM golden_examples
                    WHERE prompt_id = %s AND NOT is_negative
                """, (prompt_id,))
                row = cur.fetchone()
                total = row[0] or 0
                external = row[1] or 0
                return {
                    "total": total,
                    "external_count": external,
                    "memory_count": row[2] or 0,
                    "pure_external_count": row[3] or 0,
                    "contrastive_count": row[4] or 0,
                    "manual_count": row[5] or 0,
                    "external_ratio": round(external / max(total, 1), 2),
                }

    def _insert(
        self,
        prompt_title: str,
        input_text: str,
        output_text: str,
        source: str,
        context_text: str | None = None,
        model: str | None = None,
        conversation_id: str | None = None,
        pair_id: str | None = None,
        is_negative: bool = False,
    ) -> str:
        example_id = str(uuid.uuid4())
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                prompt_id = _resolve_prompt_id(cur, prompt_title)
                cur.execute("""
                    INSERT INTO golden_examples (
                        example_id, prompt_id, input_text, output_text,
                        context_text, source, model, conversation_id,
                        is_negative, pair_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    example_id, prompt_id, input_text, output_text,
                    context_text, source, model, conversation_id,
                    is_negative, pair_id,
                ))
                conn.commit()
        return example_id
