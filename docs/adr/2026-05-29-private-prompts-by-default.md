---
status: accepted
date: 2026-05-29
approved-by: operator
drafted-by: operator
retire-evidence: a corpus where public prompts serve real work
switch: none
---
# Retrieval returns private prompts unless public ones are asked for

## Context and Problem Statement

Retrieved prompts were not functionally relevant: the top result for a
go-to-market query was a public demo prompt, while the private GTM prompts
ranked nowhere. Public and private prompts were searched together.

## Decision Drivers

* The private vault is the working corpus; public prompts are demo material

## Considered Options

* Default to `source='private'`; return public prompts only when the caller passes `source='public'`
* Search both together (as before): demo prompts outranked the working ones

## Decision Outcome

Chosen option: "private by default", because the working corpus must win
by default and demos stay one parameter away.

### Consequences

* Good, because demo prompts no longer crowd out real ones.
* Bad, because a caller wanting both makes two calls.

### Confirmation

`src/capillaries/agent/api.py` (`source` defaults to `"private"`).
