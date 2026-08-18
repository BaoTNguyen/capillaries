---
Notes: Part of the public showcase collection
Original Link: ''
Summary: 'This prompt assists decision-makers in evaluating multiple options against
  weighted criteria using a structured matrix. The model must calculate weighted scores,
  provide a recommendation with sensitivity analysis, and identify risks in a tabular
  format. Required context: [criterion], [1-5], [1-10].'
complexity_level: 2
domain:
- business
intent:
- decide
primary_stage: plan
source: public
task_type:
- compare
---

Build a weighted decision matrix to evaluate the following options:

**Decision:** {{decision_description}}
**Options to compare:** {{option_1}}, {{option_2}}, {{option_3}}
**Key criteria:** {{criteria}} (e.g., "cost, time to implement, team impact, scalability, risk")

For each criterion:
1. Assign a weight (1-5) based on importance to this specific decision
2. Score each option (1-10) against each criterion
3. Calculate weighted scores and a total

Output as:
| Criterion | Weight | {{option_1}} | {{option_2}} | {{option_3}} |
|-----------|--------|---|---|---|
| [criterion] | [1-5] | [1-10] (weighted: X) | [1-10] (weighted: X) | [1-10] (weighted: X) |
| **TOTAL** | | **X** | **X** | **X** |

After the matrix, provide:
- **Recommendation** — which option scores highest and why
- **Sensitivity check** — would the recommendation change if the top-weighted criterion were removed? If yes, flag this as a close call.
- **Risks of the recommended option** — top 2-3 things that could go wrong