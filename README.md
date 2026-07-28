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

- **Hybrid retrieval, not cosine-only.** Dense (pgvector HNSW) and sparse (pg_trgm trigram BM25) run in parallel, merge via Reciprocal Rank Fusion, then a cross-encoder reranks the survivors. Lexical matches and semantic matches both survive; neither path alone decides.
- **A gate, not just a ranker.** Retrieval can return nothing. The top rerank score has to clear a threshold before a prompt comes back, so an agent asking about something your corpus doesn't cover gets silence instead of the nearest irrelevant match.
- **Skills as first-class citizens.** A multi-step procedure with its own routing description competes against single prompts and wins when it fits better, then executes step by step with inline content — no runtime dependency on the prompts table.
- **Per-model prompt variants.** A DSPy integration tailors a prompt to the model that will run it; `resolve_prompt_text()` picks the model-specific variant before the base text.
- **It ages the corpus.** Unused prompts and skills auto-inactivate, cascade checks warn when something still references them, and stale content gets flagged for quarterly review. The library curates itself instead of growing forever.
- **Four ways in, one engine.** MCP tools, an HTTP API, a Python function, and a CLI all resolve to the same `find()` — bring whatever client you already have.

## How it works

```
query: "build a cash flow model for a SaaS startup"
                  |
          [hybrid retrieval]
          pgvector HNSW (dense) + pg_trgm BM25 (sparse)
                  |
          [RRF fusion]
          50 candidates from each path, merged
                  |
          [cross-encoder reranking]
          mxbai-rerank-base-v2 scores each (query, prompt) pair
                  |
          [skill recall]
          checks skills.skills for a validated procedure match
                  |
          returns: prompt text or skill procedure
```

Dense embeddings come from snowflake-arctic-embed-m-v2.0 (768 dimensions), served through any OpenAI-compatible endpoint. Sparse search uses PostgreSQL's pg_trgm trigram similarity. The two retrieval paths merge via Reciprocal Rank Fusion before the cross-encoder makes the final call.

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
  search/          retriever, reranker, RRF fusion, eval harness
  agent/           routing, step execution, feedback, gate, inference
  skills/          skill creation (promote), matching (recall), CLI
  db/              schema definitions, embedding generation
  lifecycle/       auto-inactivation, cascade checks, quarterly review
  optimize/        DSPy integration for per-model prompt variants
  config/          paths, DB config, environment variables
  find.py          top-level retrieval API
  server.py        FastAPI HTTP service
  mcp_server.py    MCP tool definitions
  cli.py           command-line interface

obsidian_sync/     bidirectional sync with an Obsidian vault
scripts/           setup, model download, service management
hooks/             arteries memory system integration
```

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

PYTHONPATH=src python scripts/setup_db.py --all
```

Or run `./scripts/setup.sh` for an interactive walkthrough. Full details in [docs/quick_start_guide.md](docs/quick_start_guide.md).

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

**Hybrid retrieval.** Two searches run independently against the prompts table. The dense path encodes the query with snowflake-arctic-embed and finds the 50 nearest neighbors via pgvector's HNSW index (cosine distance). The sparse path runs a pg_trgm trigram similarity query. Both respect optional filters on domain, intent, task type, complexity, and status.

**Fusion.** Results from both paths merge using Reciprocal Rank Fusion (k=50, equal weight). One ranked list comes out.

**Reranking.** The cross-encoder (mxbai-rerank-base-v2) scores each (query, candidate) pair and re-sorts. The top result's score determines the response: above the threshold, the prompt is returned directly. Below it, skill recall checks for a validated skill instead.

## Skills

Skills live in a `skills` schema in the same PostgreSQL database. Each has a routing description (one line that tells the system when to use it), a procedure (the full text of what to do), and optional steps for multi-step execution.

A step carries its own inline content. It may reference a prompt via `prompt_id` for provenance, but it does not depend on the prompts table at runtime.

```bash
python -m capillaries.skills.cli --create
python -m capillaries.skills.cli --list
python -m capillaries.skills.cli --show gtm-strategy-builder
python -m capillaries.skills.cli --edit gtm-strategy-builder
```

## Prompt optimization

A DSPy integration generates per-model prompt variants. When a prompt works well with one model but poorly with another, the optimizer produces a tailored variant stored in `prompt_variants`. At retrieval time, `resolve_prompt_text()` checks for a model-specific variant before falling back to the base text.

The optimizer is grounded in real outcomes, not a proxy metric. A serving log records what got served for each query alongside the top-k candidates the ranker considered but passed over — the negatives the optimizer needs to learn ranking, not just "was the served prompt any good." `harvest.py` joins that log against the reward signal (episode-reward-weighted first, then explicit skill/classification feedback, with an LLM judge only as a fallback for prompts that have no real traffic yet) and turns it into golden examples for DSPy. A fence guard keeps an optimized variant from shipping unless it clears the base text on held-out examples, and new variants roll out behind an A/B gate rather than replacing the base outright. Optimization events tee to heart's event spine, so a variant's win or regression is visible in the same `pulse` view as everything else in the stack.

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
| `EMBED_MODEL` | `snowflake-arctic-embed-m-v2.0` | Embedding model |
| `OBSIDIAN_VAULT_PATH` | unset | Obsidian vault root |
| `ARTERIES_ROOT` | unset | Arteries memory project (optional) |

Full reference in [docs/quick_start_guide.md](docs/quick_start_guide.md).
