# Prompt Database Schema

**Last updated:** 2026-04-18
**Total prompts:** 972
**DB:** PostgreSQL 16 + pgvector, database `capillaries`
**Source of truth:** Obsidian vault frontmatter — DB is rebuilt from vault files
**`intent` and `task_type` are always lowercase in the DB.** `domain` preserves original casing (e.g. `AI` stays uppercase). Obsidian displays Title Case for intent/task_type via the sync layer.

---

## Table: `prompts`

### Identity

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `prompt_id` | varchar | NOT NULL (PK) | Filename without `.md` extension |
| `file_path` | text | NOT NULL | Absolute path to the Obsidian markdown file |
| `content_hash` | varchar | NOT NULL | SHA of prompt_text — used to detect changes |
| `file_mtime` | timestamp | — | File modification time from disk |

### Content

| Column | Type | Fill rate | Notes |
|--------|------|-----------|-------|
| `prompt_text` | text | 100% | Raw markdown body (no frontmatter) |

### Classification (LLM-generated, synced to Obsidian frontmatter)

| Column | Type | Fill rate | Obsidian field | Valid values |
|--------|------|-----------|----------------|--------------|
| `intent` | varchar[] | 71% | Intent | `adapt` `automate` `build` `communicate` `decide` `explore` `improve` `learn` `prepare` `reflect` `validate` |
| `task_type` | varchar[] | 72% | Task Type | `analyze` `compare` `debug` `design` `evaluate` `explain` `generate` `model` `optimize` `synthesize` |
| `domain` | varchar[] | 72% | Category | `AI` `business` `career` `finance` `learning` `personal` `product` `strategy` `technical` `writing` |
| `primary_stage` | varchar | 59% | Primary Stage | `clarify` `plan` `execute` `verify` `reflect` — enforced by CHECK constraint |
| `complexity_level` | integer | 59% | Complexity | 1–5 scale, enforced by CHECK constraint |

### Prompt I/O

| Column | Type | Fill rate | Obsidian field | Notes |
|--------|------|-----------|----------------|-------|
| `expected_input` | text | ~0% | Expected Input | What the prompt expects as input |
| `expected_output` | text | ~0% | Expected Output | What the prompt produces |

### Obsidian-synced metadata

| Column | Type | Fill rate | Obsidian field | Notes |
|--------|------|-----------|----------------|-------|
| `status` | varchar | 100% | status | `draft` `active` `inactive` — enforced by CHECK |
| `original_link` | text | ~79% | Original Link | URL the prompt was sourced from |
| `notes` | text | ~28% | Notes / notes | Freeform notes |
| `last_evaluated` | date | ~0% | Last Evaluated | When the prompt was last tested/reviewed |

### System / versioning

| Column | Type | Notes |
|--------|------|-------|
| `last_updated` | timestamp | Auto-set on insert, updated on sync |
| `last_classified` | timestamp | When LLM classification last ran |
| `classification_version` | varchar | Current: `v1.0-qwen3.5-latest` |
| `backfill_status` | varchar | `pending` `processing` `complete` `needs_review` `failed` |
| `metadata_confidence` | jsonb | Per-field confidence scores from classifier |

### Search infrastructure

| Column | Type | Fill rate | Notes |
|--------|------|-----------|-------|
| `embedding` | halfvec(EMBED_DIM), default 1024 | — | Qwen3-Embedding-0.6B embeddings; Python values remain `list[float]` |
| `embedding_version` | varchar | — | Embedding model/version recorded with the vector |
| `search_vector` | tsvector | ~100% | Full-text search vector, populated on insert |

---

## Indexes

| Index | Type | Columns | Purpose |
|-------|------|---------|---------|
| `prompts_pkey` | btree | `prompt_id` | Primary key |
| `idx_prompts_embedding_active` | **partial HNSW** | `embedding halfvec_cosine_ops`, `status = 'active'` | Vector similarity search. `m=16, ef_construction=64` |
| `idx_prompts_search` | GIN | `search_vector` | Full-text search |
| `idx_prompts_intent` | GIN | `intent` | Array containment filter |
| `idx_prompts_task_type` | GIN | `task_type` | Array containment filter |
| `idx_prompts_domain` | GIN | `domain` | Array containment filter |
| `idx_prompts_stage` | btree | `primary_stage` | Equality filter |
| `idx_prompts_complexity` | btree | `complexity_level` | Range filter |
| `idx_prompts_status` | btree | `status` | Equality filter |
| `idx_prompts_backfill` | btree | `backfill_status` | Processing state filter |
| `idx_prompts_confidence` | GIN | `metadata_confidence` | JSONB field queries |

---

## Distributions

### primary_stage
| Stage | Count | % |
|-------|-------|---|
| execute | 269 | 47.0% |
| plan | 166 | 29.0% |
| verify | 77 | 13.5% |
| clarify | 56 | 9.8% |
| reflect | 5 | 0.9% |

**Note:** Heavy skew toward `execute`. Chains rarely form naturally because `clarify` and `reflect` prompts are sparse.

### complexity_level
| Level | Count | % |
|-------|-------|---|
| 1 | 3 | 0.5% |
| 2 | 200 | 35.0% |
| 3 | 278 | 48.6% |
| 4 | 71 | 12.4% |
| 5 | 21 | 3.7% |

### domain (top values, multi-valued field)
| Domain | Appearances |
|--------|-------------|
| business | 350 |
| AI | 237 |
| technical | 160 |
| product | 145 |
| personal | 104 |
| learning | 92 |
| strategy | 71 |
| writing | 56 |
| finance | 51 |
| career | 35 |

---

## Related tables

### `skills.skills`

Skill routing uses `routing_embedding halfvec(EMBED_DIM)` with the same
config-driven width (1024 by default). Its partial HNSW index is
`idx_skills_routing_embedding_active`, using `halfvec_cosine_ops`,
`m=16`, `ef_construction=64`, and `WHERE status = 'active'`.

All partial-HNSW query paths set `hnsw.iterative_scan` to
`'relaxed_order'` locally in the transaction immediately before the ordered
query. This matters when a nearest-neighbor query also filters on `status`:
without iterative scanning, the initial index scan can run out of candidates
before enough rows pass the partial-index filter, causing under-return.

The Python embedding interface remains `list[float]`; SQL values assigned to or
compared with these columns use `::halfvec`.

### `batch_processing_log`
Tracks LLM classification runs. FK to `prompts.prompt_id`.

### `classification_feedback`
Reserved for future human correction of LLM classifications. FK to `prompts.prompt_id`.

---

## Known gaps

| Gap | Impact | Fix |
|-----|--------|-----|
| 401 prompts pending classification | 41% of prompts have no taxonomy metadata | Run batch classifier |
| `reflect` stage has only 5 prompts | Chains never complete with a reflection step | Add reflect-stage prompts to vault |
| `last_evaluated` near 0% | No quality signal per prompt | Populate as prompts are used |
| `expected_input` / `expected_output` at 0% | Can't verify chain coherence (does step N output feed step N+1 input?) | Add to classification or populate manually |

---

## Evaluation & Diagnostics

Use this section alongside `capillaries.search.eval` to diagnose retrieval quality and decide where to invest improvement effort.

### Symptom → Layer Map

| What you observe in eval results | Layer | What to investigate / fix |
|---|---|---|
| Right prompt exists but ranked low | **Reranking** | Increase `MAX_DOC_CHARS` (currently 1200 in `reranker.py`) — key content may be past truncation. Try `ms-marco-MiniLM-L-12-v2` (2x params, still fast on 3090). |
| Right prompt never appears in candidates | **Retrieval** | Increase `RETRIEVAL_CANDIDATES` (currently 50 in `api.py`). Check whether the prompt's embedding captures its intent — long prompts are truncated at `MAX_CHARS=4000` in `embed.py`. |
| Dense retrieves it, sparse doesn't (or vice versa) | **Retrieval balance** | Adjust `RRF_K` (currently 60 in `retriever.py`). Vocabulary mismatch (user says "churn", prompt says "attrition") is a dense-only signal — sparse can't bridge synonyms. |
| A stage is always empty (e.g. reflect) | **Data coverage** | Check stage distribution above — only 5 reflect prompts, 56 clarify. Add prompts to the vault. |
| Wrong `primary_stage` on a prompt | **Classification** | Fix the Obsidian frontmatter directly. If the pattern is systemic, update `config/classification_prompt_template.md` and re-run the batch classifier. |
| Good prompt excluded by a domain/intent filter | **Classification metadata** | The prompt's `domain`/`intent` arrays may be too narrow. A finance prompt about strategy should have `["finance", "strategy"]` not just `["finance"]`. |
| All results vaguely related, none precise | **Embedding model** | `Qwen3-Embedding-0.6B` is a general-purpose model. If domain-specific terms are central to the query, the embedding may lack precision. Consider a domain-tuned model or adding keyword emphasis to prompt text. |
| Duplicate / near-duplicate prompts in top results | **Data dedup** | Two vault files cover the same ground. Merge them or differentiate their stage/domain metadata so filters separate them. |
| Same prompt appears in multiple chain stages | **Data coverage** | Not enough stage-specific prompts for this topic. The system reuses the best general match per stage. |
| Most chain steps flagged ⚠ WEAK | **Data + query fit** | Either the query is too broad for the corpus, or the problem space lacks prompt coverage. Check if adding 2-3 targeted prompts fixes the chain. |

### Iteration Process

```
1. Run eval         python -m capillaries.search.eval
2. Read report      tests/artifacts/eval_<timestamp>.txt
3. For each query ask:
     - Are the right prompts showing up?     → retrieval or reranking problem
     - Are stages correctly assigned?         → classification / data problem
     - Are ⚠ WEAK flags justified?            → threshold or data coverage problem
4. Identify the layer from the table above
5. Make ONE change, re-run eval, compare reports
6. Run tests/test_search.py golden set as regression guard
```

### Fix Priority (highest leverage first)

| Priority | Layer | Action | Why |
|----------|-------|--------|-----|
| 1 | Data | Classify pending 401 prompts | 41% of corpus invisible to filtered queries |
| 2 | Data | Add reflect-stage prompts (target 20-30) | 5 prompts is not enough for any chain to complete |
| 3 | Data | Populate `expected_input` / `expected_output` | Enables coherence scoring: does step N's output feed step N+1's input? |
| 4 | Reranking | Increase `MAX_DOC_CHARS` 1200→1800 | MiniLM-L-6 handles 512 tokens (~2000 chars); current truncation is conservative |
| 5 | Retrieval | Increase `RETRIEVAL_CANDIDATES` if reranker finds good results at positions 40-50 | Ensures reranker sees all plausible matches |
| 6 | Classification | Audit prompts where domain arrays are singleton | Many prompts span multiple domains but were classified with only one |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-29 | Migrated embedding storage to pgvector 0.8 `halfvec(EMBED_DIM)` with partial HNSW indexes using `halfvec_cosine_ops`; embedding width remains 1024 by default. |
| 2026-04-18 | Dropped `secondary_stages`, `context_variables`, `accomplishes` (never populated). Renamed `input_schema`→`expected_input`, `output_schema`→`expected_output` to match Obsidian. Normalized all `intent`/`task_type` values to lowercase. |
| 2026-03-29 | Switched vector index from IVFFlat to HNSW (`m=16, ef_construction=64`) |
