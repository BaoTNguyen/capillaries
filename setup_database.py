#!/usr/bin/env python3
"""
Database setup for Prompt Flow system
Includes schema creation, data ingestion, and batch classification preparation
"""

import os
import json
import psycopg2
import frontmatter
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import hashlib

# Path configuration
OBSIDIAN_VAULT_PATH = Path("/c/Users/baotn/Obsidian Vaults/Main Vault")
PROMPTS_PATH = OBSIDIAN_VAULT_PATH / "Areas/AI/Prompts"
BASE_DB_PATH = OBSIDIAN_VAULT_PATH / "Bases/Prompt Database.base"

# Database connection settings
DB_CONFIG = {
    'host': 'localhost',
    'database': 'prompt_flow',
    'user': 'bao',  # adjust to your username
    'password': '',  # set if needed
}

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

        -- Core classification fields (your taxonomies)
        intent VARCHAR[] DEFAULT '{}',  -- Multiple values allowed
        task_type VARCHAR[] DEFAULT '{}',  -- Multiple values allowed
        domain VARCHAR[] DEFAULT '{}',  -- Multiple values allowed
        status VARCHAR DEFAULT 'active' CHECK (status IN ('active', 'deferred', 'archived')),

        -- Workflow fields
        primary_stage VARCHAR CHECK (primary_stage IN ('clarify', 'plan', 'execute', 'verify', 'reflect')),
        secondary_stages VARCHAR[] DEFAULT '{}',
        complexity_level INTEGER CHECK (complexity_level BETWEEN 1 AND 5),

        -- Chain compatibility flags (populated by batch classification)
        accepts_prior_output BOOLEAN DEFAULT FALSE,
        has_template_vars BOOLEAN DEFAULT FALSE,
        is_chain_prompt BOOLEAN DEFAULT FALSE,

        -- Retained for display/reference; not used in chain construction
        input_schema TEXT,
        output_schema TEXT,
        context_variables VARCHAR[] DEFAULT '{}',
        accomplishes TEXT,

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

        -- Vector search
        embedding_version VARCHAR,
        embedding VECTOR(1536),  -- OpenAI Ada-002 dimension

        -- Full-text search
        search_vector TSVECTOR GENERATED ALWAYS AS (
            to_tsvector('english',
                prompt_text || ' ' ||
                COALESCE(array_to_string(intent, ' '), '') || ' ' ||
                COALESCE(array_to_string(task_type, ' '), '') || ' ' ||
                COALESCE(array_to_string(domain, ' '), '')
            )
        ) STORED
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

    # Create indexes for performance
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_prompts_intent ON prompts USING GIN (intent);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_task_type ON prompts USING GIN (task_type);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_domain ON prompts USING GIN (domain);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_stage ON prompts (primary_stage);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_complexity ON prompts (complexity_level);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_status ON prompts (status);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_search ON prompts USING GIN (search_vector);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_embedding ON prompts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_confidence ON prompts USING GIN (metadata_confidence);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_backfill ON prompts (backfill_status);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_accepts_prior ON prompts (accepts_prior_output);",
        "CREATE INDEX IF NOT EXISTS idx_prompts_is_chain ON prompts (is_chain_prompt);",
    ]

    for index_sql in indexes:
        cursor.execute(index_sql)

def generate_content_hash(content: str) -> str:
    """Generate hash for content change detection"""
    return hashlib.sha256(content.encode()).hexdigest()[:16]

def parse_frontmatter_to_canonical(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Convert frontmatter to canonical schema"""
    canonical = {}

    # Map inconsistent field names to canonical ones
    field_mappings = {
        'Original Link': 'original_link',
        'Intent': 'intent',
        'Task Type': 'task_type',
        'Category': 'domain',  # Map Category to domain
        'status': 'status',
        'Status': 'status',
        'Models Tested': 'models_tested',
        'Parent Prompt': 'parent_prompt',
        'Last Evaluated': 'last_evaluated',
        'notes': 'notes',
        'Notes': 'notes'
    }

    for original_key, canonical_key in field_mappings.items():
        if original_key in metadata:
            value = metadata[original_key]

            # Handle array fields
            if canonical_key in ['intent', 'task_type', 'domain', 'models_tested', 'context_variables', 'secondary_stages']:
                if isinstance(value, str):
                    # Split string values into arrays
                    canonical[canonical_key] = [v.strip() for v in value.split(',') if v.strip()]
                elif isinstance(value, list):
                    canonical[canonical_key] = value
                else:
                    canonical[canonical_key] = [str(value)] if value else []
            else:
                canonical[canonical_key] = value

    return canonical

def load_prompts_from_obsidian(prompts_path: Path) -> List[Dict[str, Any]]:
    """Load and parse all prompt files from Obsidian vault"""
    prompts = []

    if not prompts_path.exists():
        print(f"Error: Prompts path does not exist: {prompts_path}")
        return prompts

    print(f"Loading prompts from: {prompts_path}")

    # Find all markdown files, excluding Clippings
    for md_file in prompts_path.rglob("*.md"):
        if "Clippings" in str(md_file):
            continue

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)

            # Generate prompt ID from filename
            prompt_id = md_file.stem

            # Parse metadata to canonical format
            canonical_metadata = parse_frontmatter_to_canonical(post.metadata)

            prompt_data = {
                'prompt_id': prompt_id,
                'file_path': str(md_file),
                'prompt_text': post.content,
                'content_hash': generate_content_hash(post.content),
                'file_mtime': datetime.fromtimestamp(md_file.stat().st_mtime),
                **canonical_metadata
            }

            prompts.append(prompt_data)

        except Exception as e:
            print(f"Error processing {md_file}: {e}")
            continue

    print(f"Loaded {len(prompts)} prompts (excluding Clippings)")
    return prompts

def insert_prompts_batch(cursor, prompts: List[Dict[str, Any]]):
    """Insert prompts into database with batch processing"""

    insert_sql = """
    INSERT INTO prompts (
        prompt_id, file_path, prompt_text, content_hash, file_mtime,
        intent, task_type, domain, status,
        parent_prompt, original_link, models_tested, notes, last_evaluated,
        backfill_status, last_updated
    ) VALUES (
        %(prompt_id)s, %(file_path)s, %(prompt_text)s, %(content_hash)s, %(file_mtime)s,
        %(intent)s, %(task_type)s, %(domain)s, %(status)s,
        %(parent_prompt)s, %(original_link)s, %(models_tested)s, %(notes)s, %(last_evaluated)s,
        'pending', CURRENT_TIMESTAMP
    ) ON CONFLICT (prompt_id) DO UPDATE SET
        prompt_text = EXCLUDED.prompt_text,
        content_hash = EXCLUDED.content_hash,
        file_mtime = EXCLUDED.file_mtime,
        last_updated = CURRENT_TIMESTAMP,
        backfill_status = CASE
            WHEN prompts.content_hash != EXCLUDED.content_hash THEN 'pending'
            ELSE prompts.backfill_status
        END
    """

    # Prepare data for batch insert
    batch_data = []
    for prompt in prompts:
        data = {
            'prompt_id': prompt['prompt_id'],
            'file_path': prompt['file_path'],
            'prompt_text': prompt['prompt_text'],
            'content_hash': prompt['content_hash'],
            'file_mtime': prompt['file_mtime'],
            'intent': prompt.get('intent', []),
            'task_type': prompt.get('task_type', []),
            'domain': prompt.get('domain', []),
            'status': prompt.get('status', 'active'),
            'parent_prompt': prompt.get('parent_prompt'),
            'original_link': prompt.get('original_link'),
            'models_tested': prompt.get('models_tested', []),
            'notes': prompt.get('notes'),
            'last_evaluated': prompt.get('last_evaluated')
        }
        batch_data.append(data)

    # Execute batch insert
    cursor.executemany(insert_sql, batch_data)
    print(f"Inserted/updated {len(batch_data)} prompts")

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
    """Main setup function"""
    print("Setting up Prompt Flow database...")

    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("Creating database schema...")
        create_database_schema(cursor)
        conn.commit()

        print("Loading prompts from Obsidian vault...")
        prompts = load_prompts_from_obsidian(PROMPTS_PATH)

        if not prompts:
            print("No prompts found. Please check the path configuration.")
            return

        print("Inserting prompts into database...")
        insert_prompts_batch(cursor, prompts)
        conn.commit()

        print("Analyzing metadata confidence...")
        mark_low_confidence_prompts(cursor)
        conn.commit()

        print("Database setup complete!")
        print(f"Ready for batch LLM classification of prompts marked 'pending'")

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