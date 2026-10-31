---
status: accepted
date: 2026-09-08
approved-by: operator
drafted-by: operator
retire-evidence: a change in threat or requirement; replay is not valid evidence
switch: none
---
# Search refuses an index embedded by a different model

## Context and Problem Statement

Every embedding in the database was garbage: the configured embedder returned
collapsed vectors, and vectors from two models share a column but not a space.
Querying across them returns confident nonsense and raises nothing.

## Decision Drivers

* A model swap must fail loudly, not degrade silently

## Considered Options

* Record `embedding_version` per row and refuse to search when it differs from the configured model
* Trust the column, as before: how the corrupt index went unnoticed

## Decision Outcome

Chosen option: "refuse on mismatch", because the check is one query and the
failure it prevents is invisible otherwise.

### Consequences

* Good, because a swapped model forces a re-embed instead of silent wrong results.
* Bad, because changing `EMBED_MODEL` takes search down until re-embedding finishes.

### Confirmation

`src/capillaries/search/retriever.py::assert_index_matches_model`.
