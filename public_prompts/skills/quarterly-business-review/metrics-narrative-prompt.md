---
Notes: Part of the quarterly-business-review skill
Original Link: ''
Summary: This prompt targets executives preparing quarterly business reviews by transforming
  raw metrics into strategic insights. The model must generate a concise narrative
  highlighting key trends, variance root causes, and resource asks, outputting a polished
  section ready for presentation insertion.
complexity_level: 4
domain:
- finance
- strategy
intent:
- communicate
primary_stage: execute
source: public
task_type:
- synthesize
---

Transform the following raw metrics into an executive narrative for a quarterly business review:

**Company/Team:** {{company_or_team}}
**Quarter:** {{quarter}}
**Key metrics:**
{{metrics_data}}

**Prior quarter comparisons:**
{{prior_quarter_data}}

**Annual targets:**
{{annual_targets}}

Write a narrative that:
1. **Opens with the headline** — one sentence that captures the quarter's story (e.g., "Revenue grew 18% but customer acquisition costs increased faster, compressing margins to their lowest level this year")
2. **Highlights 3-5 key metrics** — for each, state the number, the trend (vs. prior quarter and vs. plan), and the "so what" (why it matters strategically)
3. **Explains variance** — for any metric that deviated >10% from plan, provide a root cause analysis in 2-3 sentences
4. **Identifies leading indicators** — what do this quarter's numbers suggest about next quarter?
5. **Frames the ask** — what decisions or resource changes do the numbers point toward?

Rules:
- Lead with insight, not data. "Revenue was $4.2M" is data. "Revenue beat plan by 12%, driven entirely by enterprise upsells" is insight.
- Use comparisons: vs. plan, vs. prior quarter, vs. same quarter last year
- Avoid "we" when possible — use the team/company name for clarity
- Keep the entire narrative under 600 words

Output as a polished section ready to insert into a QBR presentation.