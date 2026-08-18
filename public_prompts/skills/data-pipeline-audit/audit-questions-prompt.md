---
Notes: Part of the data-pipeline-audit skill
Original Link: ''
Summary: This prompt serves senior data platform architects auditing data pipeline
  infrastructure for risks and operational gaps. The model must generate prioritized
  interview questions across six categories, tailored to the interviewee's role, with
  notes on concerning answers for critical items.
complexity_level: 3
domain:
- technical
- business
intent:
- evaluate
primary_stage: discover
source: public
task_type:
- audit
---

# Data Pipeline Audit Interview Questions

You are a senior data platform architect conducting an audit of an organization's data pipeline infrastructure. Generate structured interview questions tailored to the context below, designed to surface risks, undocumented dependencies, and operational gaps.

## Audit Context

- **Organization:** {{organization_name}}
- **Pipeline scope:** {{pipeline_description}} (e.g., "ETL from 12 source systems into a Snowflake data warehouse")
- **Known pain points:** {{known_issues}}
- **Audit objective:** {{audit_objective}} (e.g., compliance readiness, migration planning, reliability improvement)
- **Interviewee role:** {{interviewee_role}} (e.g., data engineer, analytics manager, platform owner)

## Question Generation Instructions

Generate interview questions organized into the following categories. Tailor questions to the interviewee's role -- a data engineer should get technical depth questions, while a business stakeholder should get impact and requirements questions.

### 1. Pipeline Architecture and Design
- How data flows end-to-end from source to consumption
- Design decisions, trade-offs, and technical debt
- Schema evolution strategy and backward compatibility approach

### 2. Data Quality and Validation
- What checks exist at ingestion, transformation, and serving layers
- How data quality issues are detected, reported, and resolved
- Historical examples of data quality incidents and their root causes

### 3. Operational Health
- Monitoring, alerting, and on-call practices
- Failure modes and recovery procedures
- SLAs for data freshness, completeness, and accuracy

### 4. Dependencies and Change Management
- Upstream source system dependencies and change notification processes
- Downstream consumers and their sensitivity to schema or timing changes
- Deployment and rollback procedures for pipeline changes

### 5. Security and Compliance
- Data classification and access control policies
- PII handling, masking, and retention rules
- Audit trail and lineage tracking capabilities

### 6. Scalability and Future State
- Current bottlenecks and capacity constraints
- Planned changes to source systems or consumption patterns
- Technology or architecture changes on the roadmap

## Output Format

For each category, provide 4-6 questions. Mark each question with a priority: CRITICAL (must ask), IMPORTANT (ask if time permits), or EXPLORATORY (follow-up for deep dives). Include a brief note on what a concerning answer would look like for each critical question.