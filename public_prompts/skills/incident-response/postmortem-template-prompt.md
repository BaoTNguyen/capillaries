---
intent: [reflect]
task_type: [synthesize]
domain: [technical, business]
primary_stage: reflect
complexity_level: 3
source: public
Original Link: ""
Notes: "Part of the incident-response skill"
---

Create a blameless postmortem document for the following incident:

**Incident title:** {{incident_title}}
**Date:** {{incident_date}}
**Duration:** {{duration}} (detection to resolution)
**Severity:** {{severity}}
**Incident Commander:** {{ic_name}}
**Timeline:** {{timeline_summary}}

Generate a complete postmortem document with these sections:

### 1. Executive Summary (3-4 sentences)
What happened, how long it lasted, who was affected, and what the outcome was.

### 2. Impact
- Users affected: [number or percentage]
- Revenue impact: [estimated]
- SLA/SLO impact: [which SLOs were breached, by how much]
- Support tickets generated: [count]

### 3. Timeline
| Time (UTC) | Event | Actor |
|-----------|-------|-------|
[Build from the timeline data provided, in chronological order]

### 4. Root Cause Analysis
- **Proximate cause:** What directly triggered the incident
- **Contributing factors:** What conditions allowed it to happen
- **Underlying cause:** Why those conditions existed (ask "why" 5 times)

### 5. What Went Well
- [3-5 things the team did right during the response — celebrate these]

### 6. What Could Be Improved
- [3-5 areas where the response could have been faster or better]

### 7. Action Items
| # | Action | Owner | Priority | Due Date | Status |
|---|--------|-------|----------|----------|--------|
[Each action must prevent recurrence or improve detection/response time. Include both technical fixes and process improvements.]

### 8. Lessons Learned
- [2-3 broader takeaways that apply beyond this specific incident]

Tone: Blameless — focus on systems and processes, not individuals. Use "the system" or "the process" rather than personal names when discussing failures. The goal is learning, not blame.

Output as a complete markdown document ready to share with the engineering team.
