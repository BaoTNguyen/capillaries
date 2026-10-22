"""Capillaries' emitter onto the event spine (heart/SPINE.md). Writes through
the vendored pulse_emit, so every line carries pulse's full envelope; caller
kwargs go into `payload` and nowhere else; `envelope_episode_id` is the one
way to set the envelope's episode_id.
"""
from __future__ import annotations

from capillaries import pulse_emit, vascular_paths


def emit(kind: str, *, envelope_episode_id: str | None = None, **payload) -> None:
    try:
        envelope = {} if envelope_episode_id is None else {"episode_id": envelope_episode_id}
        pulse_emit.emit(
            "capillaries", kind, vascular_paths.journal_dir(),
            vascular_paths.path("state", "pulse", "contexts"),
            payload=payload or None, **envelope,
        )
    except Exception:
        pass  # observability must never take down the observed
