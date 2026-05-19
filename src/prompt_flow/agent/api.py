"""
FastAPI endpoints for agent integration layer.

Exposes /agent/route, /agent/step, /agent/feedback, /agent/catalog, /agent/discover.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from prompt_flow.agent.catalog import CatalogHandler, get_discover_response
from prompt_flow.agent.execute import SkillExecutor
from prompt_flow.agent.feedback import FeedbackHandler
from prompt_flow.agent.route import AgentRouter


router = APIRouter(prefix="/agent", tags=["agent"])


class RouteRequest(BaseModel):
    situation: str = Field(..., min_length=10, max_length=2000)
    stage: str | None = Field(None, description="Current workflow stage")
    domain: list[str] | None = Field(None, description="Domain hints")
    intent: list[str] | None = Field(None, description="Intent hints")
    complexity: int | None = Field(None, ge=1, le=5)
    prefer: str = Field(default="auto", description="'single', 'skill', or 'auto'")
    context: dict[str, Any] | None = Field(None, description="Structured context for template filling")
    session_id: str | None = Field(None, description="For continuing previous interaction")


class StepRequest(BaseModel):
    session_id: str
    step_order: int = Field(..., ge=1)
    previous_output: str | None = Field(None, max_length=50000)
    variables: dict[str, str] | None = None
    action: str = Field(default="execute", description="'execute', 'skip', or 'abort'")
    skip_reason: str | None = None


class FeedbackRequest(BaseModel):
    trace_id: str
    outcome: str = Field(..., description="'success', 'partial', 'failure', or 'skipped'")
    quality_score: float | None = Field(None, ge=0, le=1)
    failure_step: int | None = None
    failure_reason: str | None = Field(None, description="'irrelevant', 'too_vague', 'too_specific', 'wrong_domain', 'wrong_stage', 'outdated', 'template_unfillable', 'other'")
    notes: str | None = Field(None, max_length=2000)
    prompt_modifications: list[dict] | None = None
    session_id: str | None = None
    per_step_feedback: list[dict] | None = None


class CatalogRequest(BaseModel):
    view: str = Field(default="overview", description="'overview', 'domains', 'skills', or 'stages'")
    domain_filter: str | None = None


_router: AgentRouter | None = None
_executor: SkillExecutor | None = None
_feedback_handler: FeedbackHandler | None = None
_catalog_handler: CatalogHandler | None = None


def _get_router() -> AgentRouter:
    global _router
    if _router is None:
        _router = AgentRouter()
    return _router


def _get_executor() -> SkillExecutor:
    global _executor
    if _executor is None:
        _executor = SkillExecutor()
    return _executor


def _get_feedback_handler() -> FeedbackHandler:
    global _feedback_handler
    if _feedback_handler is None:
        _feedback_handler = FeedbackHandler()
    return _feedback_handler


def _get_catalog_handler() -> CatalogHandler:
    global _catalog_handler
    if _catalog_handler is None:
        _catalog_handler = CatalogHandler()
    return _catalog_handler


@router.post("/route")
async def route(req: RouteRequest) -> dict:
    """
    Primary entry point for agents. Find the best prompt or skill for your situation.
    """
    router = _get_router()
    result = await router.route(
        situation=req.situation,
        stage=req.stage,
        domain=req.domain,
        intent=req.intent,
        complexity=req.complexity,
        prefer=req.prefer,
        context=req.context,
        session_id=req.session_id,
    )
    return result.to_dict()


@router.post("/step")
async def execute_step(req: StepRequest) -> dict:
    """
    Execute a step in a multi-step skill workflow.
    """
    executor = _get_executor()
    result = await executor.execute_step(
        session_id=req.session_id,
        step_order=req.step_order,
        previous_output=req.previous_output,
        variables=req.variables,
        action=req.action,
        skip_reason=req.skip_reason,
    )

    return {
        "session_id": result.session_id,
        "status": result.status,
        "current_step": result.current_step,
        "progress": result.progress,
        "context_summary": result.context_summary,
        "next_step_preview": result.next_step_preview,
    }


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """
    Report whether a prompt or skill worked.
    """
    handler = _get_feedback_handler()
    return handler.submit_feedback(
        trace_id=req.trace_id,
        outcome=req.outcome,
        mode="single",
        quality_score=req.quality_score,
        failure_step=req.failure_step,
        failure_reason=req.failure_reason,
        notes=req.notes,
        prompt_modifications=req.prompt_modifications,
        per_step_feedback=req.per_step_feedback,
        session_id=req.session_id,
    )


@router.get("/catalog")
async def get_catalog(view: str = "overview", domain_filter: str | None = None) -> dict:
    """
    Browse available domains, skills, and statistics.
    """
    handler = _get_catalog_handler()
    return handler.get_catalog(view=view, domain_filter=domain_filter)


@router.get("/discover")
async def discover() -> dict:
    """
    Self-describing endpoint for agent discovery.
    """
    return get_discover_response()