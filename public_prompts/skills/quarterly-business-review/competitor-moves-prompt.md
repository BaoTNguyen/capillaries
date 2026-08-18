---
Notes: Part of the quarterly-business-review skill
Original Link: ''
Summary: This prompt analyzes competitive landscape changes for a specified company
  and market segment during a given quarter. The model must generate a Competitor
  Activity Matrix, strategic implications, emerging threats, opportunities, and recommended
  responses in under 800 words.
complexity_level: 4
domain:
- strategy
- business
intent:
- explore
primary_stage: clarify
source: public
task_type:
- analyze
---

Summarize the competitive landscape changes relevant to **{{company_name}}** during **{{quarter}}**.

**Our market segment:** {{market_segment}}
**Key competitors:** {{competitor_list}}

**Known competitor activity this quarter:**
{{competitor_activity}}

Analyze and produce:

1. **Competitor Activity Matrix:**
| Competitor | Product Changes | Pricing Moves | Market Expansion | Key Hires/Departures | Funding/M&A |
|-----------|----------------|---------------|------------------|---------------------|-------------|

2. **Strategic Implications** — for each significant move, answer: "What does this mean for us specifically?" Consider impact on our:
   - Win rates
   - Pricing power
   - Feature roadmap priorities
   - Talent competition
   - Market positioning

3. **Emerging Threats** — any new entrants, substitute products, or technology shifts that weren't on our radar last quarter

4. **Opportunities Created** — competitor missteps, market gaps they've left open, or customer segments they've abandoned

5. **Recommended Responses** — 3-5 specific actions we should consider, each with urgency level (this quarter / next quarter / monitor)

Keep the entire analysis under 800 words. Focus on actionable intelligence, not exhaustive reporting.