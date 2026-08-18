---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt targets CHROs and CEOs seeking a strategic restructuring proposal
  for a specific department. The model must generate a comprehensive document detailing
  rationale, new org charts, role mappings, a 90-day transition plan, risk assessments,
  communication scripts, and success metrics.
complexity_level: 5
domain:
- business
- strategy
intent:
- decide
- build
primary_stage: plan
source: public
task_type:
- design
- analyze
---

Design a restructuring plan for the **{{department}}** department at **{{company_name}}**.

Current state:
- Team size: {{current_headcount}} people
- Current org structure: {{current_structure_description}}
- Key pain points: {{pain_points}}
- Business objective driving the restructure: {{restructure_reason}}
- Budget constraints: {{budget_constraints}}

Produce a comprehensive restructuring proposal with:
1. **Rationale** — Why the current structure is failing to meet objectives (tie to business metrics)
2. **Proposed Structure** — New reporting lines, team groupings, and role definitions. Include an org chart description.
3. **Role Changes** — Table of current roles mapped to new roles (eliminated, merged, created, unchanged)
4. **Transition Plan** — Phased timeline across 90 days with milestones for each phase
5. **Risk Assessment** — Top 5 risks (flight risk of key talent, knowledge gaps, morale) with mitigations
6. **Communication Plan** — Who hears what, when, and from whom. Script key talking points for managers.
7. **Success Metrics** — How we will measure whether the restructure achieved its goals at 6 and 12 months

Tone: Strategic and empathetic. This document will be reviewed by the CHRO and CEO.
Output as a structured proposal document with clear section headers.