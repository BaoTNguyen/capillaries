---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt targets finance leaders seeking to identify savings opportunities
  for a specific company against industry benchmarks. The model must produce an executive
  briefing with a prioritization matrix, implementation roadmap, and categorized savings
  analysis.
complexity_level: 4
domain:
- finance
- business
intent:
- improve
- decide
primary_stage: plan
source: public
task_type:
- analyze
- optimize
---

Identify and prioritize cost reduction opportunities for **{{company_name}}** with a target savings of **${{savings_target}}** over **{{time_horizon}}**.

Current cost structure:
- Total annual operating costs: ${{total_opex}}
- People costs: ${{people_costs}} ({{headcount}} employees)
- Technology/software: ${{tech_costs}}
- Facilities: ${{facilities_costs}}
- Marketing: ${{marketing_costs}}
- Professional services: ${{services_costs}}
- Other: ${{other_costs}}

Constraints:
- Cannot reduce headcount by more than {{max_headcount_reduction}}%
- Must maintain {{protected_functions}} teams at current capacity
- Customer-facing quality cannot degrade

Produce the following analysis:
1. **Cost Benchmarking** — Compare our cost ratios (cost as % of revenue) against {{industry}} industry benchmarks. Highlight categories where we are above benchmark.
2. **Quick Wins** (0-3 months) — 5+ opportunities requiring minimal effort. For each: action, estimated savings, implementation steps, and risk.
3. **Medium-Term Initiatives** (3-12 months) — 5+ structural changes. For each: action, estimated savings, investment required, payback period, and risk.
4. **Strategic Restructuring** (12+ months) — 3+ transformational options with full business case.
5. **Prioritization Matrix** — Rank all initiatives by: savings potential vs. implementation difficulty (2x2 matrix).
6. **Implementation Roadmap** — Phased timeline with milestones and accountable owners.

Output as an executive briefing with summary table upfront showing total identified savings by category and timeframe.