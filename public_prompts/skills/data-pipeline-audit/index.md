---
name: Data Pipeline Audit
slug: data-pipeline-audit
status: active
routing_description: >
  Audit and assess the health of data pipelines, ETL processes, and data
  infrastructure. Covers schema validation, query performance profiling,
  data quality assessment, and monitoring configuration for pipeline reliability.
domain: [technical, business]
intent: [evaluate, analyze]
task_type: [audit, data-quality, performance-analysis]
complexity_level: 4
source: public
created_by: system
files:
  - path: audit-questions-prompt.md
    type: prompt
    description: Generate structured audit interview questions for pipeline owners
  - path: schema-validator.py
    type: code
    language: python
    description: Validate schema definitions for consistency and integrity issues
  - path: query-profiler.sql
    type: code
    language: sql
    description: PostgreSQL queries to identify slow queries, missing indexes, and full table scans
  - path: data-quality-prompt.md
    type: prompt
    description: Generate a comprehensive data quality assessment report
  - path: monitoring-alerts.yaml
    type: config
    language: yaml
    description: Prometheus and Grafana alert rules for pipeline health monitoring
---

## Overview

This skill provides a structured approach to auditing data pipelines, from initial stakeholder interviews through technical validation and ongoing monitoring. It is designed for data engineers, analytics leaders, and platform teams who need to assess pipeline reliability, data quality, and operational health.

The toolkit combines human-facing prompts for stakeholder discovery with technical tools for automated validation. The schema validator catches structural issues like type mismatches and orphan references before they cause downstream failures. The query profiler identifies performance bottlenecks in PostgreSQL-based pipelines. The monitoring configuration provides a production-ready starting point for alerting on pipeline health.

This skill is particularly valuable during platform migrations, compliance audits, or when onboarding to an inherited data infrastructure where documentation is sparse.

## When to Use This

- You are conducting a formal audit of data pipeline infrastructure
- You inherited a data platform and need to assess its current state
- You are troubleshooting data quality issues across multiple pipeline stages
- You need to establish monitoring and alerting for pipeline reliability
- You are preparing for a compliance or governance review of data systems

## How to Use

Begin with **audit-questions-prompt.md** to structure stakeholder interviews and surface undocumented knowledge about pipeline behavior. Run **schema-validator.py** against your schema definitions to catch structural issues. Use **query-profiler.sql** against your PostgreSQL database to identify performance bottlenecks. Feed findings into **data-quality-prompt.md** to generate a formal assessment report. Deploy **monitoring-alerts.yaml** as a starting point for ongoing pipeline health monitoring.
