---
Notes: Part of the public showcase collection
Original Link: ''
Summary: 'This prompt generates a compliance checklist for a specific regulation applicable
  to a company in a defined industry. The model must output a markdown checklist covering
  data handling, reporting, employee requirements, documentation, technical controls,
  and third-party risk, flagging items requiring external counsel. Required context:
  [ ], [EXTERNAL].'
complexity_level: 3
domain:
- business
intent:
- validate
primary_stage: verify
source: public
task_type:
- analyze
---

Generate a compliance checklist for **{{regulation_or_standard}}** applicable to **{{company_name}}** in the **{{industry}}** industry.

The checklist should cover:
1. **Data handling & privacy** — consent, storage, access controls, retention policies
2. **Reporting obligations** — what must be reported, to whom, and how often
3. **Employee requirements** — training, certifications, background checks
4. **Documentation** — what records must be maintained and for how long
5. **Technical controls** — encryption, access logging, incident response procedures
6. **Third-party risk** — vendor assessments, data processing agreements, subcontractor requirements

For each item, provide:
- [ ] The specific requirement (actionable, one sentence)
- Responsible role (e.g., "CISO", "HR Director", "DPO")
- Evidence needed to demonstrate compliance
- Review frequency (annual, quarterly, continuous)

Output as a markdown checklist grouped by the 6 categories above. Flag any items that typically require external counsel or auditor involvement with "[EXTERNAL]".