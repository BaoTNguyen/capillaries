---
intent: [validate]
task_type: [analyze]
domain: [business]
primary_stage: verify
complexity_level: 3
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
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
