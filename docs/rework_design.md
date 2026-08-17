# Capillaries rework — design

Target branch: `rework`. Audit run against `dev` @ `6cf2811` with the live
`capillaries` database attached.

Corpus as measured, not assumed:

| Thing | Count |
|---|---|
| `prompts` rows (all `status='active'`) | 916 |
| ...with embeddings | 916 |
| ...longer than the 4 000-char embed cap | 276 (30%) |
| prompt_text length: median / mean / max | 2 044 / 4 046 / 41 881 chars |
| prompts containing `[UPPERCASE]` slots | 181 |
| ...`{{mustache}}` slots | 68 |
| ...`[paste …]` slots | 95 |
| `skills.skills` | 6 |
| `serving_log` rows | 2 895 |
| ...with a non-null `episode_id` | **2** |
| distinct queries in `serving_log` | 155 |
| `arteries.rewards` | 34 |
| `golden_examples` | **0** |
| `optimization_runs` | **0** |
| `skills.agent_feedback` | **0** |

Everything below follows from those numbers.

---

## 1. Findings

### The corpus is 30% invisible to vector search

`db/embed.py:27` caps embedding input at 4 000 characters. 276 prompts exceed
it, and the longest is ten times over. For those, everything past the cap was
never embedded — it cannot be retrieved semantically, at all, today. This is
the strongest argument for chunking, and it is not a quality argument, it's a
coverage one.

### The reranker sees the first 512 characters and nothing else — on CPU

`search/reranker.py:41` truncates each document to 512 chars before scoring,
and `reranker.py:145` defaults the device to `"cpu"`. Neither is a model limit;
both are self-imposed. See §4 for the measurements.

Median prompt is 2 044 chars, so the component that decides final rank order
judges roughly the first quarter of a typical prompt and about 1% of the
longest — every prompt with a boilerplate preamble is ranked on its preamble —
and it does so 110× slower than the hardware allows.

### Keyword search is over-weighted *and* mis-aimed

Two separate problems, easy to conflate.

Weight: `retriever.py:42-43` sets `DENSE_WEIGHT = SPARSE_WEIGHT = 0.5`. Your
diagram wants 80–90 / 10–20. Straightforward config change.

Aim: `_to_or_tsquery` (`retriever.py:265`) OR-joins **every** token in the
query. A query of eight words matches any prompt containing any one of them,
and with 916 documents `ts_rank_cd` then has to sort a near-corpus-wide
candidate list. The sparse channel is currently a second, worse recall channel
rather than a precision instrument. Re-weighting alone would mask this without
fixing it.

Also: `search_tsv` is built with the `english` config, which stems and
lowercases. `slugify()`, `--reembed`, `search_tsv` itself, `L-6-v2` — the
tokens that vectors are genuinely bad at — are exactly the tokens the `english`
tokenizer mangles.

### Placeholder handling is inference-time regex with no registry

`agent/route.py:107` `resolve_template_variables` re-discovers slots on every
call and matches them against a flat context dict. Three real defects:

- `_match_context` (`route.py:100`) falls back to **substring** key matching.
  Slot `[BUDGET]` will happily bind to a context key `budget_owner_email`.
  Silent, wrong, unauditable.
- `_is_real_slot` is a stopword blacklist. `[NOTE THAT THIS IS IMPORTANT]`
  passes as a slot.
- No slot types beyond `paste`/`choice`/`fill`, no source of truth for values,
  no "Base info" store of any kind. Your diagram's leftmost box does not exist
  in the code.

### The DSPy loop is fully built and has never run

`optimize/` is complete scaffolding — capture, harvest, metrics, fences, A/B
gate, run logging. It has processed zero examples. Two reasons, one mechanical
and one conceptual.

Mechanical: `harvest.py` joins `serving_log` to `arteries.rewards` on
`episode_id`, and 2 893 of 2 895 serving rows have a null `episode_id`.
`serving/log_serving` reads `$ARTERIES_EPISODE_ID` (`serving.py:80`) and that
variable is not reaching the process. The join returns ~2 rows. Fix the env
propagation and the loop has data tomorrow.

Conceptual, and more serious: `harvest.py:141` captures
`output_text=row["prompt_text"]` — the retrieved prompt's own text as the
golden *output*. Combined with `metrics.exact_match` (difflib ratio), the
optimizer is being trained to reproduce the prompt library verbatim. That's a
retrieval metric wearing a generation metric's clothes. Whatever the rework
does, this join must not survive it.

Third, structural: `dspy_optimize.PromptOptimizer` optimizes **one prompt at a
time** and requires ≥5 golden examples for each. 916 prompts × 5 examples =
4 580 labeled examples to cover the corpus, against 155 distinct queries ever
observed. Per-prompt optimization is unreachable by construction. See §5.

### The 2 895 serving rows are synthetic

155 distinct queries, and `search/eval.py` ships a hardcoded query list. The
log is a record of `eval.py` runs, not of use. Treat it as zero real traffic.

### Audit table

| Module | Verdict | Why |
|---|---|---|
| `db/setup.py` schema | **Rewrite** | Needs chunk, slot, and base-info tables; `prompts` becomes the parent record |
| `db/setup_skills.py` | **Keep** | Skills schema is sound; `steps` JSONB already carries what it needs |
| `db/embed.py` | **Rewrite** | Embeds whole prompts; must embed chunks |
| `search/retriever.py` | **Rewrite** | RRF merge logic is good and keeps its shape; the SQL, the tokenizer, and the weights all change |
| `retriever.expand_acronyms` + `ACRONYMS` | **Keep** | 85 hand-curated entries, works, costs nothing |
| `search/reranker.py` | **Keep, retune** | Daemon plumbing and length penalty are fine; `MAX_DOC_CHARS` and the input unit change |
| `search/api.py` | **Rewrite** | Two-tier logic gets a chunk→parent rollup step |
| `search/memory_filter.py` | **Keep** | Independent of the rework; operates post-rerank |
| `search/eval.py` | **Rewrite** | Report generator with no ground truth. Becomes the eval harness (§6) |
| `agent/gate.py` | **Keep** | Two-signal gate is well-calibrated and independently justified. `_SPEC_TOKEN` gets reused — see §4 |
| `agent/route.py` slot code | **Rewrite** | Moves to ingest-time extraction + typed registry (§3) |
| `agent/route.py` router | **Keep** | Thin over `find`/`recall` |
| `agent/execute.py` | **Keep** | Session stepping is orthogonal |
| `find.py` | **Keep** | Correct seam. Body changes, contract doesn't |
| `optimize/serving.py` | **Keep, fix** | Right schema. `episode_id` propagation is broken |
| `optimize/harvest.py` | **Delete** | The prompt-text-as-golden-output join is wrong at the root |
| `optimize/metrics.py` | **Rewrite** | `exact_match` on prose is noise; judge is absolute-scored (§5) |
| `optimize/fences.py` | **Keep** | Reusable as fill-time validation |
| `optimize/dspy_optimize.py` | **Rewrite** | Per-prompt target is unreachable; optimize modules instead |
| `skills/promote.py` `ab_gate` | **Keep** | Promotion gate is sound once metrics are |
| `classify/batch.py` | **Keep** | Taxonomy backfill, unaffected |

---

## 2. Chunking

> **Revised after implementation.** The first draft of this section assumed
> Markdown headings were the section delimiter. They aren't. Measured over the
> 916 prompts: XML-ish tags (`<role>`, `<guardrails>`, `<instructions>`) in
> 186, bold headers in 233, horizontal rules in 237, headings in only **109**,
> and **510 prompts with none of the above**. A heading-based chunker would
> have degenerated to whole-document chunks on 88% of the corpus. Implemented
> in `src/capillaries/chunk.py` as a cascade instead.

Prompts aren't prose. They have structure — a role block, constraints, a
worked example, an output spec — and that structure is exactly where the
boundaries belong. Fixed-token windows would cut a few-shot input from its
output about as often as not. But the structure is expressed four different
ways across this vault, so the splitter tries each in turn.

### Rule

Split on the strongest delimiter present, and descend only when a piece is
still over target:

| Level | Delimiter | Prompts using it |
|---|---|---|
| 1 | XML section tag on its own line, `^<tag>$` | 186 |
| 2 | Markdown heading, `^#{1,6} ` | 109 |
| 3 | Horizontal rule, `^---+$` | 237 |
| 4 | Bold header line, `^**...**$` | 233 |
| 5 | Blank-line paragraph break | fallback — carries the 510 |

Code fences and Markdown tables are masked before splitting, so a `---` row
inside a table and a `# comment` inside a fence never become boundaries.

Splitting goes down to TARGET granularity (1 600 chars), then a packing pass
reassembles neighbours back up to TARGET. Cutting only at the ceiling would
leave a 3 900-char prompt as a single chunk — which overflows the
cross-encoder window and puts us back where the unchunked index already was.

Sizes are characters, not tokens. ~4 chars/token is close enough to keep chunks
inside a 512-token window, and it avoids a `tiktoken` dependency for a number
that only has to be roughly right.

**Measured result:** 916 prompts → 2 072 chunks, median 1 713 chars (~430
tokens), max 7 926, 19 oversized-atomic. 475 prompts stay single-chunk. 241 of
the 276 previously-truncated prompts now have indexed content past char 4 000;
the remaining 35 lost their tail to self-duplicate collapse, which is correct.

### Self-duplication

169 prompts repeat their own opening verbatim — the Obsidian note holds the
prompt twice, usually either side of a `---`. `The Orchestrator Prompt` splits
into 104 raw spans of which **54 are byte-identical duplicates**. Chunks with
an identical whitespace-normalized hash collapse to their first occurrence
within a prompt, which is why corpus coverage lands at 91.6% rather than 100%.
The missing 8.4% is duplicated text, not lost text.

Cross-prompt duplication turned out to be minor: 34 chunks share an exact hash
with a chunk in another prompt, 140 sit above 0.95 cosine to one. Worth a
cleanup pass, not worth a mechanism.

### Atomic blocks and bounds

- **Atomic blocks, never split:** fenced code and Markdown tables, masked
  before the cascade runs. An atomic block over the ceiling becomes its own
  oversized chunk and is flagged `is_atomic` — correctness beats the budget.
  19 chunks land here.
- **Budget:** TARGET 1 600 chars, CEILING 4 000.
- **Floor:** 320 chars. A trailing scrap below it merges into the chunk above;
  it's a fragment of that section, not a unit of its own.
- **Overlap:** none. Every chunk is prefixed at embed time with
  `{title} > {label}`. Overlap buys context by duplicating tokens into the
  index; a breadcrumb buys the same context for ~15 tokens and doesn't.

The breadcrumb also earns its keep at rollup time — `label` is extracted from
whichever delimiter made the cut, so the top labels across the corpus come out
as `instructions` (527), `guardrails` (112), `output` (91).

### Small-to-big

Retrieve chunks, return parents. The chunk is the ranking unit; the prompt is
the serving unit. A prompt matching on three chunks should not occupy three of
your ten result slots.

```sql
CREATE TABLE prompt_chunks (
    chunk_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id     UUID NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,          -- 0-based, document order
    heading_path  TEXT,                      -- 'Constraints > Output format'
    chunk_text    TEXT NOT NULL,
    char_start    INTEGER NOT NULL,          -- offset into prompts.prompt_text
    char_end      INTEGER NOT NULL,
    is_atomic     BOOLEAN DEFAULT FALSE,     -- oversized block kept whole
    token_count   INTEGER,
    content_hash  VARCHAR NOT NULL,          -- reuse embeddings across re-ingest

    embedding         VECTOR(768),
    embedding_version VARCHAR,
    search_tsv        TSVECTOR,              -- 'english' config, stemmed
    exact_tsv         TSVECTOR,              -- 'simple' config, see §4

    UNIQUE (prompt_id, chunk_index)
);

CREATE INDEX idx_chunks_embedding ON prompt_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_chunks_tsv   ON prompt_chunks USING GIN (search_tsv);
CREATE INDEX idx_chunks_exact ON prompt_chunks USING GIN (exact_tsv);
CREATE INDEX idx_chunks_parent ON prompt_chunks (prompt_id, chunk_index);
```

`prompts.embedding` stays, holding a whole-document embedding of the first
4 000 chars. `gate.py` uses it for the nearest-neighbour proximity check and
wants one vector per prompt, not per chunk. Two vectors, two jobs.

Rollup: `parent_score = max(chunk_score) + 0.05 × (n_matching_chunks − 1)`,
capped at `max + 0.10`. Max, not mean, because one excellent chunk is a real
match and averaging punishes long prompts twice — the length penalty already
in `reranker.py:214` handles that concern once.

### Edge cases

| Case | Handling |
|---|---|
| Prompt shorter than the floor | One chunk, `chunk_index=0`, identical to the prompt |
| 41 881-char monolith | Cascades to paragraph packing; produced bounded chunks, no manual sectioning needed |
| Skill with attached files | Chunk the skill's `routing_description` + each step's prompt separately; the skill row keeps its single routing embedding for recall |
| Prompt edited upstream | Re-chunk whole; embeddings are reused by `content_hash`, across runs and across prompts sharing a boilerplate section |

### Status, and one honest caveat

Built and backfilled. `prompt_chunks` holds 2 072 rows, all embedded, all with
both tsvectors, covering all 916 parents. Offsets verified: zero rows where
`prompt_text[char_start:char_end] ≠ chunk_text`.

**Nothing reads this table yet.** `retriever.py` still queries `prompts`, so
live retrieval is unchanged and nothing is at risk.

That last point is deliberate, because the obvious next move — point retrieval
at the chunks — is not yet justified by evidence. Two probes:

- 30 queries drawn verbatim from content past char 4 000: recall@10 was 4/30
  under the old whole-prompt index and 2/30 under chunks. At n=30 and p≈0.1 the
  difference is inside the noise, so this says nothing except that both are bad
  at verbatim-excerpt probes — which is expected, since the query prefix on
  `arctic-embed` is built for questions, not passages.
- 60 natural-language queries from `serving_log`: top-1 changed for **59 of
  60**. Median top-1 similarity rose 0.443 → 0.606, but that comparison is not
  apples to apples — chunks are shorter, and cosine to a short query rises
  mechanically as the document shortens.

So chunking has reshuffled ranking almost completely, and there is currently no
way to tell whether that is an improvement. That is exactly the failure mode §7
Phase 1 exists to prevent, and I built Phase 2 before it. **Do not switch
`retriever.py` over to chunks until the labeled eval set exists** — build it,
score the old index, score the new one, then cut over on the number.

---

## 3. Placeholder filling

### Slot syntax

Keep `[UPPERCASE SLOT]`, `{{mustache}}`, `[paste …]` — 344 prompt-instances
already use them and rewriting the vault is not on the table. But stop
detecting them at inference time. Extract once, at ingest, into a registry,
where a human can inspect and correct them.

```sql
CREATE TABLE prompt_slots (
    slot_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id   UUID NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
    chunk_id    UUID REFERENCES prompt_chunks(chunk_id) ON DELETE CASCADE,
    raw         TEXT NOT NULL,        -- '[TARGET SEGMENT]' exactly as written
    slot_key    VARCHAR NOT NULL,     -- 'target_segment' (normalized)
    slot_type   VARCHAR NOT NULL CHECK (slot_type IN
                    ('fact','artifact','choice','derived')),
    choices     TEXT[],               -- populated when slot_type='choice'
    required    BOOLEAN DEFAULT TRUE,
    description TEXT,                 -- LLM-written, one line, from surrounding text
    occurrences INTEGER DEFAULT 1,
    verified    BOOLEAN DEFAULT FALSE,-- a human confirmed this is a real slot
    UNIQUE (prompt_id, raw)
);
```

The four types, because the fill policy differs completely per type:

- **`fact`** — a stable value about the user or their work. `[COMPANY NAME]`,
  `[FISCAL YEAR END]`. Looked up. Never generated.
- **`artifact`** — content the user must supply. `[paste your churn data]`.
  Never generated, never looked up. Always a blocking need.
- **`choice`** — enumerated. `[WEEKLY/MONTHLY/QUARTERLY]`. Filled from base
  info if the value is in `choices`; otherwise asked.
- **`derived`** — inferable from the current situation. `[THE PROBLEM YOU'RE
  SOLVING]`. The only type an LLM is allowed to fill.

`verified` matters. Extraction is a heuristic plus an LLM pass, and both are
wrong sometimes. An unverified slot still fills, but a fill that fails review
is one `UPDATE` away from never recurring.

### Base info

```sql
CREATE TABLE base_info (
    info_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key         VARCHAR NOT NULL,     -- 'company_name'
    value       TEXT NOT NULL,
    aliases     TEXT[] DEFAULT '{}',  -- 'org name', 'business name'
    scope       VARCHAR DEFAULT 'global',  -- 'global' | domain | project slug
    kind        VARCHAR DEFAULT 'fact',
    source      VARCHAR NOT NULL,     -- 'manual' | 'arteries_evergreen' | 'inferred'
    confidence  FLOAT DEFAULT 1.0,
    valid_until DATE,                 -- staleness: a fiscal year isn't forever
    embedding   VECTOR(768),          -- over 'key: description'
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (key, scope)
);
```

`source='arteries_evergreen'` is the interesting row. Arteries already holds
durable user facts in `arteries.evergreen`; base_info should sync from it
rather than becoming a second place the user types their company name.

### The fill algorithm

```
fill(prompt, situation, agent_context, scope_hints) -> (text, needs[])

slots = SELECT * FROM prompt_slots WHERE prompt_id = ? ORDER BY position
needs = []

for slot in slots:
    # 1. explicit context always wins — the caller knows more than the store
    if slot.slot_key in agent_context:           -> substitute; continue

    if slot.slot_type == 'artifact':
        needs.append(need(slot, 'user_must_supply')); continue

    # 2. exact key, scope-ordered: project > domain > global
    hit = base_info WHERE key = slot.slot_key AND scope IN scope_hints
    if hit and not stale(hit):                   -> substitute; continue

    # 3. alias match, exact string only
    hit = base_info WHERE slot.slot_key = ANY(aliases)
    if hit:                                      -> substitute; continue

    # 4. semantic match on slot.description vs base_info.embedding
    cands = top-3 by cosine, threshold 0.75
    if len(cands) == 1:                          -> substitute; continue
    if len(cands) > 1 and gap(c0, c1) < 0.05:
        needs.append(need(slot, 'ambiguous', candidates=cands)); continue
    if len(cands) > 1:                           -> substitute c0; continue

    # 5. LLM inference — derived slots only, never fact/artifact
    if slot.slot_type == 'derived':
        v = InferSlot(situation, slot.description, prompt_context)
        if v.confidence >= 0.7:                  -> substitute; continue

    needs.append(need(slot, 'unfilled'))

validate(text, prompt.prompt_text)
return text, needs
```

Steps 1–3 are pure lookup and cover the overwhelming majority. An LLM call
happens only for `derived` slots that lookup missed — on this corpus, a small
minority of a minority. Cheap, auditable, and the expensive path is the rare
one.

**No substring matching.** That's the deliberate removal of `route.py:100`'s
fallback. Semantic match on a written description is the principled version of
what that fallback was reaching for, and it reports its own confidence.

### Failure policy

**Never fabricate a `fact` or an `artifact`.** Leave the slot literally in
place, add a structured entry to `needs[]`, and return. A fabricated
`[COMPANY NAME]` doesn't error — it produces a confident, fluent, wrong
document, and nothing downstream can tell. An unfilled slot is visible to
every consumer including the human.

| Failure | Response |
|---|---|
| No match, `required=true` | Slot stays; `needs` entry; caller (`route.py`) already returns `mode='needs_context'` |
| No match, `required=false` | Slot's whole sentence is dropped; noted in `needs` as `omitted` |
| Multiple candidates within 0.05 | Never pick. Return `ambiguous` with candidates — a two-option question costs the user one second |
| Value past `valid_until` | Fill it, mark `stale` in `needs`. Last year's fiscal date beats a hole, but the caller gets told |
| LLM confidence < 0.7 | Treat as no match |

### Validation

Before a filled prompt is servable:

1. No `required` slot pattern survives in the text.
2. Code fences and frontmatter are byte-identical to the source — reuse
   `optimize/fences.py:assert_fences_unchanged`, it already does exactly this.
3. Length delta within ±40% of the sum of substituted value lengths. Catches a
   runaway LLM fill.
4. Every substituted value is non-empty after strip.

### Worked example

Source, `prompts.prompt_text`:

```markdown
## Quarterly Business Review

You are preparing a QBR for [COMPANY NAME], covering [QUARTER].

Audience: [EXEC/BOARD/TEAM].

### Inputs
[paste last quarter's metrics]

### Focus
The review should center on [THE KEY BUSINESS QUESTION].
```

**Chunked** — three chunks: the role paragraph (below floor, merges with
heading), `### Inputs`, `### Focus`. `[paste last quarter's metrics]` and its
heading stay together; the slot-with-its-defining-context rule forbids the cut.

**Extracted:**

| raw | slot_key | type | description |
|---|---|---|---|
| `[COMPANY NAME]` | `company_name` | fact | The organization the review is for |
| `[QUARTER]` | `quarter` | fact | Fiscal quarter under review |
| `[EXEC/BOARD/TEAM]` | `audience` | choice | Who receives the review |
| `[paste last quarter's metrics]` | `last_quarter_metrics` | artifact | Prior-quarter metric export |
| `[THE KEY BUSINESS QUESTION]` | `key_business_question` | derived | The central question this review answers |

**Filled**, situation = *"put together the Q3 review, I want to focus on why
enterprise renewals slipped"*:

- `company_name` → step 2, exact key in base_info, scope `global` → "Northwind"
- `quarter` → step 4, semantic 0.81 against `current_fiscal_quarter` → "Q3 FY26"
- `audience` → step 5 skipped (choice, not derived); no base_info hit →
  `needs: choice, options [EXEC, BOARD, TEAM]`
- `last_quarter_metrics` → `needs: user_must_supply`
- `key_business_question` → step 5, InferSlot → "Why enterprise renewal rates
  declined in Q3 and what reverses it"

Result: `mode='needs_context'`, two blocking needs, three slots resolved, zero
fabrications. The agent asks two questions instead of ten.

---

## 4. Retrieval

### Fusion, and what "15%" means

Keep weighted RRF. Score fusion across cosine similarity and `ts_rank_cd`
requires normalizing two quantities with no shared scale and no stable
distribution across queries; RRF sidesteps it by only reading ranks.

RRF has no natural weight knob, so here is the explicit mapping. With
`score = w_d/(k + rank_d) + w_s/(k + rank_s)`, `k = 50`:

| Config | Best possible dense-only score | Best possible sparse-only score | Sparse share |
|---|---|---|---|
| current, 0.5 / 0.5 | 0.0098 | 0.0098 | 50% |
| **proposed, 0.85 / 0.15** | 0.0167 | 0.0029 | **15%** |

A sparse-only rank-1 hit lands below a dense rank-9 hit. So sparse can pull a
document into the candidate set and break ties among dense-comparable
documents, but it cannot by itself put a document on top. That is the behaviour
"10–20%" should mean, and it's what makes sparse a precision instrument rather
than a vote.

Both weights move to config (`CAPILLARIES_DENSE_WEIGHT` / `_SPARSE_WEIGHT`),
because they are guesses until §6's eval harness exists. They are guesses now,
too — the difference is that config guesses can be swept.

### What keyword search is for

Vectors are bad at tokens that carry no distributional meaning: file paths,
function names, flags, error strings, version numbers, env vars. `gate.py:69`
already contains a regex that identifies exactly these — `_SPEC_TOKEN`, written
for a different purpose and correct for this one.

So: **route spec tokens to a dedicated exact channel, everything else to
dense.**

```python
def split_query(q: str) -> tuple[str, list[str]]:
    """(prose remainder, spec tokens) — spec tokens go exact, prose goes dense."""
    spec = [m.group(0) for m in _SPEC_TOKEN.finditer(q)]
    return _SPEC_TOKEN.sub(" ", q), spec
```

Three channels, not two:

| Channel | Index | Query form | Weight |
|---|---|---|---|
| dense | `chunks.embedding` (HNSW) | full query, embedded | 0.85 |
| exact | `chunks.exact_tsv` (`simple` config) | `phraseto_tsquery('simple', …)` over spec tokens, AND-joined | 0.15 |
| stemmed | `chunks.search_tsv` (`english`) | `websearch_to_tsquery` | fallback only — used when the query yields no spec tokens *and* dense returns fewer than 5 above 0.3 |

The `simple` config doesn't stem or drop stopwords, so `slugify`, `--reembed`,
and `L-6-v2` survive as lexemes. For identifiers, index both the joined and
split forms — `search_tsv` gets `snake_case` → `snake_case`, `snake`, `case` —
so a query for either shape hits.

**`OR` becomes `AND`.** Today's OR-of-every-token is the actual precision leak:
one shared common word admits a document. Under AND, sparse returns few or no
rows for most queries, which is correct — the dense channel is meant to carry
recall. When AND returns nothing, sparse contributes nothing, and the search is
purely dense. That is the intended behaviour at an 85/15 split, not a
degradation.

Drop `SPARSE_CANDIDATES` from 50 to 20. A precision channel returning 50
candidates is not being precise.

### Reranking

Keep it, and fix it. `MAX_DOC_CHARS = 512` (`reranker.py:41`) is the single
biggest ranking bug in the repo. Two changes:

- Score **chunks**, not prompts. A 300–800-token chunk fits the cross-encoder's
  window natively — chunking fixes reranking as a side effect.
- Drop `MAX_DOC_CHARS` entirely, or set it to ~6 000 as a safety rail.
  **Correction:** an earlier draft said this model handles 512 tokens. It
  doesn't. The docstring at `reranker.py:8-10` still describes
  `cross-encoder/ms-marco-MiniLM-L-6-v2` (22M params, 512 tokens), but line 39
  loads `mixedbread-ai/mxbai-rerank-base-v2` — Qwen2.5-0.5B-based, with
  `max_position_embeddings: 32768`. Measured on a 3090, 50 pairs of real
  chunks: 249 ms truncated at 512 chars, **536 ms at full length**. There is no
  cost worth paying for the truncation.
- Set `RERANKER_DEVICE=cuda`. It defaults to `"cpu"` (`reranker.py:145`) on a
  two-3090 box. Same 50 pairs: **27 354 ms on CPU vs 249 ms on GPU.**
- Consequence for §2: the reranker is **not** the binding constraint on chunk
  size. Sizing is governed by embedding dilution, which is flat to ~6 000
  chars, so TARGET 1 600 stands and there is no reason to drop it to 1 200.

Corpus size doesn't argue against reranking here — 916 prompts is small, but
reranking runs over ~50 candidates regardless of corpus size, and the daemon in
`daemon.py` already amortizes the 4.4 s model load. Cost is the daemon staying
resident; latency is ~50 ms. Keep it.

### Prefilter vs. ranking

`_build_filter_clause` (`retriever.py:180`) stays as-is and stays a hard `WHERE`
prefilter: `status`, `domain`, `intent`, `task_type`, `complexity`, `source`,
`modality`. Filters express *eligibility*; scores express *preference*. Never
convert a filter to a boost — an inactive prompt with a great score is still
inactive.

Filters apply to `prompts`, joined from `prompt_chunks` — chunks inherit their
parent's eligibility and don't duplicate the columns.

---

## 5. DSPy with almost no data

### The structural correction

`dspy_optimize.py` optimizes one prompt for one model and demands ≥5 golden
examples per prompt. Covering 916 prompts needs 4 580 labeled examples. You
have 0, and 155 distinct queries have ever been observed. The long tail will
never have data — that's what a long tail is.

**Optimize the system's own modules, not the corpus.** There are perhaps six
DSPy modules in this design, every one of them exercised by every request, and
their training data accumulates at the rate of total traffic rather than
per-prompt traffic. Per-prompt optimization is a later luxury for the handful
of prompts with real volume.

Modules worth compiling:

| Module | Signature | Data source | Judgeable how |
|---|---|---|---|
| `ExtractSlots` | `chunk_text -> slots[]` | 344 slot instances already in the vault | Human verification flag; programmatic — did regex and LLM agree |
| `InferSlot` | `situation, slot_description, context -> value, confidence` | Fill traces | Was the value edited before use |
| `WriteQuery` | `situation -> retrieval_query` | `serving_log` | Recall@k against the eval set |
| `RouteMode` | `situation -> single \| skill \| none` | `serving_log` + feedback | Did the served mode get used |
| `SummarizeStep` | `step_output -> context_summary` | `skill_sessions` | Judge |
| `WriteRouting` | `skill_steps -> routing_description` | 6 skills | Recall of the skill for its own queries |

`ExtractSlots` first. It has 344 free labels sitting in the vault right now,
its output is checkable without a judge, and it's a hard blocker for §3.

### Tiers

| Examples | Optimizer | What's reachable | Ceiling |
|---|---|---|---|
| **0** | none | Hand-write signatures. Run `ExtractSlots` and `WriteRouting` as plain `dspy.Predict`. Build the eval set (§6) | You're guessing; no evidence anything improved |
| **~10–30** | `BootstrapFewShot`, `max_bootstrapped_demos=4` | Demo selection for `ExtractSlots`, `InferSlot` | Demos only; instructions untouched. Typically most of the available win |
| **~50–200** | `MIPROv2`, `auto="light"`, 30/20 train/val | Instruction proposal for `WriteQuery`, `RouteMode` | Overfits hard below ~50; hold out val strictly |
| **200+** | `MIPROv2` `auto="medium"`; per-prompt for the top ~20 by traffic | Corpus-level optimization for high-volume prompts only | The tail stays uncompiled — correctly |

Realistic near-term: tier 2 for `ExtractSlots`, tier 1 for everything else.

### The metric problem

This is the hardest part and the current code gets it wrong twice —
`exact_match` is a difflib ratio on generated prose (noise), and `llm_judge`
scores a candidate 0–10 in absolute terms, which is the least reliable way to
use a judge. Absolute scores drift between calls and cluster around 7.

Metrics, cheapest and most trustworthy first:

1. **Programmatic, no judge.** Slot-fill completeness (fraction of required
   slots resolved without a `need`); fence integrity; validation-pass rate;
   schema conformance. Free, deterministic, and enough to optimize
   `ExtractSlots` and `InferSlot` end to end.
2. **Behavioural.** Was the served prompt used without edit? Did the user
   re-query within 60 s (a retrieval failure signal)? Requires logging the
   *outcome*, not just the serving — see below. No labels, no judge, and it
   measures what you actually care about.
3. **Episode reward.** `arteries.rewards`, 34 rows and growing. Real signal,
   sparse. Weight it heavily where it exists.
4. **Pairwise LLM judge**, last resort. Ask "which of A or B better answers
   this?", randomize position, and require both orders to agree — a judge that
   flips when the options swap has told you the pair is a tie. Never absolute
   scoring.

### Closing the loop

`serving_log` records what was served. It does not record what happened next,
and that's the gap between "we have telemetry" and "we have training data."

```sql
ALTER TABLE serving_log
    ADD COLUMN prompt_variant_id UUID,   -- which text actually went out
    ADD COLUMN chunk_ids         UUID[], -- which chunks won, for chunk-level eval
    ADD COLUMN slots_total       INTEGER,
    ADD COLUMN slots_filled      INTEGER,
    ADD COLUMN needs             JSONB DEFAULT '[]',
    ADD COLUMN fill_trace        JSONB DEFAULT '[]';  -- per slot: source, score

CREATE TABLE serving_outcome (
    serving_id   BIGINT PRIMARY KEY REFERENCES serving_log(id),
    used         BOOLEAN,      -- did the prompt reach the model
    edited       BOOLEAN,      -- was the text changed before use
    edit_distance INTEGER,
    requeried_within_60s BOOLEAN,
    reward       FLOAT,        -- from arteries.rewards when the episode closes
    recorded_at  TIMESTAMPTZ DEFAULT now()
);
```

**Fix `episode_id` propagation before anything else in this section.** Two rows
out of 2 895 carry one; `serving.py:80` reads `$ARTERIES_EPISODE_ID` and the
variable isn't arriving. Every downstream item — reward join, outcome
attribution, A/B gate — is blocked on it. It is very likely a one-line fix in
the arteries hook, and it is the highest-leverage change in the repo. Yes, I
agree with the framing in your diagram that Results → DSPy is where the
compounding is; this is the wire that carries it.

### Optimizing retrieval, not just generation

`WriteQuery` and `InferSlot` are DSPy modules on the retrieval side and both
have programmatic metrics (recall@k, fill completeness). They're better first
targets than any generation module — cheaper to evaluate and they compound,
since better retrieval improves every downstream metric.

### Skills

A skill is `routing_description` + ordered `steps` + `changelog`. Optimizable
and frozen split cleanly:

- **Optimizable:** `routing_description` (it's a retrieval surface — compile it
  against "does this skill get recalled for the queries it should"), and each
  step prompt's instruction body, subject to the same fence guard as prompts.
- **Frozen:** `steps` ordering, `step_order`, `prompt_id` references, and
  `pinned_hash`. A prompt optimizer must never reorder or drop a step —
  sequence is the skill's semantics, not its phrasing. Enforce with a check
  alongside `assert_fences_unchanged`.

### Guardrails

- **Train/val separation.** Below ~50 examples, a held-out set is too small to
  trust and too costly to give up. Use 5-fold cross-validation and report the
  spread, not a point score. Never report a score computed on the trainset —
  `dspy_optimize._evaluate` currently evaluates baseline *and* optimized on the
  same `dspy_examples` (`dspy_optimize.py:98,107`), which measures memorization.
- **Overfitting.** At n<50, `MIPROv2` will find instructions that ace your
  examples and nothing else. That's the reason for the tier table, not caution
  for its own sake.
- **Versioning.** `prompt_variants` already handles this correctly — variants
  are model-scoped, canonical is never overwritten by the optimizer, and
  promotion goes through `ab_gate`. Keep all three properties.
- **Regression + rollback.** `ab_gate` is the mechanism; it needs the eval
  harness to be meaningful. Every promotion records the run_id that justified
  it; rollback is `UPDATE prompt_variants SET is_current` on the prior row.
  `MIN_IMPROVEMENT = 0.02` (`metrics.py:13`) is too tight for a 30-example set —
  raise to 0.05 until n > 100.

---

## 6. Gaps

| Component | Why | When |
|---|---|---|
| **Retrieval eval set** | "80/20" is unfalsifiable without one. `eval.py` prints a report with no ground truth. 155 distinct queries in `serving_log` are the seed — label the correct prompt for ~50 of them by hand and you can measure recall@10 and MRR. Nothing else in §4 or §5 can be validated first | **Now.** Blocks everything |
| **`episode_id` propagation** | 2 / 2 895. Breaks the reward join, outcome attribution, and the A/B gate | **Now.** One-line fix, largest payoff |
| **Near-duplicate detection** | 916 prompts out of an Obsidian vault will contain variants of the same prompt. Chunking multiplies them, and duplicates crowd the top-10 with the same content. Cosine > 0.95 between chunks of different parents, surfaced for review | **Now**, before re-embedding |
| **Re-index / embedding-version strategy** | `embedding_version` exists and nothing reads it. Changing the embedding model silently mixes vector spaces — searches return garbage with no error. Refuse to search when a chunk's version ≠ the configured model | Now (as a guard); later for online migration |
| **Slot review UI** | Extraction is heuristic + LLM. 344 slot instances need a human pass once. A `cap slots review` CLI over `prompt_slots.verified` costs an afternoon and produces the training set for `ExtractSlots` | Now — it's also tier-2 training data |
| **Cost / latency budget** | Reranker daemon is resident; embedding server is a separate process; fill may make LLM calls. Nobody has written down the target for end-to-end `find()` | Later — measure first |

---

## 7. Build order

**Phase 0 — instrument (½ day).** Fix `episode_id` propagation. Add
`serving_outcome`. Ship before anything else changes, so the rework's own
traffic is captured from day one. *Done when:* a `find()` call produces a
`serving_log` row with a non-null `episode_id` that joins to
`arteries.rewards`.

**Phase 1 — eval harness (1 day).** Rewrite `search/eval.py` into a
ground-truth harness: `(query, expected_prompt_id[])` fixtures, recall@k, MRR,
nDCG. Hand-label ~50 queries from the existing 155. *Done when:* current `dev`
retrieval has a baseline number. Everything after this is measured against it,
and without it nothing after this is measurable.

**Phase 2 — chunking (2 days).** `prompt_chunks` table, chunker, chunk
embedding, chunk-level retrieval + rollup. Raise `MAX_DOC_CHARS`. *Done when:*
recall@10 beats the Phase-1 baseline, and the 276 truncated prompts are fully
indexed.

**Phase 3 — retrieval rework (1 day).** Three channels, `simple` config exact
tsv, AND semantics, 0.85/0.15 weights in config. *Done when:* a query
containing `snake_case_identifier` retrieves the prompt containing it — the
case that fails today — with no regression on the Phase-1 prose queries.

**Phase 4 — slots and base info (2–3 days).** `prompt_slots`, `base_info`,
ingest-time extraction, the fill algorithm, validation, `cap slots review`.
*Done when:* the QBR worked example in §3 runs end to end and produces exactly
two needs.

**Phase 5 — DSPy modules (2 days).** `ExtractSlots` compiled with
`BootstrapFewShot` on the reviewed slots. `WriteQuery` compiled against the
Phase-1 eval set. Rewrite `metrics.py` — programmatic first, pairwise judge
last. Delete `harvest.py`. *Done when:* a compiled `ExtractSlots` beats the
uncompiled baseline on held-out folds and the delta survives cross-validation.

**Phase 6 — dedup + hygiene.** Near-duplicate report, embedding-version guard.

Phases 0–1 before 2–4 is the ordering that matters. Building chunking first
would feel faster and leave you unable to tell whether it worked.

---

## 8. Open questions

Each has a default, so none of this blocks.

1. **Does `base_info` sync from `arteries.evergreen`, or is it independently
   maintained?** *Default:* one-way sync from arteries, with manual rows
   allowed at `scope='global'`. Avoids a second place to type your company
   name.
2. **Slot review — CLI or generated Markdown for editing in Obsidian?**
   *Default:* CLI. It writes straight to Postgres; a Markdown round-trip needs
   a parser you'd then have to maintain.
3. **Does `chunk_text` get its heading breadcrumb stored, or prepended only at
   embed time?** *Default:* prepend at embed time, store clean. Keeps
   `chunk_text` byte-identical to a `prompt_text` slice, which makes offset
   validation trivial.
4. **Is the 41 881-char prompt one prompt or several?** *Default:* chunk it
   mechanically and flag it. It probably wants splitting in the vault, but
   that's your editorial call.
5. **Do you want per-prompt DSPy optimization kept for the top-20 by traffic,
   or dropped entirely for now?** *Default:* keep the code path, don't run it
   until §5's tier 4 is reached.
