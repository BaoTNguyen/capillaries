---
name: Product Launch Campaign
slug: product-launch-campaign
status: active
routing_description: >
  Plan and execute a product launch campaign from positioning through go-to-market.
  Covers market analysis, pricing strategy, launch announcements, and readiness
  checklists for new product or feature releases.
domain: [marketing, product]
intent: [plan, create, analyze]
task_type: [campaign-planning, market-analysis, pricing]
complexity_level: 4
source: public
created_by: system
files:
  - path: market-positioning-prompt.md
    type: prompt
    description: Analyze competitive market positioning for a new product
  - path: launch-announcement-email.md
    type: prompt
    description: Draft a compelling launch announcement email
  - path: pricing-sensitivity.py
    type: code
    language: python
    description: Calculate pricing elasticity and recommend optimal price range
  - path: launch-checklist-prompt.md
    type: prompt
    description: Generate a go/no-go launch readiness checklist
  - path: timeline-template.csv
    type: template
    language: csv
    description: 12-week launch timeline with phases and milestones
---

## Overview

This skill provides a complete toolkit for planning and executing a product launch campaign. It covers the full lifecycle from initial market positioning analysis through pricing strategy, stakeholder communications, and launch readiness assessment.

The prompts guide you through critical pre-launch decisions: where your product sits in the competitive landscape, how to price it for maximum adoption, and whether your organization is truly ready for launch day. The pricing calculator gives you quantitative backing for pricing discussions, while the timeline template keeps the entire cross-functional effort on track.

Whether you are launching a net-new product, a major feature release, or entering a new market segment, this skill adapts to your context through flexible placeholders and configurable parameters.

## When to Use This

- You are planning a new product launch and need a structured approach
- You need to justify pricing decisions with data-driven analysis
- Your team needs a shared launch timeline across marketing, engineering, sales, and support
- You want a go/no-go framework before committing to a launch date
- You are writing the first external announcement and want to nail the messaging

## How to Use

Start with **market-positioning-prompt.md** to understand where your product fits competitively. Use **pricing-sensitivity.py** to model different price points against estimated demand curves. When you are ready to communicate externally, **launch-announcement-email.md** helps craft the first impression. Before committing to launch, run through **launch-checklist-prompt.md** to surface any blockers. The **timeline-template.csv** can be imported into any project management tool to track milestones across the 12-week window.

These files complement each other but can be used independently based on what stage of the launch you are in.
