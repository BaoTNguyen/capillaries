---
Notes: Part of the incident-response skill
Original Link: ''
Summary: This prompt assists incident responders in classifying production outages
  by evaluating user impact, revenue risk, and data integrity against defined severity
  tiers. The model must output a severity level (SEV-1 to SEV-4) with specific escalation
  requirements, communication cadence, and resolution windows.
complexity_level: 2
domain:
- technical
intent:
- validate
primary_stage: clarify
source: public
task_type:
- evaluate
---

Assess the severity of the following production incident and recommend the appropriate response level:

**Incident description:** {{incident_description}}
**Systems affected:** {{affected_systems}}
**User impact:** {{user_impact}} (e.g., "API returning 500s for 30% of requests", "payments processing delayed")
**Duration so far:** {{duration}}
**Workaround available:** {{workaround}} (yes/no, describe if yes)

Evaluate against these dimensions:

| Dimension | Assessment | Evidence |
|-----------|-----------|----------|
| **User Impact Scope** | % of users affected | |
| **Revenue Impact** | Estimated revenue at risk per hour | |
| **Data Integrity** | Any data loss or corruption risk? | |
| **Security Exposure** | Any unauthorized access or data exposure? | |
| **Regulatory Impact** | Any compliance obligations triggered? | |
| **Reputational Risk** | Likelihood of external visibility | |

**Recommended Severity:**
- **SEV-1 (Critical):** Complete outage, data breach, >50% users affected
- **SEV-2 (High):** Major degradation, revenue impact, >10% users affected
- **SEV-3 (Medium):** Partial degradation, workaround available, <10% users
- **SEV-4 (Low):** Minor issue, no user impact, cosmetic or internal

For the assigned severity, specify:
- **Escalation requirement** — who must be notified immediately
- **Communication cadence** — how often to update stakeholders
- **Response team size** — minimum roles needed (IC, comms lead, subject matter expert)
- **Expected resolution window** — based on severity SLA