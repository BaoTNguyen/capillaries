# Prompt Optimization & Lifecycle Management — Implementation Spec

**Date:** 2026-06-17
**Status:** Draft
**Depends on:** PostgreSQL 16 + pgvector, DSPy, existing capillaries infrastructure

---

## 1. Overview

Two interconnected features:

1. **DSPy-based prompt optimization** — tune prompt text using golden examples, store per-model variants, serve the right variant at runtime based on the active model.
2. **Evidence-based lifecycle management** — unified `draft/active/inactive` status, auto-inactivation after 6 months of disuse, advisory cascade to dependent skills, quarterly review surface.

Design principles:
- Postgres is the source of truth. Obsidian sync is a convenience layer.
- Minimal human involvement — quarterly review cadence, not daily triage.
- Never auto-delete. Only auto-transition `active → inactive`.
- Advisory cascades only — flag dependencies, don't auto-transition them.

---

## 2. Schema Changes

### 2.1 Status Unification

Unify both `prompts` and `skills.skills` to use `draft / active / inactive`.

**Migration: `prompts.status`**

Current CHECK: `('active', 'deferred', 'archived')`

```sql
-- Remap existing values
UPDATE prompts SET status = 'inactive' WHERE status IN ('deferred', 'archived');

-- Replace constraint
ALTER TABLE prompts DROP CONSTRAINT IF EXISTS prompts_status_check;
ALTER TABLE prompts ADD CONSTRAINT prompts_status_check
    CHECK (status IN ('draft', 'active', 'inactive'));
```

**Migration: `skills.skills.status`**

Current CHECK: `('draft', 'active', 'deprecated', 'archived')`

```sql
UPDATE skills.skills SET status = 'inactive' WHERE status IN ('deprecated', 'archived');

ALTER TABLE skills.skills DROP CONSTRAINT IF EXISTS skills_status_check;
ALTER TABLE skills.skills ADD CONSTRAINT skills_status_check
    CHECK (status IN ('draft', 'active', 'inactive'));
```

**Code changes:**
- `obsidian_sync/ingest.py:52` — update validation: `v if v in ('draft', 'active', 'inactive') else 'active'`
- `obsidian_sync/frontmatter.py` — FIELD_MAP status transform: accept/emit the new values
- `src/capillaries/skills/promote.py:312-319` — rename `deprecate()` to `inactivate()`, update `_set_status` calls
- `src/capillaries/db/setup.py:34` — update CHECK constraint in CREATE TABLE
- `src/capillaries/db/setup_skills.py:59-60` — update CHECK constraint

### 2.2 Drop `parent_prompt`

The column doesn't exist in the live schema (`setup.py`), but references persist in docs and a stale worktree.

**Files to update:**
- `docs/schema.md:44` — remove parent_prompt row from table
- `docs/prompt_picker_discovery_and_plan.md:190,212` — remove references
- `docs/phase1_agentic_orchestration_implementation_spec.md:72,175` — remove from JSON example and neighbor expansion bullet

No DB migration needed — the column was never created in the current schema.

### 2.3 Drop `models_tested` Column

Replace with derived query from the new `prompt_variants` table.

```sql
ALTER TABLE prompts DROP COLUMN IF EXISTS models_tested;
```

**Code changes:**
- `obsidian_sync/ingest.py` — remove `models_tested` from field_mappings, insert_sql, and batch_data
- `obsidian_sync/frontmatter.py` — remove `models_tested` from FIELD_MAP; replace with a derived lookup that queries `prompt_variants` to populate the Obsidian frontmatter field
- `src/capillaries/db/setup.py` — remove from CREATE TABLE
- `docs/schema.md` — remove row

### 2.4 New Table: `prompt_variants`

Per-model optimized versions of a prompt. The most recently optimized variant (any model) is treated as canonical for Obsidian sync.

```sql
CREATE TABLE IF NOT EXISTS prompt_variants (
    variant_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_title    VARCHAR NOT NULL REFERENCES prompts(title) ON DELETE CASCADE,
    model           VARCHAR NOT NULL,       -- e.g. 'claude-sonnet-4-6', 'gpt-4o'

    prompt_text     TEXT NOT NULL,           -- the optimized prompt body
    content_hash    VARCHAR NOT NULL,        -- SHA of prompt_text

    -- Optimization provenance
    optimizer       VARCHAR NOT NULL,        -- 'bootstrap_few_shot', 'miprov2', 'manual'
    optimization_run_id UUID,               -- links to optimization_runs for full trace
    metric_score    FLOAT,                  -- score achieved on the metric during optimization

    -- Lifecycle
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_current      BOOLEAN DEFAULT TRUE,   -- only one current variant per (prompt_title, model)

    UNIQUE (prompt_title, model, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_variants_prompt_model
    ON prompt_variants (prompt_title, model) WHERE is_current = TRUE;
```

**Canonical variant for Obsidian:** `SELECT prompt_text FROM prompt_variants WHERE prompt_title = %s AND is_current = TRUE ORDER BY created_at DESC LIMIT 1`. This is the text that `frontmatter.py` syncs to the vault file body.

**Runtime variant selection:** When the agent pipeline resolves a prompt for execution, it passes the active model identifier:

```sql
SELECT prompt_text FROM prompt_variants
WHERE prompt_title = %s AND model = %s AND is_current = TRUE;
-- Falls back to prompts.prompt_text if no variant exists
```

**Deriving `models_tested` for Obsidian frontmatter:**

```sql
SELECT ARRAY_AGG(DISTINCT model) FROM prompt_variants
WHERE prompt_title = %s AND is_current = TRUE;
```

### 2.5 New Table: `golden_examples`

Training data for DSPy optimization. Each row is one input/output pair for a specific prompt.

```sql
CREATE TABLE IF NOT EXISTS golden_examples (
    example_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_title    VARCHAR NOT NULL REFERENCES prompts(title) ON DELETE CASCADE,

    -- The example
    input_text      TEXT NOT NULL,           -- the user message / task that triggered the prompt
    output_text     TEXT NOT NULL,           -- the golden output
    context_text    TEXT,                    -- surrounding conversational context (optional)

    -- Provenance
    source          VARCHAR NOT NULL         -- 'memory_project', 'external', 'contrastive', 'manual'
                    CHECK (source IN ('memory_project', 'external', 'contrastive', 'manual')),
    model           VARCHAR,                 -- which model produced this output (if known)
    conversation_id VARCHAR,                 -- trace back to source conversation

    -- Quality
    is_negative     BOOLEAN DEFAULT FALSE,   -- TRUE for "bad" examples in contrastive pairs
    pair_id         UUID,                    -- links positive/negative contrastive pairs

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_golden_prompt ON golden_examples (prompt_title);
CREATE INDEX IF NOT EXISTS idx_golden_source ON golden_examples (source);
```

**Source distribution safeguard:** before running DSPy optimization, validate:

```sql
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE source != 'memory_project') AS external_count,
    ROUND(COUNT(*) FILTER (WHERE source != 'memory_project')::numeric / GREATEST(COUNT(*), 1), 2) AS external_ratio
FROM golden_examples
WHERE prompt_title = %s;
```

Require `external_ratio >= 0.2` (20% non-circular examples) before allowing optimization. Warn at 0.2-0.3, block below 0.2.

### 2.6 New Table: `optimization_runs`

Audit log of every DSPy optimization invocation.

```sql
CREATE TABLE IF NOT EXISTS optimization_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_title    VARCHAR NOT NULL REFERENCES prompts(title),
    model           VARCHAR NOT NULL,

    -- Config
    optimizer       VARCHAR NOT NULL,        -- 'bootstrap_few_shot', 'miprov2'
    num_examples    INTEGER NOT NULL,        -- how many golden examples were used
    metric_type     VARCHAR NOT NULL,        -- 'exact_match', 'llm_judge', 'custom'

    -- Results
    baseline_score  FLOAT,                   -- score of original prompt on the metric
    optimized_score FLOAT,                   -- score of best optimized variant
    improvement     FLOAT GENERATED ALWAYS AS (optimized_score - baseline_score) STORED,

    -- Metadata
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP,
    status          VARCHAR DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'no_improvement')),
    error_message   TEXT,
    dspy_config     JSONB DEFAULT '{}'       -- full optimizer config for reproducibility
);

CREATE INDEX IF NOT EXISTS idx_opt_runs_prompt ON optimization_runs (prompt_title, started_at DESC);
```

---

## 3. DSPy Optimization Pipeline

### 3.1 Architecture

```
CLI command
  → load golden_examples for prompt
  → validate source distribution (≥20% external)
  → build DSPy metric (exact_match | llm_judge | custom)
  → configure optimizer (BootstrapFewShot default, MIPROv2 optional)
  → run optimization against target model
  → compare optimized vs. baseline score
  → if improved: write variant to prompt_variants, log to optimization_runs
  → if not improved: log as 'no_improvement', don't write variant
  → trigger Obsidian sync for the canonical variant
```

### 3.2 DSPy Module Design

New module: `src/capillaries/optimize/dspy_optimize.py`

```python
import dspy

class PromptTask(dspy.Signature):
    """Execute a prompt against an input and produce output."""
    input_text: str = dspy.InputField(desc="The user's task or query")
    prompt_template: str = dspy.InputField(desc="The prompt to optimize")
    output_text: str = dspy.OutputField(desc="The generated output")

class PromptExecutor(dspy.Module):
    def __init__(self):
        self.generate = dspy.Predict(PromptTask)

    def forward(self, input_text, prompt_template):
        return self.generate(input_text=input_text, prompt_template=prompt_template)
```

### 3.3 Metric Functions

New module: `src/capillaries/optimize/metrics.py`

Three metric types, selected per optimization run:

1. **`exact_match`** (default) — normalized string similarity between candidate output and golden output. Use `difflib.SequenceMatcher` ratio with a configurable threshold (default 0.85). Handles whitespace/formatting variance.

2. **`llm_judge`** — LLM-as-judge scoring. Send (golden_output, candidate_output, task_description) to a judge model. Returns 0.0-1.0. Use a cheaper/faster model than the one being optimized to avoid circular evaluation.

3. **`custom`** — per-prompt metric function loaded from a registry. For prompts that need domain-specific evaluation (e.g., "analysis prompts must cover these 5 sections"). Stored as Python callables registered by prompt title.

### 3.4 CLI Interface

New module: `src/capillaries/optimize/cli.py`

```
python -m capillaries.optimize optimize <prompt_title> --model claude-sonnet-4-6
python -m capillaries.optimize optimize <prompt_title> --model gpt-4o --optimizer miprov2
python -m capillaries.optimize optimize <prompt_title> --model claude-sonnet-4-6 --metric llm_judge
python -m capillaries.optimize status <prompt_title>       # show variants and optimization history
python -m capillaries.optimize compare <prompt_title>      # side-by-side diff of variants
```

Flags:
- `--model` (required): target model for optimization
- `--optimizer`: `bootstrap_few_shot` (default) or `miprov2`
- `--metric`: `exact_match` (default), `llm_judge`, or `custom`
- `--dry-run`: run optimization but don't write results
- `--min-examples`: minimum golden examples required (default 5)
- `--force`: bypass the 20% external source ratio check (with warning)

### 3.5 Variant Lifecycle

When DSPy produces an improved variant:
1. Set `is_current = FALSE` on any existing variant for the same `(prompt_title, model)`
2. Insert new variant row with `is_current = TRUE`
3. If this is the most recent variant across all models, update `prompts.prompt_text` with the new text and recompute `content_hash`
4. Trigger `obsidian_sync/frontmatter.py` to sync the updated canonical text to the vault file body
5. Recompute the prompt's embedding with the new text

Old variants are retained for audit/rollback but marked `is_current = FALSE`.

---

## 4. Golden Example Capture

### 4.1 Memory Project Feed (Primary Volume Source)

The memory project already captures outputs with surrounding context. Wire it to write golden examples:

New module: `src/capillaries/optimize/capture.py`

```python
class ExampleCapture:
    def capture_from_memory(
        self,
        prompt_title: str,
        input_text: str,
        output_text: str,
        context_text: str | None = None,
        model: str | None = None,
        conversation_id: str | None = None,
    ) -> str:
        """Ingest a golden example from the memory project feed.
        Returns example_id."""
        # Insert with source='memory_project'
        ...

    def capture_external(
        self,
        prompt_title: str,
        input_text: str,
        output_text: str,
        model: str | None = None,
    ) -> str:
        """Manually add an external golden example.
        Returns example_id."""
        # Insert with source='external'
        ...

    def capture_contrastive(
        self,
        prompt_title: str,
        input_text: str,
        good_output: str,
        bad_output: str,
        model: str | None = None,
    ) -> tuple[str, str]:
        """Add a contrastive pair. Returns (positive_id, negative_id)."""
        # Insert both with shared pair_id, source='contrastive'
        ...
```

### 4.2 CLI Capture

For capturing golden examples from Claude Code CLI conversations:

```
python -m capillaries.optimize capture <prompt_title> --input "..." --output "..."
python -m capillaries.optimize capture <prompt_title> --input "..." --output "..." --source external
python -m capillaries.optimize capture <prompt_title> --contrastive --input "..." --good "..." --bad "..."
python -m capillaries.optimize examples <prompt_title>     # list examples with source breakdown
```

### 4.3 Feedback Loop Safeguard

Before each optimization run, the CLI checks the source distribution of golden examples:

| External ratio | Behavior |
|---|---|
| ≥ 0.30 | Proceed normally |
| 0.20 – 0.29 | Warn: "Only N% of examples are from external sources. Consider adding more before optimizing." Proceed. |
| < 0.20 | Block: "Insufficient external examples (N%). Add external or contrastive examples, or use --force to bypass." |

---

## 5. Lifecycle Management

### 5.1 Status Semantics

| Status | Meaning | In retrieval | Gets optimized | Gets run-tracked |
|---|---|---|---|---|
| `draft` | Newly created, untested | No | No | No |
| `active` | In use, in workflows | Yes | Yes | Yes |
| `inactive` | Candidate for removal or revision | No | No | No |

### 5.2 Auto-Inactivation Rule

Prompts and skills that have zero direct usage for 6 months are automatically transitioned to `inactive`.

**"Usage" definition:**
- For prompts: a row in `skills.agent_feedback` where `prompt_id = <title>` and `outcome != 'skipped'`
- For skills: a row in `skills.skill_runs` where `skill_id = <id>`
- Skill-mediated usage of a prompt does NOT count as direct usage for the prompt

**Implementation:** New module `src/capillaries/lifecycle/inactivate.py`

```sql
-- Prompts: no direct feedback in 6 months
UPDATE prompts SET status = 'inactive'
WHERE status = 'active'
  AND title NOT IN (
      SELECT DISTINCT prompt_id FROM skills.agent_feedback
      WHERE prompt_id IS NOT NULL
        AND created_at > NOW() - INTERVAL '6 months'
        AND outcome != 'skipped'
  )
RETURNING title;

-- Skills: no runs in 6 months
UPDATE skills.skills SET status = 'inactive'
WHERE status = 'active'
  AND skill_id NOT IN (
      SELECT DISTINCT skill_id FROM skills.skill_runs
      WHERE started_at > NOW() - INTERVAL '6 months'
  )
RETURNING name, slug;
```

**Trigger:** run as a CLI command, not a background job. Execute before each quarterly review or on-demand:

```
python -m capillaries.lifecycle inactivate          # apply auto-inactivation rules
python -m capillaries.lifecycle inactivate --dry-run # preview what would be inactivated
```

### 5.3 Advisory Cascade

When a prompt is inactivated (auto or manual), flag dependent active skills for review.

**Implementation:** after any prompt status change to `inactive`, query:

```sql
SELECT s.skill_id, s.name, s.slug, step->>'step_order' AS step_order
FROM skills.skills s,
     jsonb_array_elements(s.steps) AS step
WHERE s.status = 'active'
  AND step->>'prompt_id' = %s;
```

Output as a warning: "The following active skills reference inactivated prompt '{title}': ..."

No automatic status change on the skill. The warning is logged and surfaced in the quarterly review.

### 5.4 Quarterly Review Surface

CLI command that surfaces all `inactive` items with decision-support metadata:

```
python -m capillaries.lifecycle review               # full review
python -m capillaries.lifecycle review --prompts-only
python -m capillaries.lifecycle review --skills-only
```

**Per-prompt output:**

| Field | Source |
|---|---|
| Title | `prompts.title` |
| Status | `prompts.status` |
| Last direct use | `MAX(created_at) FROM skills.agent_feedback WHERE prompt_id = title` |
| Total lifetime runs | `COUNT(*) FROM skills.agent_feedback WHERE prompt_id = title` |
| Success rate | `prompt_quality_prior.success_rate` |
| Active skills using it | Count from steps JSONB query |
| Similar active prompts | Top 3 nearest neighbors by embedding where `status = 'active'` |
| Domain / Intent | `prompts.domain`, `prompts.intent` |
| Has golden examples | `COUNT(*) FROM golden_examples WHERE prompt_title = title` |
| Has variants | `COUNT(*) FROM prompt_variants WHERE prompt_title = title AND is_current = TRUE` |

**Per-skill output:**

| Field | Source |
|---|---|
| Name / Slug | `skills.skills.name`, `slug` |
| Status | `skills.skills.status` |
| Last run | `skills.skills.last_run_at` |
| Total runs | `skills.skills.total_runs` |
| Success rate | `skills.skills.success_rate` |
| Step count | `jsonb_array_length(steps)` |
| Steps with inactive prompts | Count of steps where prompt status = 'inactive' |

---

## 6. Runtime Variant Selection

### 6.1 Model Detection

The model identifier is available programmatically at the point of LLM invocation — it's a required parameter in both the Anthropic and OpenAI SDK calls. The variant selection happens in the prompt resolution layer.

### 6.2 Integration Point

Modify the prompt text resolution in the search/execution pipeline. When a `prompt_title` is resolved to its text:

```python
def resolve_prompt_text(prompt_title: str, model: str | None = None) -> str:
    """Return the best prompt text for the given model.
    Falls back to canonical prompt_text if no variant exists."""
    if model:
        variant = _get_current_variant(prompt_title, model)
        if variant:
            return variant["prompt_text"]
    return _get_canonical_text(prompt_title)
```

**Where to wire this in:**
- `src/capillaries/skills/recall.py` — `SkillRecall._resolve_steps()` currently fetches `prompt_text` directly. Add `model` parameter.
- `src/capillaries/agent/execute.py` — `SkillExecutor.execute_step()` resolves prompt text for each step. Pass the active model through.
- `src/capillaries/search/api.py` — `PromptSearch.search()` returns prompt text in results. Add optional model for variant selection.

### 6.3 Obsidian Sync for Variants

Modify `obsidian_sync/frontmatter.py` to:
1. When syncing a prompt to Obsidian, check `prompt_variants` for the most recent `is_current = TRUE` variant (any model)
2. If a variant exists, write that variant's `prompt_text` as the file body instead of `prompts.prompt_text`
3. Populate `Models Tested` frontmatter field from `SELECT ARRAY_AGG(DISTINCT model) FROM prompt_variants WHERE prompt_title = %s AND is_current = TRUE`

---

## 7. Obsidian Sync Updates

### 7.1 Ingest Direction (Obsidian → DB)

`obsidian_sync/ingest.py` changes:
- Remove `models_tested` from field mappings and insert SQL
- Update status validation to accept `draft / active / inactive`
- No change to the delete-orphans logic

### 7.2 Export Direction (DB → Obsidian)

`obsidian_sync/frontmatter.py` changes:
- Update FIELD_MAP status transform for new values
- Add `models_tested` derivation from `prompt_variants`
- Add prompt body replacement with canonical variant text

`obsidian_sync/skills_vault.py` changes:
- Update status values in export/import
- No structural changes — skills don't have variants

---

## 8. New Package Structure

```
src/capillaries/
├── optimize/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point for optimize/capture/status/compare
│   ├── dspy_optimize.py    # DSPy module, optimizer wrappers
│   ├── metrics.py          # exact_match, llm_judge, custom metric registry
│   └── capture.py          # ExampleCapture class for golden example ingestion
├── lifecycle/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point for inactivate/review
│   ├── inactivate.py       # Auto-inactivation logic
│   ├── cascade.py          # Advisory cascade checks
│   └── review.py           # Quarterly review surface queries
```

---

## 9. Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
optimize = [
    "dspy>=2.5.0",
]
```

DSPy is an optional dependency — the core capillaries system doesn't require it. Only the `optimize` package imports it.

---

## 10. Implementation Order

### Phase 1: Schema & Lifecycle (no DSPy dependency)
1. Status migration — unify to `draft/active/inactive` across DB, sync layer, and all Python code
2. Drop `models_tested` column
3. Create `prompt_variants`, `golden_examples`, `optimization_runs` tables
4. Build `lifecycle/` package — inactivate, cascade, review CLI
5. Update Obsidian sync for new status values
6. Clean up `parent_prompt` references in docs

### Phase 2: Golden Example Capture
7. Build `optimize/capture.py` — ExampleCapture class
8. Build capture CLI commands
9. Wire memory project feed into ExampleCapture (integration point TBD based on memory project's output format)

### Phase 3: DSPy Optimization
10. Build `optimize/metrics.py` — metric functions
11. Build `optimize/dspy_optimize.py` — DSPy module and optimizer wrappers
12. Build optimize CLI with source distribution safeguard
13. Wire variant selection into `recall.py`, `execute.py`, `api.py`
14. Update `frontmatter.py` to sync canonical variant to Obsidian

### Phase 4: Validation
15. Run optimization on 3-5 well-covered prompts as proof of concept
16. Run quarterly review surface on full DB to validate output quality
17. End-to-end test: capture → optimize → variant served → Obsidian synced
