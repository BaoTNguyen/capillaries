---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt targets process owners and compliance teams needing to formalize
  operational workflows within specific regulatory or departmental contexts. The model
  must generate a structured, print-ready Standard Operating Procedure document containing
  headers, roles, step-by-step instructions with decision branches, and revision history
  based on provided process details.
complexity_level: 2
domain:
- business
intent:
- build
- automate
primary_stage: execute
source: public
task_type:
- generate
---

Write a Standard Operating Procedure (SOP) for the **{{process_name}}** process at **{{company_name}}**.

Process context:
- Department: {{department}}
- Process owner: {{process_owner}}
- Frequency: {{frequency}}
- Who performs this: {{performer_roles}}
- Tools/systems involved: {{tools_used}}
- Regulatory or compliance requirements: {{compliance_requirements}}

The procedure involves: {{process_summary}}

Structure the SOP as follows:
1. **Document Header** — SOP title, document number ({{sop_number}}), version, effective date, and review date
2. **Purpose** — Why this procedure exists (2-3 sentences)
3. **Scope** — What this SOP covers and what it does not cover
4. **Definitions** — Key terms and acronyms used in this document
5. **Roles & Responsibilities** — Table of who does what
6. **Prerequisites** — What must be in place before starting (access, tools, approvals)
7. **Procedure Steps** — Numbered step-by-step instructions. Each step must be:
   - Written as a single clear action
   - Specify who performs it
   - Include expected outcome or checkpoint
   - Note any decision points with if/then branches
8. **Exception Handling** — What to do when things go wrong or deviate from normal
9. **Quality Checks** — Verification steps to confirm the procedure was completed correctly
10. **Related Documents** — Links to forms, templates, or related SOPs
11. **Revision History** — Table with version, date, author, and change description

Output as a formal, print-ready SOP document.