# Retrieval Pipeline Tuning

**Date:** 2026-05-29
**Query:** "I need to build a go-to-market strategy for a new B2B SaaS product launching next quarter"
**Corpus:** 916 prompts (849 private, 67 public)

## Problem

Retrieved prompts were not functionally relevant. The top result was `competitor-moves` (a public demo prompt about quarterly competitive landscape). None of the actual GTM prompts in the private vault surfaced. Three root causes identified:

1. Public prompts mixed with private in retrieval
2. Dense search dominated RRF fusion (0.7/0.3 weighting), burying sparse keyword matches
3. Acronym mismatch: query used "go-to-market" but prompts used "GTM" — embedding model scored these 0.08 apart

## Change 1: Source filtering

Default retrieval to `source='private'`. Public prompts only returned when explicitly requested via `source='public'` parameter.

**Files:** `agent/route.py`, `agent/api.py`, `search/retriever.py` (already had source filter support)

## Change 2: Acronym expansion

Added `expand_acronyms()` — a dictionary of ~80 business/tech acronyms that expands in-place: "GTM strategy" → "GTM (go-to-market) strategy".

Applied at:
- Query embedding (`retriever.py:embed_query`)
- Sparse/BM25 query (`retriever.py:search`)
- Document embedding (`db/embed.py:get_embedding`)
- search_tsv construction (`obsidian_sync/ingest.py` + one-time SQL backfill)

**Similarity improvement for GTM prompts (query → stored embedding):**

| Prompt | Before | After | Delta |
|---|---|---|---|
| GTM Strategy - Customer Segment Focus | 0.635 | 0.724 | +0.089 |
| Product-Led vs. Sales-Led GTM Motion | 0.618 | 0.689 | +0.071 |
| GTM & Launch Plan Review | 0.819 | 0.839 | +0.020 |

## Change 3: RRF weight rebalancing

| Parameter | Before | After |
|---|---|---|
| DENSE_WEIGHT | 0.7 | 0.5 |
| SPARSE_WEIGHT | 0.3 | 0.5 |
| RRF_K | 60 | 50 |

With 0.7/0.3, a sparse-only hit at rank 1 couldn't beat a dense-only hit at rank 50. Equal weights let sparse top 7 naturally land in RRF top 20.

**Math at 0.7/0.3, k=60:**
```
Sparse rank 1, no dense: 0.3/(60+1) = 0.00492
Dense rank 50, no sparse: 0.7/(60+50) = 0.00636  ← sparse #1 loses to dense #50
```

**Math at 0.5/0.5, k=50:**
```
Sparse rank 1, no dense: 0.5/(50+1) = 0.00980
Dense rank 50, no sparse: 0.5/(50+50) = 0.00500  ← sparse #1 now wins
```

## Change 4: Title prepend at embed time

Prompt_id (Obsidian title) prepended to prompt text before embedding: `f"{prompt_id}\n\n{prompt_text}"`. Anchors template-heavy prompts to their functional topic.

**Files:** `db/embed.py:get_embedding` (title parameter added)

## Change 5: Title in search_tsv with A-weight + acronym expansion

Title terms added to search_tsv with PostgreSQL weight 'A' (highest). Both title and body acronyms expanded before tsvector construction.

**Before:** `GTM Strategy - Customer Segment Focus` not in sparse top 50
**After:** sparse rank 11

**Files:** `obsidian_sync/ingest.py` (future ingests), one-time SQL backfill for existing rows

## Change 6: Sparse guarantee (tested then removed)

Tested forcing top-N sparse hits into the reranker pool regardless of RRF score. With 0.5/0.5 weights, sparse top 7 naturally landed in RRF top 20 without forcing. Removed in favor of tuning weights.

## Final pipeline result

```
 #1. [rerank=1.000000] PRODUCT LAUNCH PRESENTATION
 #2. [rerank=1.000000] GTM & Launch Plan Review – Stress-Test the Plan
 #3. [rerank=0.996094] Market & Topic Research Pack
 #4. [rerank=0.996094] Image Gen Market Sizing TAM SAM SOM
 #5. [rerank=0.992188] Head of Sales - Sales Strategy Document
```

vs. original:

```
 #1. competitor-moves (public, wrong corpus)
 #2. launch-checklist (public)
 #3. market-entry-analysis (public)
 #4. strategic-initiative-brief (public)
```

## Parameters (final)

```python
# retriever.py
DENSE_WEIGHT = 0.5
SPARSE_WEIGHT = 0.5
RRF_K = 50
DENSE_CANDIDATES = 50
SPARSE_CANDIDATES = 50

# reranker.py
MAX_DOC_CHARS = 8_000
MAX_QUERY_CHARS = 500

# gate.py
SIMILARITY_THRESHOLD = 0.35
```
