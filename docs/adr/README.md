# Decisions

Why capillaries is shaped the way it is, one file per decision in trimmed MADR 4.
Format and rules: [vascular/docs/adr](https://github.com/BaoTNguyen/vascular/tree/main/docs/adr).
The "In force" table is generated from each record's front matter: run
`python3 docs/adr/index.py` after adding or superseding one. CI fails when the
table is stale.

## In force

<!-- adr-index:start -->
| Decision | Date |
|---|---|
| [Search refuses an index embedded by a different model](2026-09-08-refuse-mismatched-embedder.md) | 2026-09-08 |
| [Dense and sparse fuse at 50/50](2026-09-08-fusion-weights.md) | 2026-09-08 |
| [The prompt optimizer edits prose, never code](2026-07-20-optimizer-never-edits-code.md) | 2026-07-20 |
| [The gate logs the candidates it didn't serve](2026-07-20-log-unserved-candidates.md) | 2026-07-20 |
| [A candidate prompt or skill is promoted only after winning an A/B](2026-07-20-ab-gate-before-promotion.md) | 2026-07-20 |
| [Reranker scores carry a progressive length penalty](2026-06-01-reranker-length-penalty.md) | 2026-06-01 |
| [Retrieval returns private prompts unless public ones are asked for](2026-05-29-private-prompts-by-default.md) | 2026-05-29 |
<!-- adr-index:end -->

## Stack decisions that bind capillaries

| Decision | Date |
|---|---|
| [A feature lives in the repo whose question it answers](https://github.com/BaoTNguyen/vascular/blob/main/docs/adr/2026-07-20-ownership-by-question.md) | 2026-07-20 |
| [Seams are pinned by contract tests in each repo](https://github.com/BaoTNguyen/vascular/blob/main/docs/adr/2026-07-20-contract-tests.md) | 2026-07-20 |
| [GitHub enforces PR plus CI on main](https://github.com/BaoTNguyen/vascular/blob/main/docs/adr/2026-10-30-protect-main.md) | 2026-10-30 |
