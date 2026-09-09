# Extra context — capillaries

Session handoff, written 2026-08-26. What the repo's own docs don't say.
`README.md` and `AGENTS.md` cover what capillaries *is*; this covers where it
stands and what will bite you.

## State

Branch `dev`, in sync with origin, at `0cb5542`. The
`event-journal-and-sandbox` line merged down cleanly. Recent work, newest first:

- `0cb5542` log what was served, not what ranked first
- `95f505c` size the reranker from measurement; stop one GPU hiding the other
- `c0cea0c` read the memory frame under either arteries shape
- `ebeec0e` settle the router question with a test — **it is not the router**

That last one matters. A run of retrieval misfires got blamed on the router;
the test says otherwise. Don't reopen that theory without new evidence.

## The hooks were broken and are now fixed

`.claude/settings.local.json` registered six arteries hooks pointing at
`.arteries/hooks/`, and that directory did not exist. `.arteries/` is
gitignored (`.gitignore:229`), so when it was untracked in `2e4e482` the
generated hooks went with it and nothing regenerated them. Every hook failed
silently on every turn.

The damage is visible in the store: capillaries' newest persistent memory is
dated 2026-08-22, its newest ephemeral row 2026-08-19. Roughly a week of
sessions here recorded nothing and received nothing.

Reinstalled 2026-08-26 for both `claude` and `codex` and verified with a live
write. If `.arteries/hooks/` ever goes missing again:

```
cd <repo> && python3 -m arteries.setup_cli install claude --no-db
```

with arteries' `src` on `PYTHONPATH`. The same failure can happen in any repo
that gitignores `.arteries/` — check the directory exists, not just that
settings reference it.

## Running the tests

`python3 -m pytest -q` from the repo root. 178 passed, 3 skipped, 1 xfailed,
about 2m50s.

The suite is **not hermetic**. It prints a live golden-set report mid-run —
recall 100%, MRR 0.787 across 20 queries — which means it queries the real
index with the real reranker. That's why it takes three minutes when every
sibling repo finishes in seconds. Consequence: drift in `public.prompts` shows
up as a test failure in a run that changed no code. If the golden set breaks,
check the corpus before you check the diff.

`--timeout` is not available; pytest-timeout isn't installed.

## Known open threads

**Retrieval fires on prompts that don't want it.** Two documented cases scored
0.974 and 0.978 — above the average accepted retrieval — for prompts that had
nothing to do with the work in progress. The system scores similarity to a
library entry, not usefulness to the turn. Arteries added a bare-imperative
triage guard (`arteries/eval.py`), which catches roughly 1 case in 61. The real
fix is unbuilt.

A tempting dead end, already tested and rejected: gating on the **margin**
between top-1 and runner-up rerank scores. It inverts. The worst retrieval had
a margin of 0.526; an apt one had 0.035.

Domain filtering also fails on the observed cases — both offending prompts are
tagged `technical`.

**The 23 uncompiled ephemeral rows** dated 08-19 and earlier are casualties of
an arteries compile bug (truncated JSON from the local model, cut points
clustered at 2325–3354 characters). New turns compile fine; the backlog needs a
retry once that's fixed.

## Cross-repo

- arteries imports `capillaries.find` on the retrieval path. A capillaries
  import failure takes down arteries' eval — this has happened
  (`No module named 'capillaries'`).
- capillaries imports only `arteries.memory_types` — stdlib dataclasses, no DB
  access on that path. Keep it that way; the dependency is deliberately thin
  and undeclared in `pyproject.toml` because arteries isn't on PyPI.
- marrow imports capillaries for the loop logic. The loop is a subcommand and
  is not invoked automatically.
- `eval/plexus_queries.jsonl` holds 237 rows.
