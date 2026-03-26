# Prompt Picker Phase 1: Agentic Orchestration Implementation Spec

Date: 2026-02-18
Status: Draft for implementation

## 1) Goal

Define a production-ready Phase 1 orchestration workflow for selecting and ordering prompts from the vault.

Scope:
- In scope: task understanding, candidate retrieval, chain planning, critique, final selection, output packaging.
- Out of scope: executing selected prompts in external runtimes.

## 2) Weaknesses In Current Scope And Required Fixes

### 2.1 Current Known Weaknesses
| Weakness | Risk | Phase 1 Fix |
|---|---|---|
| No abstain/clarify policy | Bad retrieval on ambiguous tasks | Add confidence gates and explicit `clarify` outcome |
| Chain score not calibrated | Thresholds are arbitrary | Calibrate `T_single`, `T_chain`, `delta` using offline set |
| Enrichment has no quality loop | Metadata noise degrades retrieval | Add enrichment confidence and review queue |
| No deterministic task schema | Inconsistent behavior between runs | Add strict `TaskSpec` JSON contract |
| No state machine for retries/fallback | Fragile control flow | Add bounded planner-critic loop with fallback |
| Weak explainability | Hard to trust outputs | Return per-prompt evidence and score components |
| No version/freshness controls | Stale vectors and drift | Hash/version prompts and incremental reindex |

### 2.2 Core Workflow Orchestration Problems
| Problem Category | Specific Issue | Implementation Impact |
|---|---|---|
| **Chain Construction Optimization** | Combinatorial explosion (600 prompts × 5 stages = millions of chains) | Need beam search with early pruning, pre-computed compatibility matrices |
| **Context State Management** | Chain prompts modify context - later selections depend on earlier outputs | Requires dynamic re-ranking, context state modeling |
| **Scoring Calibration** | Weighted formula coefficients are arbitrary/uncalibrated | Need A/B testing, user feedback loops, historical success tracking |
| **Dynamic Chain Length** | No principled way to decide 1 prompt vs 5-prompt chain | Requires confidence thresholds, task complexity classification |
| **Real-Time Performance** | Complex workflow analysis is computationally expensive | Need caching, pre-computation, async processing |
| **Quality Assessment** | Scoring chains before execution - unknown real compatibility | Need historical success rates, simulated validation, dry-run checks |

## 3) Phase 1 Architecture

```text
User Task
  -> IntakeAgent (TaskSpec compiler)
  -> RiskAndAmbiguityAgent (proceed | clarify)
  -> RetrieverAgent (metadata + BM25 + vector + neighbor expansion)
  -> PlannerAgent (build candidate chains)
  -> CriticAgent (coverage/coherence/redundancy checks)
      -> optional replan loop (max 2 iterations)
  -> SelectorAgent (single vs chain vs clarify policy)
  -> PackagerAgent (strict JSON output + rationale + provenance)
```

Data stores:
- Metadata store: SQLite/Postgres/DuckDB
- Lexical index: BM25
- Vector index: ChromaDB
- Run logs: append-only JSONL or SQL table

## 4) Canonical Data Contracts

### 4.1 PromptRecord

```json
{
  "prompt_id": "string",
  "prompt_text": "string",
  "intent": "string|null",
  "task_type": "string|null",
  "domain": "string|null",
  "expected_input": "string|null",
  "expected_output": "string|null",
  "status": "string|null",
  "models_tested": ["string"],
  "parent_prompt": "string|null",
  "original_link": "string|null",
  "last_updated": "YYYY-MM-DDTHH:MM:SSZ",
  "last_evaluated": "YYYY-MM-DD|null",
  "notes": "string|null",
  "content_hash": "string",
  "embedding_version": "string"
}
```

### 4.2 TaskSpec

```json
{
  "task_id": "uuid",
  "raw_query": "string",
  "intent": "string",
  "task_type": "string",
  "domain_hint": "string|null",
  "constraints": ["string"],
  "deliverable": "string|null",
  "risk_level": "low|medium|high",
  "stages": ["clarify", "plan", "execute", "verify", "reflect"],
  "requires_multistep": true,
  "ambiguity_score": 0.0
}
```

### 4.3 Candidate

```json
{
  "prompt_id": "string",
  "dense_sim": 0.0,
  "bm25_sim": 0.0,
  "metadata_match": 0.0,
  "quality_prior": 0.0,
  "freshness": 0.0,
  "stage_fit": {
    "clarify": 0.0,
    "plan": 0.0,
    "execute": 0.0,
    "verify": 0.0,
    "reflect": 0.0
  },
  "retrieval_sources": ["metadata", "bm25", "vector", "neighbor"]
}
```

### 4.4 FinalOutput

```json
{
  "mode": "single|chain|clarify",
  "confidence": 0.0,
  "task_id": "uuid",
  "selected_prompts": [
    {
      "prompt_id": "string",
      "stage": "clarify|plan|execute|verify|reflect",
      "rank": 1,
      "why": "string",
      "evidence": {
        "dense_sim": 0.0,
        "bm25_sim": 0.0,
        "metadata_match": 0.0,
        "stage_fit": 0.0
      }
    }
  ],
  "fallback": {
    "mode": "single|chain|clarify",
    "prompt_ids": ["string"]
  },
  "clarification_questions": ["string"],
  "trace_id": "string"
}
```

## 5) Agent Responsibilities

## 5.1 IntakeAgent
- Input: raw user task
- Output: `TaskSpec`
- Rules:
  - normalize wording into structured fields
  - infer stages and multi-step requirement
  - never emit empty `intent` and `task_type`

## 5.2 RiskAndAmbiguityAgent
- Input: `TaskSpec`
- Output: `proceed` or `clarify`
- Rules:
  - if `ambiguity_score >= T_ambiguity`, produce `clarify`
  - if required constraints missing, produce `clarify`

## 5.3 RetrieverAgent
- Input: `TaskSpec`
- Output: candidate pool (target 30-80 prompts)
- Retrieval sources:
  - metadata filtering (hard and soft constraints)
  - BM25 over prompt text
  - vector similarity
  - neighbor expansion via `parent_prompt` and near-duplicate graph

## 5.4 PlannerAgent
- Input: candidates + `TaskSpec`
- Output: 1-3 candidate chains
- Rules:
  - maximize stage coverage
  - avoid repeated prompts unless explicit reason
  - allow single prompt proposal when confidence is high

## 5.5 CriticAgent
- Input: chain proposals
- Output: accepted chain(s) or critique messages
- Checks:
  - missing required stage
  - transition incoherence
  - redundancy/conflict
  - low confidence margin

## 5.6 SelectorAgent
- Input: best single + best chain + confidence stats
- Output: `single`, `chain`, or `clarify`
- Decision policy:
  - choose `single` if `single_score >= T_single` and `(chain_score - single_score) < delta`
  - choose `chain` if `chain_score >= T_chain`
  - else `clarify`

## 5.7 PackagerAgent
- Input: final selection and evidence
- Output: strict `FinalOutput` JSON
- Rules:
  - include rationale per selected prompt
  - include fallback mode
  - include trace id for observability

## 6) Ranking And Decision Logic

Individual prompt score:

`S_prompt = 0.35*dense_sim + 0.25*bm25_sim + 0.15*metadata_match + 0.10*stage_fit + 0.10*quality_prior + 0.05*freshness - penalties`

Chain score:

`S_chain = 0.45*avg_prompt_score + 0.25*workflow_coverage + 0.15*transition_coherence + 0.10*non_redundancy + 0.05*confidence_margin`

Initial thresholds (to calibrate):
- `T_ambiguity = 0.65`
- `T_single = 0.76`
- `T_chain = 0.72`
- `delta = 0.06`

Tie-breakers:
1. Higher workflow coverage
2. Higher quality prior
3. Lower redundancy
4. More recent `last_updated`

## 7) Orchestration State Machine

```text
START
  -> INTAKE
  -> RISK_CHECK
      -> if clarify: END_CLARIFY
  -> RETRIEVE
  -> PLAN
  -> CRITIQUE
      -> if fail and retries < 2: PLAN
      -> if fail and retries == 2: SELECT_FALLBACK
  -> SELECT
      -> if low confidence: END_CLARIFY
  -> PACKAGE
  -> END
```

Hard limits:
- max critique loops: 2
- max candidates passed to planner: 80
- max chain length: 5
- max latency target: p95 <= 2.5s (excluding offline indexing)
- max beam search width: 10 (for chain construction)
- max compatibility matrix cache: 10k prompt pairs

## 8) Observability And Safeguards

Per-run log fields:
- `trace_id`, `task_id`, timestamps
- agent outputs and confidence values
- retrieval source attribution
- threshold decisions (`single|chain|clarify`)
- final selected ids

Safeguards:
- automatic fallback to BM25-only if vector index unavailable
- abstain when confidence low and ambiguity high
- dedupe by exact hash then similarity threshold
- incremental reindex when `content_hash` changed

## 9) Validation Plan

Offline benchmark:
- 80-150 representative tasks
- include edge cases: ambiguous intent, duplicates, sparse metadata, multi-step workflows

Metrics:
- precision@k
- nDCG@k
- MRR
- sequence accuracy (stage order and completeness)
- abstain quality (precision of clarify triggers)
- latency p50/p95

Calibration routine:
1. run baseline with fixed thresholds
2. sweep `T_single`, `T_chain`, `delta`, `T_ambiguity`
3. pick operating point maximizing task-success proxy at acceptable abstain rate

## 10) Example End-To-End Run

Input task:
- "Create a 2-week content strategy and execution plan for a B2B AI newsletter."

Output:

```json
{
  "mode": "chain",
  "confidence": 0.79,
  "task_id": "3f7d8e37-184a-4a3a-8a8f-b0c17a92f6d1",
  "selected_prompts": [
    {
      "prompt_id": "p_102",
      "stage": "clarify",
      "rank": 1,
      "why": "extracts audience, constraints, and publishing cadence",
      "evidence": {"dense_sim": 0.80, "bm25_sim": 0.69, "metadata_match": 0.74, "stage_fit": 0.90}
    },
    {
      "prompt_id": "p_331",
      "stage": "plan",
      "rank": 2,
      "why": "strong planning template for multi-week editorial calendars",
      "evidence": {"dense_sim": 0.83, "bm25_sim": 0.72, "metadata_match": 0.78, "stage_fit": 0.92}
    },
    {
      "prompt_id": "p_087",
      "stage": "execute",
      "rank": 3,
      "why": "execution checklist aligns with newsletter drafting workflow",
      "evidence": {"dense_sim": 0.77, "bm25_sim": 0.70, "metadata_match": 0.71, "stage_fit": 0.88}
    },
    {
      "prompt_id": "p_455",
      "stage": "verify",
      "rank": 4,
      "why": "adds quality control and consistency checks before publication",
      "evidence": {"dense_sim": 0.75, "bm25_sim": 0.68, "metadata_match": 0.69, "stage_fit": 0.86}
    }
  ],
  "fallback": {"mode": "single", "prompt_ids": ["p_331"]},
  "clarification_questions": [],
  "trace_id": "trc_20260218_001"
}
```

## 11) Build Breakdown (Implementation Order)

### Phase 1A: Foundation
1. Finalize canonical schemas and JSON validators.
2. Implement intake and ambiguity agents.
3. Implement hybrid retriever with source attribution.
4. **Build prompt compatibility matrix and caching layer.**

### Phase 1B: Core Orchestration
5. Implement planner with beam search optimization.
6. Implement critic loop with context state tracking.
7. **Add dynamic chain length decision logic.**
8. Implement selector policy and packager contract.

### Phase 1C: Optimization & Validation
9. **Implement performance optimizations (caching, pre-computation).**
10. Add logging, metrics, and evaluation harness.
11. **Build scoring calibration system with A/B testing capability.**
12. Calibrate thresholds using historical success data.

### Phase 2 (Future): Learning & Adaptation
13. **Add user feedback loops for scoring refinement.**
14. **Implement context state simulation for quality prediction.**
15. **Add real-time performance monitoring and auto-scaling.**

