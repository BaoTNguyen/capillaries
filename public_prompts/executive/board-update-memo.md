---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt addresses executives preparing concise updates for a board of
  directors regarding company performance. The model must draft a one-to-two-page
  memo covering financials, operational highlights, risks, and strategic priorities,
  using a confident and honest tone.
complexity_level: 4
domain:
- business
- strategy
intent:
- communicate
primary_stage: execute
source: public
task_type:
- synthesize
---

Write a board of directors update memo for **{{company_name}}** covering **{{time_period}}**.

**Key data points to incorporate:**
- Revenue: {{revenue_figure}} (vs. {{revenue_target}} target)
- Key metric: {{key_metric_name}} = {{key_metric_value}}
- Headcount: {{headcount}} ({{headcount_change}} from prior period)
- Major wins: {{major_wins}}
- Key challenges: {{key_challenges}}

Structure the memo as:
1. **Executive Summary** (3-4 sentences — the story of the quarter in plain language)
2. **Financial Performance** — revenue, margins, burn rate, runway. Compare to plan with variance explanations for anything >10%.
3. **Operational Highlights** — product milestones, customer wins, partnerships
4. **Risks & Challenges** — be candid. For each risk, state what you're doing about it.
5. **Strategic Priorities for Next Period** — 3-5 items with owners and target dates
6. **Asks of the Board** — specific decisions, introductions, or guidance needed

Tone: Confident but honest. Lead with outcomes, not activities. Board members have 5 minutes to read this — make every sentence count.

Output as a 1-2 page memo ready to send.