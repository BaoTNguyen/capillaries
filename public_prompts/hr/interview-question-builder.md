---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt supports hiring managers in creating structured interview guides
  for specific roles and seniority levels. The model generates behavioral, technical,
  and situational questions with scoring rubrics, strong answer criteria, and red
  flags to assess candidate fit.
complexity_level: 2
domain:
- career
- business
intent:
- prepare
primary_stage: plan
source: public
task_type:
- generate
---

Create a structured interview question set for the **{{role_title}}** position at the **{{seniority_level}}** level.

Generate questions in these categories:
1. **Behavioral** (4 questions) — Use the STAR format prompt. Focus on {{key_competency_1}} and {{key_competency_2}}.
2. **Technical / Role-Specific** (4 questions) — Assess hands-on ability in {{primary_skill}}.
3. **Culture Fit** (3 questions) — Align with our values: {{company_values}}.
4. **Situational** (3 questions) — Present realistic scenarios the candidate would face in this role.

For each question, include:
- The question itself
- What a strong answer looks like (2-3 sentences)
- A red flag to watch for

Interview duration: {{interview_duration_minutes}} minutes.
Output as a printable interviewer guide with a scoring rubric (1-5) for each question.