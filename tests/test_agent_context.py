import unittest

from capillaries.agent.context import AgentContext, normalize_agent_context, with_agent_context
from capillaries.find import FindResult


class AgentContextTests(unittest.TestCase):
    def test_normalizes_cli_metadata_aliases(self):
        ctx = normalize_agent_context({
            "cli": "Cursor",
            "event": "prompt",
            "agentId": "child",
            "parentAgentId": "parent",
            "role": "subagent",
            "sessionId": "s1",
            "projectDirectory": "/repo",
            "capabilities": {"can_inject_context": True},
        })

        self.assertEqual(ctx.cli, "cursor")
        self.assertEqual(ctx.agent_id, "child")
        self.assertEqual(ctx.parent_agent_id, "parent")
        self.assertEqual(ctx.agent_role, "subagent")
        self.assertEqual(ctx.session_id, "s1")
        self.assertEqual(ctx.cwd, "/repo")
        self.assertTrue(ctx.capabilities["can_inject_context"])

    def test_with_agent_context_preserves_existing_context(self):
        merged = with_agent_context({"name": "Bao"}, AgentContext(cli="opencode", agent_id="agent-1"))

        self.assertEqual(merged["name"], "Bao")
        self.assertEqual(merged["agent_context"]["cli"], "opencode")
        self.assertEqual(merged["agent_context"]["agent_id"], "agent-1")

    def test_find_result_includes_agent_context_only_when_present(self):
        base = FindResult(mode="none", confidence=0.0).to_dict()
        enriched = FindResult(
            mode="single",
            confidence=0.9,
            prompt_text="Do the thing",
            agent_context={"cli": "hermes"},
        ).to_dict()

        self.assertNotIn("agent_context", base)
        self.assertEqual(enriched["agent_context"], {"cli": "hermes"})


if __name__ == "__main__":
    unittest.main()
