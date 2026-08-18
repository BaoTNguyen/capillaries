---
Notes: Part of the contract-negotiation skill
Original Link: ''
Summary: Designed for negotiators preparing for contract discussions, this prompt
  leverages BATNA analysis to structure strategy. The model must produce opening positions,
  concession tactics, scripted responses, and a one-page cheat sheet containing key
  numbers and walk-away points.
complexity_level: 3
domain:
- business
intent:
- prepare
primary_stage: plan
source: public
task_type:
- design
---

Prepare a negotiation strategy and talking points for the following contract discussion:

**Counterparty:** {{counterparty_name}}
**Negotiation context:** {{context}} (e.g., new agreement, renewal, amendment)
**Our BATNA:** {{batna}} (Best Alternative to Negotiated Agreement)
**Their likely BATNA:** {{their_batna}}
**Key issues to negotiate:** {{key_issues}}
**Meeting format:** {{format}} (e.g., video call, in-person, email exchange)
**Our negotiator:** {{negotiator_role}}

Generate:

1. **Opening position** — how to frame the conversation, what to lead with, establishing tone
2. **For each key issue:**
   - Our ideal outcome
   - Our acceptable range
   - Their likely position and why
   - Concession strategy — what we give to get what we need
   - Specific language to use (exact phrases)
3. **Anchoring strategy** — what number or position to put on the table first and why
4. **If they push back** — scripted responses for 3-4 likely objections
5. **Body language / tactical notes** — when to pause, when to show flexibility, when to hold firm
6. **Closing protocol** — how to wrap up, what to confirm verbally vs. in writing, next steps

End with a **one-page cheat sheet** — a quick-reference card the negotiator can glance at during the meeting with key numbers, walk-away points, and scripted phrases.