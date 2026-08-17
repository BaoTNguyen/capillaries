---
intent: [improve, decide]
task_type: [analyze, optimize]
domain: [technical, strategy]
primary_stage: plan
complexity_level: 4
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Analyze and prioritize technical debt for the **{{project_name}}** project at **{{company_name}}**.

Known tech debt items:
{{tech_debt_list}}

Additional context:
- Team size: {{team_size}} engineers
- Upcoming roadmap priorities: {{roadmap_priorities}}
- Current pain points from the team: {{team_pain_points}}
- Recent incident history related to tech debt: {{incident_history}}
- Available engineering time for debt reduction: {{available_capacity}} per sprint

For each tech debt item, assess:
1. **Impact Score (1-5)** — How much does this slow down development, cause incidents, or degrade user experience?
2. **Effort Estimate** — T-shirt size (S/M/L/XL) with approximate sprint count
3. **Risk of Inaction** — What happens if we ignore this for another 6 months?
4. **Dependencies** — Does this block or enable other work?
5. **Quick Win Potential** — Can this be partially addressed with a small investment?

Then produce:
- **Prioritized Backlog** — Ordered list using an impact-to-effort ratio, with the top item explained in detail
- **Recommended Quarterly Plan** — Which items to tackle in Q1 vs Q2 vs Q3, balancing quick wins with strategic investments
- **Business Case Summary** — A non-technical paragraph explaining to leadership why this investment matters, with projected benefits (velocity improvement, incident reduction, developer satisfaction)
- **Tracking Dashboard Spec** — Suggest 5 metrics to track tech debt reduction progress over time

Output as a prioritization document suitable for sprint planning and leadership review.
