---
Notes: Part of the product-launch-campaign skill
Original Link: ''
Summary: 'Intended for product marketing strategists defining competitive positioning,
  this prompt analyzes category definition, competitor matrices, and differentiation
  attributes. It outputs a positioning document featuring a formal positioning statement,
  messaging hierarchy, and identified positioning risks. Required context: [target
  customer], [need/pain point], [category], [key benefit], [primary competitor], [key
  differentiator].'
complexity_level: 4
domain:
- marketing
- product
intent:
- analyze
primary_stage: plan
source: public
task_type:
- market-analysis
---

# Market Positioning Analysis

You are a senior product marketing strategist. Analyze the competitive market positioning for the product described below and produce a structured positioning document.

## Product Context

- **Product name:** {{product_name}}
- **One-line description:** {{product_description}}
- **Target audience:** {{target_audience}}
- **Key capabilities:** {{key_capabilities}}
- **Known competitors:** {{competitor_list}}

## Analysis Instructions

1. **Category Definition:** Define the market category this product competes in. If the product creates a new category, articulate what that category is and why existing categories are insufficient.

2. **Competitive Landscape Matrix:** For each competitor listed (and any obvious ones I missed), evaluate across these dimensions:
   - Core value proposition
   - Target buyer persona
   - Pricing model (if publicly known)
   - Key strengths and weaknesses
   - Market share or momentum indicators

3. **Differentiation Analysis:** Identify the 3-5 attributes where {{product_name}} most clearly differentiates. For each, explain:
   - Why this matters to {{target_audience}}
   - How defensible this advantage is (easy to copy vs. structural moat)
   - Evidence or proof points that support the claim

4. **Positioning Statement:** Write a positioning statement following this framework:
   - For [target customer] who [need/pain point], {{product_name}} is the [category] that [key benefit]. Unlike [primary competitor], we [key differentiator].

5. **Messaging Hierarchy:** Propose a three-tier messaging hierarchy:
   - **Tier 1 (headline):** One sentence that captures the essence
   - **Tier 2 (elevator pitch):** 2-3 sentences expanding on the value
   - **Tier 3 (proof points):** 3-5 supporting claims with evidence

6. **Positioning Risks:** Identify potential positioning pitfalls:
   - Claims that competitors could credibly counter
   - Audience segments where this positioning may not resonate
   - Market shifts that could undermine the positioning within 12 months

## Output Format

Return a structured document with clear section headers matching the six areas above. Use tables for the competitive matrix. Be specific and opinionated rather than generic.