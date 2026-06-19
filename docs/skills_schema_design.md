# Skills Schema Design

Date: 2026-03-30
Status: Draft

## Overview

Skills are persistent, versioned chain compositions built from individual prompts in `public.prompts`. They live in a separate PostgreSQL schema (`skills`) within the same `capillaries` database, preserving foreign key integrity with the prompts table while maintaining logical separation.

The orchestrator has two modes:
1. **Build** — dynamically compose a chain for a novel request (Phase 1 spec)
2. **Recall** — match an existing validated skill when a request closely fits one

Successful builds get persisted as skills, so the system compounds over time.

## Schema: `skills`

### `skills.skills`

The core skill record. Represents a validated chain that an agent can invoke as a single unit.

```sql
CREATE SCHEMA IF NOT EXISTS skills;

CREATE TABLE skills.skills (
    skill_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR NOT NULL,

    -- Routing: single-line, agent-optimized trigger description.
    -- This is the primary signal an orchestrator uses to match a request to a skill.
    -- Must stay on one line. Be specific: name artifact types, trigger phrases, output shape.
    routing_description TEXT NOT NULL,

    -- Contracts
    input_contract  JSONB NOT NULL DEFAULT '{}',   -- what the skill expects (required fields, data types, constraints)
    output_contract JSONB NOT NULL DEFAULT '{}',    -- what it produces (format, sections, structure)

    -- Edge cases: explicit failure modes and handling instructions.
    -- Agents cannot infer these from common sense; write them down.
    edge_cases      TEXT[] DEFAULT '{}',

    -- Classification (mirrors prompt-level taxonomy for routing)
    intent          VARCHAR[] DEFAULT '{}',
    task_type       VARCHAR[] DEFAULT '{}',
    domain          VARCHAR[] DEFAULT '{}',
    complexity_level INTEGER CHECK (complexity_level BETWEEN 1 AND 5),

    -- Versioning
    version         INTEGER NOT NULL DEFAULT 1,
    parent_skill_id UUID REFERENCES skills.skills(skill_id),  -- links to prior version

    -- Quality metrics (populated by test runs and usage feedback)
    confidence      FLOAT,           -- overall reliability score
    success_rate    FLOAT,           -- % of invocations rated successful
    total_runs      INTEGER DEFAULT 0,

    -- Lifecycle
    status          VARCHAR DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'deprecated', 'archived')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by      VARCHAR DEFAULT 'orchestrator'  -- 'orchestrator' | 'manual'
);
```

### `skills.skill_steps`

Ordered mapping of prompts within a skill. Each step maps to a workflow stage and defines how context flows between prompts.

```sql
CREATE TABLE skills.skill_steps (
    id              SERIAL PRIMARY KEY,
    skill_id        UUID NOT NULL REFERENCES skills.skills(skill_id) ON DELETE CASCADE,
    prompt_id       VARCHAR NOT NULL REFERENCES public.prompts(prompt_id),
    step_order      INTEGER NOT NULL,
    stage           VARCHAR NOT NULL CHECK (stage IN ('clarify', 'plan', 'execute', 'verify', 'reflect')),

    -- Why this prompt was selected for this step (provenance from the orchestrator)
    rationale       TEXT,

    -- Per-step evidence scores from retrieval (mirrors Phase 1 Candidate schema)
    evidence        JSONB DEFAULT '{}',

    -- Context handoff: what this step passes to the next step
    -- Ensures composability — downstream steps know what they're receiving
    output_mapping  JSONB DEFAULT '{}',

    UNIQUE (skill_id, step_order)
);
```

### `skills.skill_runs`

Append-only log of every time a skill is invoked. Feeds back into confidence and success_rate on the parent skill.

```sql
CREATE TABLE skills.skill_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id        UUID NOT NULL REFERENCES skills.skills(skill_id),
    task_id         UUID,                    -- links to the originating TaskSpec
    trace_id        VARCHAR,                 -- observability trace

    -- Outcome
    status          VARCHAR CHECK (status IN ('success', 'partial', 'failure', 'aborted')),
    feedback_score  FLOAT,                   -- user or agent rating (0-1)
    feedback_notes  TEXT,

    -- Timing
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP,
    duration_ms     INTEGER,

    -- Snapshot of which prompt versions were used (content_hash at run time)
    step_hashes     JSONB DEFAULT '[]'       -- [{prompt_id, content_hash}, ...]
);
```

### `skills.skill_tests`

Versioned test cases for quantitative validation. Run these against a skill after changes to confirm it still performs.

```sql
CREATE TABLE skills.skill_tests (
    test_id         SERIAL PRIMARY KEY,
    skill_id        UUID NOT NULL REFERENCES skills.skills(skill_id) ON DELETE CASCADE,
    test_name       VARCHAR NOT NULL,

    -- Input fixture
    test_input      JSONB NOT NULL,          -- simulated TaskSpec or equivalent

    -- Expected behavior
    expected_mode   VARCHAR CHECK (expected_mode IN ('single', 'chain', 'clarify')),
    expected_prompts VARCHAR[],              -- prompt_ids that should appear in output
    expected_stages VARCHAR[],               -- stages that should be covered
    quality_threshold FLOAT DEFAULT 0.7,     -- minimum confidence to pass

    -- Results from last run
    last_result     VARCHAR CHECK (last_result IN ('pass', 'fail', 'skip')),
    last_run_at     TIMESTAMP,
    last_score      FLOAT,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Indexes

```sql
-- Skill retrieval by routing signals
CREATE INDEX idx_skills_intent ON skills.skills USING GIN (intent);
CREATE INDEX idx_skills_task_type ON skills.skills USING GIN (task_type);
CREATE INDEX idx_skills_domain ON skills.skills USING GIN (domain);
CREATE INDEX idx_skills_status ON skills.skills (status);

-- Full-text search on routing descriptions
CREATE INDEX idx_skills_routing_fts ON skills.skills
    USING GIN (to_tsvector('english', routing_description));

-- Step lookups
CREATE INDEX idx_skill_steps_skill ON skills.skill_steps (skill_id, step_order);
CREATE INDEX idx_skill_steps_prompt ON skills.skill_steps (prompt_id);

-- Run history
CREATE INDEX idx_skill_runs_skill ON skills.skill_runs (skill_id, started_at DESC);
```

## Contract Examples

### input_contract

```json
{
  "required": ["target_audience", "timeframe", "content_type"],
  "optional": ["brand_voice_ref", "competitor_list"],
  "types": {
    "target_audience": "string",
    "timeframe": "string (e.g. '2 weeks')",
    "content_type": "string (e.g. 'newsletter', 'blog series')"
  }
}
```

### output_contract

```json
{
  "format": "markdown",
  "sections": ["executive_summary", "weekly_breakdown", "topic_list", "publishing_schedule"],
  "parseable_by_agent": true,
  "downstream_compatible": ["execute_stage", "verify_stage"]
}
```

### evidence (on skill_steps)

```json
{
  "dense_sim": 0.83,
  "bm25_sim": 0.72,
  "metadata_match": 0.78,
  "stage_fit": 0.92
}
```

## Relationship to Phase 1 Orchestrator

| Phase 1 Component | Skills Schema Interaction |
|---|---|
| IntakeAgent | Produces TaskSpec; skills.skill_runs logs the task_id |
| RetrieverAgent | Queries both `public.prompts` AND `skills.skills` for recall |
| PlannerAgent | Assembles chains; successful chains become `skills.skills` + `skills.skill_steps` |
| CriticAgent | Validates chains; edge_cases from existing skills inform critique |
| SelectorAgent | Compares dynamic chain vs recalled skill confidence |
| PackagerAgent | FinalOutput includes skill_id if a recalled skill was used |

## Lifecycle

```
Orchestrator builds a novel chain
  -> Chain validated by CriticAgent
  -> User confirms output is good (or agent rates it)
  -> Chain persisted as skill (status: draft)
  -> Skill accumulates runs and feedback
  -> Passes test suite -> status: active
  -> Subsequent similar requests recall this skill instead of rebuilding
  -> Skill refined over time -> version incremented, parent_skill_id links history
  -> Superseded or broken -> status: deprecated/archived
```

## Prompt Drift Policy

Skills always execute on **current prompt content**. Drift (a prompt's content changing after a skill was validated) is not a blocker and does not require immediate re-validation.

`pinned_hash` on each step and `step_hashes` on each run are **diagnostic tools**, not locks:
- If a skill's output quality degrades, diff `step_hashes` against `pinned_hash` to identify which prompts changed and when
- Drift review is periodic maintenance (e.g. monthly), triggered by observed quality drops — not by every prompt edit
- A changed prompt may be an improvement; forcing re-validation on every edit creates unnecessary friction

The status field is the quality gate. A skill stays `active` until its outputs are observed to be poor, at which point it moves to `deprecated` and a new version is built.

## Prompts Table Additions

Three fields to add to `public.prompts` to improve per-prompt agent readability:

```sql
ALTER TABLE public.prompts ADD COLUMN IF NOT EXISTS
    routing_description TEXT;  -- single-line trigger description for agent matching

ALTER TABLE public.prompts ADD COLUMN IF NOT EXISTS
    output_format TEXT;        -- what this prompt produces (markdown, JSON, table, etc.)

ALTER TABLE public.prompts ADD COLUMN IF NOT EXISTS
    known_edge_cases TEXT[] DEFAULT '{}';  -- failure modes and handling instructions
```

These fields are backfilled via batch classification (same pipeline as intent/domain/task_type) and improve both direct prompt retrieval and the quality of skills composed from those prompts.
