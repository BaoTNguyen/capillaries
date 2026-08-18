---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt targets software architects and engineering leads documenting
  technical choices for a specific system. The model must generate a formal Architecture
  Decision Record (ADR) including context, ranked drivers, a comparison matrix, and
  consequences for the selected option.
complexity_level: 3
domain:
- technical
intent:
- decide
primary_stage: plan
source: public
task_type:
- analyze
- compare
---

Write an Architecture Decision Record (ADR) for the decision: **{{decision_title}}**.

Context:
- System or project: {{system_name}}
- Decision date: {{decision_date}}
- Decision makers: {{decision_makers}}
- Current architecture context: {{architecture_context}}

The decision involves choosing between:
- Option A: {{option_a}}
- Option B: {{option_b}}
- Option C: {{option_c}}

Write the ADR following this structure:
1. **Title** — ADR-{{adr_number}}: {{decision_title}}
2. **Status** — Proposed / Accepted / Deprecated / Superseded
3. **Context** — What is the technical or business situation that requires this decision? What forces are at play (scalability, team expertise, timeline, cost)?
4. **Decision Drivers** — Ranked list of criteria that matter most (e.g., performance, maintainability, time-to-market, cost, team familiarity)
5. **Options Considered** — For each option: description, pros (3+), cons (3+), estimated effort, and long-term implications
6. **Comparison Matrix** — Table scoring each option against the decision drivers (1-5 scale)
7. **Decision** — Which option was chosen and a 2-3 sentence rationale
8. **Consequences** — What changes as a result: new dependencies, team training needed, technical debt created or resolved, follow-up decisions required
9. **Compliance** — How we will verify the decision is being followed

Output as a formal ADR document that can be stored in the project's decision log.