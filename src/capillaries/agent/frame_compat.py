"""Reading arteries' MemoryFrame across a contract rename.

arteries renamed the frame's third tier: `MemoryFrame.evergreen` became
`.scope`, `EvergreenMemory` became `ScopeMemory`, and `ground_truth_insights`
became `sibling_insights`. The tier never described permanence -- it describes
how far out context reaches -- and with scope groups it holds sibling-repo
memory.

capillaries consumes that contract from a sibling checkout. arteries is not on
PyPI, so there is no version to pin and no resolver to complain: whichever
branch happens to be installed is the contract. Both shapes therefore have to
work, or capillaries breaks whenever arteries is on the other side of the
rename -- which is exactly what happened, and stayed hidden because no test
exercised the memory-context path with a real frame.

Delete this module when every arteries checkout in use exposes ScopeMemory:

    python -c "from arteries.memory_types import ScopeMemory"
"""

from __future__ import annotations

from typing import Any


def scope_tier(context: Any) -> Any | None:
    """The frame's third tier under either name."""
    if context is None:
        return None
    tier = getattr(context, "scope", None)
    if tier is None:
        tier = getattr(context, "evergreen", None)
    return tier


def sibling_insights(context: Any) -> list:
    """Insights from the wider scope, under either field name."""
    tier = scope_tier(context)
    if tier is None:
        return []
    return list(getattr(tier, "sibling_insights", None)
                or getattr(tier, "ground_truth_insights", None)
                or [])


def user_intent(context: Any) -> list[str]:
    tier = scope_tier(context)
    return list(getattr(tier, "user_intent", None) or []) if tier else []


def recurring_domains(context: Any) -> list[str]:
    tier = scope_tier(context)
    return list(getattr(tier, "recurring_domains", None) or []) if tier else []


def scope_memory_class():
    """ScopeMemory where arteries has it, EvergreenMemory where it does not."""
    from arteries import memory_types

    return getattr(memory_types, "ScopeMemory", None) or memory_types.EvergreenMemory


def build_scope_tier(raw: dict) -> Any:
    """Construct the third tier from posted JSON, under either shape."""
    cls = scope_memory_class()
    from arteries.memory_types import Insight

    insights = [Insight(**i) for i in
                (raw.get("sibling_insights") or raw.get("ground_truth_insights") or [])]
    common = {
        "user_intent": raw.get("user_intent", []),
        "recurring_domains": raw.get("recurring_domains", []),
        "last_retrieval_ts": raw.get("last_retrieval_ts"),
        "retrieval_confidence": raw.get("retrieval_confidence"),
    }
    field = "sibling_insights" if cls.__name__ == "ScopeMemory" else "ground_truth_insights"
    return cls(**common, **{field: insights})


def frame_kwarg_name() -> str:
    """Whether MemoryFrame takes `scope=` or `evergreen=`."""
    from arteries.memory_types import MemoryFrame

    return "scope" if "scope" in MemoryFrame.__dataclass_fields__ else "evergreen"
