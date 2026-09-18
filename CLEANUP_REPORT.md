# capillaries cleanup: import placement and duplication

Branch `dev`. Two commits: the import audit, then the dedup.

## Counts

| | |
|---|---|
| function-local imports audited | 95 |
| hoisted to module top | 48 |
| kept local | 47 |
| kept with a stated reason | 47 of 47 |

Of the 47 kept, 13 are `Usage:` examples inside docstrings rather than
executable imports. The remaining 34 are real, and every one now says why it
is where it is.

## KEEP categories

| category | count | reason |
|---|---|---|
| `from arteries ...` | 9 | capillaries installs and imports without arteries. `find.py:45` has said so for a while; this is the property the stack's layering rests on, and hoisting any one of these would end it |
| optional extras | 14 | dspy, sentence-transformers, faiss, torch, uvicorn's SSE path, starlette, mcp. Declared in `[project.optional-dependencies]`, so a module-scope import turns an opt-in feature into a hard install failure |
| test-visible binding | 1 | `search/api.py` — `log_serving` must be looked up when it is called, not when the module loads. See below |
| intra-package cycle | 10 | mostly `search.*` modules reaching sideways |

### The one the audit got wrong

`from capillaries.optimize.serving import log_serving` was hoisted to module
scope in `search/api.py`. It imports fine and the package walks clean, so
nothing looked broken — but `tests/test_serving_identity.py` patches
`serving.log_serving` and asserts the join keys arrive. Binding the name at
module load makes the patch invisible, and the test fails on an empty dict.

It is worth naming because of how it failed. A hoist that breaks an import
announces itself. A hoist that changes *when* a name is resolved breaks only
the code that was watching, which here was the test protecting the
episode_id/turn_id join. Reverted, with the reason in a comment.

## Within-repo duplication

### Extracted

**`outcome_score_sql()` in `config/paths.py`** — the feedback scoring ladder
(`success` 1.0, `partial` 0.5, `failure` 0.0) was written out in three SQL
literals across `db/setup_skills.py` and `agent/feedback.py`. They had already
diverged: the two success-rate averages treat an unrecognised outcome as NULL
and drop the row; the Bayesian prior scores it 0.0 and counts it against the
prompt. Both readings are defensible. Neither was visible without reading
three string literals in two files. The helper takes the unknown case as its
argument, so the choice is now made where it matters.

`config/paths.py` is the home because it already holds `MIN_CONFIDENCE` and
`clears_floor` for the same reason, and says so: "The decision lives here now
and both layers ask it the same question."

**`_row_metadata()` in `search/retriever.py`** — the six prompt columns that
ride along with a result, built independently in `retriever.py` and
`union.py`. The tell was in the retriever's copy, which had lost the
indentation of its last key. That is what a block looks like when nobody has
read it in a while. A seventh column now arrives in one place.

**`asdict(result)`** — `mcp_server.py` and `agent/api.py` each transcribed
`StepResponse` into a dict, field by field, for two transports. It is a flat
dataclass of exactly those six fields, so this is stdlib.

### Left alone

| what | why |
|---|---|
| `SELECT prompt_text FROM prompts WHERE prompt_id = %s` in `optimize/dspy_optimize.py:209` and `optimize/resolve.py:33` | five lines, two different queries that happen to share a shape. A shared fetch helper would be longer than both |
| `SELECT prompt_id, prompt_text ... WHERE title = %s` in `skills/promote.py:631` and `optimize/dspy_optimize.py:234` | same |
| overlapping rank fields on `SearchResult` and `RankedResult` | two types that describe different stages of the same pipeline. Merging them couples the retriever to the reranker for no gain |

## Verification

| check | result |
|---|---|
| `PYTHONPATH=src pytest -q` | 187 passed, 1 xfailed, 10 subtests (was 185 before the two new tests) |
| full package import walk | 0 modules fail |
| imports with `arteries` stubbed out | passes |
| `tests/test_shared_definitions.py` | new; fails if any of the three consolidated definitions is respelled locally |

## Cross-repo duplication candidates

Reported, not extracted — there is no shared package yet, and arteries is the
only sibling capillaries may legally depend on.

| # | logic | files | ~lines | worth it? |
|---|---|---|---|---|
| 1 | `migrate_embed_dim` — resizing pgvector columns when the embedding model changes. Both files are 108 lines and the same algorithm: read `atttypmod`, drop, re-add, report. Docstrings and table lists differ; the logic does not. | `capillaries/db/migrate_embed_dim.py` vs `arteries/migrate_embed_dim.py` | ~100 each | **Yes, post-monorepo.** The largest duplication found anywhere in the stack. The two already disagree about which tables they cover, which is the failure this becomes: a model change migrates one database and half the other. |
| 2 | Building a `tsquery` from free text by running `ts_parse` and OR-ing the tokens, with the same `tokid != 12` filter. | `capillaries/search/retriever.py` vs `arteries/storage.py` | ~12 | **Yes, and it is nearly free.** arteries already hard-depends on capillaries (`eval.py:46` imports `capillaries.find` at module scope), so exporting the builder from capillaries is an import, not a package. The `tokid != 12` magic number is the kind of thing that gets fixed in one copy. |
| 3 | `DB_CONFIG` — host, port, database, user, password from the same five env vars, same defaults. arteries even defaults `DB_NAME` to `"capillaries"`. | `capillaries/config/paths.py` vs `arteries/config.py` | ~8 | **Already half-solved, finish it.** `arteries/config.py:38` imports `EMBED_DIM`/`EMBED_MODEL`/`EMBED_URL`/`QUERY_PREFIX` from capillaries with a comment about a dimension mismatch that would have failed silently. `DB_CONFIG` is the one that did not get the same treatment, and the two point at the same database. |
| 4 | `capillaries/spine.py` mirroring `heart/events.py` `emit()` | `capillaries/spine.py:12` vs `heart/events.py:25` | ~15 | **No.** The file argues its own case: "No shared library by design." heart is not a legal dependency of capillaries, the shared artifact is the journal format in `heart/SPINE.md`, and a spec beats a package for fifteen stdlib lines. |

## Suspected bugs

None found beyond the drift described above. The `ELSE NULL` / `ELSE 0.0`
split in the outcome scoring is arguably one — the Bayesian prior penalises
outcomes it does not recognise — but it may well be intended, so the
consolidation preserved both behaviours rather than picking one.
