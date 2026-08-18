---
Notes: Part of the contract-negotiation skill
Original Link: ''
Summary: This prompt helps procurement teams evaluate vendor proposals against ranked
  priorities and specific contractual dimensions. The model must output a comparison
  table, an overall recommendation, negotiation leverage points, and identified deal-breakers.
complexity_level: 3
domain:
- business
intent:
- decide
primary_stage: plan
source: public
task_type:
- compare
---

Compare the following vendor proposals side-by-side and produce a structured evaluation:

**Vendor 1 ({{vendor_1_name}}):** {{vendor_1_summary}}
**Vendor 2 ({{vendor_2_name}}):** {{vendor_2_summary}}
**Vendor 3 ({{vendor_3_name}}, optional):** {{vendor_3_summary}}

**Our priorities (rank 1-5, 1=most important):**
{{ranked_priorities}}

Compare across these dimensions:

| Dimension | {{vendor_1_name}} | {{vendor_2_name}} | {{vendor_3_name}} | Winner |
|-----------|---|---|---|---|
| Pricing (total cost over {{contract_term}}) | | | | |
| Payment terms & flexibility | | | | |
| SLA / uptime guarantees | | | | |
| Liability cap | | | | |
| Termination flexibility | | | | |
| Data ownership & portability | | | | |
| Support & escalation | | | | |
| Implementation timeline | | | | |
| Contract length & renewal terms | | | | |

For each dimension, note specific clause references and any red flags.

After the comparison, provide:
- **Overall recommendation** with rationale
- **Negotiation leverage points** — where the recommended vendor's terms are weakest and competitors are stronger (use this in negotiation)
- **Deal-breakers** — terms that must change regardless of which vendor is selected