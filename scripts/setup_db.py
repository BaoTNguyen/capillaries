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
    create_skills_indexes(cur)
    conn.commit()

    print("Analyzing metadata confidence...")
    mark_low_confidence_prompts(cur)
    conn.commit()

    cur.close()
    conn.close()
    print("Schemas ready.")


async def run_embed() -> None:
    from capillaries.db.embed import run
    await run()


async def run_classify() -> None:
    from capillaries.classify.batch import BatchClassifier
    classifier = BatchClassifier(db_config=DB_CONFIG)
    stats = await classifier.process_all_prompts()
    print(f"\nClassification results: {stats}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up the capillaries database (schemas, embeddings, classification)."
    )
    parser.add_argument("--embed", action="store_true", help="Generate embeddings for prompts missing them")
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
