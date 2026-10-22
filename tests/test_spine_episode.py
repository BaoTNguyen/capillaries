"""spine.emit's envelope_episode_id lands in the envelope; payload stays payload."""
import json
from pathlib import Path

import pytest

from capillaries import pulse_emit, spine

CONTRACT = json.loads((Path(__file__).parent / "pulse_envelope.json").read_text())
FIELDS = {**CONTRACT["required"], **CONTRACT["optional"]}


def _type_ok(t: str, v) -> bool:
    if t == "integer":
        return type(v) is int and v >= 0
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
    if t == "object":
        return isinstance(v, dict)
    return isinstance(v, str)


@pytest.fixture
def journal(monkeypatch, tmp_path):
    monkeypatch.setenv("VASCULAR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EVENT_JOURNAL_DIR", str(tmp_path / "events"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pulse_emit, "_announced", set())
    return tmp_path / "events"


def _by_kind(journal: Path) -> dict:
    return {e["kind"]: e for f in sorted(journal.glob("*.ndjson"))
            for e in map(json.loads, f.read_text().splitlines())}


def test_envelope_episode_id_set(journal):
    spine.emit("probe.ep", envelope_episode_id="ep-1", episode_id="ep-1", x=1)
    ev = _by_kind(journal)["probe.ep"]
    assert ev["episode_id"] == "ep-1"
    assert ev["payload"] == {"episode_id": "ep-1", "x": 1}


def test_no_kwarg_no_envelope_episode_id(journal):
    spine.emit("probe.plain", episode_id="ep-2")
    ev = _by_kind(journal)["probe.plain"]
    assert "episode_id" not in ev
    assert ev["payload"] == {"episode_id": "ep-2"}


def test_line_fits_the_envelope(journal):
    spine.emit("probe.ep", envelope_episode_id="ep-1", episode_id="ep-1", x=1)
    ev = _by_kind(journal)["probe.ep"]
    for k, v in ev.items():
        assert k in FIELDS, k
        assert _type_ok(FIELDS[k], v), (k, v)
    assert set(CONTRACT["required"]) <= ev.keys()
