---
Notes: Part of the public showcase collection
Original Link: ''
Summary: 'This prompt helps technical writers create internal documentation for specific
  audiences and expertise levels. It produces a markdown article with step-by-step
  instructions, FAQs, and placeholders for screenshots, ready for Confluence or Notion.
  Required context: [Screenshot: description].'
complexity_level: 1
domain:
- writing
- technical
intent:
- build
primary_stage: execute
source: public
task_type:
- explain
---

Write an internal knowledge base article about:

**Topic:** {{topic}}
**Target audience:** {{audience}} (e.g., new hires, all employees, engineering team)
**Expertise level:** {{expertise_level}} (beginner / intermediate / advanced)

Structure the article as:
1. **Title** — clear, searchable (think: what would someone type to find this?)
2. **TL;DR** — 2-3 sentence summary at the top
3. **Overview** — what this is, why it matters, when someone would need this
4. **Step-by-step instructions** or **explanation** — the main content, with:
   - Numbered steps for procedures
   - Screenshots or diagram placeholders marked as `[Screenshot: description]`
   - Code snippets in fenced blocks if applicable
   - Pro tips in callout format: `> 💡 **Tip:** ...`
5. **Common issues / FAQ** — 3-5 questions someone might have, with answers
6. **Related articles** — suggest 2-3 related topics (as placeholders)

Writing rules:
- Use second person ("you") not third person
- One idea per paragraph, max 3 sentences
- Use bold for key terms on first mention
- Include a "Last updated: {{date}}" footer

Output as a complete markdown article ready to paste into Confluence, Notion, or any wiki.