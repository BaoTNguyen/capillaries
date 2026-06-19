# Agent Integration Layer Design for Prompt Flow

Date: 2026-05-18
Status: Design specification
Author: Systems architecture review

---

## Table of Contents

1. [MCP Server Specification](#1-mcp-server-specification)
2. [Agentic Routing Endpoint](#2-agentic-routing-endpoint)
3. [Skill Execution Protocol](#3-skill-execution-protocol)
4. [Feedback and Learning Loop](#4-feedback-and-learning-loop)
5. [Discovery and Bootstrapping](#5-discovery-and-bootstrapping)
6. [Prompt Template Resolution](#6-prompt-template-resolution)
7. [Bootstrap Checklist](#7-bootstrap-checklist)

---

## 1. MCP Server Specification

### Design Decision

Expose four MCP tools rather than mirroring every REST endpoint. Agents mid-task need to (a) find the right prompt for a situation, (b) get a full skill workflow, (c) resolve a template into ready text, and (d) report back. Fewer tools means higher self-selection accuracy: LLM tool-use performance degrades measurably above 8-10 tools, and each extra tool dilutes the description space.

The key tradeoff: collapsing search + routing into a single `capillaries_find` tool (instead of separate `search` and `route` tools) trades off fine-grained control for discoverability. An agent that has never seen this system can use one tool for everything. Power users can pass structured hints to get the same precision.

### Schema

#### Tool 1: `capillaries_find`

```json
{
  "name": "capillaries_find",
  "description": "Find the best prompt or multi-step skill for your current situation. Describe what you're trying to do, what's going wrong, or what you need help with. Returns ready-to-use prompt text, not just metadata. Use this whenever you need a structured approach to a task: debugging, code review, planning, analysis, writing, strategy, optimization. Works with natural language - just describe your situation.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "situation": {
        "type": "string",
        "description": "What you're doing right now and what you need. Be specific: 'I'm debugging a race condition in a Go HTTP handler' is better than 'help with debugging'. Include what went wrong if applicable."
      },
      "stage": {
        "type": "string",
        "enum": ["clarify", "plan", "execute", "verify", "reflect"],
        "description": "Where you are in the workflow. 'clarify' = understanding the problem, 'plan' = designing the approach, 'execute' = doing the work, 'verify' = checking the result, 'reflect' = capturing lessons. Omit to let the system infer from your situation."
      },
      "domain": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["AI", "business", "career", "finance", "learning", "personal", "product", "strategy", "technical", "writing"]
        },
        "description": "Domain(s) of the task. Omit to let the system infer from your situation."
      },
      "complexity": {
        "type": "integer",
        "minimum": 1,
        "maximum": 5,
        "description": "Task complexity (1=simple, 5=very complex). Omit for auto-detection."
      },
      "prefer": {
        "type": "string",
        "enum": ["single", "skill", "auto"],
        "default": "auto",
        "description": "'single' = one best prompt, 'skill' = multi-step workflow, 'auto' = let the system decide based on task complexity."
      }
    },
    "required": ["situation"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "mode": {
        "type": "string",
        "enum": ["single", "skill", "chain"]
      },
      "confidence": {
        "type": "number",
        "minimum": 0,
        "maximum": 1
      },
      "recommendation": {
        "type": "object",
        "description": "For mode=single: a single prompt. For mode=skill: a matched skill. For mode=chain: a dynamically assembled sequence.",
        "properties": {
          "prompt_id": { "type": "string" },
          "prompt_text": { "type": "string" },
          "variables": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "description": { "type": "string" },
                "required": { "type": "boolean" },
                "inferred_value": { "type": "string" }
              }
            }
          },
          "skill": {
            "type": "object",
            "properties": {
              "skill_id": { "type": "string" },
              "name": { "type": "string" },
              "slug": { "type": "string" },
              "session_id": { "type": "string" },
              "steps": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "step_order": { "type": "integer" },
                    "stage": { "type": "string" },
                    "prompt_id": { "type": "string" },
                    "prompt_text": { "type": "string" },
                    "rationale": { "type": "string" },
                    "variables": { "type": "array" }
                  }
                }
              }
            }
          },
          "metadata": {
            "type": "object",
            "properties": {
              "intent": { "type": "array", "items": { "type": "string" } },
              "task_type": { "type": "array", "items": { "type": "string" } },
              "domain": { "type": "array", "items": { "type": "string" } },
              "primary_stage": { "type": "string" },
              "complexity_level": { "type": "integer" }
            }
          }
        }
      },
      "alternatives": {
        "type": "array",
        "maxItems": 3,
        "items": {
          "type": "object",
          "properties": {
            "prompt_id": { "type": "string" },
            "summary": { "type": "string" },
            "score": { "type": "number" }
          }
        }
      },
      "trace_id": { "type": "string" }
    }
  }
}
```

**Usage example (agent perspective):**
```
Agent is mid-task debugging a Python import cycle. It calls:

capillaries_find({
  "situation": "I have a circular import between two Python modules. Module A imports from B at module level, and B imports from A inside a function. Getting ImportError at startup.",
  "stage": "execute",
  "domain": ["technical"]
})

Response:
{
  "mode": "single",
  "confidence": 0.82,
  "recommendation": {
    "prompt_id": "Python Debug - Circular Import Resolution",
    "prompt_text": "You are debugging a circular import in a Python project...\n\n## Context\n{{error_traceback}}\n{{module_a_imports}}\n{{module_b_imports}}\n\n## Instructions\n1. Map the full import graph...",
    "variables": [
      {"name": "error_traceback", "description": "The full ImportError traceback", "required": true, "inferred_value": null},
      {"name": "module_a_imports", "description": "Import statements from module A", "required": true, "inferred_value": null},
      {"name": "module_b_imports", "description": "Import statements from module B", "required": true, "inferred_value": null}
    ],
    "metadata": {
      "intent": ["debug"],
      "task_type": ["debug"],
      "domain": ["technical"],
      "primary_stage": "execute",
      "complexity_level": 2
    }
  },
  "alternatives": [
    {"prompt_id": "General Debug Methodology", "summary": "Systematic debugging framework for any error type", "score": 0.64},
    {"prompt_id": "Python Architecture Review", "summary": "Full module dependency analysis and refactoring plan", "score": 0.58}
  ],
  "trace_id": "pf_tr_20260518_a3f7d8e3"
}
```

#### Tool 2: `capillaries_execute_step`

```json
{
  "name": "capillaries_execute_step",
  "description": "Execute the next step of a multi-step skill workflow. Call this after capillaries_find returns a skill (mode=skill). Pass the session_id and the output from the previous step. The system tracks where you are in the workflow and returns the next prompt with context from previous steps injected. If you're starting a skill, pass step_order=1 with no previous_output.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "Session ID returned by capillaries_find when a skill was matched."
      },
      "step_order": {
        "type": "integer",
        "minimum": 1,
        "description": "Which step to execute (1-based). The system validates this matches the expected next step."
      },
      "previous_output": {
        "type": "string",
        "description": "The output produced by the previous step. Omit for step 1. This is injected into the next prompt's context."
      },
      "variables": {
        "type": "object",
        "description": "Key-value pairs to fill any remaining template variables in this step's prompt.",
        "additionalProperties": { "type": "string" }
      },
      "skip_reason": {
        "type": "string",
        "description": "If skipping this step, explain why. The system will advance to the next step and note the skip."
      }
    },
    "required": ["session_id", "step_order"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "session_id": { "type": "string" },
      "current_step": {
        "type": "object",
        "properties": {
          "step_order": { "type": "integer" },
          "stage": { "type": "string" },
          "prompt_id": { "type": "string" },
          "prompt_text_resolved": { "type": "string" },
          "rationale": { "type": "string" },
          "unfilled_variables": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "description": { "type": "string" }
              }
            }
          }
        }
      },
      "progress": {
        "type": "object",
        "properties": {
          "completed_steps": { "type": "integer" },
          "total_steps": { "type": "integer" },
          "is_final_step": { "type": "boolean" }
        }
      },
      "context_summary": {
        "type": "string",
        "description": "Compressed summary of all previous step outputs, suitable for injection into the current step without exhausting context window."
      }
    }
  }
}
```

#### Tool 3: `capillaries_feedback`

```json
{
  "name": "capillaries_feedback",
  "description": "Report whether a prompt or skill worked. Call this after using a prompt from capillaries_find. Minimum viable signal: just pass the trace_id and outcome. Rich signal: include which step failed and what went wrong. This data improves future recommendations.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "trace_id": {
        "type": "string",
        "description": "The trace_id returned by capillaries_find."
      },
      "outcome": {
        "type": "string",
        "enum": ["success", "partial", "failure", "skipped"],
        "description": "Did the prompt/skill achieve what you needed?"
      },
      "quality_score": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "0 = completely unhelpful, 1 = exactly what was needed. Optional."
      },
      "failure_step": {
        "type": "integer",
        "description": "If a skill failed, which step number broke. Optional."
      },
      "notes": {
        "type": "string",
        "description": "What went wrong, what you'd change, what was missing. Optional but valuable."
      }
    },
    "required": ["trace_id", "outcome"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "acknowledged": { "type": "boolean" },
      "feedback_id": { "type": "string" }
    }
  }
}
```

#### Tool 4: `capillaries_catalog`

```json
{
  "name": "capillaries_catalog",
  "description": "Browse what prompt categories, skills, and domains are available. Use this to understand what the system can help with before searching. Returns a summary of available capabilities, not individual prompts. Good for: 'what domains do you cover?', 'how many skills exist for technical work?', 'what workflow stages are available?'",
  "inputSchema": {
    "type": "object",
    "properties": {
      "view": {
        "type": "string",
        "enum": ["overview", "domains", "skills", "stages"],
        "default": "overview",
        "description": "'overview' = top-level stats, 'domains' = prompts per domain, 'skills' = active skills list, 'stages' = prompts per workflow stage"
      },
      "domain_filter": {
        "type": "string",
        "description": "Filter to a specific domain when view=skills or view=stages."
      }
    },
    "required": []
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "total_prompts": { "type": "integer" },
      "total_skills": { "type": "integer" },
      "domains": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "prompt_count": { "type": "integer" }
          }
        }
      },
      "skills": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "slug": { "type": "string" },
            "routing_description": { "type": "string" },
            "domain": { "type": "array" },
            "success_rate": { "type": "number" },
            "total_runs": { "type": "integer" }
          }
        }
      },
      "stages": {
        "type": "object",
        "properties": {
          "clarify": { "type": "integer" },
          "plan": { "type": "integer" },
          "execute": { "type": "integer" },
          "verify": { "type": "integer" },
          "reflect": { "type": "integer" }
        }
      }
    }
  }
}
```

### Integration Snippet

MCP server configuration (Python, using the `mcp` SDK):

```python
# src/capillaries/mcp_server.py

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Prompt Flow",
    description="Find and use the best prompts and multi-step skills for any task",
)

@mcp.tool()
async def capillaries_find(
    situation: str,
    stage: str | None = None,
    domain: list[str] | None = None,
    complexity: int | None = None,
    prefer: str = "auto",
) -> dict:
    """Find the best prompt or multi-step skill for your current situation..."""
    # Delegates to POST /agent/route internally
    ...

@mcp.tool()
async def capillaries_execute_step(
    session_id: str,
    step_order: int,
    previous_output: str | None = None,
    variables: dict | None = None,
    skip_reason: str | None = None,
) -> dict:
    """Execute the next step of a multi-step skill workflow..."""
    # Delegates to POST /agent/step internally
    ...

@mcp.tool()
async def capillaries_feedback(
    trace_id: str,
    outcome: str,
    quality_score: float | None = None,
    failure_step: int | None = None,
    notes: str | None = None,
) -> dict:
    """Report whether a prompt or skill worked..."""
    # Delegates to POST /agent/feedback internally
    ...

@mcp.tool()
async def capillaries_catalog(
    view: str = "overview",
    domain_filter: str | None = None,
) -> dict:
    """Browse what prompt categories, skills, and domains are available..."""
    # Delegates to GET /agent/catalog internally
    ...
```

### Failure Mode

**Most likely failure:** An agent calls `capillaries_find` with a vague situation like "help me" and gets back a low-confidence generic prompt that wastes a tool call. **Mitigation:** The response includes `confidence` and `alternatives`. When confidence is below 0.3, the response includes a `clarification_hint` field suggesting what additional context would improve results. The MCP tool description explicitly coaches the agent to be specific. Additionally, the system never returns nothing: even at low confidence it returns the best available match with a clear signal that it is a weak match.

**Second failure mode:** The MCP server process crashes or is unavailable. **Mitigation:** Each tool is designed to be non-blocking for the calling agent's primary task. If `capillaries_find` fails, the agent continues without a prompt rather than blocking. The MCP protocol's standard error responses handle this gracefully. The health check at startup (`/health`) prevents the MCP server from advertising tools before models are loaded.

---

## 2. Agentic Routing Endpoint

### Design Decision

Create `POST /agent/route` as a new endpoint separate from the existing `POST /search`. The search endpoint is optimized for the frontend (returns ranked lists for display); the route endpoint is optimized for agents (returns a single actionable recommendation with prompt text ready to use).

The key tradeoff is latency vs. precision. The routing endpoint runs the full pipeline (skill recall -> retrieval -> reranking) but returns only the top recommendation with resolved text, rather than a ranked list. This costs the same server-side compute but minimizes agent-side token consumption and decision overhead.

For the cold-start problem, the endpoint accepts a free-form `situation` string and infers all structured fields (intent, domain, stage, complexity) server-side using keyword heuristics and the existing taxonomy. An agent that has never seen this system can describe its situation in plain English and get a useful result. No configuration, no taxonomy knowledge required.

### Schema

#### Request: `POST /agent/route`

```json
{
  "type": "object",
  "properties": {
    "situation": {
      "type": "string",
      "minLength": 10,
      "maxLength": 2000,
      "description": "Natural language description of what the agent is doing, what went wrong, and what it needs next."
    },
    "stage": {
      "type": "string",
      "enum": ["clarify", "plan", "execute", "verify", "reflect"],
      "description": "Current workflow stage. Omit for auto-inference."
    },
    "domain": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Domain hints. Omit for auto-inference."
    },
    "intent": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Intent hints (build, debug, analyze, etc). Omit for auto-inference."
    },
    "complexity": {
      "type": "integer",
      "minimum": 1,
      "maximum": 5,
      "description": "Task complexity. Omit for auto-inference."
    },
    "prefer": {
      "type": "string",
      "enum": ["single", "skill", "auto"],
      "default": "auto"
    },
    "context": {
      "type": "object",
      "description": "Structured context that can be used to pre-fill template variables.",
      "properties": {
        "language": { "type": "string" },
        "framework": { "type": "string" },
        "error_message": { "type": "string" },
        "file_path": { "type": "string" },
        "project_type": { "type": "string" }
      },
      "additionalProperties": { "type": "string" }
    },
    "session_id": {
      "type": "string",
      "description": "If continuing a previous interaction, pass the session_id to maintain context."
    }
  },
  "required": ["situation"]
}
```

#### Response

```json
{
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": ["single", "skill", "chain", "clarify"],
      "description": "What was matched. 'clarify' means the situation is too ambiguous."
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "How well the recommendation matches the situation. Below 0.3 is a weak match."
    },
    "recommendation": {
      "type": "object",
      "description": "The recommended prompt or skill.",
      "properties": {
        "prompt_id": { "type": "string" },
        "prompt_text": {
          "type": "string",
          "description": "Full prompt text. If template variables could be filled from context, they are already resolved. Remaining unfilled variables are wrapped in {{variable_name}}."
        },
        "variables": {
          "type": "array",
          "description": "Template variables that still need values.",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "description": { "type": "string" },
              "type": { "type": "string", "default": "string" },
              "required": { "type": "boolean" },
              "inferred_value": {
                "type": "string",
                "description": "Value inferred from the context object. Null if not inferrable."
              }
            }
          }
        },
        "metadata": {
          "type": "object",
          "properties": {
            "intent": { "type": "array", "items": { "type": "string" } },
            "task_type": { "type": "array", "items": { "type": "string" } },
            "domain": { "type": "array", "items": { "type": "string" } },
            "primary_stage": { "type": "string" },
            "complexity_level": { "type": "integer" }
          }
        }
      }
    },
    "skill": {
      "type": "object",
      "description": "Present when mode=skill. Contains the full skill with all steps and a session_id for execution.",
      "properties": {
        "skill_id": { "type": "string", "format": "uuid" },
        "name": { "type": "string" },
        "slug": { "type": "string" },
        "routing_description": { "type": "string" },
        "session_id": {
          "type": "string",
          "description": "Use this to call /agent/step for each step in the skill."
        },
        "total_steps": { "type": "integer" },
        "steps_preview": {
          "type": "array",
          "description": "Summary of each step (stage + rationale) without full prompt text. Full text is returned step-by-step via /agent/step.",
          "items": {
            "type": "object",
            "properties": {
              "step_order": { "type": "integer" },
              "stage": { "type": "string" },
              "prompt_id": { "type": "string" },
              "rationale": { "type": "string" }
            }
          }
        },
        "first_step": {
          "type": "object",
          "description": "The full first step, ready to execute immediately.",
          "properties": {
            "step_order": { "type": "integer" },
            "stage": { "type": "string" },
            "prompt_id": { "type": "string" },
            "prompt_text": { "type": "string" },
            "variables": { "type": "array" }
          }
        }
      }
    },
    "alternatives": {
      "type": "array",
      "maxItems": 3,
      "description": "Other viable options. Summaries only, not full prompt text.",
      "items": {
        "type": "object",
        "properties": {
          "prompt_id": { "type": "string" },
          "summary": { "type": "string", "maxLength": 200 },
          "score": { "type": "number" },
          "mode": { "type": "string" }
        }
      }
    },
    "clarification_hint": {
      "type": "string",
      "description": "Present when confidence < 0.3 or mode=clarify. Suggests what additional information would improve results."
    },
    "inferred": {
      "type": "object",
      "description": "What the system inferred from the situation text. Useful for debugging mismatches.",
      "properties": {
        "domain": { "type": "array", "items": { "type": "string" } },
        "intent": { "type": "array", "items": { "type": "string" } },
        "stage": { "type": "string" },
        "complexity": { "type": "integer" }
      }
    },
    "trace_id": {
      "type": "string",
      "description": "Unique identifier for this request. Pass to /agent/feedback."
    }
  }
}
```

### Integration Snippet

```python
# Agent calling the routing endpoint directly (non-MCP)
import httpx

async def find_prompt(situation: str, **kwargs) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:1100/agent/route",
            json={"situation": situation, **kwargs},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()

# Example: LangChain tool wrapper
from langchain.tools import StructuredTool

capillaries_tool = StructuredTool.from_function(
    func=find_prompt,
    name="capillaries_find",
    description="Find the best prompt or skill for a task. Pass a natural language situation description.",
    args_schema=PromptFlowFindInput,  # Pydantic model matching the request schema
)
```

### Failure Mode

**Most likely failure:** Inference misclassifies the domain or stage, returning a prompt from the wrong category. Example: an agent says "I need to build a pricing model" and the system infers domain=["business"] when the agent means a machine learning pricing model (domain=["AI", "technical"]).

**Mitigation:** The response includes an `inferred` object showing exactly what the system inferred. An agent (or its human operator) can see the mismatch and re-call with explicit `domain` and `intent` hints. The routing pipeline applies inference only to fields not explicitly provided by the caller, so providing any structured hint overrides inference for that field. Additionally, the inference logic prioritizes words found in the prompt corpus taxonomy rather than relying on general-purpose NLU.

---

## 3. Skill Execution Protocol

### Design Decision

Use a **step-by-step callback model** rather than returning all steps upfront. Three reasons:

1. **Context window preservation.** A 5-step skill where each prompt is 1,000-2,000 characters would add 5,000-10,000 tokens to the agent's context just from the prompts. Returning one step at a time keeps the overhead to one prompt plus a compressed context summary.

2. **Failure isolation.** If step 2 fails, the agent does not need to parse and discard steps 3-5. It can report the failure, get guidance, or skip to a recovery step.

3. **Context flow.** The output of step N is meaningful input to step N+1. The server compresses previous outputs into a context summary that gets injected into the next prompt, so the agent does not need to manage this state.

The tradeoff is more round-trips (N calls for N steps instead of 1). This is acceptable because each call is lightweight (the server already has the skill loaded) and the alternative (all-upfront) wastes tokens and requires the agent to self-orchestrate handoffs.

The first step's full text is included in the `/agent/route` response so the agent can begin immediately without an extra round-trip.

### Schema

#### `POST /agent/step`

```json
{
  "request": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "From the /agent/route skill response."
      },
      "step_order": {
        "type": "integer",
        "minimum": 1,
        "description": "Step to execute. Must be current or next expected step."
      },
      "previous_output": {
        "type": "string",
        "maxLength": 50000,
        "description": "Output from the previous step. Server compresses this for context injection."
      },
      "variables": {
        "type": "object",
        "additionalProperties": { "type": "string" },
        "description": "Template variable values for this step."
      },
      "action": {
        "type": "string",
        "enum": ["execute", "skip", "abort"],
        "default": "execute",
        "description": "'skip' advances past this step with a note. 'abort' terminates the session."
      },
      "skip_reason": {
        "type": "string",
        "description": "Required when action=skip."
      }
    },
    "required": ["session_id", "step_order"]
  },
  "response": {
    "type": "object",
    "properties": {
      "session_id": { "type": "string" },
      "status": {
        "type": "string",
        "enum": ["ready", "completed", "aborted", "error"]
      },
      "current_step": {
        "type": "object",
        "properties": {
          "step_order": { "type": "integer" },
          "stage": { "type": "string" },
          "prompt_id": { "type": "string" },
          "prompt_text_resolved": {
            "type": "string",
            "description": "Full prompt with (a) template variables filled from the variables object and agent context, and (b) previous step context injected into a ## Prior Context section."
          },
          "rationale": { "type": "string" },
          "unfilled_variables": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "description": { "type": "string" }
              }
            }
          }
        }
      },
      "progress": {
        "type": "object",
        "properties": {
          "completed_steps": { "type": "integer" },
          "total_steps": { "type": "integer" },
          "is_final_step": { "type": "boolean" },
          "skipped_steps": {
            "type": "array",
            "items": { "type": "integer" }
          }
        }
      },
      "context_summary": {
        "type": "string",
        "description": "Compressed narrative of all previous step outputs. Updated after each step. Suitable for direct injection into a prompt. Max ~500 tokens regardless of how many steps have run."
      },
      "next_step_preview": {
        "type": "object",
        "description": "Lightweight preview of the next step (stage + rationale, no prompt text). Null on final step.",
        "properties": {
          "step_order": { "type": "integer" },
          "stage": { "type": "string" },
          "rationale": { "type": "string" }
        }
      }
    }
  }
}
```

### Session State Management

Sessions are stored server-side in a `skills.skill_sessions` table:

```sql
CREATE TABLE IF NOT EXISTS skills.skill_sessions (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id        UUID NOT NULL REFERENCES skills.skills(skill_id),
    trace_id        VARCHAR NOT NULL,
    current_step    INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'aborted', 'expired')),

    -- Context accumulator: compressed summary updated after each step
    context_summary TEXT DEFAULT '',

    -- Per-step outputs (append-only JSONB array)
    step_outputs    JSONB DEFAULT '[]',

    -- Metadata
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'),

    -- Variables provided by the agent across all steps
    agent_context   JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_skill_sessions_active
    ON skills.skill_sessions (session_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_skill_sessions_expire
    ON skills.skill_sessions (expires_at)
    WHERE status = 'active';
```

### Protocol flow

```
Agent                                Server
  |                                    |
  |--- POST /agent/route ------------->|  (situation: "build GTM strategy")
  |<-- {mode: "skill", skill: {        |
  |      session_id: "sess_abc",       |
  |      first_step: {prompt_text...}, |
  |      steps_preview: [...]          |
  |    }}                              |
  |                                    |
  | (Agent executes step 1 prompt)     |
  |                                    |
  |--- POST /agent/step {             -|->  (session_id: "sess_abc",
  |      step_order: 2,                |     step_order: 2,
  |      previous_output: "..."        |     previous_output: step 1 output)
  |    }                               |
  |<-- {current_step: {                |
  |      prompt_text_resolved: "...",  |     (context_summary includes step 1)
  |      ...                           |
  |    }, progress: {2/4, false}}      |
  |                                    |
  | (Agent executes step 2 prompt)     |
  |                                    |
  | ... repeats for steps 3, 4 ...     |
  |                                    |
  |--- POST /agent/step {step_order:4, |
  |      previous_output: "..."}       |
  |<-- {status: "completed",           |
  |     progress: {4/4, true},         |
  |     context_summary: "full..."}    |
  |                                    |
  |--- POST /agent/feedback {          |
  |      trace_id, outcome: "success"} |
  |<-- {acknowledged: true}            |
```

### Failure handling

**(a) Step produces unexpected output:** The agent can re-call the same `step_order` with action="execute" to retry. The server does not advance the step counter until a new step_order is requested. Maximum 3 retries per step, then the server suggests skipping.

**(b) Agent interrupted mid-skill:** Sessions have a 24-hour TTL. The agent can resume by calling `/agent/step` with the next step_order at any time before expiry. The `context_summary` persists server-side, so even if the agent has lost context, it can read the summary.

**(c) Step failure with no recovery:** The agent calls with `action="skip"` and `skip_reason`. The server notes the skip, advances to the next step, and adjusts the context summary to note the gap. Alternatively, `action="abort"` terminates the session and logs a partial run.

### Integration Snippet

```python
# Agent-side skill execution loop (pseudocode)
result = await capillaries_find(situation="build a GTM strategy for AI product")

if result["mode"] == "skill":
    session_id = result["skill"]["session_id"]
    # Step 1 is already in the response
    step1_prompt = result["skill"]["first_step"]["prompt_text"]
    step1_output = await agent.execute(step1_prompt)

    for step_num in range(2, result["skill"]["total_steps"] + 1):
        step = await capillaries_execute_step(
            session_id=session_id,
            step_order=step_num,
            previous_output=step1_output,
        )
        if step["status"] == "completed":
            break
        step_output = await agent.execute(step["current_step"]["prompt_text_resolved"])
        step1_output = step_output  # carry forward for next step

    await capillaries_feedback(trace_id=result["trace_id"], outcome="success")
```

### Failure Mode

**Most likely failure:** Context summary becomes stale or loses critical details from early steps by the time the agent reaches step 4 or 5. The 500-token compression limit might discard specifics that a later step needs.

**Mitigation:** The context summary is generated using a structured compression approach: each step's output is reduced to key decisions, artifacts produced, and constraints established. The summary is cumulative (not just the last step). If an agent finds the summary insufficient, it can pass its own `variables` to inject specific values it remembers from earlier steps. The `step_outputs` JSONB array stores full uncompressed outputs server-side, so a future "expand context" call could retrieve the full history for a specific step if needed (not in MVP, but the data is preserved).

---

## 4. Feedback and Learning Loop

### Design Decision

Two tiers of feedback: **lightweight** (2 required fields, agent sends automatically) and **rich** (optional detailed post-mortem). The lightweight signal is cheap enough that every agent tool call can include it without meaningful overhead. The rich signal is for cases where something interesting happened (failure, unexpected success, prompt modification).

Feedback flows into two places: (1) `skills.skill_runs` for skill-level scoring (updates `success_rate`, `total_runs`), and (2) a new `agent_feedback` table for prompt-level signal that informs future reranking.

The key tradeoff is trust: agent self-reported quality scores are noisy (the agent may not know whether its output was actually good). The system weights outcome (success/failure) heavily and treats quality_score as a softer signal. Hard signals (the agent explicitly aborted, or the same prompt was skipped 5 times by different agents) are more actionable than quality scores.

### Schema

#### `POST /agent/feedback`

```json
{
  "request": {
    "type": "object",
    "properties": {
      "trace_id": {
        "type": "string",
        "description": "From the original /agent/route response."
      },
      "outcome": {
        "type": "string",
        "enum": ["success", "partial", "failure", "skipped"],
        "description": "Overall outcome of using the recommended prompt/skill."
      },
      "quality_score": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "0=useless, 1=perfect. Optional."
      },
      "failure_step": {
        "type": "integer",
        "description": "If a skill execution failed, which step. Optional."
      },
      "failure_reason": {
        "type": "string",
        "enum": [
          "irrelevant",
          "too_vague",
          "too_specific",
          "wrong_domain",
          "wrong_stage",
          "outdated",
          "template_unfillable",
          "other"
        ],
        "description": "Category of the failure. Optional."
      },
      "notes": {
        "type": "string",
        "maxLength": 2000,
        "description": "Free-form feedback: what went wrong, what was missing, what you'd change."
      },
      "prompt_modifications": {
        "type": "array",
        "description": "If the agent modified the prompt before using it, describe what changed.",
        "items": {
          "type": "object",
          "properties": {
            "prompt_id": { "type": "string" },
            "modification": { "type": "string" },
            "reason": { "type": "string" }
          }
        }
      },
      "session_id": {
        "type": "string",
        "description": "If this is feedback for a skill execution session."
      },
      "per_step_feedback": {
        "type": "array",
        "description": "Per-step feedback for multi-step skill executions.",
        "items": {
          "type": "object",
          "properties": {
            "step_order": { "type": "integer" },
            "outcome": { "type": "string", "enum": ["success", "partial", "failure", "skipped"] },
            "notes": { "type": "string" }
          }
        }
      }
    },
    "required": ["trace_id", "outcome"]
  },
  "response": {
    "type": "object",
    "properties": {
      "acknowledged": { "type": "boolean" },
      "feedback_id": { "type": "string", "format": "uuid" }
    }
  }
}
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS skills.agent_feedback (
    feedback_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        VARCHAR NOT NULL,
    session_id      UUID REFERENCES skills.skill_sessions(session_id),

    -- What was recommended
    mode            VARCHAR NOT NULL,  -- 'single', 'skill', 'chain'
    prompt_id       VARCHAR,           -- for single-prompt recommendations
    skill_id        UUID,              -- for skill recommendations

    -- Agent's assessment
    outcome         VARCHAR NOT NULL CHECK (outcome IN ('success', 'partial', 'failure', 'skipped')),
    quality_score   FLOAT CHECK (quality_score BETWEEN 0 AND 1),
    failure_step    INTEGER,
    failure_reason  VARCHAR,
    notes           TEXT,

    -- Prompt modifications (JSONB array)
    prompt_modifications JSONB DEFAULT '[]',

    -- Per-step feedback (JSONB array)
    per_step_feedback    JSONB DEFAULT '[]',

    -- Context at time of feedback
    situation_text  TEXT,              -- original situation from the route request
    inferred_domain VARCHAR[],
    inferred_stage  VARCHAR,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_feedback_prompt
    ON skills.agent_feedback (prompt_id, created_at DESC)
    WHERE prompt_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_feedback_skill
    ON skills.agent_feedback (skill_id, created_at DESC)
    WHERE skill_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_feedback_outcome
    ON skills.agent_feedback (outcome);
```

### Feedback Integration Pipeline

Feedback data flows into scoring through a periodic aggregation job (not inline with the feedback write, to avoid latency):

```sql
-- Update skill success_rate from recent feedback (run every N minutes or on-demand)
UPDATE skills.skills s
SET
    success_rate = sub.success_rate,
    total_runs = sub.total_runs
FROM (
    SELECT
        skill_id,
        COUNT(*) AS total_runs,
        AVG(CASE
            WHEN outcome = 'success' THEN 1.0
            WHEN outcome = 'partial' THEN 0.5
            WHEN outcome = 'failure' THEN 0.0
            ELSE NULL
        END) AS success_rate
    FROM skills.agent_feedback
    WHERE skill_id IS NOT NULL
      AND outcome != 'skipped'
    GROUP BY skill_id
) sub
WHERE s.skill_id = sub.skill_id;
```

For prompt-level scoring (influences reranking), a `quality_prior` is derived from feedback:

```sql
-- Materialized view for prompt quality prior (refreshed periodically)
CREATE MATERIALIZED VIEW IF NOT EXISTS prompt_quality_prior AS
SELECT
    prompt_id,
    COUNT(*) AS feedback_count,
    AVG(CASE
        WHEN outcome = 'success' THEN 1.0
        WHEN outcome = 'partial' THEN 0.5
        WHEN outcome = 'failure' THEN 0.0
        ELSE NULL
    END) AS success_rate,
    AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) AS avg_quality,
    -- Bayesian average: blend with global prior (0.5) until enough samples
    (COUNT(*) * AVG(CASE WHEN outcome = 'success' THEN 1.0 WHEN outcome = 'partial' THEN 0.5 ELSE 0.0 END)
     + 5 * 0.5) / (COUNT(*) + 5) AS bayesian_quality
FROM skills.agent_feedback
WHERE prompt_id IS NOT NULL
  AND outcome != 'skipped'
GROUP BY prompt_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pqp_prompt
    ON prompt_quality_prior (prompt_id);
```

The `bayesian_quality` score can be used as a reranking signal: prompts with strong feedback history get a small boost, while prompts with consistent failures get penalized.

### Integration Snippet

```python
# Minimum viable feedback (agent sends this automatically after every tool use)
await capillaries_feedback(
    trace_id="pf_tr_20260518_a3f7d8e3",
    outcome="success"
)

# Rich feedback after a skill execution
await capillaries_feedback(
    trace_id="pf_tr_20260518_a3f7d8e3",
    outcome="partial",
    quality_score=0.6,
    failure_step=3,
    failure_reason="too_vague",
    notes="Step 3 (verify) prompt asked for test results but didn't specify what format. Had to improvise.",
    session_id="sess_abc",
    per_step_feedback=[
        {"step_order": 1, "outcome": "success"},
        {"step_order": 2, "outcome": "success"},
        {"step_order": 3, "outcome": "partial", "notes": "verify prompt too generic for this use case"},
        {"step_order": 4, "outcome": "skipped"}
    ]
)
```

### Failure Mode

**Most likely failure:** Agents never send feedback because the tool call is optional and adds latency. Over time, the feedback tables remain empty and the learning loop never materializes.

**Mitigation:** Two mechanisms. (1) The MCP tool `capillaries_find` includes a `trace_id` in every response, and the tool description for `capillaries_feedback` is worded to encourage feedback ("improves future recommendations"). (2) For skill executions, the server auto-logs a run in `skills.skill_runs` when a session completes (the final `/agent/step` call with is_final_step=true). This captures at minimum: skill_id, duration, number of completed vs. skipped steps. Even without explicit feedback calls, completion patterns provide signal.

Additionally, the system can detect implicit negative feedback: if the same situation text is routed twice within a short window (the agent tried the prompt and came back), that is a soft failure signal.

---

## 5. Discovery and Bootstrapping

### Design Decision

Three integration paths at three levels of coupling. Each path should get an agent from zero to "I found a useful prompt" in under 2 minutes of human setup time.

The tradeoff is between integration depth and setup friction. MCP gives the deepest integration (tools appear natively in the agent's tool list) but requires config files. OpenAPI gives broad compatibility but no native tool-use integration. The self-describing endpoint gives zero-friction discovery but requires the agent to understand HTTP.

### Path A: MCP Configuration (Claude Code, Cursor)

**Claude Code** (`~/.claude/settings.json` or project-level `.claude/settings.json`):

```json
{
  "mcpServers": {
    "capillaries": {
      "command": "python",
      "args": ["-m", "capillaries.mcp_server"],
      "cwd": "/path/to/capillaries",
      "env": {
        "OBSIDIAN_VAULT_PATH": "/home/user/Documents/Obsidian/Main Vault",
        "DB_HOST": "/var/run/postgresql",
        "DB_NAME": "capillaries"
      }
    }
  }
}
```

Alternatively, if the server is already running (recommended for shared use):

```json
{
  "mcpServers": {
    "capillaries": {
      "type": "sse",
      "url": "http://localhost:1100/mcp/sse"
    }
  }
}
```

**CLAUDE.md** snippet (add to project root or `~/.claude/CLAUDE.md`):

```markdown
## Prompt Flow Integration

This project has access to a prompt and skill retrieval system via MCP tools.

When you encounter a task that would benefit from a structured approach - debugging,
architecture review, planning, analysis, code generation - use `capillaries_find`
to get a proven prompt template for the situation. Describe your current situation
naturally.

For multi-step tasks (building a strategy, conducting a review, designing a system),
the system may return a skill - a validated multi-step workflow. Execute it step by
step using `capillaries_execute_step`.

After using a prompt or skill, report the outcome via `capillaries_feedback`.

Available tools:
- `capillaries_find` - Find the best prompt or skill for your situation
- `capillaries_execute_step` - Execute next step in a multi-step skill
- `capillaries_feedback` - Report whether a prompt/skill worked
- `capillaries_catalog` - Browse available capabilities
```

**Cursor** (`.cursor/mcp.json` in project root):

```json
{
  "mcpServers": {
    "capillaries": {
      "command": "python",
      "args": ["-m", "capillaries.mcp_server"],
      "cwd": "/path/to/capillaries",
      "env": {
        "OBSIDIAN_VAULT_PATH": "/home/user/Documents/Obsidian/Main Vault"
      }
    }
  }
}
```

### Path B: OpenAPI Auto-Discovery (LangChain, CrewAI, LangGraph)

The FastAPI app already generates an OpenAPI schema. The agent endpoints are added under the `/agent` prefix with tags and detailed descriptions:

```python
# In server.py - the OpenAPI schema is auto-generated by FastAPI
app = FastAPI(
    title="Prompt Flow",
    description="Semantic prompt and skill retrieval for AI agents. "
                "Start with POST /agent/route to find the best prompt for your situation.",
    version="2.0.0",
    servers=[{"url": "http://localhost:1100", "description": "Local"}],
)
```

**LangChain integration:**

```python
from langchain_community.agent_toolkits.openapi import planner
from langchain_community.utilities.openapi import OpenAPISpec

spec = OpenAPISpec.from_url("http://localhost:1100/openapi.json")
agent = planner.create_openapi_agent(spec, llm, allow_dangerous_requests=True)
```

**CrewAI integration:**

```python
from crewai_tools import APITool

capillaries_find = APITool(
    name="capillaries_find",
    description="Find the best prompt or skill for a task",
    base_url="http://localhost:1100",
    endpoint="/agent/route",
    method="POST",
    headers={"Content-Type": "application/json"},
)
```

### Path C: Self-Describing Endpoint

A single endpoint that any HTTP-capable agent can hit to learn what the system offers and how to use it:

#### `GET /agent/discover`

```json
{
  "service": "Prompt Flow",
  "version": "2.0.0",
  "description": "Semantic prompt and skill retrieval. I store ~1000 reusable prompts across 10 domains and 5 workflow stages. Search with natural language, get back ready-to-use prompt text.",
  "quickstart": "POST /agent/route with {\"situation\": \"describe what you need\"} to get started.",
  "capabilities": {
    "prompt_search": "Find individual prompts by natural language query",
    "skill_matching": "Match validated multi-step workflows to complex tasks",
    "template_resolution": "Fill prompt template variables from context",
    "feedback_loop": "Report outcomes to improve future recommendations"
  },
  "endpoints": {
    "route": {
      "method": "POST",
      "path": "/agent/route",
      "description": "Primary entry point. Describe your situation, get the best prompt or skill.",
      "example_request": {
        "situation": "I need to debug a memory leak in a Python web application"
      }
    },
    "step": {
      "method": "POST",
      "path": "/agent/step",
      "description": "Execute next step of a multi-step skill. Use session_id from /agent/route."
    },
    "feedback": {
      "method": "POST",
      "path": "/agent/feedback",
      "description": "Report outcome. Minimum: {trace_id, outcome}."
    },
    "catalog": {
      "method": "GET",
      "path": "/agent/catalog",
      "description": "Browse available domains, skills, and statistics."
    },
    "health": {
      "method": "GET",
      "path": "/health",
      "description": "Service liveness check."
    },
    "openapi": {
      "method": "GET",
      "path": "/openapi.json",
      "description": "Full OpenAPI 3.1 schema for all endpoints."
    }
  },
  "stats": {
    "total_prompts": 572,
    "total_skills": 12,
    "domains": ["AI", "business", "career", "finance", "learning", "personal", "product", "strategy", "technical", "writing"],
    "stages": ["clarify", "plan", "execute", "verify", "reflect"]
  },
  "mcp": {
    "supported": true,
    "sse_endpoint": "/mcp/sse",
    "tools": ["capillaries_find", "capillaries_execute_step", "capillaries_feedback", "capillaries_catalog"]
  }
}
```

This endpoint is static (changes only on deploy), so it can be cached aggressively by agents.

### Integration Snippet

```python
# Zero-config agent discovery (any HTTP client)
import httpx

# Step 1: Discover
discovery = httpx.get("http://localhost:1100/agent/discover").json()
route_endpoint = discovery["endpoints"]["route"]

# Step 2: Use
result = httpx.post(
    f"http://localhost:1100{route_endpoint['path']}",
    json={"situation": "I need to review a pull request for security issues"},
).json()

print(result["recommendation"]["prompt_text"])
```

### Failure Mode

**Most likely failure:** Claude Code agents discover the MCP tools but never autonomously use them because the CLAUDE.md instructions are not specific enough about when to invoke `capillaries_find`. The tools sit idle.

**Mitigation:** The CLAUDE.md snippet above uses action-oriented language ("When you encounter...") rather than passive description. The tool descriptions themselves are written to match common agent internal reasoning patterns: when an agent thinks "I need a structured approach to this debugging task," the phrase "structured approach" in the tool description triggers tool selection. Testing with a set of 10 representative agent scenarios (provided in the bootstrap checklist) validates that the descriptions achieve >80% self-selection accuracy.

---

## 6. Prompt Template Resolution

### Design Decision

Template resolution is handled **server-side** as part of the `/agent/route` and `/agent/step` responses. The agent never receives a raw template it must parse; it receives (a) the prompt text with known variables filled, (b) a list of remaining unfilled variables with descriptions and types, and (c) inferred values for variables that match the agent's provided context.

The key tradeoff: server-side resolution means the server must understand variable extraction and type inference. But the alternative (agents parsing `{{placeholder}}` syntax themselves) leads to inconsistency across different agent frameworks, and agents may fill variables incorrectly without type hints.

Template variables use `{{variable_name}}` syntax. The server extracts these via regex, matches them against (a) the prompt's `input_schema` if populated, (b) the agent's `context` object from the request, and (c) a heuristic type inference based on common variable names.

### Schema

#### Variable Resolution Pipeline

```
1. Extract variables: regex scan for {{...}} patterns in prompt_text
2. Match to schema: if prompt has input_schema, use it for name/type/description
3. Match to context: for each variable, check if agent's context object has a matching key
4. Infer from situation: for common patterns ({{language}}, {{error}}, {{file_path}}),
   extract from the situation text using keyword matching
5. Resolve: fill matched variables into prompt text
6. Report: return unfilled variables with descriptions
```

#### Variable Metadata Object

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Variable name as it appears in the template (without braces)."
    },
    "description": {
      "type": "string",
      "description": "What this variable represents. Derived from input_schema or inferred."
    },
    "type": {
      "type": "string",
      "enum": ["string", "text", "number", "list", "code_block", "file_path", "url"],
      "default": "string",
      "description": "Expected value type."
    },
    "required": {
      "type": "boolean",
      "default": true,
      "description": "Whether the prompt makes sense without this variable."
    },
    "inferred_value": {
      "type": "string",
      "description": "Value inferred from agent context. Null if not inferrable. Agent should verify before using."
    },
    "source": {
      "type": "string",
      "enum": ["context", "situation", "default", "none"],
      "description": "Where the inferred_value came from."
    }
  }
}
```

#### Common Variable Name Heuristics

The server maintains a lookup table for common variable patterns:

```python
VARIABLE_HEURISTICS = {
    # Pattern -> (type, description, context_key)
    "language":         ("string", "Programming language", "language"),
    "programming_language": ("string", "Programming language", "language"),
    "framework":        ("string", "Framework or library", "framework"),
    "error":            ("text", "Error message or traceback", "error_message"),
    "error_message":    ("text", "Error message or traceback", "error_message"),
    "error_traceback":  ("code_block", "Full error traceback", "error_message"),
    "file_path":        ("file_path", "Path to the relevant file", "file_path"),
    "file":             ("file_path", "Path to the relevant file", "file_path"),
    "code":             ("code_block", "Code snippet to analyze", None),
    "code_snippet":     ("code_block", "Code snippet to analyze", None),
    "project":          ("string", "Project name or description", "project_type"),
    "project_type":     ("string", "Type of project", "project_type"),
    "url":              ("url", "URL to reference", None),
    "topic":            ("string", "Topic or subject", None),
    "audience":         ("string", "Target audience", None),
    "target_audience":  ("string", "Target audience", None),
    "goal":             ("string", "Objective or goal", None),
    "timeframe":        ("string", "Time period or deadline", None),
    "context":          ("text", "Background context", None),
    "requirements":     ("text", "Requirements or specifications", None),
    "constraints":      ("text", "Constraints or limitations", None),
}
```

### Integration Snippet

```python
# Server-side resolution logic (simplified)
import re

TEMPLATE_PATTERN = re.compile(r'\{\{(\w+)\}\}')

def resolve_template(
    prompt_text: str,
    agent_context: dict,
    situation: str,
    input_schema: dict | None = None,
) -> tuple[str, list[dict]]:
    """
    Resolve template variables in a prompt.

    Returns (resolved_text, unfilled_variables).
    """
    variables = TEMPLATE_PATTERN.findall(prompt_text)
    if not variables:
        return prompt_text, []

    resolved_text = prompt_text
    unfilled = []

    for var_name in set(variables):
        # 1. Check agent context
        value = agent_context.get(var_name)
        source = "context" if value else None

        # 2. Check heuristic mapping
        if not value and var_name in VARIABLE_HEURISTICS:
            vtype, desc, context_key = VARIABLE_HEURISTICS[var_name]
            if context_key and context_key in agent_context:
                value = agent_context[context_key]
                source = "context"

        # 3. Check input_schema
        schema_info = {}
        if input_schema and var_name in input_schema.get("types", {}):
            schema_info = {
                "type": input_schema["types"][var_name],
                "required": var_name in input_schema.get("required", []),
            }

        if value:
            # Fill the variable
            resolved_text = resolved_text.replace(f"{{{{{var_name}}}}}", str(value))
        else:
            # Report as unfilled
            heuristic = VARIABLE_HEURISTICS.get(var_name, ("string", f"Value for {var_name}", None))
            unfilled.append({
                "name": var_name,
                "description": schema_info.get("description", heuristic[1]),
                "type": schema_info.get("type", heuristic[0]),
                "required": schema_info.get("required", True),
                "inferred_value": None,
                "source": "none",
            })

    return resolved_text, unfilled
```

### Failure Mode

**Most likely failure:** The prompt corpus has inconsistent variable naming (`{{code}}` vs `{{code_snippet}}` vs `{{source_code}}`). The heuristic table covers some but not all patterns, leading to variables that should be filled from context but are not.

**Mitigation:** The heuristic table is a starting point, not the final solution. Two paths forward: (1) A batch job that scans all prompts for `{{...}}` patterns and builds a frequency table of variable names. The top 50 patterns cover the majority of usage and should all be in the heuristic table. (2) Populating the `input_schema` field on prompts (currently 0% filled per docs/schema.md) provides authoritative variable metadata that overrides heuristics. The design falls back gracefully: even unrecognized variables are reported to the agent with their raw name and a generic description, so the agent can still fill them.

---

## 7. Bootstrap Checklist

Implementation steps ordered by dependency, with the smallest useful milestone marked.

### Phase 0: Database Additions (1-2 days)

- [ ] Create `skills.skill_sessions` table (schema in section 3)
- [ ] Create `skills.agent_feedback` table (schema in section 4)
- [ ] Create `prompt_quality_prior` materialized view (section 4)
- [ ] Add indexes per the schemas above
- [ ] Verify backward compatibility: existing `POST /search`, `GET /prompts/{id}`, `GET /health` unchanged

### Phase 1: Routing Endpoint --- SMALLEST USEFUL MILESTONE (3-5 days)

- [ ] Implement situation-to-query inference (keyword extraction, domain/stage/intent classification from free text)
- [ ] Implement `POST /agent/route` endpoint
  - Internally delegates to existing `PromptSearch.search()` for retrieval
  - Wraps response in the agent-optimized schema
  - Adds `trace_id` generation
  - Single-prompt mode only (no skill matching yet)
- [ ] Implement template variable extraction (`{{...}}` regex scan)
- [ ] Implement basic variable resolution from agent `context` object
- [ ] Implement `GET /agent/discover` static endpoint
- [ ] Implement `GET /agent/catalog` with live stats from DB
- [ ] Add tests: 10 representative situations covering each domain, verify correct prompt retrieval

**At this point: an agent can call `POST /agent/route` with a situation description and get back a ready-to-use prompt. This is the minimum viable integration.**

### Phase 2: MCP Server (2-3 days)

- [ ] Create `src/capillaries/mcp_server.py` with FastMCP
- [ ] Implement `capillaries_find` tool (wraps `/agent/route`)
- [ ] Implement `capillaries_catalog` tool (wraps `/agent/catalog`)
- [ ] Implement `capillaries_feedback` tool (wraps `/agent/feedback`)
- [ ] Test with Claude Code: add MCP config, verify tools appear, run 5 test scenarios
- [ ] Write CLAUDE.md integration snippet
- [ ] Write Cursor MCP config

### Phase 3: Feedback Loop (2-3 days)

- [ ] Implement `POST /agent/feedback` endpoint
- [ ] Wire feedback writes to `skills.agent_feedback` table
- [ ] Wire skill feedback to `skills.skill_runs` (reuse existing `SkillRecall.log_run()`)
- [ ] Implement periodic aggregation job (update `success_rate`, refresh materialized view)
- [ ] Add `capillaries_feedback` to MCP server
- [ ] Test: submit 20 feedback entries, verify aggregation updates quality scores

### Phase 4: Skill Execution Protocol (3-5 days)

- [ ] Implement session creation in `/agent/route` when a skill is matched
- [ ] Implement `POST /agent/step` endpoint
  - Session lookup and validation
  - Previous output compression into context_summary
  - Template resolution with accumulated context
  - Step advancement logic (execute, skip, abort)
- [ ] Implement session TTL and cleanup (24-hour expiry)
- [ ] Add `capillaries_execute_step` to MCP server
- [ ] Test: execute a full skill end-to-end via MCP from Claude Code

### Phase 5: Advanced Features (ongoing)

- [ ] Implement variable heuristic table scan across all prompts (build frequency map)
- [ ] Populate `input_schema` on top-50 most-used prompts
- [ ] Add reranking boost from `prompt_quality_prior` materialized view
- [ ] Implement implicit negative feedback detection (repeat routing within short window)
- [ ] Add SSE transport for MCP server (`/mcp/sse`)
- [ ] Add auth header support for non-local deployments
- [ ] Build OpenAPI-first LangChain/CrewAI integration examples
- [ ] Expand context summary compression (currently heuristic, consider LLM-based compression for high-value skills)

### Testing Scenarios for Validation

These 10 scenarios should be used to validate that tool descriptions achieve good agent self-selection:

1. "I'm debugging a Python ImportError with circular imports" -> should return a debug prompt
2. "I need to write a go-to-market strategy for a B2B SaaS product" -> should return a skill (GTM workflow)
3. "Review this pull request for security issues" -> should return a code review / security prompt
4. "Help me understand the tradeoffs between microservices and monolith" -> should return an analysis/comparison prompt
5. "I need to optimize a slow SQL query that's timing out" -> should return a technical optimization prompt
6. "Plan a 2-week sprint for a new feature" -> should return a planning prompt (stage=plan)
7. "Write unit tests for this authentication module" -> should return a test generation prompt (stage=verify)
8. "What did we learn from the last product launch?" -> should return a reflection prompt (stage=reflect)
9. "I have customer churn data and need to find patterns" -> should return a data analysis prompt
10. "Explain how transformer attention mechanisms work to a junior developer" -> should return an explanation prompt

Each scenario should be tested for: (a) correct domain inference, (b) correct stage inference, (c) prompt relevance (top-1 precision), (d) template variables correctly identified.
