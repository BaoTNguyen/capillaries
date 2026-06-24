---
intent: [automate]
task_type: [synthesize]
domain: [business]
primary_stage: reflect
complexity_level: 2
source: public
Original Link: ""
Notes: "Part of the quarterly-business-review skill"
---

Convert the following meeting notes or discussion transcript into tracked action items:

**Meeting:** {{meeting_name}}
**Date:** {{meeting_date}}
**Attendees:** {{attendees}}

**Raw notes/transcript:**
{{meeting_notes}}

For each action item identified, create a SMART entry:

| # | Action Item | Owner | Due Date | Priority | Dependencies | Status |
|---|------------|-------|----------|----------|-------------|--------|
| 1 | [Specific, measurable action — not vague like "improve X" but "Reduce X from Y to Z by doing W"] | [Name] | [Date] | P1/P2/P3 | [Blocking items] | Not Started |

After the table, provide:

1. **Decisions Made** — list any decisions that were finalized during the meeting, with who made them
2. **Open Questions** — items discussed but not resolved, with suggested owner to follow up
3. **Parking Lot** — topics raised but deferred to a future meeting
4. **Follow-up meeting needed?** — yes/no, with suggested agenda if yes

Rules:
- Every action item must have a single owner (no "team" ownership)
- Due dates must be specific (not "next week" — give a calendar date)
- If the notes don't specify an owner or date, suggest one based on context and flag it with "[SUGGESTED]"
- Consolidate duplicate or overlapping action items
