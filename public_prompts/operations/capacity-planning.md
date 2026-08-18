---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt assists operations leaders in forecasting staffing needs and
  resource gaps for a team over a planning horizon. The model must create a capacity
  plan with demand forecasts, scenario modeling, hiring timelines, and budget implications.
complexity_level: 4
domain:
- business
- strategy
intent:
- decide
- explore
primary_stage: plan
source: public
task_type:
- model
- analyze
---

Create a capacity plan for the **{{team_or_department}}** at **{{company_name}}** covering the next **{{planning_horizon}}**.

Current state:
- Current headcount: {{current_headcount}} (by role: {{role_breakdown}})
- Current utilization rate: {{utilization_rate}}%
- Current throughput: {{throughput_metric}} per {{time_unit}}
- Average ramp time for new hires: {{ramp_time}}
- Current backlog: {{backlog_size}}
- Attrition rate: {{attrition_rate}}% annually

Demand forecast:
- Projected demand growth: {{demand_growth}}
- Upcoming projects/initiatives: {{upcoming_projects}}
- Seasonal patterns: {{seasonality}}
- Known demand spikes: {{demand_spikes}}

Produce the following:
1. **Current Capacity Assessment** — How much capacity do we have today? What is our throughput ceiling? Where are we already constrained?
2. **Demand Forecast** — Project demand month-by-month for the planning horizon, accounting for growth and seasonality.
3. **Gap Analysis** — Where and when will demand exceed capacity? Quantify the gap in headcount equivalents.
4. **Scenarios** — Model three staffing scenarios:
   - **Conservative** — Hire only for confirmed demand
   - **Moderate** — Hire for projected demand with a buffer
   - **Aggressive** — Hire ahead of demand to enable growth
   For each: headcount plan, total cost, risk level, and capacity coverage.
5. **Hiring Timeline** — When to open each requisition, accounting for hiring lead time and ramp time
6. **Non-Hiring Levers** — Alternatives to hiring: contractors, automation, process optimization, workload redistribution. Estimate capacity gain from each.
7. **Budget Implications** — Fully loaded cost per headcount and total investment by scenario.

Output as a planning document with month-by-month tables and a recommendation on which scenario to pursue.