---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt generates structured performance reviews for employees based
  on provided accomplishments, growth areas, and peer feedback. The model must output
  a manager-ready document containing a summary, achievements, strengths, development
  areas, SMART goals, and an overall rating.
complexity_level: 3
domain:
- career
- business
intent:
- communicate
- reflect
primary_stage: execute
source: public
task_type:
- generate
- analyze
---

Draft a performance review for **{{employee_name}}**, a **{{role_title}}** on the **{{team_name}}** team, covering the period **{{review_period}}**.

Use the following inputs to write the review:
- Key accomplishments: {{accomplishments_summary}}
- Areas where growth was observed: {{growth_areas}}
- Areas needing improvement: {{improvement_areas}}
- Peer feedback themes: {{peer_feedback_summary}}

Structure the review with these sections:
1. **Overall Performance Summary** (3-4 sentences, balanced and specific)
2. **Key Achievements** (3-5 bullet points with measurable impact where possible)
3. **Strengths** (2-3 strengths with concrete examples)
4. **Development Areas** (2-3 areas with actionable, specific suggestions)
5. **Goals for Next Period** (3 SMART goals aligned to team objectives)
6. **Overall Rating** — use the scale: Exceeds Expectations / Meets Expectations / Developing / Below Expectations

Tone: Constructive, evidence-based, and forward-looking. Avoid vague praise or criticism.
Output as a complete, manager-ready review document.