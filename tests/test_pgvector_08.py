"""Offline regression checks for the pgvector 0.8 halfvec contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from capillaries.config import EMBED_DIM
from capillaries.db import migrate_pgvector_08 as migration


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text().lower()


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


class _Cursor:
    def __init__(self) -> None:
        self.description = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=None) -> None:
        sql = str(statement).lower()
        if "select t.typname" in sql:
            self._row = ("halfvec", EMBED_DIM, True)
        elif "from pg_class ic" in sql:
            self._row = ("hnsw", "halfvec_cosine_ops", ("m=16", "ef_construction=64"),
                         "(status = 'active'::character varying)")
        elif "from pg_extension e" in sql:
            self._row = ("0.8.0", "0.8.0")
        else:
            self._row = None

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def cursor(self):
        return _Cursor()

    def close(self) -> None:
        self.closed = True


class MigrationTests(unittest.TestCase):
    def test_targets_are_canonical_and_dry_run_recognizes_completed_migration(self):
        self.assertEqual(
            migration.TARGETS,
            (
                ("public", "prompts", "embedding", "idx_prompts_embedding_active"),
                ("public", "prompt_chunks", "embedding", "idx_chunks_embedding_active"),
                ("skills", "skills", "routing_embedding", "idx_skills_routing_embedding_active"),
            ),
        )
        connection = _Connection()
        with patch.object(migration.psycopg2, "connect", return_value=connection):
            report = migration.migrate(db_config={})

        self.assertTrue(connection.closed)
        self.assertEqual(report[0]["status"], "ok")
        self.assertEqual([item["status"] for item in report[1:]], ["ok", "ok", "ok"])
        self.assertTrue(all(item.get("dim") == EMBED_DIM for item in report[1:]))

    def test_migration_source_updates_extension_before_halfvec_and_has_rollback(self):
        source = _compact(_source("src/capillaries/db/migrate_pgvector_08.py"))
        self.assertIn("def migrate(apply: bool = false, db_config: dict | none = none) -> list[dict]", source)
        self.assertIn('parser.add_argument("--apply"', source)
        self.assertIn("alter extension vector update", source)
        self.assertIn("using {}::halfvec", source)
        self.assertLess(source.index("alter extension vector update"), source.index("_convert_column(cur"))
        self.assertIn("using column::vector", source)
        self.assertIn("vector_cosine_ops", source)
        self.assertLess(source.index("using column::vector"), source.index("alter extension vector update to"))
        self.assertIn("if type_name == \"halfvec\" and index_current", source)


class StorageContractTests(unittest.TestCase):
    def test_schema_and_writers_keep_configured_halfvec_contract(self):
        sources = {
            "fresh prompt schema": _source("src/capillaries/db/setup.py"),
            "chunk schema": _source("src/capillaries/chunk.py"),
            "skills schema": _source("src/capillaries/db/setup_skills.py"),
            "embedding writers": _source("src/capillaries/db/embed.py"),
            "optimizer writer": _source("src/capillaries/optimize/dspy_optimize.py"),
            "dimension migration": _source("src/capillaries/db/migrate_embed_dim.py"),
        }
        for name in ("fresh prompt schema", "chunk schema", "skills schema",
                     "embedding writers", "dimension migration"):
            source = sources[name]
            with self.subTest(name=name):
                self.assertIn("embed_dim", source)
                self.assertNotRegex(source, r"halfvec\(1024\)")

        self.assertIn("embedding halfvec(embed_dim)", _compact(sources["fresh prompt schema"]))
        self.assertIn("embedding halfvec(embed_dim)", _compact(sources["chunk schema"]))
        self.assertIn("routing_embedding halfvec(embed_dim)", _compact(sources["skills schema"]))
        for source in (sources["fresh prompt schema"], sources["chunk schema"],
                       sources["skills schema"], sources["embedding writers"]):
            self.assertIn("halfvec_cosine_ops", source)
            self.assertRegex(_compact(source), r"m\s*=\s*16.*ef_construction\s*=\s*64")

        self.assertIn("embedding = %s::halfvec", sources["embedding writers"])
        self.assertIn("routing_embedding = %s::halfvec", sources["embedding writers"])
        self.assertIn("embedding = %s::halfvec", sources["optimizer writer"])
        self.assertIn("add column {column} halfvec({embed_dim})", sources["dimension migration"])

    def test_dense_paths_use_relaxed_order_and_halfvec_casts(self):
        paths = {
            "prompt retrieval": ("src/capillaries/search/retriever.py", True),
            "chunk retrieval": ("src/capillaries/search/channels.py", True),
            "skill retrieval": ("src/capillaries/skills/recall.py", True),
            "gate similarity lookup": ("src/capillaries/agent/gate.py", False),
            "review similarity lookup": ("src/capillaries/lifecycle/review.py", False),
        }
        for name, (path, has_ef_search) in paths.items():
            source = _source(path)
            with self.subTest(name=name):
                self.assertIn("set local hnsw.iterative_scan = 'relaxed_order'", source)
                self.assertIn("order by", source)
                self.assertIn("<=>", source)
                scan_setting = source.index("set local hnsw.iterative_scan = 'relaxed_order'")
                # The statement immediately following the transaction-local
                # setting is the ordered vector query (some paths build that
                # SQL string before they set the transaction option).
                self.assertNotEqual(source.find("cur.execute(", scan_setting + 1), -1)
                if path.endswith("review.py"):
                    # Both operands are stored halfvec values in this lookup.
                    self.assertIn("select embedding from prompts", source)
                else:
                    self.assertIn("::halfvec", source)
                # ef_search must NOT be pinned any more: the iterative scan
                # replaced the `max(2 * n, 100)` guess, and keeping both means
                # every query pays the inflated first walk it was meant to
                # avoid. `has_ef_search` records where the old tuning lived.
                if has_ef_search:
                    self.assertNotIn("set local hnsw.ef_search", source)


if __name__ == "__main__":
    unittest.main()
