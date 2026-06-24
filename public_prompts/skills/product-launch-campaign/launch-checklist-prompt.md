---
intent: [evaluate]
task_type: [checklist-generation]
domain: [marketing, product]
primary_stage: evaluate
complexity_level: 3
source: public
Original Link: ""
Notes: "Part of the product-launch-campaign skill"
---

# Launch Go/No-Go Checklist

You are a product launch program manager with experience across SaaS, hardware, and marketplace launches. Generate a comprehensive go/no-go checklist tailored to the product launch described below.

## Launch Context

- **Product name:** {{product_name}}
- **Product type:** {{product_type}} (e.g., SaaS platform, mobile app, physical product, API service)
- **Launch date:** {{launch_date}}
- **Launch scope:** {{launch_scope}} (e.g., public GA, limited beta, regional rollout)
- **Team size:** {{team_size}}
- **Known risks or concerns:** {{known_risks}}

## Checklist Requirements

Generate a go/no-go checklist organized by the following functional areas. For each item, include:
- The checkpoint description
- The responsible team or role
- A status indicator: MUST HAVE (launch blocker) or SHOULD HAVE (can launch without, with risk)
- A suggested verification method (how to confirm it is done)

### Functional Areas to Cover

1. **Product Readiness**
   - Core feature completeness, critical bugs resolved, performance benchmarks met
   - Accessibility and localization requirements
   - Data migration or backward compatibility (if applicable)

2. **Infrastructure and Operations**
   - Scaling capacity, monitoring and alerting, rollback plan
   - Security review and penetration testing sign-off
   - Disaster recovery and backup verification

3. **Sales and Revenue**
   - Pricing finalized in billing system, sales team trained
   - CRM and lead routing configured
   - Contract templates and legal approvals

4. **Marketing and Communications**
   - Website and landing pages live, SEO metadata set
   - Press release and media kit prepared
   - Social media and email campaigns scheduled

5. **Customer Success and Support**
   - Support documentation and knowledge base published
   - Support team trained on new features and known issues
   - Escalation paths defined and communicated

6. **Legal and Compliance**
   - Terms of service and privacy policy updated
   - Regulatory approvals (if applicable)
   - Third-party license and attribution compliance

7. **Analytics and Measurement**
   - Success metrics defined and tracking instrumented
   - Dashboards built and shared with stakeholders
   - Post-launch review cadence scheduled

## Output Format

Return a structured checklist grouped by functional area. Use a table format with columns: Item, Owner, Priority (MUST/SHOULD), Verification Method, Status (leave blank for the team to fill in). After the checklist, include a "Launch Decision Framework" section with criteria for GO, CONDITIONAL GO, and NO-GO decisions.
