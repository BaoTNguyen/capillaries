---
intent: [improve, automate]
task_type: [optimize, generate]
domain: [business]
primary_stage: execute
complexity_level: 1
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Create an optimized meeting agenda for: **{{meeting_title}}**.

Meeting details:
- Duration: {{duration_minutes}} minutes
- Meeting type: {{meeting_type}} (e.g., team sync, project kickoff, decision meeting, brainstorm, stakeholder update)
- Attendees: {{attendees}}
- Meeting owner: {{meeting_owner}}
- Desired outcomes: {{desired_outcomes}}

Topics to cover: {{topics_list}}
Pre-read materials: {{pre_reads}}

Generate:
1. **Optimized Agenda** — For each agenda item, include:
   - Topic title
   - Owner/presenter
   - Time allocation (in minutes)
   - Purpose tag: Inform / Discuss / Decide / Brainstorm
   - Expected output (e.g., "Decision on X", "Aligned on Y", "List of action items")

2. **Time Management Tips** — Suggest which items to cut if the meeting runs over, and which items could be handled async instead.

3. **Pre-Meeting Communication** — Draft a brief email to attendees with the agenda, pre-reads, and what to prepare.

4. **Post-Meeting Template** — A notes template with sections for: decisions made, action items (with owners and due dates), open questions, and follow-ups.

Rules to follow:
- Front-load decisions — put them in the first half when energy is highest
- No agenda item should be longer than {{max_item_minutes}} minutes
- End with 5 minutes for action item review
- Every item must have a clear owner

Output the agenda, pre-meeting email, and post-meeting template as three separate sections.
