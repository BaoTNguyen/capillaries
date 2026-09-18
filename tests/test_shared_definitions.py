"""The duplicated definitions that were consolidated, and the drift they hid.

Each of these was written out by hand in two or three places before. The point
of the test is not that the helper works -- it is that nothing goes back to
spelling the mapping out locally.
"""
import pathlib
import re

from capillaries.config.paths import outcome_score_sql
from capillaries.search.retriever import _row_metadata

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "capillaries"


def test_outcome_scores_are_defined_once():
    body = outcome_score_sql()
    assert "'success' THEN 1.0" in body
    assert "'partial' THEN 0.5" in body
    assert "'failure' THEN 0.0" in body
    assert body.endswith("ELSE NULL END")
    # the Bayesian prior counts an unknown outcome against the prompt
    assert outcome_score_sql("0.0").endswith("ELSE 0.0 END")

    handwritten = [
        p for p in SRC.rglob("*.py")
        if p.name != "paths.py" and "WHEN outcome = 'success'" in p.read_text()
    ]
    assert handwritten == [], f"outcome scoring respelled in {handwritten}"


def test_row_metadata_is_defined_once():
    row = {"summary": None, "intent": None, "domain": ["x"], "status": "active"}
    meta = _row_metadata(row)
    assert meta == {"summary": "", "intent": [], "task_type": [], "domain": ["x"],
                    "status": "active", "notes": None}

    handwritten = [
        p for p in SRC.rglob("*.py")
        if p.name != "retriever.py" and re.search(r'"summary": row\.get', p.read_text())
    ]
    assert handwritten == [], f"row metadata respelled in {handwritten}"
