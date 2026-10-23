"""setup_db.py must create prompt_chunks, and chunk.apply_ddl must be safe to rerun.

No database: psycopg2.connect and every builder are patched out, so this runs
in the sandbox verifier without Postgres.
"""
import importlib.util
import pathlib
import re
from unittest.mock import MagicMock

from capillaries import chunk
from capillaries.config import EMBED_DIM

SETUP_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "setup_db.py"

BUILDERS = [
    "create_database_schema",
    "create_skills_schema",
    "create_skills_table",
    "create_skill_runs_table",
    "create_skill_variants_table",
    "create_skill_sessions_table",
    "create_agent_feedback_table",
    "add_skills_columns",
    "create_skills_indexes",
    "create_materialized_views",
    "mark_low_confidence_prompts",
]


def _load_setup_db():
    spec = importlib.util.spec_from_file_location("setup_db_under_test", SETUP_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_setup_schemas_applies_chunk_ddl_after_prompts(monkeypatch):
    mod = _load_setup_db()
    conn = MagicMock()
    monkeypatch.setattr(mod.psycopg2, "connect", lambda **kw: conn)

    calls: list[tuple[str, tuple]] = []
    for name in BUILDERS + ["apply_chunk_ddl"]:
        monkeypatch.setattr(mod, name, lambda *a, _n=name: calls.append((_n, a)))
    conn.commit.side_effect = lambda: calls.append(("commit", ()))

    mod.setup_schemas()

    names = [n for n, _ in calls]
    chunk_calls = [a for n, a in calls if n == "apply_chunk_ddl"]
    assert chunk_calls == [(conn.cursor.return_value,)]
    assert names.index("create_database_schema") < names.index("apply_chunk_ddl")
    # Same transaction as the prompts schema: committed by that block's commit.
    assert names.index("apply_chunk_ddl") < names.index("commit")


class _Stop(Exception):
    pass


def _run_backfill(monkeypatch, dry):
    conn = MagicMock()
    monkeypatch.setattr(chunk.psycopg2, "connect", lambda **kw: conn)
    calls: list[tuple[str, tuple]] = []
    monkeypatch.setattr(chunk, "apply_ddl", lambda *a: calls.append(("apply_ddl", a)))
    conn.commit.side_effect = lambda: calls.append(("commit", ()))

    def execute(sql, *a):  # first query after the DDL block: stop there
        raise _Stop

    conn.cursor.return_value.execute.side_effect = execute
    try:
        chunk.backfill(dry=dry, db_config={})
    except _Stop:
        pass
    return conn, calls


def test_backfill_applies_ddl_then_commits(monkeypatch):
    conn, calls = _run_backfill(monkeypatch, dry=False)
    assert calls == [("apply_ddl", (conn.cursor.return_value,)), ("commit", ())]


def test_backfill_dry_run_skips_ddl(monkeypatch):
    _, calls = _run_backfill(monkeypatch, dry=True)
    assert calls == []


def test_apply_ddl_is_idempotent_and_skips_hnsw():
    cur = MagicMock()
    chunk.apply_ddl(cur)
    executed = [c.args[0] for c in cur.execute.call_args_list]
    joined = "\n".join(executed)

    assert "CREATE TABLE IF NOT EXISTS prompt_chunks" in joined
    assert f"HALFVEC({EMBED_DIM})" in joined
    assert "EMBED_DIM" not in joined
    assert chunk.SYNC_STATUS_SQL in executed
    for sql in chunk.INDEXES[:-1]:
        assert sql in executed
    assert chunk.INDEXES[-1] not in executed
    assert "hnsw" not in joined.lower()
    cur.connection.commit.assert_not_called()

    # CREATE TRIGGER has no IF NOT EXISTS before PG14; a preceding DROP ... IF
    # EXISTS of the same trigger is what makes it rerunnable.
    for m in re.finditer(r"CREATE\b[^\n;(]*", joined):
        stmt = m.group(0)
        trig = re.match(r"CREATE TRIGGER (\w+)", stmt)
        if trig:
            assert f"DROP TRIGGER IF EXISTS {trig.group(1)}" in joined[: m.start()], stmt
        else:
            assert "IF NOT EXISTS" in stmt or "OR REPLACE" in stmt, stmt
