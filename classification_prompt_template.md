# Classification Prompt Template

Use this template to classify prompts via batch LLM calls.
Process **10–15 prompts per API call** using `claude-haiku-4-5-20251001` for cost efficiency.

---

## Taxonomy Reference

```
intent:         adapt | automate | build | communicate | decide | explore |
                improve | learn | prepare | reflect | validate

task_type:      analyze | compare | debug | evaluate | model | optimize |
                design | generate | synthesize | explain

domain:         AI | business | career | finance | learning | personal |
                product | strategy | writing | technical

primary_stage:  clarify | plan | execute | verify | reflect

complexity:     1 | 2 | 3 | 4 | 5
                  1 = single instruction, no role, minimal structure
                  2 = defined role + clear output format, low context requirement
                  3 = expert role + multi-point output + moderate context required
                  4 = expert role + multi-phase output + substantial input data required
                  5 = multi-phase workflow or embedded step chains, comprehensive artifact output

accepts_prior_output:  true | false
                  true = prompt explicitly or implicitly expects a previous LLM output
                         as its main input
                  signals: "[PASTE PRIOR OUTPUT]", "You previously wrote",
                           "Given the above", "Based on your analysis",
                           "Now attack your previous answer", "your prior response"

has_template_vars:  true | false
                  true = prompt contains user-fillable ALL-CAPS bracket placeholders
                  signals: [COMPANY], [YOUR X], [LIST], [NUMBER], [DESCRIBE], [ENTER],
                           [AMOUNT], [PRODUCT]
                  NOT: structural/example brackets like [1], [see above], [optional]
                  Note: ~32% of the library uses this pattern

is_chain_prompt:  true | false
                  true = prompt internally embeds multiple numbered steps or phases
                         to be run sequentially as a single artifact
                  signals: "Step 1", "Step 2", "Phase 1", "Phase 2", "Prompt Chain:" header
                  Note: treat these as atomic — do not chain them with other prompts
```

---

## How these fields drive chain construction

| Field | Role |
|---|---|
| `intent` + `task_type` + `domain` | Layer 1 retrieval — narrows the candidate pool |
| `primary_stage` | Sequencing — orders prompts in a chain (clarify → plan → execute → verify → reflect) |
| `accepts_prior_output` | Primary chain compatibility signal — step N+1 must have this true |
| `is_chain_prompt` | Routing — return as single prompt, never combine with others |
| `has_template_vars` | Output packaging — flag prompts that require user input before running |
| `complexity` | Chain length hint — avoid chaining two complexity-5 prompts |

Note: `input_schema` / `output_schema` are **not classified** — free text dominates the library
and `accepts_prior_output` captures the only distinction that matters for chain construction.
The compatibility matrix is also deferred — greedy stage-ordered assembly is sufficient for v1.

---

## System Prompt

```
You are a prompt metadata classifier. Analyze each prompt and classify its
characteristics using ONLY the allowed values for each field.

Return a valid JSON array only. No explanation, no markdown fences, no commentary.
Each object in the array must correspond to one prompt, in the same order given.

RULES:
- intent and task_type: arrays of 1–3 values each
- domain: array of 1–2 values
- primary_stage, complexity, accepts_prior_output, has_template_vars, is_chain_prompt: single values
- confidence: per-field dict with scores 0.0–1.0 reflecting how clearly the prompt signals each field
- If a field is ambiguous, pick the closest match and lower its confidence score
```

---

## User Prompt Template

```
ALLOWED VALUES:
intent:        adapt | automate | build | communicate | decide | explore | improve | learn | prepare | reflect | validate
task_type:     analyze | compare | debug | evaluate | model | optimize | design | generate | synthesize | explain
domain:        AI | business | career | finance | learning | personal | product | strategy | writing | technical
primary_stage: clarify | plan | execute | verify | reflect
complexity:    1 | 2 | 3 | 4 | 5

COMPLEXITY SCALE:
1 = Single instruction, no role, minimal structure
2 = Defined role + clear output format, low context requirement
3 = Expert role + multi-point output + moderate context required
4 = Expert role + multi-phase output + substantial input data required
5 = Multi-phase workflow or embedded step chains, comprehensive artifact output

accepts_prior_output: true if the prompt explicitly or implicitly expects a previous LLM output as its main input
  (signals: "[PASTE PRIOR OUTPUT]", "You previously wrote", "Given the above", "Based on your analysis",
   "Now attack your previous answer", "your previous answer", "prior response")

has_template_vars: true if the prompt contains user-fillable ALL-CAPS bracket placeholders
  (signals: [COMPANY], [YOUR X], [LIST], [NUMBER], [DESCRIBE], [ENTER], [AMOUNT], [PRODUCT]
   NOT: structural/example brackets like [1], [see above], [optional])

is_chain_prompt: true if the prompt internally embeds multiple numbered steps or phases to be run sequentially
  (signals: "Step 1", "Step 2", "Phase 1", "Phase 2", "Prompt Chain:" header, explicit multi-step structure)

---

EXAMPLES:

Prompt title: "Adversarial Stress Test Template"
Prompt text: "[YOUR INITIAL REQUEST AND MODEL RESPONSE]\n\nNow attack your previous answer:\n1. Identify five specific ways it could be wrong..."
Output:
{
  "intent": ["improve", "validate"],
  "task_type": ["evaluate", "analyze"],
  "domain": ["AI"],
  "primary_stage": "verify",
  "complexity": 2,
  "accepts_prior_output": true,
  "has_template_vars": true,
  "is_chain_prompt": false,
  "confidence": {"intent": 0.92, "task_type": 0.95, "domain": 0.70, "primary_stage": 0.90, "complexity": 0.88}
}

Prompt title: "Management Consultant - Executive Summary"
Prompt text: "I'm a strategy consultant writing an executive summary for a detailed analysis. Audience is C-suite.\n\nAnalysis Scope: [What question you were answering]\n..."
Output:
{
  "intent": ["communicate", "build"],
  "task_type": ["synthesize", "generate"],
  "domain": ["business", "strategy"],
  "primary_stage": "execute",
  "complexity": 3,
  "accepts_prior_output": false,
  "has_template_vars": true,
  "is_chain_prompt": false,
  "confidence": {"intent": 0.90, "task_type": 0.88, "domain": 0.95, "primary_stage": 0.85, "complexity": 0.85}
}

Prompt title: "Department Budget vs. Actual Tracker"
Prompt text: "Prompt Chain:\n\nStep 1 - Setup Structure:\nCreate a department budget tracker with this structure..."
Output:
{
  "intent": ["build", "model"],
  "task_type": ["design", "generate"],
  "domain": ["finance", "business"],
  "primary_stage": "execute",
  "complexity": 5,
  "accepts_prior_output": false,
  "has_template_vars": false,
  "is_chain_prompt": true,
  "confidence": {"intent": 0.88, "task_type": 0.90, "domain": 0.95, "primary_stage": 0.85, "complexity": 0.92}
}

---

NOW CLASSIFY THE FOLLOWING PROMPTS:

{{PROMPT_1_TITLE}}
---
{{PROMPT_1_CONTENT}}

{{PROMPT_2_TITLE}}
---
{{PROMPT_2_CONTENT}}

[...repeat up to 15 prompts]

Return a JSON array of {{N}} objects in the same order as the prompts above.
```

---

## Low-Confidence Handling

```python
CONFIDENCE_THRESHOLD = 0.75

for result in classifications:
    confidence = result["confidence"]
    min_confidence = min(confidence.values())

    backfill_status = "complete" if min_confidence >= CONFIDENCE_THRESHOLD else "needs_review"

    record.update({
        "backfill_status": backfill_status,
        "metadata_confidence": confidence,        # per-field dict
        "classification_version": "v1.0-haiku",
        "last_classified": datetime.utcnow()
    })
```

---

## Validation Checklist (before full run)

1. Run pilot on 30 prompts you know well
2. Manually verify each classification — target >85% accuracy
3. If accuracy is below 85%: add one more few-shot example that covers the failure pattern
4. After full run: check that no single `intent` or `task_type` value exceeds 40% of all records
5. Spot-check the first 20 `needs_review` records to calibrate the 0.75 threshold
6. Only mark pilot batch as `backfill_status = complete` after manual sign-off

---

## Edge Case Notes

- **Image Gen prompts**: `primary_stage = execute`, `domain = ["AI"]` or relevant subject domain
- **Meta-prompts** (~9 in library): `domain = ["AI"]`, note in `notes` field
- **Embedded chain prompts** (~present in library): `is_chain_prompt = true`, `complexity = 5` — return as atomic single-prompt results, never combine with other prompts in a chain
- **`accepts_prior_output`** is the primary chain compatibility signal — a chain step N+1 must have this true, or the chain breaks (user would need to manually copy output between steps)
- **`has_template_vars`** is for output packaging only, not retrieval — the vector DB handles semantic matching regardless of whether a prompt has fillable slots
