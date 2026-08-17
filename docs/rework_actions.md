# Rework — action list

Every concrete recommendation from the audit, in the order I'd do them. Each
one is marked with what backs it:

- **[measured]** — I ran it against this repo or this database. Numbers are real.
- **[reasoned]** — follows from measured facts, but the change itself is untested.
- **[unverified]** — plausible, no evidence yet. Do not treat as settled.

The full reasoning lives in `rework_design.md`. This file is the checklist.

---

## DONE — embedder fixed and corpus re-embedded

Shipped on `rework`. Verified state below; see Tier −1 for the diagnosis.

| Check | Before | After |
|---|---|---|
| Verbatim self-retrieval, rank 1 | 1 / 40 | **15 / 40** |
| Verbatim self-retrieval, top 10 | 2 / 40 | **27 / 40** |
| `notes`-as-query R@10 | 0.8% | **25.3%** |
| Mean pairwise cos | 0.625 | **0.432** |
| Warm search latency | ~7 900 ms | **158 ms** |
| Test suite | 7 failed / 509 s | **3 failed / 14 s** |
| Golden set (existing, 20 cases) | *no baseline taken* | **17/20, MRR 0.546** |

Changed: `serve_embeddings.py` (model + self-check + `/health` dim),
`config/paths.py` (`EMBED_MODEL`, `EMBED_DIM`, `QUERY_PREFIX`),
`db/migrate_embed_dim.py` (new), four `VECTOR(768)` → `EMBED_DIM`,
`retriever.assert_index_matches_model`, `reranker._autodetect_device`,
re-frozen `GOLDEN_GATE`, `SIMILARITY_THRESHOLD` 0.47 → 0.58.

Deleted three monkeypatches that existed solely to keep arctic's custom remote
code alive: `_patch_snowflake_source` (rewrote the model's cached source on
disk), `_fix_rotary_caches`, `_disable_xformers`. Someone had already fought
this bug; the patches were not enough, and `_disable_xformers` was skipped on
CUDA — the exact path in use.

### Corrections to earlier claims in this document

**1. Ground truth already existed.** I repeatedly wrote that no eval set exists
and that it blocked every decision. Wrong: `tests/test_search.py` has
`GOLDEN_SET` — 20 query→expected-title cases with recall and MRR reporting —
and `tests/test_gate.py` has `GOLDEN_GATE`, 9 labelled retrieve/skip cases.
Small and single-label, but real, and they should have been the starting point.
The gate set in particular proved the fix independently.

**2. No before/after baseline on the golden set.** I re-embedded before running
the suite, so the 17/20 has nothing to compare against. Sequencing error —
measure first.

**3. The golden set is unrepresentative, and it was pointing the wrong way on
dense/sparse weighting.** Measured on the golden set:

| Channel | Golden-set recall |
|---|---|
| dense only | 14 / 20 |
| **sparse only** | **17 / 20** |
| hybrid + rerank | 17 / 20 |

Sparse alone equals the full pipeline — **which is why a completely dead dense
channel went unnoticed for so long.** BM25 was carrying the system. Read alone,
this argues against weighting sparse down.

It is misleading. Golden-set queries share literal words with their expected
titles ("build a 13-week cash flow model" → "13-Week Cash Flow Model"), which
is the one shape where BM25 wins. **Real conversational traffic is not shaped
like that** — see the plexus findings below, where sparse is the *source* of
every bad result. Rebalance the golden set before trusting it on weights.

---

## Real-traffic evaluation: 237 turns from `Projects/plexus`

The `serving_log` is 155 distinct queries that are all recordings of
`search/eval.py`. Genuine traffic was extracted instead from 18 Claude Code
sessions on the plexus project — 237 distinct human-typed turns, 41 of them
questions — and replayed blind through the fixed system. Saved as
`eval/plexus_queries.jsonl` with gate decision and top-1 result per row, ready
for labelling. **It contains verbatim private development conversation; gitignore
it if this repo is ever pushed anywhere shared.**

### Gate behaviour on real traffic

| | |
|---|---|
| Opened (would retrieve) | **83 / 237 (35%)** |
| ...among questions only | 16 / 41 |
| Top skip reason | no semantic match (115) |

### Retrieval quality by score band (hand-judged, 6 per band)

| Band | Median top-1 | Useful |
|---|---|---|
| Top quartile | ~0.99 | **5 / 6** |
| Mid | ~0.94 | 4 / 6 |
| Bottom quartile | ~0.35 | 1 / 6 |

The reranker score does discriminate — but the useful range is compressed
(overall median 0.937, p90 0.982), so most results crowd into a narrow band at
the top where an absolute cut cannot separate a genuine match from a lexical
accident. Direct support for the normalized decision layer.

Real hits worth noting, because they show the vault covers this domain better
than expected: *"What triggers retrieval to run in the first place"* →
**Retrieval Trigger Design** (1.000); *"What's left to test and use in real
workflows"* → **Workflow Testability Diagnostic**; *"Can't Codex and Claude Code
find my current plan"* → **CLAUDE.md Bootstrapper**.

### Sparse is the source of the bad results

Tracing the worst outputs back to their channel:

| Query | dense top-1 | sparse top-1 |
|---|---|---|
| `budget_exhausted per episode…` | **Token Burn Diagnostic** ✓ | Market & Topic Research Pack ✗ |
| `routing … subagents with different effort levels` | **Three-Axis Agent Evaluator** ✓ | Image Gen Timeline Activity Sheet ✗ |
| `Why isn't Codex counting` | **Token Burn Diagnostic** ✓ | Adversarial Mini Check ✗ |
| `can't interact with the terminal…` | Full Version | Remotion Video Prompt Builder ✗ *(won after fusion)* |

Dense had the right answer every time; sparse dragged in a lexical collision
that outranked it after 50/50 fusion. The failure mode is common words —
"budget", "routing" — matching titles from unrelated domains.

It confirms the embedder fix end-to-end: dense now returns `Token Burn
Diagnostic` for a question about token accounting.

**It does not vindicate 85/15** — an earlier version of this section said it
did. Those plexus queries are out-of-domain: the vault has no right answer, so
"sparse brought garbage" really meant "nothing correct existed to outrank it."
That is an abstention failure, not a channel-weight failure. Direct measurement
on labelled queries (below) says 85/15 is the worst configuration available.

---

## Fusion weights — both changes retracted, keep 50/50

### Benchmark provenance, and one contaminated population

| Data | n | Query is | Label | Valid |
|---|---|---|---|---|
| A. "naming" | 200–300 | the prompt's own `title` | its `prompt_id` | ❌ **leaked** |
| B. "describing" | 261 | the prompt's `notes` field | its `prompt_id` | ✅ clean |
| `GOLDEN_SET` | 20 | hand-written | expected title | ✅ tiny, lexical |
| `GOLDEN_GATE` | 9 | hand-written | retrieve/skip | ✅ |
| plexus turns | 237 | real sessions | none (18 hand-judged) | ⚠️ unlabelled |
| verbatim probe | 40 | chunk's own text | itself | smoke test only |

**Population A is invalid.** `chunk.py:308` writes the title into every chunk's
breadcrumb, which lands in `search_tsv` at weight **A** and in the embedded
text — verified, 2072/2072 chunks match their own title. Querying with a title
queries a string deliberately planted in the index. Sparse's 93.7% there
measures exact string matching, not naming-query skill.

**Population B is clean** — verified 0/970 chunks match their own `notes`, and
`notes` is absent from `chunk_text`, both tsvectors, and the embeddings.

### Results on the clean population only

| Config | describing R@10 |
|---|---|
| **0.5 / 0.5 (current)** | **22.0%** |
| 0.3 / 0.7 | 21.5% |
| 0.85 / 0.15 | 17.5% |
| union ceiling | 25.7% |

**50/50 is the best configuration tested on uncontaminated data. Change
nothing.** 85/15 came from the diagram's box labels and an out-of-domain
failure trace; 0.3/0.7 came from the leaked population. Neither survived
contact with a clean benchmark.

### Full sweep, including the contaminated column

Kept for the record — the `naming` column is leak-inflated and should not be
used to justify a change.

| k | weights (dense/sparse) | naming | describing |
|---|---|---|---|
| 50 | 0.5 / 0.5 *(current)* | 92.0% | **22.0%** |
| 10 | 0.5 / 0.5 | 93.5% | 20.5% |
| 5 | 0.5 / 0.5 | 93.0% | 20.0% |
| 1 | 0.5 / 0.5 | 93.0% | 18.5% |
| 50 | **0.85 / 0.15** | **66.0%** | **17.5%** |
| 50 | **0.3 / 0.7** | **95.0%** | 21.5% |
| 50 | 0.15 / 0.85 | **96.0%** | 19.5% |

0.85/0.15 is the worst row on both populations, which is the one conclusion
that survives the leak. `k` moves things ~1.5 points and pulls the populations
in opposite directions; leave it at 50.

### Query routing: achievable, not worth building

Routing naming→sparse and describing→dense was tested and does not pay:

| | best routed | best single global config |
|---|---|---|
| naming | sparse-only 93.7% | **hybrid 0.3/0.7 → 95.0%** |
| describing | dense-only 17.2% | **hybrid 50/50 → 22.0%** |

Fusion beats single-channel routing on *both* populations. RRF already
self-routes: when one channel is confident the right document sits at its rank
1 and the other channel's rank 30, and the RRF arithmetic favours it without
being told which mode the query is in. A misrouted describing query would also
cost ~5 points, so any classifier error eats the gain.

---

## Tier −1 — every embedding in the database is garbage

**Root cause found and confirmed.** `snowflake-arctic-embed-m-v2.0` ships
custom remote code (`modeling_hf_alibaba_nlp_gte.py`) that **breaks under the
installed `transformers` 5.4.0** — a direct load returns `NaN`. The running
embedding server (PID 6781) predates the library upgrade, so it still returns
finite, perfectly reproducible numbers that are semantically wrong.

Proof: the running server's vector for a given sentence sits at **cos 0.44**
from a correctly-loaded model's vector for the same sentence. Its
unrelated-pair similarity is 0.405 where the correct model gives 0.221 — the
embedding space is collapsed into a narrow cone, so everything looks similar to
everything and ranking is near-arbitrary.

Pinning `transformers < 5` fixes it. Verified working on 4.49.0.

### Measured, before and after the fix

| Probe | broken (live DB) | **arctic fixed** | **qwen3-0.6b** |
|---|---|---|---|
| Verbatim self-retrieval, rank 1 | 1 / 40 | **25 / 40** | 19 / 40 |
| Verbatim self-retrieval, top 10 | 2 / 40 | **34 / 40** | **34 / 40** |
| `notes`-as-query R@1 (261 prompts) | 0.4% | 3.1% | **8.8%** |
| `notes`-as-query R@5 | 0.8% | 11.5% | **19.5%** |
| `notes`-as-query R@10 | 0.8% | 14.9% | **24.9%** |
| Mean pairwise cos (lower = better spread) | 0.625 | **0.303** | 0.420 |
| Full corpus embed time | — | 24.0 s | 36.8 s |

The two models split cleanly by probe type. Arctic is **better at near-lexical
matching** (verbatim rank-1, 25 vs 19). Qwen3 is **clearly better at semantic
paraphrase** (notes probe, ~1.7× at every k). The production task — a user's
situation matched to a prompt template — is a paraphrase task, which favours
Qwen3, but this is now a real trade-off between two working models rather than
a rescue from a broken one.

Qualitatively, fixed arctic is sane again: *"financial model for early stage
company"* → `financial-model-reviewer`, `SaaS Business Model Repricing`
(previously `Image Gen Art Elements Practice`).

### What this invalidates

- **`gate.py:49` `SIMILARITY_THRESHOLD = 0.47`.** The comment describes a
  0.036-wide gap and admits "no single cut fully separates them." That is what
  tuning against a collapsed embedding space looks like. Recalibrate.
- **Every retrieval measurement taken before this**, including "chunking
  changed top-1 for 59 of 60 queries" in `rework_design.md` §2. Both sides used
  the broken embedder.
- **Not the reranker work** — cross-encoders score `(query, text)` pairs
  directly and never read these vectors. Those numbers stand.

### Actions

| # | Action |
|---|---|
| −1.1 | **Pin `transformers<5` for the embedding server** and add it to `pyproject.toml`. This is the actual bug fix |
| −1.2 | **Re-embed everything.** `prompts.embedding`, `prompt_chunks.embedding`, `skills.skills.routing_embedding` are all currently garbage. 24 s for the chunk table |
| −1.3 | Add a **startup health check** to `serve_embeddings.py`: embed two related and two unrelated sentences, assert the related pair wins by a margin, refuse to serve otherwise. This bug was invisible for an unknown length of time and must never be silent again |
| −1.4 | Add the verbatim self-retrieval probe to the eval harness as a permanent smoke test — no labels needed, catches a dead index immediately |
| −1.5 | Recalibrate `gate.py` `SIMILARITY_THRESHOLD` and `find.py` `SINGLE_THRESHOLD` against whichever fixed space you keep |
| −1.6 | **Decide arctic-fixed vs Qwen3** once the eval set exists. Arctic keeps the 768-dim schema and is already deployed; Qwen3 needs `VECTOR(1024)` and native `transformers` support with no custom-code liability, and wins the semantic probe by ~1.7× |

---

## Superseded diagnosis (kept for the record)

The first pass concluded arctic itself was defective and recommended switching
to Qwen3 on those grounds. That was wrong — the model is fine, the deployment
was broken. The measurements that produced the wrong conclusion were correct;
the causal attribution was not. Worth remembering that "model is bad" and
"model is misconfigured" produce identical evidence until you load the model a
second way.

<details>
<summary>Original text</summary>

### The embedding index is broken

Found while bench-marking Qwen3-Embedding against the incumbent. This
supersedes everything below it.

**`snowflake-arctic-embed-m-v2.0`, as deployed, produces near-useless vectors.**
Three independent measurements against the live `prompt_chunks` index:

| Probe | arctic | qwen3-0.6b | random baseline |
|---|---|---|---|
| Verbatim self-retrieval — query is a sentence lifted **from the chunk itself**, rank 1 | **1 / 40** | — | ~0 |
| ...same, in top 10 | **2 / 40** | — | ~0.5 |
| `notes`-as-query recall@10 (261 prompts with a human-written description) | **0.8%** | **24.9%** | ~1.1% |
| `notes`-as-query recall@1 | **0.4%** | **8.8%** | ~0.1% |

A healthy index scores near 40/40 on verbatim self-retrieval — the answer is
literally inside the document. Arctic scores 2. On the notes probe it is **at
or below random**.

Qualitatively, on real queries:

```
"financial model for early stage company"
  arctic : Reference Class Priming | Image Gen Art Elements | Image Gen Science Experiment
  qwen3  : Solopreneur AI Business Case | Operating Model Builder | financial-model-reviewer

"quick sanity check on a decision I made"
  arctic : Correction Compounder | Reference Class Priming | CLAUDE.md Bootstrapper
  qwen3  : Decision Helper | Decision Context Documenter | The Decision Intelligence Brief
```

**Not a prefix problem.** Tested all three conventions — the v1.5 prefix
currently in use, v2.0's `"query: "`, and no prefix. All three fail.

**Likely root cause: the model's custom remote code is broken under the
installed `transformers` 5.4.0.** `snowflake-arctic-embed-m-v2.0` ships
`modeling_hf_alibaba_nlp_gte.py` and requires `trust_remote_code=True`. Loading
it directly today **returns NaN**, and separately raises
`Attention bias and Query/Key/Value should be on the same device`. The running
server (PID 6781) predates the library upgrade, so it still returns finite
numbers — self-consistent ones (re-embedding the same text reproduces the
stored vector at cos 1.0000) but semantically degraded. Deterministic garbage
is the worst failure mode available: nothing errors, nothing looks wrong.

Qwen3-Embedding-0.6B uses native `transformers` Qwen3 support with no custom
code, and works correctly.

### What this invalidates

- **`gate.py:49` `SIMILARITY_THRESHOLD = 0.47`.** The comment describes a
  0.036-wide gap between open questions (~0.498) and meta-questions (~0.462)
  and notes "no single cut fully separates them." That is what tuning against a
  broken embedding space looks like. Recalibrate from scratch.
- **Every retrieval measurement in `rework_design.md` §2**, including the
  "chunking changed top-1 for 59 of 60 queries" result. Both sides of that
  comparison used the same broken embedder.
- **The reranker comparison is unaffected** — rerankers score `(query, text)`
  pairs directly and never touch these vectors.

### Actions

| # | Action |
|---|---|
| −1.1 | Switch to `Qwen/Qwen3-Embedding-0.6B`. Not on benchmark grounds — the incumbent is not functioning, and its dependence on unmaintained custom remote code is a standing liability |
| −1.2 | Schema: `VECTOR(768)` → `VECTOR(1024)` in `db/setup.py:59`, `setup_skills.py:66`, `chunk.py:193`, `db/embed.py:24`. Re-embed and rebuild HNSW — **measured at 36.8 s for all 2 072 chunks** |
| −1.3 | Add a **startup health check** to `serve_embeddings.py`: embed two known-related and two known-unrelated sentences, assert the related pair scores higher by a margin. Refuse to serve on failure. This class of bug must never again be silent |
| −1.4 | Recalibrate `gate.py` `SIMILARITY_THRESHOLD` and `find.py` `SINGLE_THRESHOLD` against the new space |
| −1.5 | Add the verbatim self-retrieval probe to the eval harness as a permanent smoke test — it needs no labels and catches a dead index immediately |

**Caveat:** none of this establishes that Qwen3 is the *best* choice. It
establishes that the incumbent is broken and Qwen3 works. Run the full bake-off
(Tier 6) once the eval set exists.

</details>

---

## Retrieval combination — settled, and the answer is "leave it"

Union-then-rerank was built (`search/union.py`), wired into `PromptSearch`,
measured against the incumbent, and **reverted**.

| golden (n=20) | R@1 | R@5 | R@10 | MRR |
|---|---|---|---|---|
| **RRF(50+50)→20 + rerank — the incumbent** | 30.0% | **80.0%** | **90.0%** | **0.510** |
| union(10/channel) + rerank | 30.0% | 65.0% | 75.0% | 0.421 |
| union(20/channel) + rerank | 30.0% | 60.0% | 70.0% | 0.396 |
| union(30/channel) + rerank | 30.0% | 55.0% | 70.0% | 0.380 |

The union lost 15 points of R@10, and widening it made it worse — more
candidates dilute the reranker rather than help it.

**Why the earlier "+20 points for union" was wrong:** it compared union+rerank
(75%) to *vector alone, no rerank* (55%). The production path was never vector
alone — it is RRF over 50 dense + 50 sparse **chunk** candidates rolled up to
20, which has far better recall than 10 parents per channel. I benchmarked a
new design against a weak baseline instead of the incumbent, which is the same
error that produced the 85/15 and 0.3/0.7 recommendations.

Also notable: the "harmful" OR-english sparse channel in `retriever.py` — the
one this whole thread kept trying to replace — has *better* golden recall than
the key-term extraction that replaced it. Broad recall into a reranker beats
precise recall into a reranker, at this corpus size.

**Kept as standalone tools, not in the serving path:** `search/channels.py`
(`vector_search`, `keyword_search`, `exact_search`), `search/union.py`,
`search/bench_channels.py`. They are how any future combination change gets
measured, and `exact_search` is genuinely useful for finding a literal string.

### Net effect of the entire retrieval-combination investigation

Nothing changed in the serving path. Four recommendations were made and all
four withdrawn (85/15, 0.3/0.7, spec-token routing, union-then-rerank). What it
produced instead: a document-level `prompts.exact_tsv`, three benchmark
populations with their contamination documented, and the standalone channel
tooling. The measurement infrastructure is the deliverable; the tuning was not.

---

## Tier 0 — free wins, no judgment required

Two-line diffs with large measured effects. Nothing downstream depends on them,
and nothing is risked by doing them today.

| # | Action | File | Backing |
|---|---|---|---|
| 0.1 | Set `RERANKER_DEVICE` default to `cuda` | `search/reranker.py:145` | **[measured]** 50 pairs: 27 354 ms CPU → 249 ms GPU. **110×** |
| 0.2 | Drop `MAX_DOC_CHARS = 512`, or raise to ~6 000 | `search/reranker.py:41` | **[measured]** full-length costs 536 ms vs 249 ms. The model handles 32 768 tokens |
| 0.3 | Raise the 4 000-char embed cap to ~30 000 | `db/embed.py:27`, `chunk.py` backfill | **[measured]** arctic-embed truncates near 40–45 k chars, not 4 k. Currently drops the tails of 19 chunks for nothing |
| 0.4 | Fix the stale docstring naming `ms-marco-MiniLM-L-6-v2` | `search/reranker.py:8-10` | **[measured]** line 39 loads `mxbai-rerank-base-v2`. The docstring cost me a wrong conclusion; it will cost the next reader one too |

## Tier 1 — instrument before building

Do these before anything that needs to be evaluated. Every later decision is
unmeasurable without them.

| # | Action | Backing |
|---|---|---|
| 1.1 | **Fix `episode_id` propagation.** `serving.py:80` reads `$ARTERIES_EPISODE_ID`; it isn't arriving | **[measured]** 2 of 2 895 serving rows carry one. Blocks the reward join, outcome attribution, and the A/B gate |
| 1.2 | Add `serving_outcome` table — `used`, `edited`, `edit_distance`, `requeried_within_60s`, `reward` | **[reasoned]** `serving_log` records what was served, never what happened next. That gap is the difference between telemetry and training data |
| 1.3 | Add `chunk_ids` to `serving_log` | **[reasoned]** without it, chunk-level diagnosis is impossible exactly when it's needed |
| 1.4 | **Build the eval set.** ~50 labeled queries, `{"query", "relevant_prompt_ids", "notes"}`, labeled at prompt level (chunk IDs move when TARGET changes) | **[measured]** no ground truth exists. `search/eval.py` prints a report with no expected answers; the 2 895 serving rows are recordings of that script (155 distinct queries), not usage |

**1.4 is the keystone.** It has now blocked three separate decisions — the
chunk cutover, the reranker choice, and the embedding-model choice. Build it
before optimizing anything.

## Tier 2 — retrieval

| # | Action | Backing |
|---|---|---|
| 2.1 | Chunking — **done**, backfilled | **[measured]** 2 072 chunks from 916 prompts, all embedded, 0 bad offsets, 241 of 276 previously-truncated prompts now indexed past char 4 000 |
| 2.2 | **Do not point `retriever.py` at `prompt_chunks` until 1.4 exists** | **[measured]** chunking changed top-1 for **59 of 60** real queries. Whether that is an improvement is currently unknowable |
| 2.3 | Move `DENSE_WEIGHT`/`SPARSE_WEIGHT` to config. **Keep 0.5 / 0.5** | **[measured]** on the one clean benchmark, 50/50 wins. Both 85/15 and 0.3/0.7 are retracted — see below |
| 2.4 | Replace OR-of-every-token with AND semantics; add a `simple`-config `exact_tsv` channel routed by `gate.py:69`'s `_SPEC_TOKEN` regex | **[reasoned]** `_to_or_tsquery` (`retriever.py:265`) admits any document sharing one common word. The sparse channel is a second recall channel, not a precision instrument |
| 2.5 | Chunk-to-parent rollup: `max(chunk_score)` + small bonus per extra matching chunk | **[measured]** fan-out is *not* the problem I expected — median 10 distinct parents per top-10, worst case 2 slots from one prompt. Lower priority than the design doc implies |
| 2.6 | Keep TARGET at 1 600 | **[measured]** embedding dilution is flat 1 k–6 k chars and collapses (−25%) at 10 k. The reranker is **not** the binding constraint — see 0.4 |

## Tier 3 — ingest and hygiene

| # | Action | Backing |
|---|---|---|
| 3.1 | **Ingest owns raw truth only.** Strip `search_tsv` construction from `obsidian_sync/ingest.py`; add `needs_reindex` set on hash change; one downstream pass owns every derived artifact | **[measured]** ingest writes `prompts` and knows nothing about `prompt_chunks`. The next vault sync leaves chunk offsets pointing into a changed string — silent corruption, no error |
| 3.2 | Store `prompt_text` byte-exact — no normalization, no whitespace collapsing | **[reasoned]** `char_start`/`char_end` are only meaningful against the exact string that was chunked |
| 3.3 | Enforce `embedding_version` at query time; refuse to search on a mismatch | **[measured]** the column exists in both tables and nothing reads it. Mixing two models' vectors returns garbage silently |
| 3.4 | Vault-hygiene report on self-duplication — count, don't auto-fix | **[measured]** 169 prompts repeat their own opening verbatim. `The Orchestrator Prompt`: 104 spans, 54 byte-identical. Currently deduped downstream, which is why coverage is 91.6% not 100% |
| 3.5 | Frontmatter hint for monoliths (`chunk: manual`) | **[measured]** 19 atomic chunks up to 7 926 chars, mostly `SaaS Financial Model Investor-Ready` step tables. A human hint beats a better heuristic |

## Tier 4 — placeholders

| # | Action | Backing |
|---|---|---|
| 4.1 | **Extract slots at prompt level, never chunk level.** Store `chunk_id` as a locator only | **[measured]** 24 prompts have slots spread across chunk boundaries; a chunk-scoped extractor sees `[X]` with its defining context in a neighbouring row |
| 4.2 | Typed slot registry — `fact` / `artifact` / `choice` / `derived` | **[reasoned]** fill policy differs completely per type; only `derived` may be LLM-filled |
| 4.3 | **Synthesize keys for opaque slots** at ingest, once, human-reviewed | **[measured]** 153 of 1 085 slot occurrences are `[X]`(×93), `[Y]`(×32), `[N]`(×17), `[Z]`(×10) — 5 distinct forms. Keying `base_info` off the raw token would bind all 93 `[X]`s to one value |
| 4.4 | Drop the substring fallback in `_match_context` | **[measured]** `route.py:100` binds `[BUDGET]` to a context key `budget_owner_email`. Silent and wrong |
| 4.5 | Never fabricate a `fact` or `artifact`; leave the slot in place and emit a structured `need` | **[reasoned]** a fabricated `[COMPANY NAME]` produces a fluent, confident, wrong document that nothing downstream can detect |
| 4.6 | `base_info` store, ~40–60 entries to start, synced from `arteries.evergreen` | **[measured]** repeat counts suggest small coverage goes far: `[AMOUNT]`×71, `[TIMEFRAME]`×32, `[MONTHS]`×14 |

## Tier 5 — DSPy

| # | Action | Backing |
|---|---|---|
| 5.1 | **Delete `optimize/harvest.py`** | **[measured]** `harvest.py:141` captures `output_text=row["prompt_text"]` — the retrieved prompt as the golden *output*. Trains the optimizer to reproduce the library |
| 5.2 | **Optimize system modules, not the corpus** — `ExtractSlots`, `InferSlot`, `WriteQuery`, `RouteMode` | **[measured]** `dspy_optimize.py` needs ≥5 examples × 916 prompts = 4 580 labels, against 155 distinct queries ever observed. Unreachable by construction |
| 5.3 | `ExtractSlots` first, with `BootstrapFewShot` | **[measured]** 344 slot instances already in the vault are free labels, and the output is checkable without a judge |
| 5.4 | Rewrite `metrics.py`: programmatic → behavioural → episode reward → pairwise judge | **[reasoned]** `exact_match` is difflib on prose; `llm_judge` scores 0–10 absolute, the least reliable judge form |
| 5.5 | Never evaluate baseline and optimized on the same set | **[measured]** `dspy_optimize.py:98,107` both run over `dspy_examples`. That measures memorization |
| 5.6 | Raise `MIN_IMPROVEMENT` from 0.02 to 0.05 until n > 100 | **[reasoned]** 0.02 is inside the noise on a 30-example set |

## Tier 6 — model selection (blocked on 1.4)

| # | Action | Backing |
|---|---|---|
| 6.1 | Keep `mxbai-rerank-base-v2` for now | **[measured]** vs Qwen3-Reranker-0.6B: Spearman 0.673, same top-1 only 8/15, top-5 overlap 60%. mxbai scores 0–1 and clears `SINGLE_THRESHOLD=0.3` on 12/15 queries; Qwen emits raw logits (−14.7 … −1.75) and clears it on **0/15**, even after sigmoid (max 0.148) |
| 6.2 | Before any reranker swap, decouple three constants from the score scale: `find.py:39` (0.30), `reranker.py:86` (0.02), `memory_filter.py` boosts (0.02–0.10) | **[measured]** all three are calibrated to mxbai's 0–1 output and silently stop working on a different scale |
| 6.3 | Embedding bake-off: arctic-embed-m-v2.0 vs Qwen3-Embedding-0.6B, offline with numpy, no schema change | **[measured]** 2 072 × 1 024 floats ≈ 8 MB; brute-force cosine is exact and sub-millisecond. Full corpus re-embed is **~23 s** — swapping is cheap to try and cheap to revert |
| 6.4 | Recalibrate `gate.py:49` `SIMILARITY_THRESHOLD` (0.47) after any embedding change | **[measured]** hand-fitted to arctic's cosine distribution in a 0.036-wide gap. Cosine scales are not comparable across models |
| 6.5 | Test Qwen3-Embedding's per-call-site instructions | **[unverified]** three sites (`gate.py:219`, `retriever.py:169`, `skills/recall.py:251`) share one prefix but ask three different questions. Mechanism is plausible; evidence is zero |
| 6.6 | **Recommended pairing: Qwen3-Embedding-0.6B + mxbai-rerank-base-v2** (mixed, not all-Qwen) | **[measured]** see below |

### Why the mixed pair, not all-Qwen

An all-Qwen stack sounds tidier. Measured, it isn't better.

**Same-family coherence is not a retrieval benefit.** Over 20 queries, scoring
the Qwen retriever's top-30 with each reranker, correlation to the retriever's
own ordering: mxbai **+0.258**, Qwen3-Reranker **+0.321**. The same-family
reranker agrees *more* with the retriever — which makes it slightly more
redundant, since a reranker earns its latency by contributing signal the
retriever lacks. The gap is small and n=20, so read it as "no benefit," not as
evidence against. Either way, the family argument does not survive contact with
measurement.

**Where compatibility genuinely matters is dependencies, and there the
embedder is the whole story.** arctic requires `transformers<5` (its custom
remote code NaNs on 5.4.0). That pin is expensive: `sentence-transformers` 5.5
and `transformers` 4.49 could not even be imported in one process during
testing (Keras 3 conflict). Both Qwen3 models *and* mxbai run natively on
`transformers` 5.4.0 with no custom code. So dropping arctic removes the pin —
and the reranker choice contributes nothing to that.

**Retracted:** an earlier version of this section argued for mxbai because its
0–1 output preserves `find.py:39`'s `SINGLE_THRESHOLD = 0.3`. That is
backwards — the rework *replaces* that decision layer, so compatibility with it
is not a benefit. See "Decision layer" below. The remaining case for mxbai is
speed (536 ms vs 896 ms full-length) and marginally more independent signal.
Both are real but neither is decisive; this stays open until the eval set
exists.

---

## Decision layer — replace the absolute threshold

Every model swap this session broke a hand-tuned constant: `gate.py`'s 0.47,
`find.py`'s 0.30, `reranker.py`'s 0.02 length penalty, `memory_filter`'s
boosts. That is not four bugs, it is one design error — **absolute scores are
model-specific and must not be thresholded directly.**

Measured across four models, top-30 candidate lists:

| Model | raw top-1 | top1 − top2 | **z-score of top-1 vs candidates** |
|---|---|---|---|
| arctic-fixed (retriever) | +0.255 | +0.012 | **+2.80** [2.20, 3.71] |
| qwen3-embed (retriever) | +0.626 | +0.014 | **+2.74** [2.22, 3.76] |
| mxbai-base-v2 (reranker) | +0.898 | +0.078 | **+2.38** [1.83, 4.42] |
| qwen3-rerank (reranker) | **−4.125** | +0.375 | **+2.23** [1.65, 2.59] |

Raw top-1 spans +0.255 to +0.898 to −4.125 — no shared scale exists. The
z-score `(top1 − mean) / std` over the candidate list lands at **2.2–2.8 for
every model**, embedders and rerankers alike.

**Design rule: the decision layer consumes normalized confidence, never a raw
score.** A cut at z ≈ 2.0–2.5 is approximately portable, so swapping a model
becomes a config change instead of a recalibration project. Combine two
signals:

- `z` — is the top result distinctive against its own candidate set
- `margin = top1 − top2` — is the winner clearly ahead of the runner-up

**What this does not buy you.** z measures *distinctiveness*, not *quality*. A
query with no good answer can still produce one candidate that stands out, and
z will happily report high confidence. It makes the abstention decision
**portable across models**; it does not make it **correct**. Fitting the cut
still requires the eval set — including its negative queries. The win is that
you fit it once rather than once per model.

---

## Corrections made during the audit

Recorded because each one changed a recommendation, and the reasoning that
produced them will otherwise repeat.

1. **"The reranker has a 512-token window."** Wrong. Taken from the stale
   docstring at `reranker.py:8-10`. The loaded model is Qwen2.5-0.5B-based with
   `max_position_embeddings: 32768`. This had propagated into a recommendation
   to drop TARGET to 1 200 — withdrawn; 1 600 stands.
2. **"Headings are the section delimiter."** Wrong. Only 109 of 916 prompts
   have Markdown headings; 510 have no structural marker at all. The chunker is
   a cascade (XML → heading → rule → bold → paragraph) as a result.
3. **"Long prompts will flood results with fragments."** Wrong, and backwards.
   Short prompts are over-represented (65% of top-10 results from 52% of the
   corpus); ≥5-chunk prompts are under-represented (8% of results, 14% of
   corpus).
4. **"Chunking fixes reranking for free."** Wrong. `MAX_DOC_CHARS` still
   truncates at 512 chars against a median chunk of 1 713. Separate fix — 0.2.
5. **Phase order.** I built chunking before the eval set and cannot now tell
   whether it helped. Don't repeat this with the embedding or reranker swaps.
