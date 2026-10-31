---
status: accepted
date: 2026-07-20
approved-by: operator
drafted-by: operator
retire-evidence: promotion decisions with no measurable delta over months
switch: none
---
# A candidate prompt or skill is promoted only after winning an A/B

## Context and Problem Statement

An optimized version can be worse than the one it replaces.

## Decision Drivers

* Promotion must be evidence, and rollback must be cheap

## Considered Options

* Shadow the candidate (served to a share, or replayed on recent queries), compare deltas, promote only on a win, keep every version
* Replace in place on optimization: no comparison, no rollback

## Decision Outcome

Chosen option: "A/B gate". Rollback is a row flip; `skill.promoted` and
`skill.rejected` reach the spine.

### Consequences

* Good, because nothing replaces a working version without beating it.
* Bad, because a low-traffic prompt may never collect enough to promote.

### Confirmation

`src/capillaries/skills/promote.py::ab_gate`.
