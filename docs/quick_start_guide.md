# Quick Start Guide

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector) extension installed

## Automated Setup

The interactive setup script walks you through everything — database, environment, models, schema, and seed data:

```bash
./scripts/setup.sh
```

If you prefer to do each step manually, follow the sections below.

## Manual Setup

### 1. Clone and install

```bash
git clone <repo-url> capillaries
cd capillaries

# Pick an install tier:
pip install -e .                    # core only (no local ML models)
pip install -e ".[lightweight]"     # + local embeddings, reranker, spaCy
pip install -e ".[advanced]"        # + FAISS, clustering, full ML stack
```

### 2. Create the database

```bash
createdb capillaries

psql -d capillaries -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -d capillaries -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

If you need to create a database user or use password auth, see the
`PostgreSQL` section in `.env.example`.

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` to set any non-default values. Most Linux users with local
PostgreSQL can leave everything commented out — the defaults work.

### 4. Download models

```bash
# Full — snowflake-arctic-embed + mxbai-rerank + all-MiniLM + spaCy (~2 GB)
python scripts/download_models.py --profile full

# Lite — snowflake-arctic-embed + spaCy (~700 MB)
python scripts/download_models.py --profile lite

# External — skip local models, use a remote embedding API
python scripts/download_models.py --profile external
```

### 5. Set up the database schema

```bash
PYTHONPATH=src python scripts/setup_db.py
```

To also generate embeddings and run batch classification:

```bash
PYTHONPATH=src python scripts/setup_db.py --all
```

### 6. Load demo content (optional)

Ingest the bundled public prompts and skills so you have something to
search immediately:

```bash
PYTHONPATH=src python scripts/ingest_public.py --db-only
```

### 7. Start the service

```bash
./scripts/start.sh
```

### 8. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","ready":true}
```

## Configuration Reference

| Variable              | Default                                       | Description                                       |
|-----------------------|-----------------------------------------------|---------------------------------------------------|
| `PROMPTS_PATH`        | `~/.capillaries/prompts/`                     | Directory containing prompt `.md` files            |
| `SKILLS_PATH`         | `~/.capillaries/skills/`                      | Directory containing skill `.md` files             |
| `OBSIDIAN_VAULT_PATH` | *(unset)*                                     | Obsidian vault root (optional, for vault sync)     |
| `DB_HOST`             | `/var/run/postgresql`                         | PostgreSQL host or Unix socket path                |
| `DB_PORT`             | `5432`                                        | PostgreSQL port                                    |
| `DB_NAME`             | `capillaries`                                 | Database name                                      |
| `DB_USER`             | *(empty — peer auth)*                         | Database user                                      |
| `DB_PASSWORD`         | *(empty)*                                     | Database password                                  |
| `EMBED_URL`           | `http://127.0.0.1:8003/v1/embeddings`        | Embedding server endpoint                          |
| `EMBED_MODEL`         | `snowflake-arctic-embed-m-v2.0`               | Model name sent to the embedding endpoint          |
| `RERANKER_DEVICE`     | `cpu`                                         | Device for the cross-encoder reranker (`cpu`/`cuda`)|
| `ANTHROPIC_API_KEY`   | *(unset)*                                     | For LLM classification and agent features          |
| `OPENAI_API_KEY`      | *(unset)*                                     | For OpenAI-based features                          |

If both `PROMPTS_PATH` and `OBSIDIAN_VAULT_PATH` are set, `PROMPTS_PATH`
takes precedence. If neither is set, the default `~/.capillaries/prompts/`
is used (same logic for `SKILLS_PATH`).

## Using External Embedding APIs

Any OpenAI-compatible `/v1/embeddings` endpoint works as a drop-in
replacement for the local embedding server. Set `EMBED_URL` and
`EMBED_MODEL` in your `.env`:

```bash
# Example: OpenAI
EMBED_URL=https://api.openai.com/v1/embeddings
EMBED_MODEL=text-embedding-3-small
```

The database schema stores embeddings as `VECTOR(768)`. If your external
model produces a different dimension, you will need to adjust the column
definition in `src/capillaries/db/setup.py` before running schema setup.

## Obsidian Integration (Optional)

If you use Obsidian to manage prompts, install the optional extra:

```bash
pip install -e ".[obsidian]"
```

Set `OBSIDIAN_VAULT_PATH` in `.env` to your vault root. Then use the
sync commands:

```bash
# Ingest prompts from vault into the database
PYTHONPATH=. python -m obsidian_sync.ingest

# Write classifications back to vault frontmatter
PYTHONPATH=. python -m obsidian_sync.frontmatter
```

The `obsidian_sync` package is entirely optional — the core system works
without it.
