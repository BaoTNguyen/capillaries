---
intent: [build]
task_type: [explain]
domain: [writing, technical]
primary_stage: execute
complexity_level: 1
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
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
