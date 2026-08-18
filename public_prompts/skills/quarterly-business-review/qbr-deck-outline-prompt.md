---
Notes: Part of the quarterly-business-review skill
Original Link: ''
Summary: 'This prompt generates a slide-by-slide Quarterly Business Review outline
  for executive audiences within a specified time slot. The model produces a structured
  deck including financial performance, operational highlights, and risks, with key
  messages, data requirements, and speaker notes for each slide. Required context:
  [Specify which metrics to show, chart types, comparison periods], [Key wins, milestones,
  customer stories], [Shipped features, roadmap progress, technical milestones], [Market
  shifts, competitor moves, our positioning], [Top 3-5 risks with mitigation status],
  [3-5 priorities with owners and success metrics], [Specific decisions needed, resources
  requested, guidance sought].'
complexity_level: 3
domain:
- business
- strategy
intent:
- build
primary_stage: plan
source: public
task_type:
- design
---

Generate a structured QBR presentation outline for **{{company_or_team}}** for **{{quarter}}**.

**Audience:** {{audience}} (e.g., board of directors, executive team, department heads)
**Time slot:** {{duration}} minutes
**Key themes this quarter:** {{key_themes}}

Build a slide-by-slide outline:

**Slide 1: Title & Agenda** (30 seconds)
- Quarter headline (one sentence capturing the story)

**Slide 2: Executive Summary** (2 minutes)
- 4-5 key takeaways as bullets
- Overall health indicator (on track / needs attention / course correction needed)

**Slide 3-4: Financial Performance** (5 minutes)
- [Specify which metrics to show, chart types, comparison periods]
- Suggested data visualizations for each metric

**Slide 5: Operational Highlights** (3 minutes)
- [Key wins, milestones, customer stories]

**Slide 6: Product / Delivery** (3 minutes)
- [Shipped features, roadmap progress, technical milestones]

**Slide 7: Competitive Landscape** (2 minutes)
- [Market shifts, competitor moves, our positioning]

**Slide 8: Risks & Challenges** (3 minutes)
- [Top 3-5 risks with mitigation status]

**Slide 9: Next Quarter Priorities** (3 minutes)
- [3-5 priorities with owners and success metrics]

**Slide 10: Discussion & Asks** (remaining time)
- [Specific decisions needed, resources requested, guidance sought]

For each slide, include:
- **Key message** (what the audience should take away)
- **Data needed** (what inputs to gather)
- **Speaker notes** (2-3 talking points)
- **Time allocation** (calibrated to {{duration}} minutes total)

Ensure total time allocations add up to {{duration}} minutes with 20% reserved for Q&A.