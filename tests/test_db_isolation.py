"""conftest keeps db tests off the live `capillaries` database."""
import importlib
import os

from tests import conftest


class FakeItem:
    def __init__(self, keywords):
        self.keywords = keywords
        self.markers = []

    def add_marker(self, marker):
        self.markers.append(marker)


def _no_connect():
    raise AssertionError("_db_reachable must not be called")


def test_conftest_defaults_db_name(monkeypatch):
    assert os.environ["DB_NAME"] == "capillaries_test"
    monkeypatch.delenv("DB_NAME", raising=False)
    importlib.reload(conftest)
    assert os.environ["DB_NAME"] == "capillaries_test"


def test_guard_skips_db_items_on_live_db(monkeypatch):
    monkeypatch.setenv("DB_NAME", "capillaries")
    monkeypatch.setattr(conftest, "_db_reachable", _no_connect)
    db_item, plain_item = FakeItem({"db": True}), FakeItem({"other": True})
    conftest.pytest_collection_modifyitems(None, [db_item, plain_item])
    assert len(db_item.markers) == 1
    marker = db_item.markers[0]
    assert marker.name == "skip"
    assert "live database" in marker.kwargs["reason"]
    assert plain_item.markers == []


def test_guard_inactive_for_test_db(monkeypatch):
    monkeypatch.setenv("DB_NAME", "capillaries_test")
    monkeypatch.setattr(conftest, "_db_reachable", lambda: True)
    db_item, plain_item = FakeItem({"db": True}), FakeItem({"other": True})
    conftest.pytest_collection_modifyitems(None, [db_item, plain_item])
    assert db_item.markers == []
    assert plain_item.markers == []


def test_conftest_keeps_exported_db_name(monkeypatch):
    monkeypatch.setenv("DB_NAME", "some_other_db")
    importlib.reload(conftest)
    assert os.environ["DB_NAME"] == "some_other_db"


def test_live_db_reason_names_capillaries(monkeypatch):
    monkeypatch.setenv("DB_NAME", "capillaries")
    monkeypatch.setattr(conftest, "_db_reachable", _no_connect)
    items = [FakeItem({"db": True}), FakeItem({"db": True})]
    conftest.pytest_collection_modifyitems(None, items)
    for item in items:
        (marker,) = item.markers
        assert "DB_NAME=capillaries " in marker.kwargs["reason"]


def test_unreachable_skip_unchanged_for_other_db(monkeypatch):
    monkeypatch.setenv("DB_NAME", "capillaries_test")
    monkeypatch.setattr(conftest, "_db_reachable", lambda: False)
    db_item, plain_item = FakeItem({"db": True}), FakeItem({"other": True})
    conftest.pytest_collection_modifyitems(None, [db_item, plain_item])
    (marker,) = db_item.markers
    assert marker.name == "skip"
    assert marker.kwargs["reason"] == "Postgres unreachable (see DB_* in .env.example)"
    assert plain_item.markers == []


def test_no_db_items_never_connects(monkeypatch):
    monkeypatch.setattr(conftest, "_db_reachable", _no_connect)
    plain_item = FakeItem({"other": True})
    conftest.pytest_collection_modifyitems(None, [plain_item])
    assert plain_item.markers == []
