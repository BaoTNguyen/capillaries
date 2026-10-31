"""
Serving log: records what was served for a query, plus the top-k candidates
the ranker considered but didn't necessarily serve.

Prerequisite for any ranking signal (docs/adr/2026-07-20-log-unserved-candidates.md) — without the
candidates that *weren't* served, an optimizer can't learn ranking, only "was
the served thing good". harvest.py used to be the consumer; it was deleted for
using the served prompt as its golden output, and nothing has replaced it yet.
The log is still worth keeping: it is the record a future consumer needs, and
it cannot be reconstructed after the fact.

Serving records are events now: log_serving emits `retrieval.served` onto the
event spine and stores the query text as a pulse artifact, so it never touches
Postgres. The serving_log table is a read-only archive (pulse P5); DDL and
apply_ddl remain only so existing setups can still create it.

Best-effort by design: a serving log is observability, not correctness. If
the journal is unwritable or anything else goes wrong, log_serving drops the
record silently rather than breaking retrieval.
"""

from __future__ import annotations

import os

import psycopg2

from capillaries import pulse_emit, spine, vascular_paths
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

ARCHIVE_SQL = [
    """CREATE OR REPLACE FUNCTION archive_read_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION '% is a read-only archive (pulse P5); write an event instead', TG_TABLE_NAME; END $$;""",
    "DROP TRIGGER IF EXISTS read_only_archive ON serving_log;",
    "CREATE TRIGGER read_only_archive BEFORE INSERT OR UPDATE OR DELETE ON serving_log FOR EACH ROW EXECUTE FUNCTION archive_read_only();",
    # Fresh databases no longer create batch_processing_log (db/setup.py).
    """DO $do$ BEGIN
    IF to_regclass('batch_processing_log') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS read_only_archive ON batch_processing_log;
        CREATE TRIGGER read_only_archive BEFORE INSERT OR UPDATE OR DELETE ON batch_processing_log FOR EACH ROW EXECUTE FUNCTION archive_read_only();
    END IF;
END $do$;""",
]


def apply_ddl(db_config: dict | None = None) -> None:
    """Create serving_log and make it (and batch_processing_log) a read-only archive. Idempotent."""
    config = db_config or DB_CONFIG
    conn = psycopg2.connect(**config)
    try:
        cur = conn.cursor()
        cur.execute(DDL)
        for sql in INDEXES + ARCHIVE_SQL:
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
    episode_id: str | None = None,
    turn_id: str | None = None,
) -> None:
    """
    Record what was served for a query, plus the ranked candidates considered.

    candidates: list of {"id": ..., "score": float}, capped at MAX_CANDIDATES.

    episode_id/turn_id arrive as arguments, carried down from the caller's
    agent_context. They used to be read from $ARTERIES_EPISODE_ID alone, which
    only ever worked for in-process callers: capillaries also runs as a
    long-lived uvicorn and MCP server, and an HTTP client cannot set an
    environment variable inside that process. The result was 2 of 4 482 rows
    carrying an episode_id and zero of them joining to arteries.rewards.

    The env vars remain as a fallback so in-process callers that predate the
    argument keep working.

    db_config is accepted for caller compatibility and ignored.

    Best-effort: never raises. Any failure -> silently drop.
    """
    try:
        episode_id = episode_id or os.environ.get("ARTERIES_EPISODE_ID")
        turn_id = turn_id or os.environ.get("ARTERIES_TURN_ID")

        capped = [
            {"id": c.get("id"), "score": c.get("score")}
            for c in (candidates or [])[:MAX_CANDIDATES]
        ]

        ids = {k: v for k, v in (("episode_id", episode_id), ("turn_id", turn_id)) if v is not None}
        spine.emit(
            "retrieval.served",
            envelope_episode_id=episode_id,
            served_kind=served_kind,
            served_id=served_id,
            candidates=capped,
            query_chars=len(query),
            query_artifact=pulse_emit.artifact(query.encode(), vascular_paths.journal_dir()),
            **ids,
        )
    except Exception:
        pass  # observability must never take down retrieval
