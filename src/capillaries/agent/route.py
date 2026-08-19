"""
Agent routing endpoint - finds the best prompt or skill for a situation.

This is the primary entry point for agents. It takes a freeform situation
description and returns a ready-to-use prompt or skill.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG
from capillaries.find import find


# SINGLE_THRESHOLD removed — see search/api.py. Comparing a cross-encoder
# prompt score against a skill's routing_embedding cosine is comparing two
# scales from two models; PromptSearch now scores both with one reranker.


@dataclass
class RouteResponse:
    mode: str
    confidence: float
    recommendation: dict | None = None
    skill: dict | None = None
    alternatives: list[dict] = field(default_factory=list)
    clarification_hint: str | None = None
    inferred: dict | None = None
    trace_id: str = ""

    def to_dict(self) -> dict:
        result = {
            "mode": self.mode,
            "confidence": self.confidence,
            "trace_id": self.trace_id,
        }
        if self.recommendation:
            result["recommendation"] = self.recommendation
        if self.skill:
            result["skill"] = self.skill
        if self.alternatives:
            result["alternatives"] = self.alternatives
        if self.clarification_hint:
            result["clarification_hint"] = self.clarification_hint
        if self.inferred:
            result["inferred"] = self.inferred
        return result


_BRACKET_SLOT = re.compile(r'\[([A-Z][A-Z0-9 /\-_&\'\",.()]+)\]')
_MUSTACHE_SLOT = re.compile(r'\{\{(\w+)\}\}')
_PASTE_SLOT = re.compile(r'\[(paste[_ ][\w_ ]+|PASTE[_ ][\w_ ]+)\]', re.IGNORECASE)

_SLOT_BLACKLIST = {
    "YOUR", "OR", "AND", "IF", "THEN", "ELSE", "NOT", "YES", "NO",
    "E.G.", "IE", "EG", "OPTIONAL", "REQUIRED", "NOTE", "IMPORTANT",
    "EXAMPLE", "SEE", "REFER", "ALSO",
}

_PASTE_KEYWORDS = {"paste", "insert", "attach", "copy", "provide"}


def _normalize_key(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')


def _is_real_slot(raw: str) -> bool:
    words = raw.strip().split()
    if len(words) == 1 and words[0] in _SLOT_BLACKLIST:
        return False
    if len(raw) < 2:
        return False
    return True


def _classify_slot(raw: str) -> str:
    lower = raw.lower()
    if any(kw in lower for kw in _PASTE_KEYWORDS):
        return "paste"
    if '/' in raw or '|' in raw:
        return "choice"
    return "fill"


def _match_context(slot_name: str, context: dict) -> str | None:
    if not context:
        return None
    key = _normalize_key(slot_name)
    for ctx_key, ctx_val in context.items():
        if _normalize_key(ctx_key) == key:
            return str(ctx_val)
    for ctx_key, ctx_val in context.items():
        nk = _normalize_key(ctx_key)
        if nk in key or key in nk:
            return str(ctx_val)
    return None


def resolve_template_variables(prompt_text: str, context: dict | None = None) -> tuple[str, list[dict]]:
    """
    Extract all template slots from prompt text and fill from context.

    Handles three formats:
      - [UPPERCASE SLOTS] — most common in this vault
      - {{mustache}} — used by some skill/step prompts
      - [paste/insert ...] — user-supplied content blocks

    Returns: (resolved_text, unfilled_variables)
    Each unfilled variable has: name, slot_type, original (raw bracket text), required.
    """
    if context is None:
        context = {}

    filled = []
    unfilled = []
    seen_slots: set[str] = set()

    for pattern, fmt_fn in [
        (_BRACKET_SLOT, lambda raw: f"[{raw}]"),
        (_PASTE_SLOT, lambda raw: f"[{raw}]"),
        (_MUSTACHE_SLOT, lambda raw: f"{{{{{raw}}}}}"),
    ]:
        for match in pattern.finditer(prompt_text):
            raw = match.group(1)
            original = fmt_fn(raw)
            if original in seen_slots:
                continue
            seen_slots.add(original)

            if not _is_real_slot(raw):
                continue

            slot_type = _classify_slot(raw) if pattern is not _MUSTACHE_SLOT else "fill"
            value = _match_context(raw, context)

            if value:
                prompt_text = prompt_text.replace(original, value)
                filled.append({"name": raw, "original": original, "value": value})
            else:
                unfilled.append({
                    "name": raw,
                    "original": original,
                    "slot_type": slot_type,
                    "required": True,
                })

    return prompt_text, unfilled


class AgentRouter:
    """
    Compatibility formatter over the shared ``find()`` retrieval surface.
    """

    def __init__(self, db_config: dict | None = None):
        self._db_config = db_config or DB_CONFIG
    async def route(self, situation: str, domain: list[str] | None = None, intent: list[str] | None = None, prefer: str = "auto", context: dict | None = None, session_id: str | None = None, source: str = "private", modality: str = "text", memory_context=None) -> RouteResponse:
        """
        Find the best prompt or skill for the given situation.

        This endpoint retains its agent-specific response shape, but does not
        own a second retrieval path or a pre-retrieval gate.
        """
        trace_id = f"pf_tr_{uuid.uuid4().hex[:12]}"

        # Soft hints for skill recall taxonomy boost — not hard retrieval filters
        hints = {}
        if domain:
            hints["domain"] = domain
        if intent:
            hints["intent"] = intent

        filters: dict = {"source": source}
        if modality:
            filters["modality"] = modality
        result = await find(
            situation,
            context=memory_context,
            prefer=prefer,
            filters=filters,
            skill_hints=hints or None,
        )
        if result.mode == "none":
            return RouteResponse(mode="none", confidence=result.confidence, trace_id=trace_id)
        if result.mode == "skill":
            return self._build_skill_response(result, trace_id, context)

        prompt_text, unfilled = resolve_template_variables(result.prompt_text, context)
        mode = "needs_context" if unfilled else "single"

        recommendation = {
            "prompt_id": result.prompt_id,
            "title": result.title,
            "prompt_text": prompt_text,
            "variables": unfilled,
            "metadata": {
                "intent": result.intent,
                "task_type": result.task_type,
                "domain": result.domain,
            },
        }
        return RouteResponse(
            mode=mode,
            confidence=result.confidence,
            recommendation=recommendation,
            trace_id=trace_id,
        )

    def _build_skill_response(self, result, trace_id: str, context: dict | None = None) -> RouteResponse:
        """Build a skill-mode response."""
        session_id = str(uuid.uuid4())
        self._create_session(session_id, result.skill_id, trace_id)

        steps_preview = []
        for step in result.steps:
            steps_preview.append({
                "step_order": step["step_order"],
                "prompt_id": step["prompt_id"],
                "rationale": step.get("rationale", ""),
            })

        first_step = result.steps[0] if result.steps else None
        first_step_text = ""
        unfilled = []
        if first_step:
            first_step_text, unfilled = resolve_template_variables(first_step.get("prompt_text", ""), context)

        skill_response = {
            "skill_id": result.skill_id,
            "name": result.skill_name,
            "tag": result.skill_tag,
            "summary": result.skill_summary,
            "session_id": session_id,
            "total_steps": len(result.steps),
            "steps_preview": steps_preview,
            "first_step": {
                "step_order": 1,
                "prompt_id": first_step["prompt_id"] if first_step else None,
                "prompt_text": first_step_text,
                "variables": unfilled,
            } if first_step else None,
        }

        mode = "needs_context" if unfilled else "skill"

        return RouteResponse(
            mode=mode,
            confidence=result.confidence,
            skill=skill_response,
            trace_id=trace_id,
        )

    def _create_session(self, session_id: str, skill_id: str, trace_id: str) -> None:
        """Create a new skill session."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skills.skill_sessions (session_id, skill_id, trace_id, current_step, status)
                    VALUES (%s, %s, %s, 0, 'active')
                    """,
                    (session_id, skill_id, trace_id),
                )
                conn.commit()
