"""The `corpus` skip in conftest.py works without Postgres: DB probes are stubbed."""
import importlib.util
import pathlib

import pytest

TESTS = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_conftest_under_test", TESTS / "conftest.py")
conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conftest)

EMPTY_REASON = "pg_dump capillaries | psql capillaries_test"


class FakeItem:
    def __init__(self, *keywords):
        self.keywords = set(keywords)
        self.markers = []

    def add_marker(self, marker):
        self.markers.append(marker)


def _reasons(item):
    return [m.kwargs["reason"] for m in item.markers if m.name == "skip"]


@pytest.fixture
def stubs(monkeypatch):
    monkeypatch.setenv("DB_NAME", "capillaries_test")
    calls = []

    def setup(reachable, loaded):
        monkeypatch.setattr(conftest, "_db_reachable", lambda: reachable)
        monkeypatch.setattr(conftest, "_corpus_loaded", lambda: calls.append(1) or loaded)
        return calls
    return setup


def test_empty_corpus_skips_only_corpus_items(stubs):
    stubs(True, False)
    corpus, db_only = FakeItem("db", "corpus"), FakeItem("db")
    conftest.pytest_collection_modifyitems(None, [corpus, db_only])
    assert any(EMPTY_REASON in r for r in _reasons(corpus))
    assert db_only.markers == []


def test_loaded_corpus_skips_nothing(stubs):
    stubs(True, True)
    items = [FakeItem("db", "corpus"), FakeItem("db")]
    conftest.pytest_collection_modifyitems(None, items)
    assert all(i.markers == [] for i in items)


def test_unreachable_skips_once_without_corpus_query(stubs, monkeypatch):
    monkeypatch.delenv("DB_NAME")
    calls = stubs(False, False)
    corpus = FakeItem("db", "corpus")
    conftest.pytest_collection_modifyitems(None, [corpus])
    reasons = _reasons(corpus)
    assert len(reasons) == 1 and "Postgres unreachable" in reasons[0]
    assert calls == []


def test_corpus_query_runs_once_per_session(stubs):
    calls = stubs(True, False)
    conftest.pytest_collection_modifyitems(None, [FakeItem("db", "corpus") for _ in range(3)])
    assert len(calls) == 1


@pytest.mark.parametrize("name", [
    "test_search.py", "test_gate.py", "test_skill_parity.py", "test_active_only.py",
])
def test_corpus_dependent_files_are_marked(name):
    assert "pytest.mark.corpus" in (TESTS / name).read_text()


def test_no_corpus_items_means_no_corpus_query(stubs):
    calls = stubs(True, False)
    db_only = FakeItem("db")
    conftest.pytest_collection_modifyitems(None, [db_only])
    assert calls == [] and db_only.markers == []


def test_live_db_skips_once_without_probing(stubs, monkeypatch):
    calls = stubs(True, False)
    monkeypatch.setenv("DB_NAME", "capillaries")
    corpus = FakeItem("db", "corpus")
    conftest.pytest_collection_modifyitems(None, [corpus])
    reasons = _reasons(corpus)
    assert len(reasons) == 1 and "live database" in reasons[0]
    assert calls == []


def test_corpus_loaded_is_false_when_connect_fails(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")

    def boom(**kw):
        raise psycopg2.OperationalError("no server")
    monkeypatch.setattr(psycopg2, "connect", boom)
    assert conftest._corpus_loaded() is False
