---
intent: [communicate]
task_type: [generate]
domain: [technical, business]
primary_stage: execute
complexity_level: 2
source: public
Original Link: ""
Notes: "Part of the incident-response skill"
---

Draft incident communications for multiple audiences:

**Incident:** {{incident_summary}}
**Severity:** {{severity_level}}
**Current status:** {{current_status}} (investigating / identified / monitoring / resolved)
**Impact:** {{impact_description}}
**ETA to resolution:** {{eta}}

Generate separate communications for each audience:

### 1. Engineering Team (Slack/Internal Chat)
- Technical detail level: high
- Include: affected services, error codes, current hypothesis, who's working on what
- Tone: concise, tactical, no sugar-coating

### 2. Customer-Facing Status Page
- Technical detail level: low
- Include: what's affected, current status, expected resolution time
- Tone: calm, professional, empathetic
- Max 100 words

### 3. Executive Stakeholders (Email/Slack)
- Technical detail level: minimal
- Include: business impact, customer exposure, team response, ETA
- Tone: confident, in-control, transparent about unknowns

### 4. Customer Support Team (Internal)
- Include: what to tell customers who contact us, workarounds, escalation path
- Format: FAQ-style (Q: customer asks... A: respond with...)
- Include 5 anticipated customer questions with approved responses

For each communication, mark placeholders that need to be filled in real-time with [FILL: description].

Include a **follow-up template** for the next update (30/60 min later depending on severity).
