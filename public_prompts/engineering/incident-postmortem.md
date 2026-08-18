---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt helps engineering teams document blameless incident postmortems
  for technical outages. The model structures a comprehensive report including executive
  summaries, root cause analysis using the 5 Whys, and prioritized action items for
  preventive measures.
complexity_level: 3
domain:
- technical
- business
intent:
- reflect
- improve
primary_stage: reflect
source: public
task_type:
- analyze
- synthesize
---

Write a blameless incident postmortem for the **{{incident_title}}** incident at **{{company_name}}**.

Incident details:
- Severity: {{severity_level}} (SEV1-SEV4)
- Date/time detected: {{detection_time}}
- Date/time resolved: {{resolution_time}}
- Duration of customer impact: {{impact_duration}}
- Services affected: {{affected_services}}
- Number of users impacted: {{users_impacted}}
- On-call engineer: {{oncall_engineer}}

Raw timeline events: {{timeline_events}}
Root cause (preliminary): {{root_cause}}
How it was fixed: {{fix_description}}

Structure the postmortem as follows:
1. **Executive Summary** (3-4 sentences) — What happened, who was affected, how long, and current status
2. **Impact** — Quantify: error rates, failed requests, revenue impact, SLA implications
3. **Timeline** — Minute-by-minute chronology from detection to resolution, including key decisions and escalations
4. **Root Cause Analysis** — Use the "5 Whys" technique to get to the true root cause. Be specific and technical.
5. **Contributing Factors** — What made the incident worse or slower to resolve (monitoring gaps, runbook issues, communication breakdowns)
6. **What Went Well** — What worked in our response (detection speed, team coordination, etc.)
7. **Action Items** — Table with: Action | Owner | Priority (P0/P1/P2) | Due Date | Status. Include both preventive and detective measures.
8. **Lessons Learned** — 3-5 takeaways for the broader engineering org

Tone: Blameless, factual, and constructive. Output as a complete postmortem document.