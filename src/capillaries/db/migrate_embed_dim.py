#!/usr/bin/env python3
"""
Resize every vector column to config.EMBED_DIM and drop the old vectors.

Needed when the embedding model changes. pgvector cannot ALTER TYPE a vector
to a different width, so each column is dropped and re-added — which discards
the vectors, which is the point: vectors from a different model are not
comparable and must never be mixed into one index.

Run this, then re-embed:
    python3 -m capillaries.db.migrate_embed_dim
    python3 -m capillaries.db.embed --reembed
    python3 -m capillaries.chunk --backfill

Usage:
    python3 -m capillaries.db.migrate_embed_dim          # report, change nothing
    python3 -m capillaries.db.migrate_embed_dim --apply
"""

from __future__ import annotations

import argparse

import psycopg2

from capillaries.config import DB_CONFIG, EMBED_DIM, EMBED_MODEL

# (table, column, index name). The index is dropped with the column and rebuilt
# by the re-embed pass, which builds HNSW over populated rows — far faster than
# maintaining it insert-by-insert.
TARGETS = [
    ("prompts", "embedding", "idx_prompts_embedding"),
    ("prompt_chunks", "embedding", "idx_chunks_embedding"),
    ("skills.skills", "routing_embedding", "idx_skills_routing_embedding"),
]

CURRENT_DIM_SQL = """
SELECT a.atttypmod
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s AND NOT a.attisdropped
"""


def _split(table: str) -> tuple[str, str]:
    return tuple(table.split(".")) if "." in table else ("public", table)


def migrate(apply: bool = False, db_config: dict | None = None) -> list[dict]:
    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    report: list[dict] = []
    try:
        cur = conn.cursor()
        for table, column, index in TARGETS:
            schema, name = _split(table)
            cur.execute(CURRENT_DIM_SQL, (schema, name, column))
            row = cur.fetchone()
            if row is None:
                report.append({"table": table, "status": "missing"})
                continue

            current = row[0]  # pgvector stores the declared width in atttypmod
            if current == EMBED_DIM:
                report.append({"table": table, "status": "ok", "dim": current})
                continue

            report.append({"table": table, "status": "resize",
                           "from": current, "to": EMBED_DIM})
            if not apply:
                continue

            # One transaction per table: a half-migrated column is a column
            # whose width and contents disagree.
            cur.execute(f"DROP INDEX IF EXISTS {index};")
            cur.execute(f"ALTER TABLE {table} DROP COLUMN {column};")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} VECTOR({EMBED_DIM});")
            if table != "skills.skills":
                cur.execute(f"UPDATE {table} SET embedding_version = NULL;")
            conn.commit()
    finally:
        conn.close()
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="perform the migration; without it, only report")
    args = ap.parse_args()

    print(f"target model {EMBED_MODEL}  dim {EMBED_DIM}")
    for r in migrate(apply=args.apply):
        if r["status"] == "resize":
            verb = "resized" if args.apply else "would resize"
            print(f"  {r['table']:22} {verb} {r['from']} -> {r['to']}")
        else:
            print(f"  {r['table']:22} {r['status']}"
                  + (f" (dim {r['dim']})" if "dim" in r else ""))

    if not args.apply:
        print("\nDry run. Re-run with --apply, then:")
        print("  python3 -m capillaries.db.embed --reembed")
        print("  python3 -m capillaries.chunk --backfill")


if __name__ == "__main__":
    main()
