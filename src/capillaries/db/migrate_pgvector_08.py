#!/usr/bin/env python3
"""Migrate Capillaries embeddings to pgvector 0.8 ``halfvec`` storage.

The embedding width remains ``capillaries.config.EMBED_DIM``.  Existing,
non-null embeddings are converted in place, so this migration will not resize
an incompatible column: changing dimensions would make the old vectors
meaningless and cannot preserve their values.

Usage:
    python -m capillaries.db.migrate_pgvector_08          # report only
    python -m capillaries.db.migrate_pgvector_08 --apply  # make changes

Rollback (do this while pgvector 0.8 is still installed):

    1. Drop ``idx_prompts_embedding_active``,
       ``idx_chunks_embedding_active``, and
       ``idx_skills_routing_embedding_active``.
    2. ALTER each halfvec(EMBED_DIM) column back to vector(EMBED_DIM) using
       ``USING column::vector``.
    3. Recreate each index with ``vector_cosine_ops``, m=16,
       ef_construction=64, and ``WHERE status = 'active'``.
    4. Only then, if the server package offers the desired version, run
       ``ALTER EXTENSION vector UPDATE TO '<older-version>'``.

Do not downgrade the extension before converting the columns: older pgvector
versions do not know the halfvec type.
"""

from __future__ import annotations

import argparse

import psycopg2
from psycopg2 import sql

from capillaries.config import DB_CONFIG, EMBED_DIM


# (schema, table, embedding column, canonical partial HNSW index name)
TARGETS = (
    ("public", "prompts", "embedding", "idx_prompts_embedding_active"),
    ("public", "prompt_chunks", "embedding", "idx_chunks_embedding_active"),
    ("skills", "skills", "routing_embedding", "idx_skills_routing_embedding_active"),
)

_COLUMN_SQL = """
SELECT t.typname, a.atttypmod,
       EXISTS (
           SELECT 1 FROM pg_attribute status_col
           WHERE status_col.attrelid = c.oid
             AND status_col.attname = 'status'
             AND NOT status_col.attisdropped
       ) AS has_status
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
JOIN pg_type t ON t.oid = a.atttypid
WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s
  AND NOT a.attisdropped
"""

_INDEX_SQL = """
SELECT am.amname, op.opcname, ic.reloptions,
       pg_get_expr(i.indpred, i.indrelid) AS predicate
FROM pg_class ic
JOIN pg_namespace ns ON ns.oid = ic.relnamespace
JOIN pg_index i ON i.indexrelid = ic.oid
JOIN pg_am am ON am.oid = ic.relam
JOIN pg_opclass op ON op.oid = i.indclass[0]
WHERE ns.nspname = %s AND ic.relname = %s
"""


def _table_name(schema: str, table: str) -> str:
    return table if schema == "public" else f"{schema}.{table}"


def _index_is_current(cur, schema: str, index: str) -> bool:
    cur.execute(_INDEX_SQL, (schema, index))
    row = cur.fetchone()
    if row is None:
        return False
    access_method, opclass, options, predicate = row
    normal_predicate = " ".join((predicate or "").split())
    return (
        access_method == "hnsw"
        and opclass == "halfvec_cosine_ops"
        and {"m=16", "ef_construction=64"}.issubset(set(options or ()))
        and "status" in normal_predicate
        and "'active'" in normal_predicate
    )


def _vector_indexes(cur, schema: str, table: str, column: str) -> list[str]:
    """Every index on this column, from the catalog rather than a hand list.

    ALTER COLUMN ... TYPE halfvec rebuilds every index on the column and
    vector_cosine_ops refuses halfvec, so one unknown survivor aborts the whole
    conversion -- which is exactly what the legacy non-partial
    idx_prompts_embedding did.
    """
    cur.execute("""
        SELECT i.relname FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (x.indkey)
        WHERE n.nspname = %s AND t.relname = %s AND a.attname = %s
    """, (schema, table, column))
    return [r[0] for r in cur.fetchall()]


def _drop_index(cur, schema: str, index: str) -> None:
    cur.execute(sql.SQL("DROP INDEX IF EXISTS {}.{}").format(
        sql.Identifier(schema), sql.Identifier(index)
    ))


def _create_index(cur, schema: str, table: str, column: str, index: str) -> None:
    cur.execute(sql.SQL(
        "CREATE INDEX {} ON {}.{} USING hnsw ({} halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64) WHERE status = 'active'"
    ).format(
        sql.Identifier(index), sql.Identifier(schema), sql.Identifier(table),
        sql.Identifier(column),
    ))


def _convert_column(cur, schema: str, table: str, column: str) -> None:
    cur.execute(sql.SQL(
        "ALTER TABLE {}.{} ALTER COLUMN {} TYPE halfvec({}) USING {}::halfvec"
    ).format(
        sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column),
        sql.Literal(EMBED_DIM), sql.Identifier(column),
    ))


class MigrationBlocked(RuntimeError):
    """A precondition this migration must not satisfy itself. An operator has to
    do one privileged thing first; the exact command travels with the error."""


def _extension_report(cur) -> dict:
    cur.execute("""
        SELECT e.extversion, a.default_version
        FROM pg_extension e
        JOIN pg_available_extensions a ON a.name = e.extname
        WHERE e.extname = 'vector'
    """)
    row = cur.fetchone()
    if row is None:
        return {"table": "vector extension", "status": "create_and_update"}
    installed, available = row
    return {
        "table": "vector extension",
        "status": "ok" if installed == available else "update",
        "from": installed,
        "to": available,
    }


def migrate(apply: bool = False, db_config: dict | None = None) -> list[dict]:
    """Report or apply the resumable pgvector 0.8 halfvec migration.

    Each table is committed separately after its column conversion and index
    rebuild.  Consequently a later failure can be safely retried: completed
    targets are detected from the PostgreSQL catalog and left alone.
    """
    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    report: list[dict] = []
    try:
        with conn.cursor() as cur:
            extension = _extension_report(cur)
            report.append(extension)
            target_states = []
            for schema, table, column, index in TARGETS:
                label = _table_name(schema, table)
                cur.execute(_COLUMN_SQL, (schema, table, column))
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",))
                    status = "missing_column" if cur.fetchone()[0] else "missing_table"
                    report.append({"table": label, "column": column, "status": status})
                    continue

                type_name, dimension, has_status = row
                if type_name not in {"vector", "halfvec"}:
                    report.append({
                        "table": label, "column": column, "status": "unsupported_type",
                        "type": type_name,
                    })
                    continue
                if dimension != EMBED_DIM:
                    report.append({
                        "table": label, "column": column, "status": "incompatible_dim",
                        "type": type_name, "from": dimension, "to": EMBED_DIM,
                    })
                    continue
                if not has_status:
                    report.append({
                        "table": label, "column": column, "status": "missing_status"})
                    continue

                index_current = _index_is_current(cur, schema, index)
                if type_name == "halfvec" and index_current:
                    report.append({"table": label, "column": column, "status": "ok", "dim": dimension})
                    continue
                action = "convert_and_rebuild" if type_name == "vector" else "rebuild_index"
                item = {
                    "table": label, "column": column, "status": action,
                    "from": type_name, "to": "halfvec", "dim": dimension,
                }
                report.append(item)
                target_states.append((schema, table, column, index, type_name, item))

        if not apply:
            return report

        # halfvec is introduced by pgvector 0.7.  Finish this boundary before
        # any statement mentions the type, and before conversion can begin.
        # CREATE/ALTER EXTENSION need superuser or extension ownership, which
        # the application role has by design. Check the boundary, never cross it.
        if extension["status"] != "ok":
            raise MigrationBlocked(
                f"pgvector {extension.get('to', '0.7+')} is required for halfvec; "
                f"this database has {extension.get('from', 'no vector extension')}.\n"
                f"An operator must run this once, then re-run the migration:\n"
                f'  sudo -u postgres psql -d {DB_CONFIG["database"]} '
                f'-c "CREATE EXTENSION IF NOT EXISTS vector; ALTER EXTENSION vector UPDATE;"'
            )

        for schema, table, column, index, type_name, item in target_states:
            try:
                with conn.cursor() as cur:
                    for stale in _vector_indexes(cur, schema, table, column):
                        _drop_index(cur, schema, stale)
                    if type_name != "halfvec":
                        _convert_column(cur, schema, table, column)
                    _create_index(cur, schema, table, column, index)
                conn.commit()
                item["status"] = (
                    "converted_and_rebuilt" if type_name == "vector" else "rebuilt_index"
                )
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true", help="perform the migration")
    args = parser.parse_args()

    try:
        report = migrate(apply=args.apply)
    except MigrationBlocked as blocked:
        raise SystemExit(f"blocked: {blocked}") from None

    for item in report:
        details = " ".join(
            f"{key}={value}" for key, value in item.items() if key not in {"table", "status"}
        )
        print(f"{item['table']}: {item['status']}" + (f" ({details})" if details else ""))
    if not args.apply:
        print("Dry run. Re-run with --apply to make these changes.")


if __name__ == "__main__":
    main()
