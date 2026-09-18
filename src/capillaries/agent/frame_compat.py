"""Reading arteries' MemoryFrame across a contract rename.

arteries renamed the frame's third tier: `MemoryFrame.evergreen` became
`.scope` and `ground_truth_insights` became `sibling_insights`. The class was
briefly `ScopeMemory` too; it is `EvergreenMemory` again, because evergreen is
back as the knowledge-graph tier. Detect the shape by its fields, never by the
class name -- the name has now moved twice and the fields have moved once.

capillaries consumes that contract from a sibling checkout. arteries is not on
PyPI, so there is no version to pin and no resolver to complain: whichever
branch happens to be installed is the contract. Both shapes therefore have to
work, or capillaries breaks whenever arteries is on the other side of the
rename -- which is exactly what happened, and stayed hidden because no test
exercised the memory-context path with a real frame.

Delete this module when every arteries checkout in use has the new fields:

    python -c "from arteries.memory_types import MemoryFrame; MemoryFrame().scope.sibling_insights"
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
    """The third tier's class, under whichever name this checkout uses."""
    # lazy: arteries is a sibling checkout, not on PyPI; capillaries installs without it
    from arteries import memory_types

    return getattr(memory_types, "EvergreenMemory", None) or memory_types.ScopeMemory


def build_scope_tier(raw: dict) -> Any:
    """Construct the third tier from posted JSON, under either shape."""
    cls = scope_memory_class()
    # lazy: same reason as scope_memory_class -- arteries stays an optional sibling
    from arteries.memory_types import Insight

    insights = [Insight(**i) for i in
                (raw.get("sibling_insights") or raw.get("ground_truth_insights") or [])]
    common = {
        "user_intent": raw.get("user_intent", []),
        "recurring_domains": raw.get("recurring_domains", []),
        "last_retrieval_ts": raw.get("last_retrieval_ts"),
        "retrieval_confidence": raw.get("retrieval_confidence"),
    }
    # By field, not by class name: the class has been called both things.
    field = ("sibling_insights" if "sibling_insights" in cls.__dataclass_fields__
             else "ground_truth_insights")
    return cls(**common, **{field: insights})


def frame_kwarg_name() -> str:
    """Whether MemoryFrame takes `scope=` or `evergreen=`."""
    # lazy: same reason as scope_memory_class -- arteries stays an optional sibling
    from arteries.memory_types import MemoryFrame

    return "scope" if "scope" in MemoryFrame.__dataclass_fields__ else "evergreen"
