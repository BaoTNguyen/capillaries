---
intent: [automate, build]
task_type: [generate]
domain: [business]
primary_stage: execute
complexity_level: 1
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Create an offboarding process checklist for **{{employee_name}}**, a **{{role_title}}** in the **{{department}}** department. Their last day is **{{last_day}}**.

Departure type: {{departure_type}} (voluntary resignation / involuntary / retirement / contract end)

Generate a complete checklist covering:
1. **Knowledge Transfer** — Document key responsibilities, ongoing projects, passwords/access to hand over, and the designated recipient for each
2. **IT & Access** — Accounts to disable, hardware to collect, software licenses to reclaim
3. **HR Administration** — Final paycheck details, benefits continuation (COBRA or equivalent), PTO payout, exit interview scheduling
4. **Manager Tasks** — Transition communication to the team, redistribution of work, backfill requisition
5. **Exit Interview Questions** — 5 open-ended questions to gather honest feedback

For each item, specify: Task | Owner (HR / IT / Manager / Employee) | Deadline (relative to last day).
Output as a table-based checklist ready to be imported into a project management tool.
