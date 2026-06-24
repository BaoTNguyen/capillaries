---
intent: [validate]
task_type: [analyze]
domain: [finance, business]
primary_stage: verify
complexity_level: 3
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Generate a budget variance analysis report for the **{{department}}** department at **{{company_name}}** for **{{time_period}}**.

Budget data:
- Total budgeted amount: ${{budgeted_total}}
- Total actual spend: ${{actual_total}}
- Line item breakdown: {{line_items_summary}}
- Prior period variance for context: {{prior_period_variance}}

Produce the following:
1. **Executive Summary** (3-4 sentences) — Overall variance, whether favorable or unfavorable, and the headline story
2. **Variance Table** — For each budget line item, show: Budgeted | Actual | Variance ($) | Variance (%) | Favorable/Unfavorable
3. **Top 3 Favorable Variances** — What came in under budget and why
4. **Top 3 Unfavorable Variances** — What exceeded budget, root cause analysis for each
5. **Trend Analysis** — Compare this period's variance pattern to {{prior_period}} and note any recurring issues
6. **Impact Assessment** — How do these variances affect our annual budget trajectory?
7. **Recommended Actions** — 3-5 specific actions: reallocations, spending freezes, or forecast adjustments

Flag any variance exceeding {{threshold}}% as requiring immediate attention.
Output as a report with tables for quantitative data and narrative paragraphs for analysis.
