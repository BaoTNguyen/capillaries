---
intent: [evaluate]
task_type: [data-quality]
domain: [technical, business]
primary_stage: evaluate
complexity_level: 4
source: public
Original Link: ""
Notes: "Part of the data-pipeline-audit skill"
---

# Data Quality Assessment Report

You are a data quality analyst preparing a formal assessment report for stakeholders. Based on the pipeline context and findings provided, generate a comprehensive data quality report.

## Pipeline Context

- **Pipeline name:** {{pipeline_name}}
- **Data source(s):** {{data_sources}}
- **Target system:** {{target_system}}
- **Data volume:** {{data_volume}} (e.g., "2M rows/day across 45 tables")
- **Known quality issues:** {{known_issues}}
- **Quality check results (if available):** {{quality_check_results}}

## Report Generation Instructions

Generate a data quality report with the following sections:

### 1. Executive Summary
Write a 3-4 sentence overview of the pipeline's data quality posture. State whether quality is acceptable, at risk, or critical. Quantify the scope of issues where possible.

### 2. Quality Dimensions Assessment
Evaluate the pipeline across these six standard data quality dimensions. For each dimension, provide:
- A rating: GREEN (meets standards), YELLOW (minor issues), RED (significant issues)
- Evidence supporting the rating
- Specific examples from the findings

**Dimensions:**
- **Completeness:** Are all expected records and fields present? What is the null rate for critical fields?
- **Accuracy:** Do values reflect reality? Are there outliers or impossible values?
- **Consistency:** Are the same entities represented the same way across tables and systems?
- **Timeliness:** Is data arriving within SLA? What is the typical lag from source to target?
- **Uniqueness:** Are there duplicate records? Are primary keys truly unique?
- **Validity:** Do values conform to expected formats, ranges, and business rules?

### 3. Issue Inventory
For each identified issue, document:
- **Issue ID:** Sequential identifier (DQ-001, DQ-002, ...)
- **Dimension:** Which quality dimension is affected
- **Severity:** Critical / High / Medium / Low
- **Description:** What the issue is
- **Impact:** Who or what is affected downstream
- **Root cause (if known):** Why this is happening
- **Recommended fix:** Specific remediation steps
- **Effort estimate:** Quick fix (< 1 day), Moderate (1-5 days), Significant (1-4 weeks)

### 4. Trend Analysis
Based on the information provided, assess whether data quality is:
- Improving, stable, or degrading
- Correlated with any events (schema changes, volume spikes, source system updates)
- Likely to worsen without intervention

### 5. Recommendations
Provide a prioritized list of 5-8 recommendations:
- Quick wins that can be implemented immediately
- Structural improvements for long-term quality
- Monitoring and alerting additions to catch issues earlier

### 6. Quality Scorecard
Create a summary scorecard table with each dimension, its rating, and a one-line rationale.

## Output Format

Use professional report formatting with clear headers, numbered findings, and a summary table. The report should be suitable for sharing with both technical teams and business stakeholders.
