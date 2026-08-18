---
Notes: Part of the public showcase collection
Original Link: ''
Summary: 'This prompt generates a concise project status report for stakeholders to
  assess health in 30 seconds. The model formats provided details into a one-page
  artifact with progress, risks, and metrics. Required context: [status], [Bullet
  list of what was accomplished], [Bullet list of planned work with owners], [Each
  risk with severity and mitigation], [Any decisions required from stakeholders, with
  deadline].'
complexity_level: 1
domain:
- business
intent:
- communicate
primary_stage: execute
source: public
task_type:
- synthesize
---

Generate a project status report for **{{project_name}}** covering **{{reporting_period}}**.

**Project details:**
- Owner: {{project_owner}}
- Status: {{overall_status}} (On Track / At Risk / Blocked)
- Key milestones completed: {{completed_milestones}}
- Upcoming milestones: {{upcoming_milestones}}
- Blockers or risks: {{blockers}}

Format the report as:

**{{project_name}} — Status Report ({{reporting_period}})**
🟢/🟡/🔴 Overall: [status]

**Progress this period:**
- [Bullet list of what was accomplished]

**Upcoming (next 2 weeks):**
- [Bullet list of planned work with owners]

**Risks & Blockers:**
- [Each risk with severity and mitigation]

**Decisions Needed:**
- [Any decisions required from stakeholders, with deadline]

**Key Metrics:**
| Metric | Current | Target | Trend |
|--------|---------|--------|-------|

Keep it under 1 page. Stakeholders should understand project health in 30 seconds.