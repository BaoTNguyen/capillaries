---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt serves communications teams managing high-stakes scenarios like
  data breaches or product recalls. The model must generate an actionable playbook
  including stakeholder matrices, holding statements, Q&A documents, and media protocols.
complexity_level: 4
domain:
- business
- strategy
intent:
- prepare
primary_stage: plan
source: public
task_type:
- design
---

Create a crisis communication plan for **{{company_name}}** to handle the following scenario:

**Crisis type:** {{crisis_type}} (e.g., data breach, product recall, executive departure, PR incident, service outage)
**Severity:** {{severity}} (low / medium / high / critical)
**Stakeholders affected:** {{affected_stakeholders}}

The plan must include:

1. **Situation Assessment** — key facts, timeline of events, scope of impact, what is known vs. unknown
2. **Response Team** — roles and responsibilities (spokesperson, legal, comms, ops, executive sponsor) with escalation chain
3. **Stakeholder Matrix** — for each audience (employees, customers, investors, media, regulators, partners):
   - What they need to hear
   - Communication channel (email, press release, social, 1:1, town hall)
   - Timing (immediate, within 24h, within 48h)
   - Draft talking points (3-5 bullets each)
4. **Holding Statement** — a ready-to-publish initial statement (under 150 words) that acknowledges the situation without speculation
5. **Q&A Document** — anticipate 10 tough questions and provide approved responses
6. **Media Protocol** — who can speak to press, what's on/off the record, bridge statements for deflecting premature questions
7. **Recovery Communication** — template for the follow-up message once the crisis is resolved, focusing on what was learned and what changed
8. **Post-Crisis Review** — checklist for a retrospective within 1 week of resolution

Output as a complete, actionable playbook that the response team can execute under pressure.