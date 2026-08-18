---
Notes: Part of the public showcase collection
Original Link: ''
Summary: 'This prompt targets teams or companies defining Objectives and Key Results
  for specific time periods and strategic priorities. The model generates qualitative
  objectives with quantitative, measurable key results, including baselines, targets,
  alignment checks, and anti-goals. Required context: [Inspiring qualitative statement],
  [Metric], [baseline], [target], [stretch], [suggested role], [Low/Med/High], [one-line
  rationale].'
complexity_level: 3
domain:
- strategy
- business
intent:
- build
primary_stage: plan
source: public
task_type:
- design
---

Build an OKR (Objectives and Key Results) framework for **{{team_or_company}}** for **{{time_period}}**.

**Strategic priorities:** {{strategic_priorities}}
**Current challenges:** {{current_challenges}}
**Team size:** {{team_size}}

Generate 3-4 Objectives, each with 3-4 Key Results, following these rules:
- **Objectives** are qualitative, ambitious, and inspiring — they describe the desired outcome, not the activity
- **Key Results** are quantitative, measurable, and time-bound — they answer "how will we know we achieved it?"
- Each Key Result must have a baseline (current state), target, and stretch target
- Include a mix of output KRs (what we deliver) and outcome KRs (what impact it has)

Format:
```
**Objective 1:** [Inspiring qualitative statement]
  KR 1.1: [Metric] from [baseline] to [target] (stretch: [stretch])
  KR 1.2: ...
  KR 1.3: ...
  Owner: [suggested role]
  Confidence: [Low/Med/High] — [one-line rationale]
```

After the OKRs, include:
- **Alignment check** — how each objective maps to the stated strategic priorities
- **Dependencies** — cross-team or external dependencies that could block key results
- **Anti-goals** — 2-3 things this team should explicitly NOT focus on this period