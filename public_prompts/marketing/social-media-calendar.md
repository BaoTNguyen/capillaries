---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt generates a social media content calendar for a specified company,
  audience, and platforms like LinkedIn or Instagram. The model must produce a weekly
  table containing post copy, visual directions, hashtags, and CTAs, alongside reactive
  content slots and pillar mix ratios.
complexity_level: 2
domain:
- business
- writing
intent:
- build
- automate
primary_stage: execute
source: public
task_type:
- generate
---

Create a {{time_period}} social media content calendar for **{{company_name}}** targeting **{{target_audience}}**.

Platforms: {{platforms}} (e.g., LinkedIn, Instagram, X/Twitter, TikTok)
Posting frequency: {{posts_per_week}} posts per week per platform
Brand voice: {{brand_voice_description}}
Upcoming events or launches: {{upcoming_events}}

For each post, include:
- **Date & Platform**
- **Content Pillar** (educational, promotional, community, behind-the-scenes, user-generated)
- **Post Copy** (full draft text, platform-appropriate length)
- **Visual Direction** (1-sentence description of the image or video concept)
- **Hashtags** (3-5 relevant hashtags)
- **CTA** (call to action)

Also include:
- A weekly theme for each week in the period
- 2-3 "reactive content" slots for trending topics or timely responses
- A mix ratio across content pillars (e.g., 40% educational, 20% promotional, etc.)

Output as a table organized by week, with one row per post.