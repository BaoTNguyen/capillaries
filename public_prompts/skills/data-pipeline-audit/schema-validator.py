"""
Schema Validator
================

Reads a schema definition dictionary and validates consistency across
tables/collections. Checks for type mismatches, missing columns referenced
in joins or foreign keys, orphan references, and naming convention violations.

Inputs:
    schema_definition: dict where keys are table names and values are dicts
    containing 'columns' (list of column defs) and optional 'foreign_keys'.

    Each column def: {"name": str, "type": str, "nullable": bool}
    Each foreign key: {"column": str, "references_table": str, "references_column": str}

Outputs:
    - List of validation errors (blocking issues)
    - List of warnings (non-blocking but suspicious)
    - Summary statistics

Dependencies: Python 3.8+ standard library only

Example schema:
    {
        "users": {
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "email", "type": "varchar", "nullable": False},
                {"name": "created_at", "type": "timestamp", "nullable": False}
            ],
            "foreign_keys": []
        },
        "orders": {
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "user_id", "type": "integer", "nullable": False},
                {"name": "total", "type": "decimal", "nullable": False}
            ],
            "foreign_keys": [
                {"column": "user_id", "references_table": "users",
                 "references_column": "id"}
            ]
        }
    }
"""

import re
import json
from typing import Dict, List, Tuple, Any

VALID_TYPES = {
    "integer", "bigint", "smallint", "serial", "bigserial",
    "varchar", "text", "char",
    "boolean",
    "decimal", "numeric", "float", "double", "real",
    "date", "timestamp", "timestamptz", "time",
    "json", "jsonb",
    "uuid",
    "bytea",
    "array",
}

NAMING_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


def validate_schema(schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a schema definition and return errors, warnings, and stats."""
    errors: List[str] = []
    warnings: List[str] = []
    stats = {
        "total_tables": len(schema),
        "total_columns": 0,
        "total_foreign_keys": 0,
        "tables_without_primary_key_hint": [],
        "nullable_percentage": 0.0,
    }

    all_tables = set(schema.keys())
    all_columns_by_table: Dict[str, Dict[str, str]] = {}
    nullable_count = 0
    total_columns = 0

    # Pass 1: Validate table and column definitions
    for table_name, table_def in schema.items():
        if not NAMING_PATTERN.match(table_name):
            warnings.append(
                f"Table '{table_name}' does not follow snake_case naming convention"
            )

        columns = table_def.get("columns", [])
        if not columns:
            errors.append(f"Table '{table_name}' has no columns defined")
            continue

        col_map: Dict[str, str] = {}
        col_names_seen: set = set()

        has_id_column = False
        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "").lower()
            nullable = col.get("nullable", True)

            if not col_name:
                errors.append(f"Table '{table_name}' has a column with no name")
                continue

            if col_name in col_names_seen:
                errors.append(
                    f"Table '{table_name}' has duplicate column '{col_name}'"
                )
            col_names_seen.add(col_name)

            if not NAMING_PATTERN.match(col_name):
                warnings.append(
                    f"Column '{table_name}.{col_name}' does not follow "
                    f"snake_case naming convention"
                )

            if col_type not in VALID_TYPES:
                warnings.append(
                    f"Column '{table_name}.{col_name}' has uncommon type "
                    f"'{col_type}' -- verify this is intentional"
                )

            if col_name == "id" or col_name == f"{table_name}_id":
                has_id_column = True

            col_map[col_name] = col_type
            total_columns += 1
            if nullable:
                nullable_count += 1

        if not has_id_column:
            stats["tables_without_primary_key_hint"].append(table_name)
            warnings.append(
                f"Table '{table_name}' has no 'id' or '{table_name}_id' column "
                f"-- may be missing a primary key"
            )

        all_columns_by_table[table_name] = col_map

    # Pass 2: Validate foreign keys
    for table_name, table_def in schema.items():
        foreign_keys = table_def.get("foreign_keys", [])

        for fk in foreign_keys:
            stats["total_foreign_keys"] += 1
            fk_col = fk.get("column", "")
            ref_table = fk.get("references_table", "")
            ref_col = fk.get("references_column", "")

            # Check source column exists
            if table_name in all_columns_by_table:
                if fk_col not in all_columns_by_table[table_name]:
                    errors.append(
                        f"Foreign key in '{table_name}' references local column "
                        f"'{fk_col}' which does not exist"
                    )

            # Check target table exists
            if ref_table not in all_tables:
                errors.append(
                    f"Foreign key '{table_name}.{fk_col}' references table "
                    f"'{ref_table}' which does not exist in schema (orphan reference)"
                )
                continue

            # Check target column exists
            if ref_table in all_columns_by_table:
                if ref_col not in all_columns_by_table[ref_table]:
                    errors.append(
                        f"Foreign key '{table_name}.{fk_col}' references "
                        f"'{ref_table}.{ref_col}' which does not exist"
                    )
                else:
                    # Check type compatibility
                    source_type = all_columns_by_table.get(table_name, {}).get(fk_col)
                    target_type = all_columns_by_table[ref_table][ref_col]
                    if source_type and source_type != target_type:
                        errors.append(
                            f"Type mismatch: '{table_name}.{fk_col}' ({source_type}) "
                            f"references '{ref_table}.{ref_col}' ({target_type})"
                        )

    stats["total_columns"] = total_columns
    stats["nullable_percentage"] = round(
        (nullable_count / total_columns * 100) if total_columns > 0 else 0, 1
    )

    return {
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
        "is_valid": len(errors) == 0,
    }


def format_report(result: Dict[str, Any]) -> str:
    """Format validation results as a human-readable report."""
    lines = ["=" * 60, "SCHEMA VALIDATION REPORT", "=" * 60, ""]
    stats = result["stats"]
    lines.append(f"Tables: {stats['total_tables']}  |  "
                 f"Columns: {stats['total_columns']}  |  "
                 f"Foreign Keys: {stats['total_foreign_keys']}")
    lines.append(f"Nullable columns: {stats['nullable_percentage']}%")
    lines.append("")

    if result["errors"]:
        lines.append(f"ERRORS ({len(result['errors'])})")
        lines.append("-" * 40)
        for e in result["errors"]:
            lines.append(f"  [ERROR] {e}")
        lines.append("")

    if result["warnings"]:
        lines.append(f"WARNINGS ({len(result['warnings'])})")
        lines.append("-" * 40)
        for w in result["warnings"]:
            lines.append(f"  [WARN]  {w}")
        lines.append("")

    status = "PASSED" if result["is_valid"] else "FAILED"
    lines.append(f"Overall: {status}")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    # Example: validate a sample e-commerce schema
    sample_schema = {
        "users": {
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "email", "type": "varchar", "nullable": False},
                {"name": "name", "type": "varchar", "nullable": True},
                {"name": "created_at", "type": "timestamp", "nullable": False},
            ],
            "foreign_keys": [],
        },
        "orders": {
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "user_id", "type": "integer", "nullable": False},
                {"name": "total", "type": "decimal", "nullable": False},
                {"name": "status", "type": "varchar", "nullable": False},
                {"name": "created_at", "type": "timestamp", "nullable": False},
            ],
            "foreign_keys": [
                {"column": "user_id", "references_table": "users",
                 "references_column": "id"},
            ],
        },
        "order_items": {
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "order_id", "type": "integer", "nullable": False},
                {"name": "product_id", "type": "varchar", "nullable": False},
                {"name": "quantity", "type": "integer", "nullable": False},
                {"name": "price", "type": "decimal", "nullable": False},
            ],
            "foreign_keys": [
                {"column": "order_id", "references_table": "orders",
                 "references_column": "id"},
                {"column": "product_id", "references_table": "products",
                 "references_column": "id"},
            ],
        },
    }

    result = validate_schema(sample_schema)
    print(format_report(result))
