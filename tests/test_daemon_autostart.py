"""The autostarted daemon must not belong to the hook that noticed it missing.

A hook that misses the daemon scores locally, runs past its timeout, and is
killed -- and a daemon spawned as its child went with it, so every prompt
missed again. Measured: 12 consecutive daemons shut down before serving one
request. Handing the start to systemd breaks that loop.
"""
from __future__ import annotations

import subprocess

from capillaries import daemon


def _miss(monkeypatch, tmp_path):
    monkeypatch.setenv("VASCULAR_HOME", str(tmp_path))
    monkeypatch.delenv("CAPILLARIES_AUTOSTART", raising=False)
    monkeypatch.delenv("CAPILLARIES_NO_REMOTE", raising=False)
    monkeypatch.setattr(daemon, "is_up", lambda: False)
    spawned = []
    monkeypatch.setattr(daemon.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    return spawned


def test_a_missing_daemon_is_started_by_systemd_when_the_unit_exists(monkeypatch, tmp_path):
    spawned = _miss(monkeypatch, tmp_path)
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(daemon.subprocess, "run", run)
    assert daemon.ensure() is True
    assert calls == [["systemctl", "--user", "start", "--no-block", daemon.UNIT]]
    assert spawned == [], "no child of the hook to die at its timeout"


def test_without_the_unit_it_still_starts_one_itself(monkeypatch, tmp_path):
    spawned = _miss(monkeypatch, tmp_path)
    monkeypatch.setattr(daemon.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 5))
    assert daemon.ensure() is True
    assert len(spawned) == 1
