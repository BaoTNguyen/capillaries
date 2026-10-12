"""Capillaries' emitter onto the event spine (heart/SPINE.md). Writes through
the vendored pulse_emit, so every line carries pulse's full envelope; caller
kwargs go into `payload` and nowhere else.
"""
from __future__ import annotations

from capillaries import pulse_emit, vascular_paths


def emit(kind: str, **payload) -> None:
    try:
        pulse_emit.emit(
            "capillaries", kind, vascular_paths.journal_dir(),
            vascular_paths.path("state", "pulse", "contexts"),
            payload=payload or None,
        )
    except Exception:
        pass  # observability must never take down the observed
