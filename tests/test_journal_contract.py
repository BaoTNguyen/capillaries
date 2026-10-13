"""The journal contract, asserted independently in each repo that writes to it.

arteries, heart and capillaries each resolve the journal path themselves --
none of them depends on the others, so none can import a shared constant. The
duplication is deliberate; drift is what is dangerous. A rename this session
proved it: with plexus reading the old variable while arteries and heart wrote
the new one, events went to two directories and the only symptom was a test
failing with "spine events not written".

These constants ARE the contract. Change one repo and its own test fails, at the
point of the change rather than in production. Change all of them together and
the rename is complete by construction.

capillaries resolves the path at emit time via vascular_paths, so this asserts the
observable behaviour: where a written event lands.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch

from capillaries import spine, vascular_paths

JOURNAL_ENV = "EVENT_JOURNAL_DIR"
JOURNAL_DEFAULT = Path.home() / ".vascular" / "spool" / "events"


def test_spine_reads_the_contract_variable(monkeypatch, tmp_path):
    tmp = tmp_path / "events"
    monkeypatch.chdir(tmp_path)
    with patch.dict(os.environ, {JOURNAL_ENV: str(tmp), "VASCULAR_HOME": str(tmp_path / "home")}):
        spine.emit("contract.check", probe=True)
    written = list(tmp.glob("*.ndjson"))
    assert len(written) == 1, "the event must land where the variable points"
    lines = [json.loads(l) for l in written[0].read_text().splitlines()]
    event = next(e for e in lines if e["kind"] == "contract.check")
    assert event["source"] == "capillaries"
    assert event["kind"] == "contract.check"


def test_the_default_matches_the_other_repos(monkeypatch, tmp_path):
    """Clear the variables, point HOME at a temp directory, and check where the
    journal resolves -- resolved at call time, so nothing is cached. Then emit
    with both variables pinned to that resolved path (an emitting test never
    leaves them unset) and check the event actually lands there."""
    home = tmp_path / "user"
    monkeypatch.chdir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k not in (JOURNAL_ENV, "VASCULAR_HOME")}
    env["HOME"] = str(home)
    with patch.dict(os.environ, env, clear=True), \
            patch.object(Path, "home", staticmethod(lambda: home)):
        resolved = vascular_paths.journal_dir()
        vascular_home = vascular_paths.home()
    assert resolved == home / ".vascular" / "spool" / "events", \
        "the default path must match arteries and heart"

    with patch.dict(os.environ, {JOURNAL_ENV: str(resolved), "VASCULAR_HOME": str(vascular_home)}):
        spine.emit("contract.check")
    landed = list(resolved.glob("*.ndjson"))

    assert landed, "the default path must match arteries and heart"
