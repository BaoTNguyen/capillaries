# Capillaries

Semantic prompt retrieval for AI agents. You describe a situation, it returns the right prompt.

Capillaries sits between an agent and a library of ~1,000 prompts stored as markdown files. Instead of hard-coding prompt selection or asking the agent to figure out which prompt fits, the agent calls Capillaries with a natural language description of what it needs. A hybrid search runs, a cross-encoder reranks the candidates, and the best match comes back ready to use.

The system also handles skills, which are multi-step procedures with their own routing descriptions. When "quarterly business review" matches a validated skill better than any single prompt, the skill's procedure is returned instead.

## Where it sits in the stack

Capillaries is the retrieval layer under a five-repo agent stack. Each repo does one job and imports downward:

```text
capillaries  prompt/skill retrieval                <- this repo
arteries     memory + trace substrate
heart        orchestration + environment + reward
plexus       goal decomposition + acceptance loop
marrow       RL training on heart's episodes
```

Arteries wraps capillaries with per-project memory, heart runs coding agents through it, plexus drives goals, and marrow trains on the results. Capillaries owns nothing above the retrieval line. It answers one question, which prompt fits this situation, and leaves memory and orchestration to the repos above it.

## What sets it apart

Most "prompt library" projects are a folder of files and an embedding lookup. Capillaries is a real retrieval system:

- **Hybrid retrieval, not cosine-only.** Dense (pgvector HNSW) and lexical (PostgreSQL full-text) run in parallel, their candidates are unioned rather than weighted, and a cross-encoder orders the result. No fusion ratio to tune — measured on the golden set, every ratio was either indefensible or inside the noise. Lexical and semantic matches both survive; neither path alone decides.
- **A floor, not just a ranker.** Retrieval can return nothing. The top rerank score has to clear `MIN_CONFIDENCE` (0.3, `CAPILLARIES_MIN_CONFIDENCE`) before a prompt comes back, so an agent asking about something your corpus doesn't cover gets `mode="none"` instead of the nearest irrelevant match. A second, stricter gate on `/agent/route` also weighs query length and how specified the request already is — that one decides whether to search at all.
- **Skills as first-class citizens.** A multi-step procedure with its own routing description competes against single prompts and wins when it fits better, then executes step by step, resolving each step's prompt from the `prompts` table by UUID at run time.
- **Per-model prompt variants.** A DSPy integration tailors a prompt to the model that will run it; `resolve_prompt_text()` picks the model-specific variant before the base text.
- **It ages the corpus.** Unused prompts and skills auto-inactivate, cascade checks warn when something still references them, and stale content gets flagged for quarterly review. The library curates itself instead of growing forever.
- **Four ways in, one engine.** MCP tools, an HTTP API, a Python function, and a CLI all resolve to the same `find()` — bring whatever client you already have.

## How it works

```
query: "build a cash flow model for a SaaS startup"
                  |
          [hybrid retrieval]
          pgvector HNSW (dense) + PostgreSQL full-text (lexical)
                  |
          [union]
          both channels' candidates, deduped, no weighting
                  |
          [cross-encoder reranking]
          Qwen3-Reranker-0.6B scores each (query, prompt) pair
                  |
          [skill recall]
          checks skills.skills for a validated procedure match
                  |
          returns: prompt text or skill procedure
```

Dense embeddings come from Qwen3-Embedding-0.6B (1024 dimensions), served through any OpenAI-compatible endpoint. The lexical path uses PostgreSQL full-text search. The two paths are unioned, not weighted, before the cross-encoder makes the final call.

## Interfaces

**MCP server.** Agents running in Claude Code, Cursor, OpenCode, Hermes, or any MCP client get four tools: `capillaries_find` (describe a situation, get a prompt or skill), `capillaries_execute_step` (run the next step in a multi-step skill), `capillaries_feedback` (report whether the result worked), and `capillaries_catalog` (browse available domains and skills). MCP tools accept optional `agent_context` metadata from Arteries adapters.

**HTTP API.** FastAPI endpoints at `/agent/route`, `/agent/step`, `/agent/feedback`, `/agent/catalog`, plus `/search` for direct retrieval. `/agent/route` and `/agent/feedback` accept optional normalized `agent_context` metadata.

**Python library.**

```python
from capillaries import find

result = await find("debug auth middleware")
result.prompt_text   # the prompt, ready to use
result.confidence    # rerank score
result.mode          # 'single', 'skill', or 'none'

# Optional metadata from Arteries or another adapter is preserved, not used
# for CLI-specific branching inside Capillaries.
result = await find(
    "debug auth middleware",
    agent_context={"cli": "cursor", "agent_id": "career-ops-hook"},
)
```

**CLI.**

```bash
cap find "build a cash flow model"
```

## Project structure

```
src/capillaries/
  search/
    retriever.py     dense + broad lexical SQL against prompts
    channels.py      the two channels as standalone, inspectable searches
    union.py         union-then-rerank — the serving path
    reranker.py      cross-encoder scoring
    context_filter.py  memory-frame signals applied to candidates
    eval.py          retrieval eval harness
    bench_channels.py  channel-vs-channel benchmark
  agent/           routing, step execution, feedback, gate, inference
  skills/          skill creation (promote), matching (recall), coverage, CLI
  db/              schema definitions, embedding generation, dim migration
  lifecycle/       auto-inactivation, cascade checks, quarterly review
  optimize/        DSPy integration for per-model prompt variants
  config/          paths, DB config, environment variables
  chunk.py         prompt chunking + embedding backfill
  find.py          top-level retrieval API
  server.py        FastAPI HTTP service
  mcp_server.py    MCP tool definitions
  cli.py           command-line interface

obsidian_sync/     bidirectional sync with an Obsidian vault
scripts/           setup, teardown, ingest, model download, service management
eval/              labeled query sets for retrieval evaluation
hooks/             arteries memory system integration
```

`retriever.py` and `channels.py` both search, and that is deliberate. `channels.py` is the honest version of each channel in isolation, used for benchmarking; `union.py` serves from `retriever.py`'s broader lexical search because a first stage owes the reranker recall, not precision. The reasoning, with numbers, is in `union.py`'s docstring.

## Setup

Requires Python 3.10+ and PostgreSQL 14+ with pgvector.

```bash
git clone <repo-url> capillaries && cd capillaries

pip install -e .                    # core
pip install -e ".[lightweight]"     # + local embeddings, reranker
pip install -e ".[advanced]"        # + full ML stack

createdb capillaries
psql -d capillaries -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -d capillaries -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

cp .env.example .env               # edit as needed

PYTHONPATH=src python scripts/setup_db.py                  # schemas and indexes
PYTHONPATH=src python scripts/ingest_public.py --db-only   # load the corpus
PYTHONPATH=. python -m obsidian_sync.ingest                # + your vault, if any
PYTHONPATH=src python scripts/setup_db.py --embed          # then vectorize it
PYTHONPATH=src python -m capillaries.chunk --backfill      # and chunk it
```

Order matters, and two of these steps are easy to skip into a database that looks fine and retrieves nothing.

`ingest_public.py` writes rows and nothing derived — no embedding step — so embedding has to come after it. Run `--embed` against an empty table and you get prompts with null vectors: dense retrieval returns nothing, no error is raised.

The chunk backfill is the one people miss. Dense retrieval reads `prompt_chunks`, not `prompts` (`search/channels.py:vector_search`), so a corpus with perfectly good `prompts.embedding` values and an empty chunk table has no dense channel at all — lexical carries every query and nobody notices until recall is measured. Check both:

```bash
psql -d capillaries -c "SELECT count(*), count(embedding) FROM prompts;"
psql -d capillaries -c "SELECT count(*), count(embedding) FROM prompt_chunks;"
```

Each pair should match, and the chunk count should be several times the prompt count.

Or run `./scripts/setup.sh`, which does all of this in order and ends by running a live `find()` against what it built. Full details in [docs/quick_start_guide.md](docs/quick_start_guide.md).

### A note on arteries

The `MemoryFrame` contract — the shape arteries hands down when it wants retrieval to be memory-aware — is defined in `arteries.memory_types` and imported, never copied. Arteries produces those frames, so arteries owns their definition.

Capillaries imports and runs without arteries installed. Every reference to the contract is a type annotation, kept as a string by `from __future__ import annotations`, except at one place: `agent/api.py:_build_context_frame`, which constructs a frame from a posted JSON body and imports the types inside the function. Retrieval works standalone; the memory-aware path needs arteries and says so at the point of use rather than at import.

The dependency isn't declared in `pyproject.toml` because the name is unclaimed on PyPI, and declaring it would resolve to a stranger's package. Install the sibling checkout if you want the memory path:

```bash
pip install -e ../arteries
```

### Tearing it down

```bash
./scripts/teardown.sh --dry-run    # print the plan, change nothing
./scripts/teardown.sh              # confirm each step
./scripts/teardown.sh --force      # no prompts, for CI
./scripts/teardown.sh --models     # also drop the shared HuggingFace cache
```

Teardown reverses setup: it drops the database, deletes `.env`, removes the prompts and skills directories, uninstalls the editable package, and clears caches. It never touches tracked source or git history — this uninstalls the system, it does not delete the repo. Run `--dry-run` first; the plan it prints is exactly what the real run does.

Two guards exist because their absence cost a corpus. The database name is read from `.env` and never defaulted, so a second run after `.env` is gone refuses rather than dropping whatever is named `capillaries`. And every drop is preceded by a mandatory `pg_dump -Fc` into `~/.capillaries/backups/`; if the dump fails, the drop does not happen. `--no-backup` opts out and says plainly that it is unrecoverable.

## Running

```bash
# HTTP service
./scripts/start.sh
# or:
uvicorn capillaries.server:app --host 127.0.0.1 --port 8000

# MCP server
python -m capillaries.mcp_server
```

## Retrieval pipeline

Three stages.

**Hybrid retrieval.** Two searches run independently. The dense path encodes the query with Qwen3-Embedding and finds the nearest neighbors via pgvector's HNSW index over `prompt_chunks` (cosine distance). The lexical path runs a PostgreSQL full-text query. Both respect optional filters on domain, intent, task type, complexity, and status.

**Union.** Both candidate lists are concatenated and deduped by prompt ID. No weights, no ratio. This replaced Reciprocal Rank Fusion after the benchmark showed there was nothing to tune: on the clean population, 50/50 and 0.3/0.7 landed within half a point of each other, and RRF was already within 0.4 points of its own ceiling. Union recovers most of that with one fewer knob. See the header of `search/union.py` for the numbers, including where union does *not* help — recall@10 improved, recall@1 did not.

**Reranking.** The cross-encoder (Qwen3-Reranker-0.6B) scores each (query, candidate) pair and re-sorts. Its raw logits are sigmoid-normalized, which is what makes the gate threshold mean anything: the previous reranker put every top-1 score between 0.95 and 1.00, so no cutoff could separate a good match from a bad one. The top result's score determines the response: above the threshold, the prompt is returned directly. Below it, skill recall checks for a validated skill instead.

Because union improves rank 5–10 but not rank 1, and callers serve rank 1, the reranker is the next component that has to get better. Nothing downstream of it will show a gain until it does.

## Skills

Skills live in a `skills` schema in the same PostgreSQL database. Each has a routing description (one line that tells the system when to use it), a procedure (the full text of what to do), and optional steps for multi-step execution.

A step is a pointer, not a copy: `{prompt_id, rationale, step_order, pinned_hash}`. `execute_step` looks the text up in `prompts` by UUID, checking `prompt_variants` first when a model is named. That means editing a prompt changes every skill that uses it — which is the point, and also why `pinned_hash` records the text a step was validated against.

```bash
python -m capillaries.skills.cli --create
python -m capillaries.skills.cli --list
python -m capillaries.skills.cli --show gtm-strategy-builder
python -m capillaries.skills.cli --edit gtm-strategy-builder
```

## Prompt optimization

A DSPy integration generates per-model prompt variants. When a prompt works well with one model but poorly with another, the optimizer produces a tailored variant stored in `prompt_variants`. At retrieval time, `resolve_prompt_text()` checks for a model-specific variant before falling back to the base text.

The optimizer is meant to be grounded in real outcomes, not a proxy metric. A serving log records what got served for each query alongside the top-k candidates the ranker considered but passed over — the negatives needed to learn ranking, not just "was the served prompt any good." Each row carries the `episode_id` and `turn_id` its caller supplied via `agent_context`, which is what lets a serving be matched to the reward that followed it.

The piece that turned that log into training examples is currently missing. `optimize/harvest.py` was deleted rather than fixed: it captured the retrieved prompt as the golden *output*, which trains an optimizer to reproduce the library instead of ranking it. Golden examples now enter only through `cap optimize capture`.

Its replacement lives in marrow, not here, under `marrow/capillaries_opt/` — the label format spec, a pooled-judgment harness, and an HMAC membership oracle for the holdout. Marrow owns training for the whole stack, and a holdout it can enumerate is not a holdout. Labels key on prompt **title** rather than `prompt_id`, because `prompt_id` is `gen_random_uuid()` and does not survive a rebuild of the corpus.

What remains is the acceptance side, and it still holds: a fence guard keeps an optimized variant from shipping unless it clears the base text on held-out examples, and new variants roll out behind an A/B gate rather than replacing the base outright. Optimization events tee to heart's event spine, so a variant's win or regression is visible in the same `pulse` view as everything else in the stack.

## Obsidian sync

If prompts live in an Obsidian vault, `obsidian_sync` handles bidirectional sync:

```bash
PYTHONPATH=. python -m obsidian_sync.ingest              # vault -> DB
PYTHONPATH=. python -m obsidian_sync.frontmatter          # DB -> vault
PYTHONPATH=. python -m obsidian_sync.skills_vault export   # skills -> vault
PYTHONPATH=. python -m obsidian_sync.skills_vault import   # vault -> skills
```

Set `OBSIDIAN_VAULT_PATH` in `.env`. The sync layer is optional; the core system works without it.

## Lifecycle management

Prompts and skills that go unused get auto-inactivated. The lifecycle module tracks usage frequency via skill runs and feedback, runs cascade checks when a prompt is inactivated (warns if skills reference it), and flags stale content for quarterly review.

## Environment variables

| Variable | Default | What it does |
|----------|---------|--------------|
| `DB_HOST` | `/var/run/postgresql` | PostgreSQL host |
| `DB_NAME` | `capillaries` | Database name |
| `EMBED_URL` | `http://127.0.0.1:8003/v1/embeddings` | Embedding endpoint |
| `EMBED_MODEL` | `Qwen/Qwen3-Embedding-0.6B` | Embedding model |
| `EMBED_DIM` | `1024` | Vector width; must match the schema |
| `RERANKER_MODEL` | `Qwen/Qwen3-Reranker-0.6B` | Cross-encoder |
| `OBSIDIAN_VAULT_PATH` | unset | Obsidian vault root |
| `ARTERIES_ROOT` | unset | Arteries memory project (optional) |

Full reference in [docs/quick_start_guide.md](docs/quick_start_guide.md).
