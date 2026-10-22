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
        return
    skip = pytest.mark.skip(reason="Postgres unreachable (see DB_* in .env.example)")
    for item in db_items:
        item.add_marker(skip)
