---
intent: [build]
task_type: [generate]
domain: [technical]
primary_stage: execute
complexity_level: 3
source: public
Original Link: ""
Notes: "Part of the incident-response skill"
---

Generate a step-by-step remediation runbook for the following incident:

**Incident type:** {{incident_type}} (e.g., database overload, API gateway failure, memory leak, certificate expiry, deployment rollback)
**Environment:** {{environment}} (e.g., AWS, GCP, on-prem, Kubernetes)
**Affected service:** {{affected_service}}
**Current symptoms:** {{symptoms}}
**Hypothesis:** {{hypothesis}}

Generate a runbook with:

### Pre-Flight Checks
- [ ] Confirm you have necessary access (list specific permissions/roles needed)
- [ ] Verify the incident is still active (check monitoring dashboard)
- [ ] Announce in incident channel that you're starting remediation

### Diagnostic Steps
For each step:
```
Step N: [Action name]
Command: [exact command to run, with placeholders]
Expected output: [what you should see if this is/isn't the issue]
If unexpected: [what to do instead]
```

### Remediation Steps
For each step:
```
Step N: [Action name]
Command: [exact command]
Rollback: [how to undo this step if it makes things worse]
Verification: [how to confirm this step worked]
⚠️ Risk: [any risk associated with this step]
```

### Verification Checklist
- [ ] Primary symptom resolved (how to check)
- [ ] No secondary issues introduced (what to monitor)
- [ ] Metrics returning to baseline (which dashboards to watch, for how long)
- [ ] Customer-facing impact confirmed resolved

### Post-Remediation
- [ ] Update incident channel with resolution
- [ ] Trigger status page update
- [ ] Document root cause (one sentence)
- [ ] Schedule postmortem within 48 hours

Keep commands concrete and copy-pasteable. Use {{placeholders}} only for environment-specific values like hostnames and credentials.
