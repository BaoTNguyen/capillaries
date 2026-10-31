---
status: accepted
date: 2026-07-20
approved-by: operator
drafted-by: operator
retire-evidence: a change in requirement; replay is not valid evidence
switch: none
---
# The prompt optimizer edits prose, never code

## Context and Problem Statement

Skills are prose plus code. DSPy can improve prose against a metric; code is
verified by running it, not by a prompt metric.

## Decision Drivers

* Code changes go through execution or a person, never a text optimizer

## Considered Options

* Fence code; the optimizer edits only prose sections; a validator requires fences byte-identical before and after
* Optimize the whole skill text: an optimizer could rewrite commands it can't verify

## Decision Outcome

Chosen option: "prose only, fences byte-identical". Routing descriptions and
procedure prose are optimized; code blocks never are; frontmatter is validated.

### Consequences

* Good, because an optimized skill can't ship untested code.
* Bad, because a skill whose weakness is in its code gets no help from optimization.

### Confirmation

`src/capillaries/optimize/fences.py`, `src/capillaries/optimize/dspy_optimize.py`.
