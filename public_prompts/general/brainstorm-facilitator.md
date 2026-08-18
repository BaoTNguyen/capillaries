---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt assists product managers or team leads facilitating structured
  brainstorming sessions for specific challenges. The model must generate ideas across
  four lenses, assess effort and impact, and produce a prioritization matrix recommending
  the top three options.
complexity_level: 2
domain:
- business
intent:
- explore
primary_stage: clarify
source: public
task_type:
- generate
---

Facilitate a structured brainstorming session for the following challenge:

**Challenge:** {{challenge_description}}
**Context:** {{context}}
**Constraints:** {{constraints}} (e.g., budget, timeline, team size, technical limitations)

Generate ideas using these 4 lenses:

1. **Conventional approaches** (3-4 ideas) — what would the industry standard be? What do competitors do?
2. **Creative alternatives** (3-4 ideas) — what if we had no constraints? What would a completely different industry do?
3. **Incremental improvements** (3-4 ideas) — what small, low-risk changes could move the needle quickly?
4. **Contrarian takes** (2-3 ideas) — what if the opposite of the obvious answer is correct? What assumptions are we making that might be wrong?

For each idea, provide:
- **One-line description**
- **Effort:** Low / Medium / High
- **Impact:** Low / Medium / High
- **Key risk or assumption**

After all ideas, create a **2x2 prioritization matrix** (effort vs. impact) placing the top 8 ideas, and recommend the top 3 to explore further with a brief rationale for each.