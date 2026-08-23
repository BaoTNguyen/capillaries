#!/usr/bin/env python3
"""
Prompts table schema creation and metadata analysis.

This module only defines the database schema. Data ingestion from
the Obsidian vault is a separate concern in the obsidian_sync package.
"""

import json
import psycopg2
from typing import List, Dict, Any

from capillaries.config.paths import DB_CONFIG, EMBED_DIM

def create_database_schema(cursor):
    """Create the complete database schema"""

    # Enable pgvector extension
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")  # For fuzzy text search

    # Main prompts table
    create_prompts_table = """
    CREATE TABLE IF NOT EXISTS prompts (
        prompt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title VARCHAR NOT NULL UNIQUE,
        tag VARCHAR UNIQUE,  -- stable slug derived from title, same convention as skills.skills.tag
        file_path TEXT NOT NULL,
        prompt_text TEXT NOT NULL,

        -- Core classification fields (taxonomy values are always lowercase)
        intent VARCHAR[] DEFAULT '{}',
        task_type VARCHAR[] DEFAULT '{}',
        domain VARCHAR[] DEFAULT '{}',
        status VARCHAR DEFAULT 'active' CHECK (status IN ('draft', 'active', 'inactive')),

        -- Original metadata
        original_link TEXT,
        notes TEXT,

        -- System fields
        content_hash VARCHAR NOT NULL,
        file_mtime TIMESTAMP,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_evaluated DATE,

        -- Classification metadata
        metadata_confidence JSONB DEFAULT '{}',
        classification_version VARCHAR DEFAULT 'v1',
        last_classified TIMESTAMP,
        backfill_status VARCHAR DEFAULT 'pending' CHECK (backfill_status IN ('pending', 'processing', 'complete', 'needs_review', 'failed')),

        -- Data source
        source VARCHAR DEFAULT 'private',

        -- Vector search. Width is config-driven — see EMBED_DIM below.
        embedding_version VARCHAR,
        embedding VECTOR(EMBED_DIM),

        -- Full-text search (A-weighted title + body with acronym expansion).
        -- Written by the ingest paths, not generated: expand_acronyms() runs in
        -- Python and a generated column cannot call it.
        search_tsv TSVECTOR,

        -- Literal-token search for the exact channel (search/channels.py).
        -- GENERATED, unlike search_tsv, for two reasons. The exact channel must
        -- NOT expand or stem — 'serve.py' has to survive as one token, which is
        -- the whole point of the channel — so there is nothing for Python to do.
        -- And a derived column no ingest path can forget is the only kind that
        -- stays correct: search_tsv is written inline by each writer, one of
        -- them forgot, and 68 prompts sat invisible to lexical search.
        exact_tsv TSVECTOR GENERATED ALWAYS AS (
            to_tsvector('simple'::regconfig,
                        coalesce(title, '') || ' ' || coalesce(prompt_text, ''))
        ) STORED,

        -- Output modality
        modality VARCHAR DEFAULT 'text'
    );
    """
    # Substituted rather than f-string-interpolated: the DDL above uses `'{}'`
    # array defaults, which an f-string would try to read as fields.
    cursor.execute(create_prompts_table.replace("VECTOR(EMBED_DIM)", f"VECTOR({EMBED_DIM})"))
    cursor.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS summary TEXT;")
    cursor.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS tag VARCHAR;")
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE prompts ADD CONSTRAINT prompts_tag_key UNIQUE (tag);
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $$;
    """)
    cursor.execute("ALTER TABLE prompts DROP COLUMN IF EXISTS complexity_level;")

    # CREATE TABLE IF NOT EXISTS skips an existing table entirely, so a database
    # built before exact_tsv existed never gets the column and search/channels.py
    # raises UndefinedColumn against it. Generated columns cannot be added with
    # IF NOT EXISTS in one statement, hence the guard.
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE prompts ADD COLUMN exact_tsv TSVECTOR
                GENERATED ALWAYS AS (
                    to_tsvector('simple'::regconfig,
                                coalesce(title, '') || ' ' || coalesce(prompt_text, ''))
                ) STORED;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prompt_variants (
        variant_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        prompt_id           UUID NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
        model               VARCHAR NOT NULL,
        prompt_text         TEXT NOT NULL,
        content_hash        VARCHAR NOT NULL,
        optimizer           VARCHAR NOT NULL,
        optimization_run_id UUID,
        metric_score        FLOAT,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_current          BOOLEAN DEFAULT TRUE,
        UNIQUE (prompt_id, model, content_hash)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS golden_examples (
        example_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        prompt_id       UUID NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
        input_text      TEXT NOT NULL,
        output_text     TEXT NOT NULL,
        context_text    TEXT,
        source          VARCHAR NOT NULL CHECK (source IN ('memory_project', 'external', 'contrastive', 'manual')),
        model           VARCHAR,
        conversation_id VARCHAR,
        is_negative     BOOLEAN DEFAULT FALSE,
        pair_id         UUID,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS optimization_runs (
        run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        prompt_id       UUID NOT NULL REFERENCES prompts(prompt_id),
        model           VARCHAR NOT NULL,
        optimizer       VARCHAR NOT NULL,
        num_examples    INTEGER NOT NULL,
        metric_type     VARCHAR NOT NULL,
        baseline_score  FLOAT,
        optimized_score FLOAT,
        improvement     FLOAT GENERATED ALWAYS AS (optimized_score - baseline_score) STORED,
        started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at    TIMESTAMP,
        status          VARCHAR DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'no_improvement')),
        error_message   TEXT,
        dspy_config     JSONB DEFAULT '{}'
    );
    """)

    # Classification feedback for continuous learning
    create_feedback_table = """
    CREATE TABLE IF NOT EXISTS classification_feedback (
        id SERIAL PRIMARY KEY,
        title VARCHAR REFERENCES prompts(title),
        field_name VARCHAR NOT NULL,
        old_value TEXT,
        new_value TEXT,
        feedback_type VARCHAR CHECK (feedback_type IN ('correction', 'validation', 'enhancement', 'user_feedback')),
        confidence FLOAT,
        source VARCHAR DEFAULT 'manual',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_feedback_table)

    # Batch processing tracking
    create_batch_log_table = """
    CREATE TABLE IF NOT EXISTS batch_processing_log (
        id SERIAL PRIMARY KEY,
        batch_id VARCHAR NOT NULL,
        title VARCHAR REFERENCES prompts(title),
        processing_stage VARCHAR NOT NULL,
        status VARCHAR CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
        error_message TEXT,
        processing_time_ms INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    );
    """
    cursor.execute(create_batch_log_table)

    cursor.execute("""
    CREATE SCHEMA IF NOT EXISTS skills;
    """)

    # Create indexes for performance
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_prompts_intent ON prompts USING GIN (intent);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_task_type ON prompts USING GIN (task_type);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_domain ON prompts USING GIN (domain);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_status ON prompts (status);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_search_tsv ON prompts USING GIN (search_tsv);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_exact_tsv ON prompts USING GIN (exact_tsv);",
        # Partial, on purpose. Retrieval only ever asks for active prompts, and
        # a full index makes the planner walk inactive rows and discard them
        # after the fact — measured at 25% active, a LIMIT 50 came back with 22.
        # Restricting the graph to what can actually be returned fixes that and
        # is faster besides. Postgres maintains membership on every UPDATE, so
        # inactivating and reactivating take effect immediately; no rebuild.
        "CREATE INDEX IF NOT EXISTS idx_prompts_embedding_active ON prompts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64) WHERE status = 'active';",
        "CREATE INDEX IF NOT EXISTS idx_prompts_confidence ON prompts USING GIN (metadata_confidence);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_backfill ON prompts (backfill_status);",
        "CREATE INDEX IF NOT EXISTS idx_variants_prompt_model ON prompt_variants (prompt_id, model) WHERE is_current = TRUE;",
        "CREATE INDEX IF NOT EXISTS idx_golden_prompt ON golden_examples (prompt_id);",
        "CREATE INDEX IF NOT EXISTS idx_golden_source ON golden_examples (source);",
        "CREATE INDEX IF NOT EXISTS idx_opt_runs_prompt ON optimization_runs (prompt_id, started_at DESC);",
    ]

    for index_sql in indexes:
        cursor.execute(index_sql)

def mark_low_confidence_prompts(cursor):
    """Identify and mark prompts that will need special attention during classification"""

    # Mark prompts with missing critical metadata as low confidence
    update_sql = """
    UPDATE prompts SET
        metadata_confidence = jsonb_build_object(
            'has_intent', CASE WHEN array_length(intent, 1) > 0 THEN true ELSE false END,
            'has_task_type', CASE WHEN array_length(task_type, 1) > 0 THEN true ELSE false END,
            'has_domain', CASE WHEN array_length(domain, 1) > 0 THEN true ELSE false END,
            'has_original_link', CASE WHEN original_link IS NOT NULL THEN true ELSE false END,
            'text_length', LENGTH(prompt_text),
            'estimated_confidence', CASE
                WHEN array_length(intent, 1) > 0 AND array_length(task_type, 1) > 0 AND array_length(domain, 1) > 0 THEN 0.8
                WHEN array_length(intent, 1) > 0 OR array_length(task_type, 1) > 0 OR array_length(domain, 1) > 0 THEN 0.4
                ELSE 0.1
            END,
            'needs_classification', CASE
                WHEN array_length(intent, 1) IS NULL OR array_length(task_type, 1) IS NULL OR array_length(domain, 1) IS NULL THEN true
                ELSE false
            END
        )
    WHERE backfill_status = 'pending'
    """

    cursor.execute(update_sql)

    # Get statistics
    stats_sql = """
    SELECT
        COUNT(*) as total_prompts,
        COUNT(*) FILTER (WHERE (metadata_confidence->>'needs_classification')::boolean = true) as needs_classification,
        COUNT(*) FILTER (WHERE (metadata_confidence->>'estimated_confidence')::float < 0.5) as low_confidence,
        COUNT(*) FILTER (WHERE array_length(intent, 1) IS NOT NULL) as has_intent,
        COUNT(*) FILTER (WHERE array_length(task_type, 1) IS NOT NULL) as has_task_type,
        COUNT(*) FILTER (WHERE array_length(domain, 1) IS NOT NULL) as has_domain,
        COUNT(*) FILTER (WHERE original_link IS NOT NULL) as has_original_link
    FROM prompts
    """

    cursor.execute(stats_sql)
    stats = cursor.fetchone()

    total = stats[0]
    print("Database Statistics:")
    print(f"Total prompts: {total}")

    # An empty prompts table is the normal state on a fresh install — this
    # function runs from setup_db.py before anything has been ingested. Dividing
    # for a percentage here used to raise ZeroDivisionError and take schema
    # creation down with it, so a first-time setup failed at the last step.
    if not total:
        print("(no prompts yet — run scripts/ingest_public.py, then setup_db.py --embed)")
        return

    for label, value in (
        ("Need classification", stats[1]),
        ("Low confidence",      stats[2]),
        ("Have intent",         stats[3]),
        ("Have task_type",      stats[4]),
        ("Have domain",         stats[5]),
        ("Have original_link",  stats[6]),
    ):
        print(f"{label}: {value} ({value / total * 100:.1f}%)")

def main():
    """Create prompts schema and analyze metadata confidence."""
    print("Setting up Capillaries database...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("Creating database schema...")
        create_database_schema(cursor)
        conn.commit()

        print("Analyzing metadata confidence...")
        mark_low_confidence_prompts(cursor)
        conn.commit()

        print("Prompts schema ready.")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
