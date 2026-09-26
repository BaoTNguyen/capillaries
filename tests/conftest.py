"""Skip `db` tests when Postgres isn't reachable, so a fresh clone runs green.

The marker already says these need a live database; without this hook a machine
with no Postgres reports ~80 connection errors instead of 80 skips.
"""
import pytest


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
    if not db_items or _db_reachable():
        return
    skip = pytest.mark.skip(reason="Postgres unreachable (see DB_* in .env.example)")
    for item in db_items:
        item.add_marker(skip)
