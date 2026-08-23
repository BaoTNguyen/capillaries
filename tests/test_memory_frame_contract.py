"""The memory-context path, with a real frame.

main shipped broken because nothing exercised it. 166 tests passed while
`find(query, context=frame)` raised AttributeError and `_build_context_frame`
raised ImportError -- the contract with arteries had moved and no test touched
it. These do.

arteries is a sibling checkout, not a pinned dependency, so whichever branch is
installed is the contract. Everything here must hold under both the old
`evergreen` shape and the new `scope` one.
"""

import unittest

from arteries.memory_types import EphemeralMemory, Insight, MemoryFrame, PersistentMemory

from capillaries.agent import frame_compat
from capillaries.agent.api import _build_context_frame
from capillaries.search.context_filter import ContextFilter


def a_frame(**tier_kwargs) -> MemoryFrame:
    """A frame with a populated third tier, named however arteries names it."""
    cls = frame_compat.scope_memory_class()
    field = ("sibling_insights" if cls.__name__ == "ScopeMemory"
             else "ground_truth_insights")
    tier = cls(user_intent=tier_kwargs.get("user_intent", []),
               recurring_domains=tier_kwargs.get("recurring_domains", []),
               **{field: tier_kwargs.get("insights", [])})
    return MemoryFrame(
        ephemeral=EphemeralMemory(recent_messages=["a turn"]),
        persistent=PersistentMemory(active_domains=["technical"]),
        **{frame_compat.frame_kwarg_name(): tier},
    )


class ThirdTierAccessTests(unittest.TestCase):
    def test_the_tier_is_readable_whatever_arteries_calls_it(self):
        frame = a_frame(user_intent=["prefer stdlib"], recurring_domains=["AI"])
        self.assertEqual(frame_compat.user_intent(frame), ["prefer stdlib"])
        self.assertEqual(frame_compat.recurring_domains(frame), ["AI"])
        self.assertIsNotNone(frame_compat.scope_tier(frame))

    def test_insights_read_under_either_field_name(self):
        frame = a_frame(insights=[Insight(text="a fact", source="scope")])
        self.assertEqual(len(frame_compat.sibling_insights(frame)), 1)

    def test_a_default_frame_yields_empty_lists_not_errors(self):
        self.assertEqual(frame_compat.user_intent(MemoryFrame()), [])
        self.assertEqual(frame_compat.sibling_insights(MemoryFrame()), [])

    def test_no_context_at_all_is_survivable(self):
        self.assertIsNone(frame_compat.scope_tier(None))
        self.assertEqual(frame_compat.user_intent(None), [])


class BuildContextFrameTests(unittest.TestCase):
    """`_build_context_frame` raised ImportError on main. It is the only place
    capillaries constructs arteries' types."""

    def test_builds_from_the_new_scope_key(self):
        frame = _build_context_frame({
            "ephemeral": {"recent_messages": ["x"], "turn_count": 1},
            "persistent": {"active_domains": ["technical"]},
            "scope": {"user_intent": ["prefer stdlib"],
                      "sibling_insights": [{"text": "f", "source": "s"}]},
        })
        self.assertEqual(frame_compat.user_intent(frame), ["prefer stdlib"])
        self.assertEqual(len(frame_compat.sibling_insights(frame)), 1)

    def test_builds_from_the_old_evergreen_key(self):
        """A client posting the pre-rename shape must still work."""
        frame = _build_context_frame({
            "evergreen": {"user_intent": ["prefer stdlib"],
                          "ground_truth_insights": [{"text": "f", "source": "s"}]},
        })
        self.assertEqual(frame_compat.user_intent(frame), ["prefer stdlib"])
        self.assertEqual(len(frame_compat.sibling_insights(frame)), 1)

    def test_an_empty_payload_builds_a_usable_frame(self):
        frame = _build_context_frame({})
        self.assertEqual(frame.persistent.active_domains, [])


class ContextFilterTests(unittest.TestCase):
    """context_filter reads the third tier for two of its four boosts. It
    raised AttributeError on main."""

    def test_apply_reads_the_tier_without_raising(self):
        frame = a_frame(recurring_domains=["technical"], user_intent=["prefer stdlib"])
        self.assertEqual(ContextFilter().apply([], frame), [])

    def test_apply_survives_a_default_frame(self):
        self.assertEqual(ContextFilter().apply([], MemoryFrame()), [])


if __name__ == "__main__":
    unittest.main()
