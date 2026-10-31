---
status: accepted
date: 2026-08-17
approved-by: operator
drafted-by: operator
retire-evidence: a clean benchmark where a weighted fusion beats union at rank 1
switch: none
---
# Dense and sparse candidates are unioned, then reranked, with no ratio

## Context and Problem Statement

Weighted reciprocal rank fusion needed a dense/sparse ratio, and every ratio
tried was either indefensible or inside the noise. One benchmark population was
also leaked: `chunk.py` writes each prompt's title into its own chunks, so title
queries measured string matching (re-measured on clean data 2026-09-08).

## Decision Drivers

* Only uncontaminated data may justify a ratio (the "describing" set, 261 queries)
* A knob that changes nothing measurable should not exist

## Considered Options

* Union both channels' candidates and let the cross-encoder order them
* RRF at 0.5 / 0.5: 22.0% recall@10 on the clean set, within 0.4 points of its own ceiling
* RRF at 0.3 / 0.7: 21.5%, and derived from the leaked population
* RRF at 0.85 / 0.15: 17.5%, worse than both
* Route queries by type: achievable, not worth building

## Decision Outcome

Chosen option: "union, then rerank", because it has no ratio to tune and
recovers the recall fusion leaves behind (golden R@10 55% to 75%).

### Consequences

* Good, because nothing in serving reads a fusion weight.
* Bad, because R@1 did not improve; the gain lands at ranks 5-10, so the reranker is the next component that has to get better.

### Confirmation

`src/capillaries/search/api.py` serves through `union.union_candidates_broad`.
`DENSE_WEIGHT`/`SPARSE_WEIGHT` in `search/retriever.py` survive only as the benchmark arm.
