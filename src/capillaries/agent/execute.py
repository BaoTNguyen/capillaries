"""
Skill execution protocol - step-by-step skill execution with session state.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import psycopg2
import psycopg2.extras

from capillaries.agent.route import resolve_template_variables
from capillaries.config.paths import DB_CONFIG


CONTEXT_MAX_TOKENS = 500


@dataclass
class StepResponse:
    session_id: str
    status: str
    current_step: dict | None = None
    progress: dict | None = None
    context_summary: str = ""
    next_step_preview: dict | None = None


class SkillExecutor:
    """
    Handles step-by-step skill execution with session state management.
    """

    def __init__(self, db_config: dict | None = None):
        self._db_config = db_config or DB_CONFIG

    async def execute_step(
        self,
        session_id: str,
        step_order: int,
        previous_output: str | None = None,
        variables: dict | None = None,
        action: str = "execute",
        skip_reason: str | None = None,
        model: str | None = None,
    ) -> StepResponse:
        """Execute a step in a skill session."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM skills.skill_sessions
                    WHERE session_id = %s AND status = 'active'
                    """,
                    (session_id,),
                )
                session = cur.fetchone()

                if not session:
                    return StepResponse(
                        session_id=session_id,
                        status="error",
                        current_step=None,
                        progress=None,
                    )

                cur.execute(
                    "SELECT * FROM skills.skills WHERE skill_id = %s AND status = 'active'",
                    (session["skill_id"],),
                )
                skill = cur.fetchone()

                if not skill:
                    return StepResponse(
                        session_id=session_id,
                        status="error",
                        current_step=None,
                        progress=None,
                    )

                steps = json.loads(skill["steps"]) if isinstance(skill["steps"], str) else skill["steps"]
                total_steps = len(steps)
                current_step_num = session["current_step"]

                if action == "abort":
                    cur.execute(
                        "UPDATE skills.skill_sessions SET status = 'aborted', last_activity = CURRENT_TIMESTAMP WHERE session_id = %s",
                        (session_id,),
                    )
                    conn.commit()
                    return StepResponse(
                        session_id=session_id,
                        status="aborted",
                        progress={"completed_steps": current_step_num, "total_steps": total_steps, "is_final_step": current_step_num >= total_steps},
                    )

                if action == "skip":
                    if not skip_reason:
                        return StepResponse(
                            session_id=session_id,
                            status="error",
                            current_step=None,
                            progress=None,
                        )

                    step_outputs = json.loads(session["step_outputs"]) if session["step_outputs"] else []
                    step_outputs.append({
                        "step_order": step_order,
                        "output": f"SKIPPED: {skip_reason}",
                        "skipped": True,
                    })

                    new_context = _compress_context(session["context_summary"], f"Step {step_order}: Skipped - {skip_reason}")

                    next_step = step_order + 1
                    is_final = next_step > total_steps

                    cur.execute(
                        """
                        UPDATE skills.skill_sessions
                        SET current_step = %s, step_outputs = %s, context_summary = %s, last_activity = CURRENT_TIMESTAMP
                        WHERE session_id = %s
                        """,
                        (next_step, json.dumps(step_outputs), new_context, session_id),
                    )
                    conn.commit()

                    if is_final:
                        cur.execute(
                            "UPDATE skills.skill_sessions SET status = 'completed', last_activity = CURRENT_TIMESTAMP WHERE session_id = %s",
                            (session_id,),
                        )
                        conn.commit()

                    return StepResponse(
                        session_id=session_id,
                        status="completed" if is_final else "ready",
                        progress={"completed_steps": current_step_num, "total_steps": total_steps, "is_final_step": is_final, "skipped_steps": [step_order]},
                    )

                if previous_output is None and step_order > 1:
                    return StepResponse(
                        session_id=session_id,
                        status="error",
                        current_step=None,
                        progress={"completed_steps": current_step_num, "total_steps": total_steps, "is_final_step": False},
                    )

                step_data = None
                for s in steps:
                    if s["step_order"] == step_order:
                        step_data = s
                        break

                if not step_data:
                    return StepResponse(
                        session_id=session_id,
                        status="error",
                        current_step=None,
                        progress=None,
                    )

                prompt_text = ""
                pid = step_data["prompt_id"]
                # Steps key prompts by UUID, not title — see skills.skills.steps.
                # Both lookups below used to match on title, which silently
                # matched nothing (and the variants one named a column that does
                # not exist, raising as soon as a model was set).
                if model:
                    cur.execute("""
                        SELECT prompt_text FROM prompt_variants
                        WHERE prompt_id = %s::uuid AND model = %s AND is_current = TRUE
                        LIMIT 1
                    """, (pid, model))
                    variant_row = cur.fetchone()
                    if variant_row:
                        prompt_text = variant_row["prompt_text"]
                if not prompt_text:
                    cur.execute(
                        "SELECT prompt_text FROM prompts WHERE prompt_id = %s::uuid",
                        (pid,),
                    )
                    prompt_row = cur.fetchone()
                    prompt_text = prompt_row["prompt_text"] if prompt_row else ""

                agent_context = json.loads(session["agent_context"]) if session["agent_context"] else {}
                if variables:
                    agent_context.update(variables)

                resolved_text, unfilled = resolve_template_variables(prompt_text, agent_context)

                prior_context = session["context_summary"] or ""
                if prior_context:
                    resolved_text = f"{resolved_text}\n\n## Prior Context\n{prior_context}\n\n## Previous Step Output\n{previous_output or 'N/A'}"

                step_outputs = json.loads(session["step_outputs"]) if session["step_outputs"] else []
                step_outputs.append({
                    "step_order": step_order,
                    "output": previous_output,
                })

                new_context = _compress_context(prior_context, f"Step {step_order}: {previous_output[:200] if previous_output else 'completed'}")

                next_step = step_order + 1
                is_final = next_step > total_steps

                cur.execute(
                    """
                    UPDATE skills.skill_sessions
                    SET current_step = %s, step_outputs = %s, context_summary = %s, agent_context = %s, last_activity = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                    """,
                    (next_step, json.dumps(step_outputs), new_context, json.dumps(agent_context), session_id),
                )
                conn.commit()

                current_step_response = {
                    "step_order": step_order,
                    "prompt_id": step_data["prompt_id"],
                    "prompt_text_resolved": resolved_text,
                    "rationale": step_data.get("rationale"),
                    "unfilled_variables": unfilled,
                }

                next_preview = None
                if not is_final:
                    for s in steps:
                        if s["step_order"] == next_step:
                            next_preview = {
                                "step_order": next_step,
                                "rationale": s.get("rationale", ""),
                            }
                            break

                if is_final:
                    cur.execute(
                        "UPDATE skills.skill_sessions SET status = 'completed', last_activity = CURRENT_TIMESTAMP WHERE session_id = %s",
                        (session_id,),
                    )
                    conn.commit()

                return StepResponse(
                    session_id=session_id,
                    status="completed" if is_final else "ready",
                    current_step=current_step_response,
                    progress={"completed_steps": step_order, "total_steps": total_steps, "is_final_step": is_final},
                    context_summary=new_context,
                    next_step_preview=next_preview,
                )


def _compress_context(existing_summary: str, new_entry: str) -> str:
    """Compress context to fit within token limit."""
    if not existing_summary:
        return new_entry[:CONTEXT_MAX_TOKENS]

    lines = existing_summary.split("\n")
    if len(lines) > 10:
        lines = lines[-8:]

    lines.append(new_entry)

    combined = "\n".join(lines)
    if len(combined) > CONTEXT_MAX_TOKENS * 4:
        combined = combined[:CONTEXT_MAX_TOKENS * 4]

    return combined