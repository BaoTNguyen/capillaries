---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt supports product leaders in analyzing competitors within a specific
  industry and target market. The model must produce a strategy document featuring
  a feature matrix, positioning map, and prioritized strategic recommendations.
complexity_level: 4
domain:
- business
- strategy
intent:
- explore
- decide
primary_stage: plan
source: public
task_type:
- analyze
- compare
---

Conduct a competitive analysis for **{{company_name}}** in the **{{industry}}** space.

Our product/service: {{product_description}}
Target market: {{target_market}}
Competitors to analyze: {{competitor_1}}, {{competitor_2}}, {{competitor_3}}

For each competitor, analyze:
1. **Company Overview** — Size, funding, market position, and target customer
2. **Product Comparison** — Features, pricing model, and unique selling propositions
3. **Strengths** (3-4 per competitor, with evidence)
4. **Weaknesses** (3-4 per competitor, with evidence)
5. **Go-to-Market Strategy** — Channels, messaging, and content approach
6. **Customer Sentiment** — What their users praise and complain about (based on common review themes)

Then produce:
- **Feature Comparison Matrix** — Table with features as rows, competitors as columns, using checkmarks and X marks
- **Positioning Map** — Describe a 2x2 matrix with axes: {{axis_1}} vs {{axis_2}}, and where each player sits
- **Opportunities** — 3-5 gaps in the market we can exploit
- **Threats** — 3-5 competitive moves we should prepare for
- **Strategic Recommendations** — 5 prioritized actions with rationale

Output as a strategy document suitable for a product leadership meeting.