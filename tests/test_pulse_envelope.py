"""Every line spine.emit writes fits pulse's envelope (tests/pulse_envelope.json)."""
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


def _lines(journal: Path) -> list:
    return [json.loads(l) for f in sorted(journal.glob("*.ndjson"))
            for l in f.read_text().splitlines() if l.strip()]


def test_every_line_fits_the_envelope(journal):
    spine.emit("probe.check", a=1, b="x")
    spine.emit("probe.bare")
    lines = _lines(journal)
    assert len(lines) == 3
    for ev in lines:
        assert isinstance(ev, dict)
        for k, v in ev.items():
            assert k in FIELDS, k
            assert _type_ok(FIELDS[k], v), (k, v)
        assert set(CONTRACT["required"]) <= ev.keys()
        assert {"id", "schema_version", "emitter_seq", "context_id"} <= ev.keys()
        assert ev["schema_version"] == 1


def test_fields_set_before_still_set(journal):
    spine.emit("probe.check", a=1, b="x")
    spine.emit("probe.bare")
    by_kind = {e["kind"]: e for e in _lines(journal)}
    for kind in ("probe.check", "probe.bare"):
        ev = by_kind[kind]
        assert ev["source"] == "capillaries"
        assert ev["ts"].endswith("+00:00")
    assert by_kind["probe.check"]["payload"] == {"a": 1, "b": "x"}
    assert "a" not in by_kind["probe.check"]
    assert "payload" not in by_kind["probe.bare"]


def test_context_started_once_across_processes(journal, monkeypatch, tmp_path):
    spine.emit("probe.one")
    spine.emit("probe.two")
    monkeypatch.setattr(pulse_emit, "_announced", set())  # a new process
    spine.emit("probe.three")
    lines = _lines(journal)
    started = [e for e in lines if e["kind"] == "context.started"]
    assert len(started) == 1
    cid = started[0]["context_id"]
    assert {e["context_id"] for e in lines} == {cid}
    state = tmp_path / "home" / "state" / "pulse" / "contexts"
    # one marker, keyed by context and journal (PULSE-B03)
    assert [p.name.split("-")[0] for p in state.iterdir()] == [cid]


def test_never_raises_when_append_fails(journal, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk gone")
    monkeypatch.setattr(pulse_emit, "append", boom)
    assert spine.emit("probe.check", a=1) is None


def test_never_raises_when_journal_is_a_file(journal, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setenv("EVENT_JOURNAL_DIR", str(blocker))
    assert spine.emit("probe.check") is None


def test_never_raises_when_paths_fail(journal, monkeypatch):
    from capillaries import vascular_paths

    def boom(*a, **k):
        raise RuntimeError("no home")
    monkeypatch.setattr(vascular_paths, "journal_dir", boom)
    assert spine.emit("probe.check") is None
