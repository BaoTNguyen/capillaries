---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt targets HR professionals or managers creating a structured onboarding
  plan for a new hire joining a specific department. The model must generate a detailed
  checklist table covering five time periods, assigning owners and due dates for tasks
  like IT setup and training.
complexity_level: 1
domain:
- business
intent:
- build
- automate
primary_stage: execute
source: public
task_type:
- generate
---

Create a detailed onboarding checklist for a new **{{role_title}}** joining the **{{department}}** team at **{{company_name}}**.

Structure the checklist across these time periods:
1. **Before Day 1** — IT setup, access provisioning, welcome email, buddy assignment
2. **Day 1** — Orientation schedule, key introductions, workspace setup
3. **Week 1** — Tool walkthroughs, initial 1:1 with manager, team norms overview
4. **Days 8-30** — Role-specific training, first small deliverable, 30-day check-in
5. **Days 31-90** — Deeper project involvement, cross-team introductions, 90-day review

The new hire's manager is **{{manager_name}}** and their onboarding buddy is **{{buddy_name}}**.
Start date: {{start_date}}.

For each item, include: the task, the owner (HR / Manager / IT / Buddy), and a due date relative to start.
Output as a checklist table with columns: Task | Owner | Due | Status.