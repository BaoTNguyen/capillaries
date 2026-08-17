---
name: Incident Response
tag: incident-response
status: active
routing_description: >
  Handle production incidents from initial triage through resolution and
  postmortem. Includes severity classification, stakeholder communications,
  remediation runbook generation, log timeline analysis, and blameless
  postmortem facilitation. Use during active incidents or when preparing
  incident response procedures.
domain: [technical, business]
intent: [validate, communicate]
task_type: [analyze, generate]
complexity_level: 3
source: public
created_by: system
files:
  - path: severity-classifier-prompt.md
    type: prompt
    description: Assess incident severity, blast radius, and escalation requirements
  - path: comms-drafter-prompt.md
    type: prompt
    description: Draft audience-appropriate stakeholder communications during incidents
  - path: runbook-generator-prompt.md
    type: prompt
    description: Generate step-by-step remediation runbook for the specific incident type
  - path: timeline-builder.py
    type: code
    language: python
    description: Parse timestamped log lines into a chronological incident timeline with gap detection
  - path: postmortem-template-prompt.md
    type: prompt
    description: Create a structured blameless postmortem document
---

## Overview

This skill provides a complete incident response toolkit for engineering and operations teams. It covers the full lifecycle from initial triage through resolution and learning — severity assessment, stakeholder communication, tactical remediation, timeline reconstruction, and blameless retrospection.

The toolkit is designed to be grabbed during an active incident (severity classifier, comms drafter, runbook generator) or used post-incident for analysis and documentation (timeline builder, postmortem template). The Python timeline builder automates the tedious work of reconstructing what happened when from raw logs.

## When to Use This

- A production incident is in progress and you need to quickly classify severity and communicate
- You're the incident commander and need a remediation runbook fast
- An incident just resolved and you need to write the postmortem
- You're building or improving your team's incident response playbook
- You have log data from an incident and need to build a human-readable timeline

## How to Use

During an active incident, start with **severity-classifier** to set the response level, then **comms-drafter** to notify stakeholders immediately. Use **runbook-generator** to build a step-by-step fix plan. After resolution, run **timeline-builder.py** on your logs, then feed that timeline into **postmortem-template** to produce the final document. Not every incident needs every file — a SEV-3 might only need the postmortem template.
