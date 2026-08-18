---
Notes: Part of the contract-negotiation skill
Original Link: ''
Summary: 'Legal professionals use this prompt to generate negotiation strategies for
  risky contract clauses based on specific industry context and leverage. The model
  must provide tracked-change markup, rationale, fallback positions, and a prioritized
  negotiation package including walk-away lines for each flagged clause. Required
  context: [Original clause text or reference], [Quote the problematic text], [One
  sentence on why this is problematic], [Rewritten clause with tracked-change-style
  markup: ~~deleted text~~ and **added text**], [Why they should accept this — frame
  it as mutual benefit, not just our demand], [If they reject the primary redline,
  what''s the minimum acceptable alternative?].'
complexity_level: 3
domain:
- business
intent:
- improve
primary_stage: execute
source: public
task_type:
- generate
---

Generate specific redline suggestions for the following contract clauses that were flagged as risky:

**Flagged clauses:**
{{flagged_clauses}}

**Our position:** {{our_position}} (e.g., "mid-size buyer, moderate leverage", "sole-source vendor, limited alternatives")
**Industry:** {{industry}}

For each flagged clause, provide:

### Clause: [Original clause text or reference]

**Current language:** [Quote the problematic text]

**Issue:** [One sentence on why this is problematic]

**Suggested redline:**
> [Rewritten clause with tracked-change-style markup: ~~deleted text~~ and **added text**]

**Rationale for counterparty:** [Why they should accept this — frame it as mutual benefit, not just our demand]

**Fallback position:** [If they reject the primary redline, what's the minimum acceptable alternative?]

---

After all redlines, provide:
- **Priority order** — which redlines to push hardest on
- **Package deal suggestion** — which concessions to bundle together for a single negotiation round
- **Walk-away line** — which clause, if unchanged, should trigger escalation or alternative vendor pursuit