---
intent: [validate, improve]
task_type: [analyze, debug]
domain: [finance]
primary_stage: verify
complexity_level: 5
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Review the financial model for **{{project_or_company_name}}** and provide a comprehensive audit.

Model details:
- Purpose: {{model_purpose}} (e.g., fundraising, M&A valuation, project ROI, annual budget)
- Time horizon: {{time_horizon}}
- Key revenue drivers: {{revenue_drivers}}
- Key cost drivers: {{cost_drivers}}
- Assumptions provided: {{key_assumptions}}

Perform the following review:
1. **Structural Review** — Is the model logically organized (inputs, calculations, outputs separated)? Are there circular references? Is it easy to follow?
2. **Assumption Audit** — List every key assumption. For each, assess: Is it reasonable? Is it sourced or justified? What is the sensitivity — if it moves by 10%, how much does the output change?
3. **Formula Logic Check** — Identify any calculations that appear incorrect, inconsistent, or overly simplified. Flag hardcoded numbers that should be dynamic.
4. **Scenario & Sensitivity Analysis** — Does the model allow for scenario testing? If not, recommend which variables to parameterize. Run best/worst/base cases.
5. **Completeness Check** — What is missing? Common gaps: working capital, tax treatment, depreciation, terminal value, discount rate justification.
6. **Output Reasonableness** — Do the outputs (revenue growth, margins, valuation multiples) align with industry benchmarks for {{industry}}?
7. **Presentation Quality** — Are outputs clearly summarized? Are charts and tables effective?

For each finding, classify severity as Critical / Important / Minor and provide a specific fix.
Output as a structured audit report with a summary scorecard (1-10) at the top.
