---
status: accepted
date: 2026-07-20
approved-by: operator
drafted-by: operator
retire-evidence: a change in requirement
switch: none
---
# The gate logs the candidates it didn't serve

## Context and Problem Statement

An optimizer that sees only what was served can't learn ranking: it never
sees what the served item beat.

## Decision Drivers

* Ranking signal needs the losing candidates, with their scores

## Considered Options

* Log top-k candidate ids and scores in the gate decision payload (an additive field)
* Log only the served prompt (as before)

## Decision Outcome

Chosen option: "log top-k". It is the prerequisite for any ranking signal.

### Consequences

* Good, because served-versus-unserved pairs exist for later optimization.
* Bad, because every decision event grows by k entries.

### Confirmation

`src/capillaries/search/api.py`, `src/capillaries/optimize/serving.py`. Proven by `tests/test_optimize_m6.py`.
