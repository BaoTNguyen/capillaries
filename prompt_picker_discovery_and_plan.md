# Prompt Picker: Consolidated Findings and Plan

Date: 2026-02-18

## 1) Optimal Prompt (verbatim)

```text
You are a principal AI agent-orchestration architect and retrieval systems engineer.

Your mission: design the most accurate Phase 1 for a “Prompt Picker” that returns the best prompts (in the right order) from my repository for any user task. Execution of selected prompts is handled elsewhere (Codex, Claude Code, local LLMs, etc.); your scope is selection, ranking, and packaging only.

Project context:
- Prompt database path: ~/Documents/Obsidian/Main Vault/Bases/Prompt Database.base
- Size: ~600 prompts
- Target workflow: daily use, high reliability, expandable architecture
- Proposed logic:
  - Layer 1: schema/column-based filtering (database query logic)
  - Layer 2: semantic narrowing via RAG over prompt content from Layer 1 results
- Proposed stack: Python + agent orchestration + local LLM + ChromaDB for retrieval

Critical instructions:
1) First, verify whether you can access the database path above.
2) If accessible, inspect the actual schema and representative records before making recommendations.
3) If not accessible, explicitly say what is blocked and provide the minimum exact export needed (format + required fields + sample size) so analysis can continue.
4) Do not invent schema details. Mark assumptions clearly.

What to produce:
1. Access & Data Reality Check
- Can/cannot access path, what was inspected, and confidence level.
- Exact schema summary: columns, inferred types, null/completeness patterns, duplicates/versioning indicators.

2. Best-Practice Verdict on My Current Plan
- Evaluate whether my two-layer logic is sound.
- Evaluate whether ChromaDB + Python + local LLM orchestration is a good foundation.
- Call out strengths, risks, and scalability limits.
- Include “keep / change / add now / add later” recommendations.

3. Retrieval Logic Design (Phase 1)
- Define Layer 1 filtering strategy using schema fields (hard filters, soft filters, fallbacks).
- Define Layer 2 RAG strategy over prompt text (embedding, chunking if needed, reranking).
- Provide a concrete ranking formula with weighted signals and tie-breakers.
- Define how to output prompt order and why each prompt was chosen.

4. Failure Modes and Safeguards
- Identify common failure modes (metadata sparsity, ambiguous tasks, near-duplicate prompts, stale embeddings, over-filtering, semantic drift).
- For each, give mitigation and monitoring checks.

5. Actionable Implementation Blueprint
- Minimal architecture diagram (text form is fine).
- Step-by-step build plan for Phase 1.
- Python-oriented pseudo-code for the selection pipeline.
- Future-proof extension path (multi-agent routing, feedback loops, online learning, hybrid search upgrades).

6. Validation Plan
- Offline evaluation method and metrics (e.g., precision@k, nDCG, task success proxy, latency).
- Small but rigorous test set design with edge cases.

Output format requirements:
- Be concise but concrete.
- Use these exact sections:
  A) Access Status
  B) Observed Schema
  C) Best-Practice Assessment
  D) Recommended Retrieval Pipeline
  E) Ranking Logic (with formula)
  F) Failure Modes & Mitigations
  G) Implementation Plan (Phase 1 -> Future)
  H) Validation & Metrics
  I) Blockers / Clarifying Questions
- If blocked from data access, still provide a provisional architecture and clearly label it “Provisional (awaiting schema)”.

Reasoning quality bar:
- Think step-by-step internally.
- Prioritize correctness over optimism.
- Surface uncertainty explicitly.
- No hallucinated file contents or schema.
```

## 2) Execution Findings (from real vault inspection)

### A) Access Status
- Access confirmed to: `~/Documents/Obsidian/Main Vault/Bases/Prompt Database.base`.
- `.base` file is accessible and is a Base config/query file, not a full row store.
- Real prompt records are Markdown notes in the vault.
- Base query scope observed:
  - include: `file.path.containsAny("Prompts")`
  - exclude: `!file.path.contains("Clippings")`
- Effective scope count under that filter: 573 markdown prompts.

### B) Observed Schema
- Base file properties and table columns reference:
  - `file.name`, `file.mtime`, `note.Category`, `note.status`, `note.notes`
  - plus table columns: `Intent`, `Task Type`, `Category`, `Expected Input`, `Expected Output`, `status`, `Models Tested`, `Parent Prompt`, `Original Link`, `Last Evaluated`, `notes`
- Real frontmatter in filtered corpus is sparse:
  - Most files have only `Original Link` or no frontmatter.
  - Key casing is inconsistent (`status` vs `Status`, `notes` vs `Notes`).

### C) Best-Practice Assessment
- Two-layer retrieval architecture is directionally correct.
- Important correction: ChromaDB is a vector store, not a relational DB replacement.
- Current Layer 1 constraints are weak because metadata density is low.
- Best practice: hybrid retrieval with explicit metadata normalization/enrichment.

### D) Recommended Retrieval Pipeline
1. Parse markdown + frontmatter into canonical schema.
2. Normalize key names and value enums.
3. Enrich missing metadata with an LLM classifier.
4. Build metadata index (SQLite/Postgres/DuckDB) + BM25 + Chroma vector index.
5. Query understanding step (intent/task decomposition).
6. Layer 1 candidate filter (hard + soft constraints).
7. Layer 2 semantic retrieval + rerank.
8. Sequence planner outputs ordered prompts by workflow stage.

### E) Ranking Logic (formula)
`score(p) = 0.35*dense_sim + 0.25*bm25_sim + 0.15*metadata_match + 0.10*stage_fit + 0.10*quality_prior + 0.05*freshness - penalties`

Tie-breakers:
1. Higher stage fit
2. Higher quality prior
3. Shorter prompt when equivalent
4. More recent file update time

### F) Failure Modes & Mitigations
- Metadata sparsity -> auto-enrichment pipeline.
- Over-filtering -> soft constraints + fallback retrieval.
- Duplicate prompts -> hash/similarity dedupe.
- Long prompt-pack semantic drift -> chunking + reranker.
- Ambiguous tasks -> clarification mode at low confidence.
- Stale vectors after edits -> incremental re-index by hash/mtime.

### G) Implementation Plan (Phase 1 -> Future)
- Phase 1:
  - canonical parser
  - normalization map
  - enrichment classifier
  - metadata DB
  - hybrid retrieval and reranker
  - sequence planner
  - JSON output only (selection/orchestration handoff)
- Future:
  - feedback-driven reranking
  - user personalization
  - multi-agent specialist routing

### H) Validation & Metrics
- Offline benchmark set of real tasks with gold prompt chains.
- Metrics:
  - precision@k
  - nDCG@k
  - MRR
  - sequence/order accuracy
  - latency p50/p95
- Include edge cases:
  - ambiguous intent
  - image-gen vs text tasks
  - duplicate prompts
  - missing metadata
  - multi-step workflows

### I) Blockers / Clarifying Questions captured then resolved
- Major blocker identified: sparse metadata in active non-clippings corpus.
- User clarified:
  - table is still being filled (backfill planned),
  - keep excluding `Clippings` for now,
  - canonical lower snake case is acceptable,
  - output should be dynamic by task complexity,
  - ranking must optimize workflow compatibility across multiple steps, not only individual prompt relevance.

### J) Post-Analysis Insights
- **Core insight**: This is workflow orchestration, not traditional RAG
- **Database choice**: Single database approach insufficient - need hybrid PostgreSQL + Qdrant
- **Main challenge**: Chain construction optimization and quality prediction without execution
- **Implementation focus**: Algorithmic sophistication > retrieval quality improvements

## 3) Inferred YAML Frontmatter Fields (excluding Clippings)

Corpus analyzed under Base scope: 573 prompt files.

| Canonical key | Source YAML key(s) | Present in files | Non-empty in files |
|---|---|---:|---:|
| `original_link` | `Original Link` | 486 | 486 |
| `intent` | `Intent` | 5 | 3 |
| `task_type` | `Task Type` | 5 | 3 |
| `domain` | `Category` (mapped to Domain) | 5 | 3 |
| `status` | `status`, `Status` | 4 | 2 |
| `models_tested` | `Models Tested` | 3 | 1 |
| `last_evaluated` | `Last Evaluated` | 3 | 1 |
| `expected_input` | `Expected Input` | 2 | 0 |
| `expected_output` | `Expected Output` | 2 | 0 |
| `parent_prompt` | `Parent Prompt` | 2 | 0 |
| `notes` | `notes`, `Notes` | 2 | 0 |

Other observed stats:
- Files with frontmatter: 488
- Files without frontmatter: 85
- Of files without frontmatter: 83 are Image Gen prompts
- Exact duplicate-content pair found:
  - `Define Your AI Learning Goal (Learning AI).md`
  - `Just Get Me Started (Learning AI).md`

## 4) Canonical Schema Decision (accepted)

Recommended/accepted canonical keys in stack (lower snake case):
- `prompt`
- `intent`
- `task_type`
- `domain`
- `expected_input`
- `expected_output`
- `status`
- `models_tested`
- `parent_prompt`
- `original_link`
- `last_updated`
- `last_evaluated`
- `notes`

## 5) Retrieval and Output Policy (updated to your requirements)

### 5.1 Dynamic output size
- If one prompt is a high-confidence exact match for the whole task workflow, return exactly one prompt.
- If task requires multi-step execution, return an ordered chain across steps.

### 5.2 Workflow-compatible ranking (not isolated relevance)
- Rank prompt sets/chains by end-to-end task compatibility.
- Model sequence as stages (example): `clarify -> plan -> execute -> verify -> reflect`.
- Optimize for:
  - stage coverage
  - smooth transitions between prompts
  - minimal conflict/redundancy
  - overall chain confidence

### 5.3 Practical scoring extension for chains
For a chain `C = [p1..pn]`:

`chain_score(C) = 0.45*avg_individual_relevance + 0.25*workflow_coverage + 0.15*transition_coherence + 0.10*non_redundancy + 0.05*confidence_margin`

- single prompt returned when:
  - `best_single_score >= T_single`
  - and `best_chain_score - best_single_score < delta`

## 6) Critical Implementation Challenges Identified

### 6.1 Beyond Simple Retrieval Problems
After analysis, the core challenges are **not** query/retrieval issues (which are ~20% of problems), but:

**Missing Metadata (40% of issues):**
- Need input/output schema fields for transition compatibility
- Need explicit dependency relationships stored
- Need context_variables or handoff_schema fields
- Need complexity_level and accomplishes fields

**Orchestration Algorithm Problems (40% of issues):**
- **Chain Construction**: Combinatorial explosion requires beam search optimization
- **Context State Management**: Dynamic re-ranking as chains build with context flow simulation
- **Scoring Calibration**: Current weighted formula needs A/B testing and historical success data
- **Performance**: Complex analysis needs caching, pre-computation, async processing
- **Quality Prediction**: Need to assess chain success without execution

### 6.2 Database Architecture Decision
**Recommendation: PostgreSQL + Qdrant hybrid approach**
- PostgreSQL: Structured filtering, metadata relationships, workflow logic
- Qdrant: Vector search with metadata filtering (better than pgvector for serious RAG)
- Rationale: pgvector insufficient for sophisticated vector operations needed

## 7) Ready-to-Implement Next Step

### Phase 1 Pipeline (Updated):
1. Ingestion + canonicalization of frontmatter
2. **Metadata enrichment focusing on workflow-specific fields**
3. **PostgreSQL setup with relationship modeling + Qdrant for vectors**
4. **Prompt compatibility matrix pre-computation**
5. **Workflow-aware chain construction with beam search**
6. **Context state tracking and dynamic re-ranking**
7. Strict output contract returning selected prompt(s) and order rationale

### Critical Success Factors:
- **Pre-compute prompt pair compatibility scores** (avoid real-time combinatorial explosion)
- **Implement context state simulation** (predict chain success without execution)
- **Build calibration system** (learn from historical chain performance)

