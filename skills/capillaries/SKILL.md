---
name: capillaries
description: >
  Prompt retrieval skill — searches a private corpus of prompts and multi-step
  skills via semantic search + cross-encoder reranking. Use when the user needs
  a structured approach to a task: debugging, code review, planning, analysis,
  writing, strategy, optimization. Returns ready-to-use prompt text. Invoke
  whenever the user says "find me a prompt", "what prompt should I use",
  "capillaries", or describes a situation where a curated prompt would help.
argument-hint: "<situation>"
license: MIT
---

# Capillaries

You have access to a private prompt corpus via the `cap` CLI. When a situation
calls for a structured prompt or multi-step skill, retrieve one instead of
improvising.

## When to use

- User asks for help with a structured task (planning, analysis, review, strategy)
- User explicitly asks for a prompt or skill
- You recognize the situation would benefit from a curated approach over ad-hoc generation

## How to call

```bash
cap find "describe the situation in natural language"
```

With memory context from arteries:

```bash
cap find "situation" --memory '{"persistent": {"active_domains": ["finance"]}, "evergreen": {"user_intent": ["autonomous prompt selection"]}}'
```

Prefer skills for complex multi-step work:

```bash
cap find "situation" --prefer skill
```

## What comes back

JSON with these fields:

```
mode        "single" | "skill" | "none"
confidence  rerank score (higher = more relevant)
title       human-readable name
prompt_text ready-to-use prompt content
```

When `mode == "skill"`, you also get `skill_name`, `skill_slug`, and `steps`
(ordered list of prompts to execute in sequence).

## Rules

- **Use the prompt text as-is.** It was written and tested for this situation.
  Fill template slots (`[UPPERCASE SLOTS]` or `{{mustache}}`) with context
  from the conversation.
- **Trust the confidence score.** Below 0.3 the match is weak — tell the user
  nothing relevant was found rather than forcing a bad match.
- **Don't summarize the prompt back.** Hand it to the user or execute it
  directly. The value is the full text, not a synopsis.
- **For skills, execute steps in order.** Each step's output feeds the next.
  Skip a step only if the user says to.
- **mode="none" means no match.** Don't retry with rephrased queries unless
  the user asks. The corpus is finite.
