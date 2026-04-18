# Prompt Database Schema

**Last updated:** 2026-03-29
**Total prompts:** 572 (571 active, 1 archived)
**DB:** PostgreSQL 16 + pgvector, database `prompt_flow`
**Source of truth:** Obsidian vault frontmatter — DB is rebuilt from vault files

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
| `prompt_text` | text | 100% | Raw markdown body (no frontmatter). Min 213 chars, max 41,881, avg 2,451, median 1,388 |

### Classification (LLM-generated, synced to Obsidian frontmatter)

| Column | Type | Fill rate | Valid values |
|--------|------|-----------|--------------|
| `intent` | varchar[] | 99.1% | `adapt` `automate` `build` `communicate` `decide` `explore` `improve` `learn` `prepare` `reflect` `validate` |
| `task_type` | varchar[] | 100% | `analyze` `compare` `debug` `design` `evaluate` `explain` `generate` `model` `optimize` `synthesize` |
| `domain` | varchar[] | 100% | `AI` `business` `career` `finance` `learning` `personal` `product` `strategy` `technical` `writing` |
| `primary_stage` | varchar | 100% | `clarify` `plan` `execute` `verify` `reflect` — enforced by CHECK constraint |
| `secondary_stages` | varchar[] | 0% | Same values as primary_stage — not yet populated |
| `complexity_level` | integer | 100% | 1–5 scale, enforced by CHECK constraint |

### Workflow metadata (mostly unpopulated)

| Column | Type | Fill rate | Notes |
|--------|------|-----------|-------|
| `input_schema` | text | 0% | Description of what the prompt expects as input |
| `output_schema` | text | 0% | Description of what the prompt produces |
| `context_variables` | varchar[] | 0% | Variables that flow through from prior context |
| `accomplishes` | text | 0% | Semantic description of what the prompt achieves |
| `parent_prompt` | varchar | 0% | FK to `prompt_id` of the parent in a chain |

### Obsidian-synced metadata

| Column | Type | Fill rate | Notes |
|--------|------|-----------|-------|
| `status` | varchar | 100% | `active` (99.8%) `deferred` `archived` — enforced by CHECK |
| `original_link` | text | 84.8% | URL the prompt was sourced from |
| `models_tested` | varchar[] | 0.2% | Models this prompt has been validated against |
| `notes` | text | 0% | Freeform notes |
| `last_evaluated` | date | 0.2% | When the prompt was last tested/reviewed |

### System / versioning

| Column | Type | Notes |
|--------|------|-------|
| `last_updated` | timestamp | Auto-set on insert, updated on sync |
| `last_classified` | timestamp | When LLM classification last ran |
| `classification_version` | varchar | Current: `v1.0-qwen3.5-latest` |
| `backfill_status` | varchar | `complete` for all 572 prompts. Values: `pending` `processing` `complete` `needs_review` `failed` |
| `metadata_confidence` | jsonb | Reserved for per-field confidence scores — not yet populated |

### Search infrastructure

| Column | Type | Fill rate | Notes |
|--------|------|-----------|-------|
| `embedding` | vector(768) | 99.8% | `nomic-embed-text` embeddings with `search_document:` prefix. 1 prompt has no text |
| `embedding_version` | varchar | 99.8% | Current: `nomic-embed-text` |
| `search_vector` | tsvector | — | Full-text search vector for `pg_trgm` |

---

## Indexes

| Index | Type | Columns | Purpose |
|-------|------|---------|---------|
| `prompts_pkey` | btree | `prompt_id` | Primary key |
| `idx_prompts_embedding` | **HNSW** | `embedding` (cosine) | Vector similarity search. `m=16, ef_construction=64` |
| `idx_prompts_search` | GIN | `search_vector` | Full-text / trigram search |
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
| clarify | 55 | 9.6% |
| reflect | 5 | 0.9% |

**Note:** Heavy skew toward `execute`. Chains rarely form naturally because `clarify` and `reflect` prompts are sparse. This limits multi-stage chain retrieval.

### complexity_level
| Level | Count | % |
|-------|-------|---|
| 1 | 3 | 0.5% |
| 2 | 200 | 35.0% |
| 3 | 278 | 48.6% |
| 4 | 71 | 12.4% |
| 5 | 20 | 3.5% |

Most prompts are medium complexity (2–3). Very few are simple (1) or highly complex (5).

### domain (top values, multi-valued field)
| Domain | Appearances |
|--------|-------------|
| business | 297 |
| AI | 180 |
| technical | 137 |
| product | 124 |
| learning | 78 |
| personal | 75 |
| strategy | 57 |
| writing | 51 |
| finance | 41 |
| career | 30 |

---

## Related tables

### `batch_processing_log`
Tracks LLM classification runs. FK to `prompts.prompt_id`.

### `classification_feedback`
Reserved for future human correction of LLM classifications. FK to `prompts.prompt_id`.

---

## Known gaps (as of 2026-03-29)

| Gap | Impact | Fix |
|-----|--------|-----|
| `secondary_stages` 0% filled | Can't retrieve prompts by alternate stages | Re-run classification with secondary_stages prompt |
| `input_schema` / `output_schema` 0% filled | Can't match prompt outputs to next prompt's inputs — blocks proper chain planning | Add to classification prompt template |
| `accomplishes` 0% filled | Reduces semantic precision for chain scoring | Add to classification prompt template |
| `reflect` stage has only 5 prompts | Chains never complete with a reflection step | Add reflect-stage prompts to vault |
| `models_tested` / `last_evaluated` near 0% | No quality signal per prompt | Populate as prompts are used |
| 1 prompt with empty text (`Everything else`) | No embedding, won't appear in search | Delete or give it content |

---

## Evaluation & Diagnostics

Use this section alongside `scripts/eval_report.py` to diagnose retrieval quality and decide where to invest improvement effort.

### Symptom → Layer Map

| What you observe in eval results | Layer | What to investigate / fix |
|---|---|---|
| Right prompt exists but ranked low | **Reranking** | Increase `MAX_DOC_CHARS` (currently 1200 in `reranker.py`) — key content may be past truncation. Try `ms-marco-MiniLM-L-12-v2` (2x params, still fast on 3090). |
| Right prompt never appears in candidates | **Retrieval** | Increase `RETRIEVAL_CANDIDATES` (currently 50 in `api.py`). Check whether the prompt's embedding captures its intent — long prompts are truncated at `MAX_CHARS=4000` in `embed.py`. |
| Dense retrieves it, sparse doesn't (or vice versa) | **Retrieval balance** | Adjust `RRF_K` (currently 60 in `retriever.py`). Vocabulary mismatch (user says "churn", prompt says "attrition") is a dense-only signal — sparse can't bridge synonyms. |
| A stage is always empty (e.g. reflect) | **Data coverage** | Check stage distribution above — only 5 reflect prompts, 55 clarify. Add prompts to the vault, or populate `secondary_stages` so prompts appear in multiple stages. |
| Wrong `primary_stage` on a prompt | **Classification** | Fix the Obsidian frontmatter directly. If the pattern is systemic, update `config/classification_prompt_template.md` and re-run the batch classifier. |
| Good prompt excluded by a domain/intent filter | **Classification metadata** | The prompt's `domain`/`intent` arrays may be too narrow. A finance prompt about strategy should have `["finance", "strategy"]` not just `["finance"]`. |
| All results vaguely related, none precise | **Embedding model** | `nomic-embed-text` is general-purpose. If domain-specific terms are central to the query, the embedding may lack precision. Consider a domain-tuned model or adding keyword emphasis to prompt text. |
| Duplicate / near-duplicate prompts in top results | **Data dedup** | Two vault files cover the same ground. Merge them or differentiate their stage/domain metadata so filters separate them. |
| Same prompt appears in multiple chain stages | **Data coverage** | Not enough stage-specific prompts for this topic. The system reuses the best general match per stage. |
| Most chain steps flagged ⚠ WEAK | **Data + query fit** | Either the query is too broad for the corpus, or the problem space lacks prompt coverage. Check if adding 2-3 targeted prompts fixes the chain. |

### Iteration Process

```
1. Run eval         python scripts/eval_report.py
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
| 1 | Data | Populate `secondary_stages` | Lets prompts appear in multiple stages — single biggest chain improvement |
| 2 | Data | Add reflect-stage prompts (target 20-30) | 5 prompts is not enough for any chain to complete |
| 3 | Data | Populate `input_schema` / `output_schema` | Enables coherence scoring: does step N's output feed step N+1's input? |
| 4 | Reranking | Increase `MAX_DOC_CHARS` 1200→1800 | MiniLM-L-6 handles 512 tokens (~2000 chars); current truncation is conservative |
| 5 | Retrieval | Increase `RETRIEVAL_CANDIDATES` if reranker finds good results at positions 40-50 | Ensures reranker sees all plausible matches |
| 6 | Classification | Audit prompts where domain arrays are singleton | Many prompts span multiple domains but were classified with only one |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-29 | Switched vector index from IVFFlat to HNSW (`m=16, ef_construction=64`) |
| 2026-03-29 | Reembedded all prompts with `search_document:` prefix for nomic asymmetric retrieval |
| 2026-03-29 | Embedding dimension changed from 1536 (OpenAI) to 768 (nomic-embed-text) |
| 2026-03-29 | All 572 prompts classified via Ollama qwen3.5 (`classification_version=v1.0-qwen3.5-latest`) |
| 2026-03-25 | Initial DB build from Obsidian vault (572 prompts ingested) |
