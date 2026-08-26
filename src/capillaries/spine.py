"""Capillaries' emitter onto the event spine (heart/SPINE.md). No shared
library by design — mirrors heart/events.py's emit() in ~15 lines of stdlib.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path


def emit(kind: str, **payload) -> None:
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        event = {"ts": now.isoformat(), "source": "capillaries", "kind": kind}
        if payload:
            event["payload"] = payload
        d = Path(os.environ.get("EVENT_JOURNAL_DIR", str(Path.home() / ".local" / "share" / "heart" / "events")))
        d.mkdir(parents=True, exist_ok=True)
        with open(d / now.strftime("%Y%m%d.ndjson"), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass  # observability must never take down the observed
