---
name: Contract Negotiation
tag: contract-negotiation
status: active
summary: >
  Prepare for and execute contract negotiations with vendors, partners, or
  clients. Includes risk clause extraction, multi-vendor comparison, redline
  suggestion generation, and counter-offer preparation. Use when evaluating
  vendor proposals, renewing enterprise agreements, or negotiating new partnerships.
domain: [business]
intent: [decide, validate]
task_type: [analyze, compare]
complexity_level: 3
source: public
created_by: system
files:
  - path: risk-extraction-prompt.md
    type: prompt
    description: Extract and categorize risk clauses from contract text
  - path: comparison-matrix-prompt.md
    type: prompt
    description: Compare terms side-by-side across multiple vendor proposals
  - path: redline-suggestions-prompt.md
    type: prompt
    description: Generate specific redline suggestions with alternative language
  - path: negotiation-prep-prompt.md
    type: prompt
    description: Prepare counter-offer talking points and negotiation strategy
---

## Overview

This skill provides a complete negotiation preparation toolkit for business teams working with contracts. Whether you're evaluating new vendor proposals, renewing an existing agreement, or negotiating partnership terms, these prompts guide you through systematic analysis before you sit at the table.

The toolkit covers the full arc of pre-negotiation work: understanding what's in the contract, comparing it to alternatives, identifying what to push back on, and preparing your talking points. It deliberately focuses on preparation rather than execution — the goal is to walk into a negotiation fully informed and strategically positioned.

## When to Use This

- You've received a vendor contract and need to brief your team before signing
- You're comparing proposals from 2-4 vendors and need a structured evaluation
- A contract renewal is coming up and you want to negotiate better terms
- You need to prepare a non-legal team member for a negotiation meeting

## How to Use

Start with **risk-extraction** on the primary contract to understand what you're dealing with. If comparing multiple vendors, run **comparison-matrix** next to see terms side-by-side. Use **redline-suggestions** to generate specific counter-proposals for problematic clauses. Finally, run **negotiation-prep** before the meeting to build your strategy and talking points. Not all files are needed every time — a simple renewal might only need risk extraction and negotiation prep.
