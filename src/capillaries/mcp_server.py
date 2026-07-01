"""
MCP Server for Capillaries.

Provides 4 MCP tools for agent integration:
- capillaries_find: Find the best prompt or skill
- capillaries_execute_step: Execute next step in a skill
- capillaries_feedback: Report outcome
- capillaries_catalog: Browse available capabilities

Usage:
    python -m capillaries.mcp_server

Or configure as MCP server in Claude Code / Cursor settings.
"""

from __future__ import annotations

import asyncio
from typing import Any

from capillaries.agent.api import (
    RouteRequest,
    StepRequest,
    FeedbackRequest,
    _get_router,
    _get_executor,
    _get_feedback_handler,
    _get_catalog_handler,
)
from capillaries.agent.catalog import get_discover_response
from capillaries.agent.context import normalize_agent_context, with_agent_context


try:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("Capillaries")

    @mcp.tool()
    async def capillaries_find(
        situation: str,
        stage: str | None = None,
        domain: list[str] | None = None,
        complexity: int | None = None,
        prefer: str = "auto",
        context: dict | None = None,
        agent_context: dict | None = None,
    ) -> dict:
        """
        Find the best prompt or multi-step skill for your current situation.

        Describe what you're trying to do, what's going wrong, or what you need
        help with. Returns ready-to-use prompt text, not just metadata.

        Use this whenever you need a structured approach to a task: debugging,
        code review, planning, analysis, writing, strategy, optimization.
        Works with natural language - just describe your situation.
        """
        router = _get_router()
        normalized = normalize_agent_context(agent_context)
        result = await router.route(
            situation=situation,
            domain=domain,
            intent=[stage] if stage else None,
            complexity=complexity,
            prefer=prefer,
            context=with_agent_context(context, normalized),
        )
        response = result.to_dict()
        if normalized:
            response["agent_context"] = normalized.to_dict()
        return response

    @mcp.tool()
    async def capillaries_execute_step(
        session_id: str,
        step_order: int,
        previous_output: str | None = None,
        variables: dict | None = None,
        skip_reason: str | None = None,
    ) -> dict:
        """
        Execute the next step of a multi-step skill workflow.

        Call this after capillaries_find returns a skill (mode=skill).
        Pass the session_id and the output from the previous step.
        The system tracks where you are in the workflow and returns the
        next prompt with context from previous steps injected.
        """
        executor = _get_executor()
        action = "skip" if skip_reason else "execute"
        result = await executor.execute_step(
            session_id=session_id,
            step_order=step_order,
            previous_output=previous_output,
            variables=variables,
            action=action,
            skip_reason=skip_reason,
        )
        return {
            "session_id": result.session_id,
            "status": result.status,
            "current_step": result.current_step,
            "progress": result.progress,
            "context_summary": result.context_summary,
            "next_step_preview": result.next_step_preview,
        }

    @mcp.tool()
    async def capillaries_feedback(
        trace_id: str,
        outcome: str,
        quality_score: float | None = None,
        failure_step: int | None = None,
        notes: str | None = None,
        agent_context: dict | None = None,
    ) -> dict:
        """
        Report whether a prompt or skill worked.

        Call this after using a prompt from capillaries_find.
        Minimum viable signal: just pass the trace_id and outcome.
        Rich signal: include which step failed and what went wrong.
        This data improves future recommendations.
        """
        handler = _get_feedback_handler()
        result = handler.submit_feedback(
            trace_id=trace_id,
            outcome=outcome,
            mode="single",
            quality_score=quality_score,
            failure_step=failure_step,
            notes=notes,
        )
        normalized = normalize_agent_context(agent_context)
        if normalized:
            result["agent_context"] = normalized.to_dict()
        return result

    @mcp.tool()
    async def capillaries_catalog(
        view: str = "overview",
        domain_filter: str | None = None,
    ) -> dict:
        """
        Browse what prompt categories, skills, and domains are available.

        Use this to understand what the system can help with before searching.
        Returns a summary of available capabilities, not individual prompts.

        Good for: 'what domains do you cover?', 'how many skills exist for
        technical work?', 'what workflow stages are available?'
        """
        handler = _get_catalog_handler()
        return handler.get_catalog(view=view, domain_filter=domain_filter)

    def run_mcp_server(host: str = "127.0.0.1", port: int = 1100):
        """Run the MCP server."""
        mcp.run(transport="stdio")

    if __name__ == "__main__":
        import sys
        if len(sys.argv) > 1 and sys.argv[1] == "serve":
            import uvicorn
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route

            async def handle_sse(request):
                transport = SseServerTransport("/messages")
                await transport.connect()

            app = Starlette(routes=[Route("/sse", handle_sse)])
            uvicorn.run(app, host="127.0.0.1", port=1100)
        else:
            mcp.run(transport="stdio")

except ImportError:
    import sys

    def capillaries_find(situation: str, stage: str = None, domain: list = None, complexity: int = None, prefer: str = "auto", context: dict = None, agent_context: dict = None) -> dict:
        raise ImportError("MCP SDK not installed. Run: pip install mcp")

    def capillaries_execute_step(session_id: str, step_order: int, previous_output: str = None, variables: dict = None, skip_reason: str = None) -> dict:
        raise ImportError("MCP SDK not installed. Run: pip install mcp")

    def capillaries_feedback(trace_id: str, outcome: str, quality_score: float = None, failure_step: int = None, notes: str = None, agent_context: dict = None) -> dict:
        raise ImportError("MCP SDK not installed. Run: pip install mcp")

    def capillaries_catalog(view: str = "overview", domain_filter: str = None) -> dict:
        raise ImportError("MCP SDK not installed. Run: pip install mcp")