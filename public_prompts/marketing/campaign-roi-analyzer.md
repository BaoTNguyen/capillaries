---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt addresses marketing analysts evaluating campaign performance
  and return on investment for a specific initiative. The model must calculate key
  metrics, compare against industry benchmarks, and provide an executive-ready report
  with optimization recommendations.
complexity_level: 3
domain:
- business
- finance
intent:
- validate
- improve
primary_stage: verify
source: public
task_type:
- analyze
---

Analyze the ROI of our **{{campaign_name}}** marketing campaign run during **{{campaign_period}}** for **{{company_name}}**.

Campaign details:
- Channel(s): {{channels}}
- Total spend: ${{total_spend}}
- Objective: {{campaign_objective}}
- Target audience: {{target_audience}}

Results data:
- Impressions: {{impressions}}
- Clicks: {{clicks}}
- Conversions: {{conversions}}
- Revenue attributed: ${{revenue_attributed}}
- New leads generated: {{leads}}
- Email signups: {{email_signups}}

Produce the following analysis:
1. **Key Metrics Summary** — Table with: CTR, CPC, CPA, ROAS, conversion rate, and cost per lead
2. **ROI Calculation** — Show the formula and walk through the math step by step
3. **Channel Breakdown** — If multi-channel, compare performance across each channel
4. **Benchmark Comparison** — Compare our metrics against typical {{industry}} industry benchmarks and flag over/under-performers
5. **Funnel Analysis** — Where did we lose the most people? Identify the weakest stage.
6. **What Worked** — Top 3 things that drove performance
7. **What Didn't** — Top 3 underperformers and hypotheses for why
8. **Recommendations** — 5 specific optimizations for the next campaign with projected impact

Output as an executive-ready report with tables for quantitative data and concise paragraphs for analysis.