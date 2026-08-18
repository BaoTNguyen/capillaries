---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt targets finance professionals managing vendor billing discrepancies
  for specific companies and invoices. It generates a formal dispute letter, an internal
  finance memo, and a follow-up email template using provided dispute details and
  evidence.
complexity_level: 1
domain:
- finance
- business
intent:
- communicate
primary_stage: execute
source: public
task_type:
- generate
---

Draft a professional invoice dispute communication for **{{company_name}}** to send to **{{vendor_name}}** regarding invoice **#{{invoice_number}}**.

Dispute details:
- Invoice amount: ${{invoice_amount}}
- Invoice date: {{invoice_date}}
- Amount we believe is correct: ${{correct_amount}}
- Reason for dispute: {{dispute_reason}} (e.g., incorrect quantity, pricing mismatch, service not delivered, duplicate charge, unauthorized charges)
- Supporting evidence: {{evidence_summary}}
- Contract or PO reference: {{reference_number}}

Generate:
1. **Formal Dispute Letter** — Professional email to the vendor's accounts receivable team. Include: reference to the specific invoice, clear statement of the discrepancy, supporting evidence, the amount we are willing to pay, and a requested resolution deadline of {{resolution_deadline}}.
2. **Internal Summary** — A brief memo for our finance team documenting the dispute, amount at risk, and next steps.
3. **Follow-Up Template** — A shorter follow-up email to send if no response within 7 business days.

Tone: Firm but professional. Preserve the vendor relationship while clearly asserting our position.
Output all three documents with clear section dividers.