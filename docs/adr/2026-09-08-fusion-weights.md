---
status: accepted
date: 2026-09-08
approved-by: operator
drafted-by: operator
retire-evidence: a clean, uncontaminated benchmark where another split wins
switch: none
---
# Dense and sparse fuse at 50/50

## Context and Problem Statement

Two reweightings were proposed for reciprocal rank fusion of dense and sparse
results. One benchmark population turned out leaked: `chunk.py` writes each
prompt's title into its own chunks, so title queries measured string matching.

## Decision Drivers

* Only uncontaminated data may justify a change (the "describing" set, 261 queries)

## Considered Options

* Keep 0.5 / 0.5: 22.0% recall@10 on the clean set
* 0.3 / 0.7: 21.5%, and derived from the leaked population
* 0.85 / 0.15: 17.5%, from diagram labels and an out-of-domain failure trace
* Force top sparse hits into the rerank pool: at 50/50 they already land in the top 20
* Route queries by type: achievable, not worth building

## Decision Outcome

Chosen option: "keep 50/50", because it is the best configuration tested on
uncontaminated data.

### Consequences

* Good, because the weights stopped moving on leaked evidence.
* Bad, because the union ceiling (25.7%) shows fusion leaves recall on the table.

### Confirmation

`src/capillaries/search/retriever.py` (`DENSE_WEIGHT`, `SPARSE_WEIGHT`).
