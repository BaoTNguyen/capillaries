# PostgreSQL Setup for Prompt Flow

## Installation

### Ubuntu/Debian
```bash
# Install PostgreSQL and pgvector 0.8+
sudo apt update
sudo apt install postgresql postgresql-contrib postgresql-14-pgvector

# Confirm the installed package provides pgvector 0.8 or later.
# Package names and repository versions vary by PostgreSQL release.

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Create Database and User
```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE capillaries;
CREATE USER "your-db-user" WITH PASSWORD 'your_password';  -- Change password as needed
GRANT ALL PRIVILEGES ON DATABASE capillaries TO "your-db-user";
ALTER USER "your-db-user" CREATEDB;  -- Allow creating test databases

# Exit psql
\q
```

### Enable pgvector Extension
```bash
# Connect to your database
psql -d capillaries -U your-db-user

# Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

# Exit
\q
```

## Configuration

### Update Database Config in setup_database.py
```python
DB_CONFIG = {
    'host': 'localhost',
    'database': 'capillaries',
    'user': 'your-db-user',  # Your username
    'password': 'your_password',  # Set if you used a password
}
```

### Environment Variables (Optional)
Create `.env` file:
```
DATABASE_URL=postgresql://your-db-user:your_password@localhost/capillaries
ANTHROPIC_API_KEY=your_anthropic_key  # For batch classification
OPENAI_API_KEY=your_openai_key  # For embeddings
```

## Verification

### Test Connection
```bash
psql -d capillaries -U your-db-user -c "SELECT version();"
```

### Test pgvector
```bash
psql -d capillaries -U your-db-user -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
psql -d capillaries -U your-db-user -c "SELECT '[1,2,3]'::halfvec;"
```

## Embedding Migration and Verification

Capillaries keeps the existing embedding width at `EMBED_DIM` (1024 by
default). pgvector 0.8 stores `prompts.embedding`, `prompt_chunks.embedding`,
and `skills.skills.routing_embedding` as `halfvec(EMBED_DIM)`. Their partial
HNSW indexes are `idx_prompts_embedding_active`,
`idx_chunks_embedding_active`, and `idx_skills_routing_embedding_active`, with
`halfvec_cosine_ops`, `m=16`, `ef_construction=64`, and `WHERE status =
'active'`.

For a database created with the older vector schema, take a `pg_dump` and run
the migration's report-only preflight:

```bash
pg_dump -Fc capillaries > capillaries-before-halfvec.dump
PYTHONPATH=src python -m capillaries.db.migrate_pgvector_08
PYTHONPATH=src python -m capillaries.db.migrate_pgvector_08 --apply
```

The migration updates the `vector` extension before it uses `halfvec`, checks
the configured dimension, preserves non-null values, and can be run again
after an interrupted attempt. Verify the result with:

```bash
psql -d capillaries -U your-db-user -c "SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod) AS declared_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE (n.nspname, c.relname, a.attname) IN (('public','prompts','embedding'),('public','prompt_chunks','embedding'),('skills','skills','routing_embedding')) AND NOT a.attisdropped;"
psql -d capillaries -U your-db-user -c "SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN ('idx_prompts_embedding_active','idx_chunks_embedding_active','idx_skills_routing_embedding_active');"
psql -d capillaries -U your-db-user -c "SELECT (SELECT count(*) FROM prompts WHERE embedding IS NOT NULL), (SELECT count(*) FROM prompt_chunks WHERE embedding IS NOT NULL), (SELECT count(*) FROM skills.skills WHERE routing_embedding IS NOT NULL);"
```

Filtered HNSW query paths use `SET LOCAL hnsw.iterative_scan =
'relaxed_order'` immediately before the ordered query, while retaining their
existing `hnsw.ef_search` setting. This prevents a partial HNSW scan from
under-returning when early nearest neighbors fail the `status = 'active'`
filter.

### Rollback

Keep pgvector 0.8 installed until rollback is complete. After a fresh backup,
use a maintenance window and run this sequence, replacing `EMBED_DIM` with
the configured integer:

```sql
DROP INDEX IF EXISTS idx_prompts_embedding_active;
DROP INDEX IF EXISTS idx_chunks_embedding_active;
DROP INDEX IF EXISTS skills.idx_skills_routing_embedding_active;
ALTER TABLE prompts ALTER COLUMN embedding TYPE vector(EMBED_DIM)
  USING embedding::vector;
ALTER TABLE prompt_chunks ALTER COLUMN embedding TYPE vector(EMBED_DIM)
  USING embedding::vector;
ALTER TABLE skills.skills ALTER COLUMN routing_embedding TYPE vector(EMBED_DIM)
  USING routing_embedding::vector;
CREATE INDEX idx_prompts_embedding_active ON prompts USING hnsw
  (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
  WHERE status = 'active';
CREATE INDEX idx_chunks_embedding_active ON prompt_chunks USING hnsw
  (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
  WHERE status = 'active';
CREATE INDEX idx_skills_routing_embedding_active ON skills.skills USING hnsw
  (routing_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
  WHERE status = 'active';
```

`EMBED_DIM` is a Python configuration name, not a PostgreSQL variable. Only
after all columns and indexes use `vector` may you optionally run `ALTER
EXTENSION vector UPDATE TO '<older-version>'`, and only if the server package
supports it. Do not downgrade first: older pgvector versions cannot read
`halfvec`. ALTER TABLE and index rebuilds can lock tables and create heavy I/O,
so plan for contention or downtime and retain the backup through verification.

## Next Steps

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run database setup:**
   ```bash
   python setup_database.py
   ```

3. **Verify data loading:**
   ```bash
   psql -d capillaries -U your-db-user -c "SELECT COUNT(*) FROM prompts;"
   ```

The setup script will:
- Create all necessary tables and indexes
- Load your prompts from `/home/bao/Documents/Obsidian/Main-Vault/Areas/AI/Prompts`
- Mark low-confidence prompts for batch classification
- Generate statistics on metadata coverage
