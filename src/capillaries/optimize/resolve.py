"""Runtime variant resolution — select the right prompt text for the active model."""

from __future__ import annotations

import psycopg2

from capillaries.config.paths import DB_CONFIG


def resolve_prompt_text(
    prompt_id: str,
    model: str | None = None,
    db_config: dict | None = None,
) -> str:
    """Return the best prompt text for the given model.

    Checks prompt_variants first (for a model-specific optimized version),
    falls back to the canonical prompt_text in prompts table.
    """
    config = db_config or DB_CONFIG
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            if model:
                cur.execute("""
                    SELECT prompt_text FROM prompt_variants
                    WHERE prompt_id = %s AND model = %s AND is_current = TRUE
                    LIMIT 1
                """, (prompt_id, model))
                row = cur.fetchone()
                if row:
                    return row[0]

            cur.execute(
                "SELECT prompt_text FROM prompts WHERE prompt_id = %s",
                (prompt_id,),
            )
            row = cur.fetchone()
            return row[0] if row else ""
