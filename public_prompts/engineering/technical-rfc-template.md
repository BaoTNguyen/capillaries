---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt drafts a Technical Request for Comments for engineering stakeholders
  to review proposed system changes. The model must structure the RFC with sections
  for motivation, detailed design, alternatives, migration strategy, risks, observability,
  and timeline, incorporating provided context variables.
complexity_level: 4
domain:
- technical
- strategy
intent:
- build
- decide
primary_stage: plan
source: public
task_type:
- design
---

Write a Technical RFC (Request for Comments) for the proposed change: **{{proposal_title}}**.

Context:
- Problem statement: {{problem_statement}}
- Current system/approach: {{current_approach}}
- Why now: {{urgency_or_trigger}}
- Author: {{author_name}}
- Stakeholders: {{stakeholders}}
- Target implementation date: {{target_date}}

Structure the RFC as follows:
1. **Summary** — 2-3 sentence overview of the proposal
2. **Motivation** — Why this change is needed. Include data, user complaints, or technical debt metrics that justify the effort.
3. **Detailed Design** — The technical approach in depth. Include:
   - Architecture diagrams (describe in text/ASCII if needed)
   - Data model changes
   - API changes (request/response examples)
   - Key algorithms or logic
4. **Alternatives Considered** — At least 3 alternatives with pros/cons for each. Explain why this proposal was chosen over them.
5. **Migration & Rollout Strategy** — How we get from current state to new state. Feature flags, backward compatibility, data migration steps.
6. **Risks & Mitigations** — Technical risks, operational risks, and user-facing risks with mitigation plans.
7. **Observability** — What metrics, logs, and alerts will we add to monitor the new system?
8. **Open Questions** — Unresolved decisions that need input from reviewers
9. **Timeline & Milestones** — Phased delivery plan with estimated effort per phase

Output as a complete RFC document ready for engineering review. Include a header with: RFC number (leave as {{rfc_number}}), status (Draft), and date.