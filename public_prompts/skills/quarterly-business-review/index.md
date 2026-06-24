---
name: Quarterly Business Review
slug: quarterly-business-review
status: active
routing_description: >
  Prepare and execute a quarterly business review (QBR) including financial
  variance analysis, competitive landscape assessment, executive narrative
  building, presentation structuring, and action item tracking. Use when
  preparing board updates, leadership reviews, or quarterly planning sessions.
domain: [finance, strategy]
intent: [communicate, analyze]
task_type: [synthesize, analyze]
complexity_level: 5
source: public
created_by: system
files:
  - path: metrics-narrative-prompt.md
    type: prompt
    description: Transform raw metrics and KPIs into a compelling executive narrative
  - path: variance-analyzer.py
    type: code
    language: python
    description: Analyze budget vs actual data, flag statistically significant variances
  - path: competitor-moves-prompt.md
    type: prompt
    description: Summarize competitive landscape changes and strategic implications
  - path: qbr-deck-outline-prompt.md
    type: prompt
    description: Generate a structured presentation outline for the QBR
  - path: action-tracker-prompt.md
    type: prompt
    description: Convert meeting notes and discussions into tracked SMART action items
---

## Overview

This skill provides everything needed to prepare a compelling, data-driven quarterly business review. It combines analytical tools for financial variance detection with prompts for narrative building, competitive analysis, and presentation structuring.

The toolkit is designed for finance leaders, chiefs of staff, and operations teams who need to synthesize a quarter's worth of data into a focused leadership conversation. The Python variance analyzer handles the quantitative heavy lifting, while the prompts help translate numbers into stories and decisions.

## When to Use This

- Preparing for a quarterly board meeting or leadership review
- Building a QBR deck for investors or executive stakeholders
- Doing quarterly planning and need to assess the prior quarter first
- Preparing a department-level review for a skip-level audience

## How to Use

Start with **variance-analyzer.py** to identify which metrics moved significantly — this gives you the factual foundation. Feed those findings into **metrics-narrative** to build the executive story. Run **competitor-moves** in parallel if external context matters. Use **qbr-deck-outline** to structure the presentation. After the QBR meeting, run **action-tracker** on your notes to ensure nothing falls through the cracks.
