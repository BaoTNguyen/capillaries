---
intent: [decide, explore]
task_type: [model, analyze]
domain: [finance, strategy]
primary_stage: plan
complexity_level: 4
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Build a quarterly financial forecast for **{{company_name}}** for **{{forecast_quarter}}**.

Historical data inputs:
- Revenue last 4 quarters: {{revenue_history}}
- COGS last 4 quarters: {{cogs_history}}
- Operating expenses last 4 quarters: {{opex_history}}
- Headcount plan changes: {{headcount_changes}}
- Known one-time items: {{one_time_items}}

Key assumptions to incorporate:
- Revenue growth rate assumption: {{growth_rate}}%
- New revenue streams: {{new_revenue_streams}}
- Planned cost changes: {{planned_cost_changes}}
- Seasonality factors: {{seasonality_notes}}

Produce the following:
1. **Revenue Forecast** — By product line or revenue stream, with month-by-month breakdown
2. **COGS Forecast** — Tied to revenue projections, with gross margin calculation
3. **OpEx Forecast** — By category (people, software, facilities, marketing, G&A), with assumptions stated
4. **P&L Summary** — Projected income statement for the quarter: Revenue, COGS, Gross Profit, OpEx, EBITDA, Net Income
5. **Cash Flow Implications** — Key cash in/outflow timing considerations
6. **Scenario Analysis** — Base case, upside (+{{upside_pct}}%), and downside (-{{downside_pct}}%) scenarios with P&L for each
7. **Key Risks & Sensitivities** — What assumptions, if wrong, would most impact the forecast

Output all financial tables in a clean, consistent format with dollar amounts and percentages. Include a brief narrative for each section explaining the logic behind the numbers.
