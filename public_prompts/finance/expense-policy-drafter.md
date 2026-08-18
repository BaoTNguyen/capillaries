---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This template supports finance teams in creating comprehensive expense reimbursement
  policies tailored to company size and industry. The model must draft a numbered
  policy document covering eligibility, approval workflows, and submission processes.
complexity_level: 2
domain:
- finance
- business
intent:
- build
primary_stage: execute
source: public
task_type:
- generate
---

Draft a company expense reimbursement policy for **{{company_name}}**, a {{company_size}}-person company in the **{{industry}}** industry.

Policy parameters:
- Annual per-employee expense budget: ${{annual_budget}}
- Approval thresholds: manager approval up to ${{manager_threshold}}, VP approval up to ${{vp_threshold}}, CFO above that
- Receipt requirement threshold: ${{receipt_threshold}}
- Reimbursement timeline: {{reimbursement_days}} business days

The policy must cover:
1. **Purpose & Scope** — Who the policy applies to and its objective
2. **Eligible Expenses** — Travel (flights, hotels, ground transport), meals (per diem rates or actuals), client entertainment, office supplies, professional development, home office
3. **Ineligible Expenses** — Personal items, alcohol (policy: {{alcohol_policy}}), first-class travel, spouse travel
4. **Spending Limits** — Table with category, per-occurrence limit, and annual limit
5. **Approval Workflow** — Step-by-step process with approval tiers
6. **Submission Process** — How to submit (tool: {{expense_tool}}), required documentation, and deadlines
7. **Non-Compliance** — Consequences for policy violations
8. **Exceptions** — How to request an exception and who approves

Tone: Clear, firm but fair. Output as a policy document with numbered sections ready for leadership sign-off.