"""serving_log and batch_processing_log are read-only archives (pulse P5)."""
import inspect
from unittest import mock

import psycopg2
import pytest

import capillaries.db.setup
from capillaries.config.paths import DB_CONFIG
from capillaries.optimize.serving import ARCHIVE_SQL, apply_ddl


def test_archive_sql_installs_read_only_trigger():
    sql = "\n".join(ARCHIVE_SQL)
    assert "CREATE OR REPLACE FUNCTION archive_read_only" in sql
    assert "DROP TRIGGER IF EXISTS read_only_archive" in sql
    assert "BEFORE INSERT OR UPDATE OR DELETE" in sql
    assert "% is a read-only archive (pulse P5); write an event instead" in sql


def test_batch_processing_log_trigger_is_guarded():
    guarded = [s for s in ARCHIVE_SQL if "batch_processing_log" in s]
    assert len(guarded) == 1
    assert "to_regclass('batch_processing_log') IS NOT NULL" in guarded[0]
    assert "ON batch_processing_log FOR EACH ROW EXECUTE FUNCTION archive_read_only()" in guarded[0]


def test_apply_ddl_runs_archive_sql_last():
    with mock.patch("capillaries.optimize.serving.psycopg2.connect") as connect:
        apply_ddl({"dbname": "x"})
    cur = connect.return_value.cursor.return_value
    executed = [c.args[0] for c in cur.execute.call_args_list]
    assert executed[-len(ARCHIVE_SQL):] == ARCHIVE_SQL
    assert "CREATE TABLE" in executed[0]
    connect.return_value.commit.assert_called_once()


def test_setup_no_longer_creates_batch_processing_log():
    assert "CREATE TABLE IF NOT EXISTS batch_processing_log" not in inspect.getsource(capillaries.db.setup)


@pytest.mark.db
def test_serving_log_rejects_writes_but_allows_reads():
    apply_ddl(DB_CONFIG)
    apply_ddl(DB_CONFIG)
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM serving_log")
        cur.fetchone()
        with pytest.raises(psycopg2.Error, match="serving_log is a read-only archive"):
            cur.execute("INSERT INTO serving_log (query, served_kind) VALUES ('q', 'k')")
        conn.rollback()
    finally:
        conn.close()
