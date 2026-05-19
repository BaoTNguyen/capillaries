#!/usr/bin/env python3
"""
Prompts table schema creation and metadata analysis.

This module only defines the database schema. Data ingestion from
the Obsidian vault is a separate concern in the obsidian_sync package.
"""

import json
import psycopg2
from typing import List, Dict, Any

from prompt_flow.config.paths import PROMPTS_PATH, DB_CONFIG

def create_database_schema(cursor):
    """Create the complete database schema"""

    # Enable pgvector extension
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")  # For fuzzy text search

    # Main prompts table
    create_prompts_table = """
    CREATE TABLE IF NOT EXISTS prompts (
        prompt_id VARCHAR PRIMARY KEY,
        file_path TEXT NOT NULL,
        prompt_text TEXT NOT NULL,

        -- Core classification fields (taxonomy values are always lowercase)
        intent VARCHAR[] DEFAULT '{}',
        task_type VARCHAR[] DEFAULT '{}',
        domain VARCHAR[] DEFAULT '{}',
        status VARCHAR DEFAULT 'active' CHECK (status IN ('active', 'deferred', 'archived')),

        -- Workflow fields
        primary_stage VARCHAR CHECK (primary_stage IN ('clarify', 'plan', 'execute', 'verify', 'reflect')),
        complexity_level INTEGER CHECK (complexity_level BETWEEN 1 AND 5),

        -- Prompt I/O description (Obsidian: Expected Input / Expected Output)
        expected_input TEXT,
        expected_output TEXT,

        -- Relationship fields
        parent_prompt VARCHAR REFERENCES prompts(prompt_id),

        -- Original metadata
        original_link TEXT,
        models_tested VARCHAR[] DEFAULT '{}',
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

        -- Vector search (nomic-embed-text via Ollama, 768 dimensions)
        embedding_version VARCHAR,
        embedding VECTOR(768),

        -- Full-text search (populated on insert/update via application code)
        search_vector TSVECTOR
    );
    """
    cursor.execute(create_prompts_table)

    # Classification feedback for continuous learning
    create_feedback_table = """
    CREATE TABLE IF NOT EXISTS classification_feedback (
        id SERIAL PRIMARY KEY,
        prompt_id VARCHAR REFERENCES prompts(prompt_id),
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
        prompt_id VARCHAR REFERENCES prompts(prompt_id),
        processing_stage VARCHAR NOT NULL,
        status VARCHAR CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
        error_message TEXT,
        processing_time_ms INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    );
    """
    cursor.execute(create_batch_log_table)

    # Skill files table for non-prompt files in skills (code, config, templates)
    cursor.execute("""
    CREATE SCHEMA IF NOT EXISTS skills;
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS skills.skill_files (
        id SERIAL PRIMARY KEY,
        skill_id UUID REFERENCES skills.skills(skill_id) ON DELETE CASCADE,
        file_path VARCHAR NOT NULL,
        file_type VARCHAR NOT NULL CHECK (file_type IN ('code', 'config', 'template')),
        language VARCHAR,
        description TEXT,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(skill_id, file_path)
    );
    """)

    # Create indexes for performance
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_prompts_intent ON prompts USING GIN (intent);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_task_type ON prompts USING GIN (task_type);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_domain ON prompts USING GIN (domain);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_stage ON prompts (primary_stage);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_complexity ON prompts (complexity_level);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_status ON prompts (status);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_search ON prompts USING GIN (search_vector);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_embedding ON prompts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_confidence ON prompts USING GIN (metadata_confidence);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_backfill ON prompts (backfill_status);",
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

    print("Database Statistics:")
    print(f"Total prompts: {stats[0]}")
    print(f"Need classification: {stats[1]} ({stats[1]/stats[0]*100:.1f}%)")
    print(f"Low confidence: {stats[2]} ({stats[2]/stats[0]*100:.1f}%)")
    print(f"Have intent: {stats[3]} ({stats[3]/stats[0]*100:.1f}%)")
    print(f"Have task_type: {stats[4]} ({stats[4]/stats[0]*100:.1f}%)")
    print(f"Have domain: {stats[5]} ({stats[5]/stats[0]*100:.1f}%)")
    print(f"Have original_link: {stats[6]} ({stats[6]/stats[0]*100:.1f}%)")

def main():
    """Create prompts schema and analyze metadata confidence."""
    print("Setting up Prompt Flow database...")

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