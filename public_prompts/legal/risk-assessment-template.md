---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt guides legal and regulatory teams in assessing business initiatives
  across regulatory, contractual, data, employment, and reputational domains. The
  model must generate a structured risk register with likelihood and impact scores,
  followed by a go/no-go recommendation and counsel involvement strategy.
complexity_level: 3
domain:
- business
intent:
- decide
primary_stage: clarify
source: public
task_type:
- analyze
---

Conduct a legal and regulatory risk assessment for the following business initiative:

**Initiative:** {{initiative_description}}
**Business unit:** {{business_unit}}
**Target markets:** {{target_markets}}
**Timeline:** {{timeline}}

Analyze and produce a risk register covering:

1. **Regulatory Risks** — applicable regulations, licensing requirements, pending legislation that could affect the initiative
2. **Contractual Risks** — exposure from existing agreements, vendor dependencies, IP licensing conflicts
3. **Data & Privacy Risks** — personal data flows, cross-border transfer issues, consent requirements
4. **Employment Risks** — workforce classification, non-compete implications, labor law compliance
5. **Reputational Risks** — potential public perception issues, ethical considerations

For each identified risk, provide:
| Risk | Likelihood (L/M/H) | Impact (L/M/H) | Risk Score | Mitigation Strategy | Owner |

After the risk register, include:
- **Top 3 risks** requiring immediate attention before proceeding
- **Go / No-Go recommendation** with conditions
- **Suggested legal counsel involvement** — which risks need outside counsel vs. in-house handling

Output as a structured report with the risk register table and narrative sections.