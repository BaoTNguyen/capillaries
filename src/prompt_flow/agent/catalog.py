"""
Catalog and discovery endpoints for agent integration.
"""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from prompt_flow.config.paths import DB_CONFIG


class CatalogHandler:
    """Handles catalog browsing and discovery."""

    def __init__(self, db_config: dict | None = None):
        self._db_config = db_config or DB_CONFIG

    def get_catalog(self, view: str = "overview", domain_filter: str | None = None) -> dict:
        """Get catalog based on view type."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if view == "overview":
                    return self._overview(cur)
                elif view == "domains":
                    return self._domains(cur)
                elif view == "skills":
                    return self._skills(cur, domain_filter)
                elif view == "stages":
                    return self._stages(cur, domain_filter)
                else:
                    return self._overview(cur)

    def _overview(self, cur) -> dict:
        cur.execute("SELECT COUNT(*) as count FROM prompts WHERE status = 'active'")
        total_prompts = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) as count FROM skills.skills WHERE status = 'active'")
        total_skills = cur.fetchone()["count"]

        return {
            "total_prompts": total_prompts,
            "total_skills": total_skills,
        }

    def _domains(self, cur) -> dict:
        cur.execute("""
            SELECT domain, COUNT(*) as prompt_count
            FROM prompts, unnest(domain) as domain
            WHERE status = 'active' AND domain IS NOT NULL
            GROUP BY domain
            ORDER BY prompt_count DESC
        """)
        rows = cur.fetchall()

        return {
            "domains": [{"name": row["domain"], "prompt_count": row["prompt_count"]} for row in rows]
        }

    def _skills(self, cur, domain_filter: str | None = None) -> dict:
        query = """
            SELECT skill_id, name, slug, routing_description, domain, success_rate, total_runs
            FROM skills.skills
            WHERE status = 'active'
        """
        params = []
        if domain_filter:
            query += " AND %s = ANY(domain)"
            params.append(domain_filter)

        query += " ORDER BY total_runs DESC NULLS LAST"

        cur.execute(query, params)
        rows = cur.fetchall()

        return {
            "skills": [
                {
                    "name": row["name"],
                    "slug": row["slug"],
                    "routing_description": row["routing_description"],
                    "domain": row["domain"] or [],
                    "success_rate": row["success_rate"],
                    "total_runs": row["total_runs"] or 0,
                }
                for row in rows
            ]
        }

    def _stages(self, cur, domain_filter: str | None = None) -> dict:
        query = """
            SELECT primary_stage, COUNT(*) as count
            FROM prompts
            WHERE status = 'active'
        """
        params = []
        if domain_filter:
            query += " AND %s = ANY(domain)"
            params.append(domain_filter)

        query += " GROUP BY primary_stage"

        cur.execute(query, params)
        rows = cur.fetchall()

        stages = {"clarify": 0, "plan": 0, "execute": 0, "verify": 0, "reflect": 0}
        for row in rows:
            if row["primary_stage"]:
                stages[row["primary_stage"]] = row["count"]

        return {"stages": stages}


def get_discover_response() -> dict:
    """Get the self-describing discovery response."""
    return {
        "service": "Prompt Flow",
        "version": "2.0.0",
        "description": "Semantic prompt and skill retrieval. I store reusable prompts across 10 domains and 5 workflow stages. Search with natural language, get back ready-to-use prompt text.",
        "quickstart": "POST /agent/route with {\"situation\": \"describe what you need\"} to get started.",
        "capabilities": {
            "prompt_search": "Find individual prompts by natural language query",
            "skill_matching": "Match validated multi-step workflows to complex tasks",
            "template_resolution": "Fill prompt template variables from context",
            "feedback_loop": "Report outcomes to improve future recommendations",
        },
        "endpoints": {
            "route": {
                "method": "POST",
                "path": "/agent/route",
                "description": "Primary entry point. Describe your situation, get the best prompt or skill.",
                "example_request": {"situation": "I need to debug a memory leak in a Python web application"},
            },
            "step": {
                "method": "POST",
                "path": "/agent/step",
                "description": "Execute next step of a multi-step skill. Use session_id from /agent/route.",
            },
            "feedback": {
                "method": "POST",
                "path": "/agent/feedback",
                "description": "Report outcome. Minimum: {trace_id, outcome}.",
            },
            "catalog": {
                "method": "GET",
                "path": "/agent/catalog",
                "description": "Browse available domains, skills, and statistics.",
            },
            "health": {
                "method": "GET",
                "path": "/health",
                "description": "Service liveness check.",
            },
            "openapi": {
                "method": "GET",
                "path": "/openapi.json",
                "description": "Full OpenAPI 3.1 schema for all endpoints.",
            },
        },
        "mcp": {
            "supported": True,
            "sse_endpoint": "/mcp/sse",
            "tools": ["prompt_flow_find", "prompt_flow_execute_step", "prompt_flow_feedback", "prompt_flow_catalog"],
        },
    }