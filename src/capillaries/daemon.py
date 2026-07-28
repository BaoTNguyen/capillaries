"""Keep a capillaries daemon alive without an init system.

The daemon holds the cross-encoder in memory so that agent hooks — one
short-lived subprocess per prompt, which can never stay warm — borrow it
instead of spending ~4.4s and ~2.9GB loading their own copy.

Rather than register a service, the daemon is started by whoever first needs
it and outlives them. After a reboot, a crash, or an OOM kill, the next hook
that misses brings it straight back. That covers the reboot case without root,
without systemd, and without a unit file that can drift out of sync with where
the code actually lives.

The miss that triggers a start still falls back to local scoring, so the caller
never waits for a cold daemon. It is the *next* call that gets the fast path.

Opt out with CAPILLARIES_AUTOSTART=0.
"""
from __future__ import annotations

import fcntl
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

URL = os.getenv("CAPILLARIES_URL", "http://127.0.0.1:8000")
# a failed start must not turn every hook into a spawn attempt; wait this long
# before trying again so a broken install degrades to "slow" and not "fork bomb"
COOLDOWN_S = float(os.getenv("CAPILLARIES_AUTOSTART_COOLDOWN", "120"))


def state_dir() -> Path:
    base = os.getenv("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    d = Path(base) / "capillaries"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _host_port() -> tuple[str, int]:
    u = urlparse(URL)
    return u.hostname or "127.0.0.1", u.port or 8000


def is_up(timeout: float = 0.2) -> bool:
    """Something is listening. Deliberately a bare TCP connect rather than an
    HTTP health check: this runs on the hot path of every hook."""
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure(wait: float = 0.0) -> bool:
    """Start a daemon if none is listening. Returns True if we spawned one.

    Concurrency-safe: N hooks missing at once contend for a lock file and
    exactly one spawns. The rest return immediately and score locally.
    """
    if os.getenv("CAPILLARIES_AUTOSTART", "1") == "0" or os.getenv("CAPILLARIES_NO_REMOTE"):
        return False
    if is_up():
        return False

    lock_path = state_dir() / "autostart.lock"
    try:
        lock = open(lock_path, "w")
    except OSError:
        return False
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False  # another process is already starting one

        stamp = state_dir() / "last-autostart"
        try:
            if time.time() - stamp.stat().st_mtime < COOLDOWN_S:
                return False
        except OSError:
            pass
        if is_up():  # someone won the race while we waited for the lock
            return False

        host, port = _host_port()
        log = open(state_dir() / "daemon.log", "ab")
        try:
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "capillaries.server:app",
                 "--host", host, "--port", str(port)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                # detach: the hook that started it exits in milliseconds, and
                # the daemon must not die with it or with its process group
                start_new_session=True,
            )
        except (OSError, ValueError):
            return False
        finally:
            log.close()
        stamp.touch()

        deadline = time.time() + wait
        while wait and time.time() < deadline:
            if is_up():
                break
            time.sleep(0.1)
        return True
    finally:
        try:
            fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            lock.close()


def stop() -> bool:
    """Stop the daemon and any half-started ones. Returns True if anything was
    signalled.

    Matching on the process rather than the listening socket is deliberate:
    uvicorn binds its port only after the model finishes loading, so for the
    first ~40s a starting daemon is invisible to is_up() and would survive a
    stop that only looked at listeners.
    """
    killed = False
    out = subprocess.run(["pgrep", "-f", "uvicorn capillaries.server:app"],
                         capture_output=True, text=True).stdout
    for pid in (p for p in out.split() if p.isdigit()):
        try:
            os.kill(int(pid), 15)
            killed = True
        except OSError:
            pass
    return killed


if __name__ == "__main__":  # `python -m capillaries.daemon [start|stop|status]`
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        print("started" if ensure(wait=120) else ("already running" if is_up() else "not started"))
    elif cmd == "stop":
        print("stopped" if stop() else "not running")
    else:
        print(f"{URL}: {'up' if is_up() else 'down'}")
