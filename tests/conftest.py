"""Skip `db` tests when Postgres isn't reachable, so a fresh clone runs green.

The marker already says these need a live database; without this hook a machine
with no Postgres reports ~80 connection errors instead of 80 skips.

DB tests run against `capillaries_test`, never the live `capillaries` database.
DB_NAME defaults to capillaries_test below, before anything loads
capillaries.config.paths; load_dotenv never overrides a set variable, so this
beats .env and ~/.vascular/secrets/capillaries/env. A DB_NAME exported in the
shell still wins, and if it says `capillaries` every db test is skipped.

One-time setup of the test database:

    createdb capillaries_test
    sudo -u postgres psql -d capillaries_test -c 'CREATE EXTENSION vector'   # pgvector 0.7+
    DB_NAME=capillaries_test python scripts/setup_db.py

`corpus` tests also need the real prompts; they skip while the table is empty.
Copy the data (not the schema) of capillaries' own schemas into the one setup
built. The arteries schema shares the live database, and the archive tables'
read-only trigger would reject their rows:

    pg_dump --data-only --schema=public --schema=skills \
        --exclude-table='serving_log*' --exclude-table='batch_processing_log*' \
        capillaries | psql capillaries_test
"""
import os

os.environ.setdefault("DB_NAME", "capillaries_test")

import pytest  # noqa: E402

LIVE_DB = "capillaries"


def _db_reachable() -> bool:
    try:
        import psycopg2
        from capillaries.config.paths import DB_CONFIG
        psycopg2.connect(**DB_CONFIG, connect_timeout=2).close()
        return True
    except Exception:
        return False


def _corpus_loaded() -> bool:
    try:
        import psycopg2
        from capillaries.config.paths import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG, connect_timeout=2)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM prompts)")
                return bool(cur.fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    db_items = [i for i in items if "db" in i.keywords]
    if not db_items:
        return
    if os.environ.get("DB_NAME") == LIVE_DB:
        skip = pytest.mark.skip(
            reason=f"DB_NAME={LIVE_DB} is the live database; "
            "db tests run only against capillaries_test"
        )
        for item in db_items:
            item.add_marker(skip)
        return
    if _db_reachable():
        corpus_items = [i for i in items if "corpus" in i.keywords]
        if corpus_items and not _corpus_loaded():
            skip = pytest.mark.skip(
                reason="prompts table in capillaries_test is empty; "
                "load the corpus first (see the pg_dump --data-only command in tests/conftest.py)"
            )
            for item in corpus_items:
                item.add_marker(skip)
        return
    skip = pytest.mark.skip(reason="Postgres unreachable (see DB_* in .env.example)")
    for item in db_items:
        item.add_marker(skip)
