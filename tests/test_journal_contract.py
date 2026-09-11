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

capillaries resolves the path inline inside spine.emit, so this asserts the
observable behaviour: where a written event lands.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from capillaries import spine

JOURNAL_ENV = "EVENT_JOURNAL_DIR"
JOURNAL_DEFAULT = Path.home() / ".local" / "share" / "heart" / "events"


def test_spine_reads_the_contract_variable():
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {JOURNAL_ENV: tmp}):
            spine.emit("contract.check", probe=True)
        written = list(Path(tmp).glob("*.ndjson"))
        assert len(written) == 1, "the event must land where the variable points"
        event = json.loads(written[0].read_text().splitlines()[-1])
    assert event["source"] == "capillaries"
    assert event["kind"] == "contract.check"


def test_the_default_matches_the_other_repos():
    """Behavioural, not a source grep: clear the variable, point HOME at a temp
    directory, and check where the event actually lands. spine.py resolves the
    path inline, so the only honest assertion is on the file it writes."""
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if k != JOURNAL_ENV}
        env["HOME"] = home
        with patch.dict(os.environ, env, clear=True), \
                patch.object(Path, "home", staticmethod(lambda: Path(home))):
            spine.emit("contract.check")

        landed = list((Path(home) / ".local" / "share" / "heart" / "events").glob("*.ndjson"))

    assert landed, "the default path must match arteries and heart"
