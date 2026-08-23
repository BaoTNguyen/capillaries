"""Retrieval serves active prompts only.

One clause builder feeds every retrieval surface, so this asserts on the
clause rather than round-tripping a database: if the literal goes away, or a
caller can override it, this fails.
"""
import pathlib

from capillaries.search.channels import _filter_sql
from capillaries.search.retriever import _build_filter_clause

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_clause_pins_active():
    clause, params = _build_filter_clause({})
    assert "status = 'active'" in clause
    assert params == []


def test_caller_cannot_override_status():
    clause, params = _build_filter_clause({"status": "inactive"})
    assert "status = 'active'" in clause
    assert "inactive" not in clause
    assert "inactive" not in params


def test_other_filters_still_work():
    clause, params = _build_filter_clause({"domain": ["finance"], "modality": "image"})
    assert "status = 'active'" in clause
    assert params == [["finance"], "image"]


def test_channels_inherits_the_same_clause():
    assert _filter_sql({}) == _build_filter_clause({})


def test_every_retrieval_sql_filters_status():
    """Surfaces that read prompt_text outside the clause builder."""
    for path, needle in [
        ("src/capillaries/server.py", "WHERE title = %s AND status = 'active'"),
        ("src/capillaries/skills/recall.py", "AND status = 'active'"),
        ("src/capillaries/agent/execute.py", "AND status = 'active'"),
        ("src/capillaries/agent/gate.py", "AND status = 'active'"),
        ("src/capillaries/search/union.py", "AND status = 'active'"),
    ]:
        assert needle in (ROOT / path).read_text(), path


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
