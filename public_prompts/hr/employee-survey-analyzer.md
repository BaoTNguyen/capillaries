---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt enables HR directors to analyze employee engagement survey data
  for specific departments and time periods. The model must generate an executive
  summary, trend analysis, and prioritized action items in a presentation-ready report.
complexity_level: 3
domain:
- business
intent:
- explore
- improve
primary_stage: verify
source: public
task_type:
- analyze
---

Analyze the results of our employee engagement survey for **{{department}}** at **{{company_name}}** covering **{{survey_period}}**.

Survey data summary:
- Response rate: {{response_rate}}%
- Overall engagement score: {{engagement_score}} / 5
- Key category scores: {{category_scores}}
- Open-ended feedback themes: {{open_feedback_themes}}
- Previous period engagement score: {{previous_score}} / 5

Produce the following analysis:
1. **Executive Summary** (3-4 sentences on the overall picture)
2. **Top 3 Strengths** — categories scoring highest, with interpretation of why
3. **Top 3 Concern Areas** — categories scoring lowest, with root cause hypotheses
4. **Trend Analysis** — compare to last period's score and call out meaningful shifts
5. **Demographic Breakdowns** — note any significant differences by tenure, role level, or team if data permits
6. **Recommended Actions** (5-7 specific, prioritized initiatives with expected impact and effort level)

Present quantitative findings in tables. Write qualitative analysis in concise paragraphs.
Output as a presentation-ready report that an HR director could share with leadership.