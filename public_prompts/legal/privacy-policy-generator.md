---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt generates a compliant privacy policy for companies operating
  in specified jurisdictions with defined data practices. The model must produce a
  ready-to-publish document covering data collection, usage, rights, and security
  measures in clear, accessible language.
complexity_level: 4
domain:
- business
- technical
intent:
- build
primary_stage: execute
source: public
task_type:
- generate
---

Draft a privacy policy for **{{company_name}}**, a **{{company_description}}** that operates in **{{jurisdictions}}**.

**Data practices to cover:**
- Types of personal data collected: {{data_types}}
- Collection methods: {{collection_methods}}
- Third-party services used: {{third_party_services}}
- Data retention period: {{retention_period}}

The policy must address:
1. **Information We Collect** — categories of personal data, distinguishing between data provided directly vs. collected automatically
2. **How We Use Your Information** — each purpose tied to a legal basis (consent, legitimate interest, contractual necessity)
3. **Sharing & Disclosure** — who receives data, why, and under what safeguards
4. **Data Retention** — how long each category is kept and why
5. **Your Rights** — rights applicable in the listed jurisdictions (access, deletion, portability, opt-out)
6. **Security Measures** — general description of protections without revealing implementation details
7. **Cookies & Tracking** — what tracking technologies are used and how to control them
8. **Children's Privacy** — age restrictions and parental consent mechanisms if applicable
9. **Changes to This Policy** — how users will be notified of updates
10. **Contact Information** — how to reach the data protection officer or privacy team

Write in clear, readable language (8th-grade reading level). Include section anchors for easy navigation. Output as a complete, ready-to-publish document.