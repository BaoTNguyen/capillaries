---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt facilitates a sprint retrospective for a specified team by analyzing
  provided metrics, goals, and feedback items. The model must generate a structured
  document containing a summary, wins, challenges with root causes, actionable items,
  and a team health check rating.
complexity_level: 2
domain:
- technical
- business
intent:
- reflect
- improve
primary_stage: reflect
source: public
task_type:
- synthesize
---

Facilitate and document a sprint retrospective for the **{{team_name}}** team covering **{{sprint_name}}** ({{sprint_dates}}).

Sprint context:
- Sprint goal: {{sprint_goal}}
- Goal achieved: {{goal_achieved}} (yes/partially/no)
- Planned story points: {{planned_points}}
- Completed story points: {{completed_points}}
- Carry-over items: {{carryover_items}}
- Notable events: {{notable_events}}

Team feedback collected:
- What went well: {{went_well_items}}
- What didn't go well: {{didnt_go_well_items}}
- What confused us: {{confusion_items}}

Generate:
1. **Sprint Summary** — 3-4 sentences covering what was delivered, velocity, and whether the goal was met
2. **Wins** — Celebrate 3-5 specific things that went well, tying them to team behaviors worth repeating
3. **Challenges** — 3-5 things that slowed us down, grouped into themes (process, technical, communication, external)
4. **Root Causes** — For each challenge theme, dig one level deeper into why it happened
5. **Action Items** — 3-5 concrete, assignable actions. For each: description, owner, due date, and how we will know it is done
6. **Team Health Check** — Rate (green/yellow/red) on: collaboration, delivery pace, code quality, morale, and stakeholder satisfaction

Keep action items realistic — no more than 5 per sprint. Output as a retro document the team can reference next sprint.