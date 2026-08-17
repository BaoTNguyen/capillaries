"""
Serving log: records what was served for a query, plus the top-k candidates
the ranker considered but didn't necessarily serve.

Prerequisite for harvest.py's ranking signal (STACK_READINESS §5.1) — without
the candidates that *weren't* served, the optimizer can't learn ranking, only
"was the served thing good".

Best-effort by design: a serving log is observability, not correctness. If
Postgres is down or anything else goes wrong, log_serving drops the record
silently rather than breaking retrieval.
"""

from __future__ import annotations

import json
import os

import psycopg2

from capillaries.config.paths import DB_CONFIG

MAX_CANDIDATES = 10

DDL = """
CREATE TABLE IF NOT EXISTS serving_log (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ DEFAULT now(),
    episode_id  TEXT,
    turn_id     TEXT,
    query       TEXT NOT NULL,
    served_kind TEXT NOT NULL,
    served_id   TEXT,
    candidates  JSONB NOT NULL DEFAULT '[]'
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_serving_log_episode ON serving_log (episode_id) WHERE episode_id IS NOT NULL;",
    "CREATE INDEX IF NOT EXISTS idx_serving_log_ts ON serving_log (ts);",
]


def apply_ddl(db_config: dict | None = None) -> None:
    """Create serving_log the way db/setup.py applies the rest of the schema."""
    config = db_config or DB_CONFIG
    conn = psycopg2.connect(**config)
    try:
        cur = conn.cursor()
        cur.execute(DDL)
        for sql in INDEXES:
            cur.execute(sql)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def log_serving(
    query: str,
    served_kind: str,
    served_id: str | None,
    candidates: list[dict],
    db_config: dict | None = None,
) -> None:
    """
    Record what was served for a query, plus the ranked candidates considered.

    candidates: list of {"id": ..., "score": float}, capped at MAX_CANDIDATES.

    episode_id comes from $ARTERIES_EPISODE_ID (the convention arteries already
    uses when calling into capillaries — see arteries/spool.py, actionlog.py).
    turn_id: no env/arg convention reaches capillaries today (arteries only
    threads ARTERIES_EPISODE_ID / ARTERIES_TASK_ID this deep), so it is left
    null here until such a convention exists.

    Best-effort: never raises. DB down or any other failure -> silently drop.
    """
    try:
        episode_id = os.environ.get("ARTERIES_EPISODE_ID")
        # arteries stamps ARTERIES_TURN_ID around its retrieval call (eval.py);
        # null when the caller isn't arteries or predates the convention.
        turn_id = os.environ.get("ARTERIES_TURN_ID")

        capped = [
            {"id": c.get("id"), "score": c.get("score")}
            for c in (candidates or [])[:MAX_CANDIDATES]
        ]

        config = db_config or DB_CONFIG
        conn = psycopg2.connect(**config)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO serving_log
                        (episode_id, turn_id, query, served_kind, served_id, candidates)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (episode_id, turn_id, query, served_kind, served_id, json.dumps(capped)),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # observability must never take down retrieval
