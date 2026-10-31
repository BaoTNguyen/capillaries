---
status: accepted
date: 2026-06-01
approved-by: operator
drafted-by: operator
retire-evidence: standardized prompt structure (truncation becomes safe), or a reranker without length bias
switch: none
---
# Reranker scores carry a progressive length penalty

## Context and Problem Statement

The cross-encoder saturates near 1.0 for many prompts, and ties broke toward
long, keyword-rich prompts.

## Decision Drivers

* Rank by fit, not by keyword volume
* Don't misjudge prompts with long preambles

## Considered Options

* Progressive length penalty
* Truncate to 256 characters with the title prepended: best ranking in the test, but misjudges prompts with long preambles
* Log-based length normalization

## Decision Outcome

Chosen option: "progressive penalty", because it is more conservative than
truncation and still orders the test cases correctly.

### Consequences

* Good, because long prompts stop winning ties on volume.
* Bad, because the penalty strength is model-specific and broke on model swaps.

### Confirmation

`src/capillaries/search/reranker.py` (`LENGTH_PENALTY_STRENGTH`).
