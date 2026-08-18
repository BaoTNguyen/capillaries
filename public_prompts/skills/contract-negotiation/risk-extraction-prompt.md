---
Notes: Part of the contract-negotiation skill
Original Link: ''
Summary: Contract analysts use this prompt to identify risk-bearing clauses such as
  unlimited liability, broad indemnification, and IP assignment within provided contract
  text. The model must output a detailed table of risks with plain language summaries
  and a negotiation priority list distinguishing acceptable from unacceptable terms.
complexity_level: 3
domain:
- business
intent:
- validate
primary_stage: clarify
source: public
task_type:
- analyze
---

Analyze the following contract and extract all risk-bearing clauses:

**Contract text:**
{{contract_text}}

**Our role in this contract:** {{our_role}} (e.g., buyer, service provider, licensee)

For each risk clause found, provide:

| # | Clause Location | Risk Type | Severity | Plain Language Summary | Concern |
|---|----------------|-----------|----------|----------------------|---------|
| 1 | Section X.X | Liability / IP / Termination / Data / Financial / Exclusivity | High/Med/Low | What this clause actually means | Why it's risky for us |

Risk types to look for:
- **Unlimited liability** — clauses where our exposure isn't capped
- **Broad indemnification** — we cover losses we can't control
- **Auto-renewal traps** — short notice windows, price escalation on renewal
- **IP assignment** — we lose rights to our own work product
- **Non-compete / exclusivity** — restrictions on our business
- **Data ownership** — ambiguity about who owns data generated during the engagement
- **Termination penalties** — unreasonable exit costs
- **Governing law** — unfavorable jurisdiction

After the table, provide:
- **Top 3 clauses to negotiate first** (highest impact, most likely to move)
- **Acceptable vs. unacceptable** — which risks are industry-standard vs. genuinely problematic