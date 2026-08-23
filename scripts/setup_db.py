#!/usr/bin/env python3
"""
Set up the capillaries database: create schemas, optionally embed and classify.

This script only touches the database. Obsidian sync (ingest, frontmatter
writeback) is a separate concern — run those explicitly:
    python -m obsidian_sync.ingest
    python -m obsidian_sync.frontmatter

Usage:
    python scripts/setup_db.py                 # create schemas only
    python scripts/setup_db.py --embed         # also generate embeddings
    python scripts/setup_db.py --classify      # also run batch classification
    python scripts/setup_db.py --all           # schemas + embed + classify
"""

import argparse
import asyncio
import sys

import psycopg2

from capillaries.config.paths import DB_CONFIG
from capillaries.db.setup import create_database_schema, mark_low_confidence_prompts
from capillaries.db.setup_skills import (
    create_skills_schema,
    create_skills_table,
    create_skill_runs_table,
    create_skill_variants_table,
    create_skill_sessions_table,
    create_agent_feedback_table,
    create_materialized_views,
    add_missing_columns as add_skills_columns,
    create_indexes as create_skills_indexes,
)


def setup_schemas() -> None:
    """Create prompts and skills schemas (idempotent)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("Creating prompts schema...")
    create_database_schema(cur)
    conn.commit()

    print("Creating skills schema...")
    create_skills_schema(cur)
    create_skills_table(cur)
    create_skill_runs_table(cur)
    create_skill_variants_table(cur)
    # These were defined in setup_skills.py but never called here, so a
    # database built by this script had neither. agent/route.py could not
    # open a skill session, and lifecycle/inactivate.py reads
    # skills.agent_feedback to decide what is stale -- auto-inactivation has
    # never had a table to read.
    create_skill_sessions_table(cur)
    create_agent_feedback_table(cur)
    add_skills_columns(cur)
    create_skills_indexes(cur)
    create_materialized_views(cur)
    conn.commit()

    print("Analyzing metadata confidence...")
    mark_low_confidence_prompts(cur)
    conn.commit()

    cur.close()
    conn.close()
    print("Schemas ready.")


async def run_embed() -> None:
    # Both, deliberately. This used to call run() alone, so every documented
    # setup path embedded 1026 prompts and zero skills — and skill recall's
    # semantic channel (WHERE routing_embedding IS NOT NULL) silently matched
    # nothing for as long as that was true.
    from capillaries.db.embed import run, run_skills
    await run()
    await run_skills()


async def run_classify() -> None:
    from capillaries.classify.batch import BatchClassifier
    classifier = BatchClassifier(db_config=DB_CONFIG)
    stats = await classifier.process_all_prompts()
    print(f"\nClassification results: {stats}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up the capillaries database (schemas, embeddings, classification)."
    )
    parser.add_argument("--embed", action="store_true", help="Generate embeddings for prompts and skills missing them")
    parser.add_argument("--classify", action="store_true", help="Run batch LLM classification on pending prompts")
    parser.add_argument("--all", action="store_true", help="Schemas + embed + classify")
    args = parser.parse_args()

    setup_schemas()

    if args.all or args.embed:
        print("\nGenerating embeddings...")
        await run_embed()

    if args.all or args.classify:
        print("\nRunning batch classification...")
        await run_classify()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
