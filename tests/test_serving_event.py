"""log_serving emits retrieval.served onto the spine and never touches Postgres."""
import json
from pathlib import Path

import pytest

from capillaries import pulse_emit
from capillaries.optimize import serving


@pytest.fixture
def journal(monkeypatch, tmp_path):
    monkeypatch.setenv("VASCULAR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EVENT_JOURNAL_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ARTERIES_EPISODE_ID", raising=False)
    monkeypatch.delenv("ARTERIES_TURN_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pulse_emit, "_announced", set())

    def no_db(*a, **k):
        raise AssertionError("log_serving must not connect to Postgres")
    monkeypatch.setattr(serving.psycopg2, "connect", no_db)
    return tmp_path / "events"


def _served(journal: Path) -> list:
    return [e for f in sorted(journal.glob("*.ndjson"))
            for l in f.read_text().splitlines() if l.strip()
            for e in [json.loads(l)] if e["kind"] == "retrieval.served"]


def test_one_call_one_event(journal):
    cands = [{"id": f"p{i}", "score": 1 - i / 100, "extra": 1} for i in range(15)]
    serving.log_serving("find me a prompt", "single_prompt", "p0", cands,
                        episode_id="ep-1", turn_id="t-2")
    [ev] = _served(journal)
    p = ev["payload"]
    assert p["served_kind"] == "single_prompt"
    assert p["served_id"] == "p0"
    assert p["candidates"] == [{"id": c["id"], "score": c["score"]} for c in cands[:10]]
    assert p["query_chars"] == len("find me a prompt")
    assert p["episode_id"] == "ep-1"
    assert p["turn_id"] == "t-2"
    assert ev["episode_id"] == "ep-1"


def test_query_lands_in_artifact(journal):
    query = "long query é " * 1154  # ~15000 chars
    serving.log_serving(query, "none", None, [])
    [ev] = _served(journal)
    assert ev["payload"]["query_chars"] == len(query)
    blob = journal / "artifacts" / ev["payload"]["query_artifact"]
    assert blob.read_bytes() == query.encode()


def test_ids_absent_without_args_or_env(journal, monkeypatch):
    serving.log_serving("q", "none", None, [])
    [ev] = _served(journal)
    assert "episode_id" not in ev["payload"]
    assert "turn_id" not in ev["payload"]

    monkeypatch.setenv("ARTERIES_EPISODE_ID", "from-env")
    serving.log_serving("q", "none", None, [])
    assert _served(journal)[1]["payload"]["episode_id"] == "from-env"


def test_never_raises_when_journal_is_a_file(journal, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setenv("EVENT_JOURNAL_DIR", str(blocker))
    assert serving.log_serving("q", "none", None, [{"id": "x", "score": 0.1}]) is None
