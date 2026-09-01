"""
Tests for M6 (STACK_READINESS §5): serving log + top-k, reward-grounded
serving log, fence protection, and the A/B promotion gate.

Run:
    PYTHONPATH=src python3 -m pytest tests/test_optimize_m6.py -v
    PYTHONPATH=src python3 -m unittest tests.test_optimize_m6 -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

import psycopg2

import importlib.util

import pytest

# ab_gate imports optimize.dspy_optimize, which imports dspy. It is not a
# declared dependency, so those three failed on every clean checkout and
# "the suite is green" stopped meaning anything. Scoped to the class that
# needs it -- FenceTests and ServingLogTests do not.
_needs_dspy = pytest.mark.skipif(
    importlib.util.find_spec("dspy") is None,
    reason="optimizer extra not installed (dspy)",
)

from capillaries.config.paths import DB_CONFIG
from capillaries.optimize.fences import assert_fences_unchanged, split_fences

# Every test here opens a Postgres connection, so it belongs behind the `db`
# marker CI deselects with `-m "not db"`. Without the mark these failed on
# every machine without a database, which is every machine but this one.
pytestmark = pytest.mark.db



def _db_reachable() -> bool:
    try:
        conn = psycopg2.connect(**DB_CONFIG, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


DB_UP = _db_reachable()


# ---------------------------------------------------------------------------
# Fence protection — no DB needed
# ---------------------------------------------------------------------------

class FenceTests(unittest.TestCase):
    def test_prose_only_edit_passes(self):
        before = "Some intro text.\n\n```python\nprint('hi')\n```\n\nOutro."
        after = "A much better intro, rewritten.\n\n```python\nprint('hi')\n```\n\nDifferent outro too."
        assert_fences_unchanged(before, after)  # should not raise

    def test_fence_edit_raises(self):
        before = "Intro.\n\n```python\nprint('hi')\n```\n\nOutro."
        after = "Intro.\n\n```python\nprint('bye')\n```\n\nOutro."
        with self.assertRaises(ValueError) as ctx:
            assert_fences_unchanged(before, after)
        self.assertIn("fence", str(ctx.exception))

    def test_frontmatter_protected(self):
        before = "---\ntitle: Foo\n---\nBody text one.\n"
        after = "---\ntitle: Bar\n---\nBody text one, reworded.\n"
        with self.assertRaises(ValueError):
            assert_fences_unchanged(before, after)

    def test_frontmatter_unchanged_prose_edit_passes(self):
        before = "---\ntitle: Foo\n---\nBody text one.\n"
        after = "---\ntitle: Foo\n---\nBody text one, reworded nicely.\n"
        assert_fences_unchanged(before, after)  # should not raise

    def test_fence_count_change_raises(self):
        before = "Intro.\n\n```python\nprint('hi')\n```\n\nOutro."
        after = "Intro.\n\n```python\nprint('hi')\n```\n\n```bash\necho hi\n```\n\nOutro."
        with self.assertRaises(ValueError) as ctx:
            assert_fences_unchanged(before, after)
        self.assertIn("count", str(ctx.exception))

    def test_split_fences_roundtrip(self):
        text = "---\na: 1\n---\nprose\n```py\ncode\n```\nmore prose"
        segments = split_fences(text)
        self.assertEqual("".join(t for _, t in segments), text)
        kinds = [k for k, _ in segments]
        self.assertEqual(kinds, ["frontmatter", "prose", "fence", "prose"])


# ---------------------------------------------------------------------------
# Serving log + reward join — needs a live DB
# ---------------------------------------------------------------------------

@unittest.skipUnless(DB_UP, "Postgres not reachable")
class ServingLogTests(unittest.TestCase):
    PROMPT_TITLE_A = "m6-test-prompt-a"
    PROMPT_TITLE_B = "m6-test-prompt-b"
    EP_PREFIX = "m6-test-ep-"

    def setUp(self):
        from capillaries.optimize.serving import apply_ddl
        apply_ddl(DB_CONFIG)

        self.conn = psycopg2.connect(**DB_CONFIG)
        self.conn.autocommit = True
        cur = self.conn.cursor()

        self.prompt_id_a = self._insert_prompt(cur, self.PROMPT_TITLE_A, "Prompt A canonical text.")
        self.prompt_id_b = self._insert_prompt(cur, self.PROMPT_TITLE_B, "Prompt B canonical text.")
        cur.close()

    def tearDown(self):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM serving_log WHERE episode_id LIKE %s", (self.EP_PREFIX + "%",))
        cur.execute("DELETE FROM arteries.rewards WHERE episode_id LIKE %s", (self.EP_PREFIX + "%",))
        cur.execute("DELETE FROM prompts WHERE title IN (%s, %s)", (self.PROMPT_TITLE_A, self.PROMPT_TITLE_B))
        cur.close()
        self.conn.close()

    def _insert_prompt(self, cur, title: str, text: str) -> str:
        pid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO prompts (prompt_id, title, file_path, prompt_text, content_hash)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (pid, title, "test/path.md", text, "m6-test-hash"),
        )
        return pid

    def _insert_serving(self, cur, episode_id, query, served_kind, served_id, candidates):
        cur.execute(
            """
            INSERT INTO serving_log (episode_id, query, served_kind, served_id, candidates)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (episode_id, query, served_kind, served_id, json.dumps(candidates)),
        )

    def _insert_reward(self, cur, episode_id, value):
        cur.execute(
            """
            INSERT INTO arteries.rewards (episode_id, project_id, reward_type, value, source)
            VALUES (%s, %s, 'episode', %s, %s)
            """,
            (episode_id, "m6-test-project", value, "test"),
        )

    def test_log_serving_writes_row(self):
        from capillaries.optimize.serving import log_serving

        os.environ["ARTERIES_EPISODE_ID"] = self.EP_PREFIX + "direct"
        try:
            log_serving(
                query="m6 direct-call query",
                served_kind="single_prompt",
                served_id=self.prompt_id_a,
                candidates=[{"id": self.prompt_id_a, "score": 0.7}],
                db_config=DB_CONFIG,
            )
        finally:
            del os.environ["ARTERIES_EPISODE_ID"]

        cur = self.conn.cursor()
        cur.execute(
            "SELECT episode_id, served_kind, served_id, candidates FROM serving_log WHERE episode_id = %s",
            (self.EP_PREFIX + "direct",),
        )
        row = cur.fetchone()
        cur.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "single_prompt")
        self.assertEqual(row[2], self.prompt_id_a)
        self.assertEqual(len(row[3]), 1)

    def test_log_serving_never_raises_on_bad_db(self):
        from capillaries.optimize.serving import log_serving
        # Bad config -> should swallow the error, not raise.
        log_serving("q", "single_prompt", "x", [], db_config={"host": "nonexistent-host-xyz", "port": 1})

    def test_serving_row_carries_episode_for_reward_join(self):
        """The join key harvest.py used to consume — still the point of the log.

        harvest.py is gone (it captured the retrieved prompt as the golden
        *output*, which trains an optimizer to reproduce the library). What it
        depended on is not gone: a serving row has to carry the episode_id that
        matches it to a reward, or no downstream consumer can learn anything.
        """
        cur = self.conn.cursor()
        ep = self.EP_PREFIX + "reward-join-1"
        self._insert_serving(cur, ep, "m6 reward join query", "single_prompt", self.prompt_id_a,
                              [{"id": self.prompt_id_a, "score": 0.9}])
        self._insert_reward(cur, ep, 0.8)

        cur.execute(
            """
            SELECT s.served_id, r.value
            FROM serving_log s
            JOIN arteries.rewards r ON r.episode_id = s.episode_id
            WHERE s.episode_id = %s
            """,
            (ep,),
        )
        row = cur.fetchone()
        cur.close()

        self.assertIsNotNone(row, "serving row did not join to its reward")
        self.assertEqual(row[0], self.prompt_id_a)
        self.assertAlmostEqual(row[1], 0.8, places=5)


# ---------------------------------------------------------------------------
# A/B promotion gate — needs a live DB
# ---------------------------------------------------------------------------

@unittest.skipUnless(DB_UP, "Postgres not reachable")
@_needs_dspy
class AbGateTests(unittest.TestCase):
    PROMPT_TITLE_WIN = "m6-test-ab-win"
    PROMPT_TITLE_LOSE = "m6-test-ab-lose"
    PROMPT_TITLE_NOTRAFFIC = "m6-test-ab-notraffic"

    def setUp(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.conn.autocommit = True
        cur = self.conn.cursor()
        self.pid_win = self._insert_prompt(cur, self.PROMPT_TITLE_WIN, "baseline text")
        self.pid_lose = self._insert_prompt(cur, self.PROMPT_TITLE_LOSE, "baseline text")
        self.pid_notraffic = self._insert_prompt(cur, self.PROMPT_TITLE_NOTRAFFIC, "baseline text")
        cur.close()

        self._orig_journal = os.environ.get("EVENT_JOURNAL_DIR")
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["EVENT_JOURNAL_DIR"] = self._tmpdir.name

    def tearDown(self):
        if self._orig_journal is None:
            os.environ.pop("EVENT_JOURNAL_DIR", None)
        else:
            os.environ["EVENT_JOURNAL_DIR"] = self._orig_journal
        self._tmpdir.cleanup()

        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM prompts WHERE title IN (%s, %s, %s)",
            (self.PROMPT_TITLE_WIN, self.PROMPT_TITLE_LOSE, self.PROMPT_TITLE_NOTRAFFIC),
        )
        cur.close()
        self.conn.close()

    def _insert_prompt(self, cur, title: str, text: str) -> str:
        pid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO prompts (prompt_id, title, file_path, prompt_text, content_hash)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (pid, title, "test/path.md", text, "m6-test-hash"),
        )
        return pid

    def _spine_lines(self) -> list[dict]:
        lines: list[dict] = []
        for f in Path(self._tmpdir.name).glob("*.ndjson"):
            for line in f.read_text().splitlines():
                if line.strip():
                    lines.append(json.loads(line))
        return lines

    @staticmethod
    def _rigged_metric_prefers(text_that_wins: str):
        def metric(prediction, example):
            return 1.0 if prediction.output_text == text_that_wins else 0.0
        return metric

    def test_candidate_wins_promotes_and_emits_spine_event(self):
        from capillaries.skills.promote import ab_gate

        result = ab_gate(
            self.PROMPT_TITLE_WIN,
            candidate_text="candidate text",
            metric=self._rigged_metric_prefers("candidate text"),
            examples=[{"output_text": "irrelevant, metric is rigged"}],
            db_config=DB_CONFIG,
        )
        self.assertTrue(result["promoted"])
        self.assertGreater(result["candidate_score"], result["baseline_score"])

        cur = self.conn.cursor()
        cur.execute("SELECT prompt_text FROM prompts WHERE prompt_id = %s", (self.pid_win,))
        self.assertEqual(cur.fetchone()[0], "candidate text")
        cur.close()

        events = [e for e in self._spine_lines() if e.get("kind") == "skill.promoted"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["prompt_title"], self.PROMPT_TITLE_WIN)
        self.assertEqual(events[0]["source"], "capillaries")

    def test_candidate_loses_rejects_and_emits_spine_event(self):
        from capillaries.skills.promote import ab_gate

        result = ab_gate(
            self.PROMPT_TITLE_LOSE,
            candidate_text="candidate text",
            metric=self._rigged_metric_prefers("baseline text"),
            examples=[{"output_text": "irrelevant, metric is rigged"}],
            db_config=DB_CONFIG,
        )
        self.assertFalse(result["promoted"])

        cur = self.conn.cursor()
        cur.execute("SELECT prompt_text FROM prompts WHERE prompt_id = %s", (self.pid_lose,))
        self.assertEqual(cur.fetchone()[0], "baseline text")
        cur.close()

        events = [e for e in self._spine_lines() if e.get("kind") == "skill.rejected"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["prompt_title"], self.PROMPT_TITLE_LOSE)

    def test_no_traffic_never_promotes_blind(self):
        from capillaries.skills.promote import ab_gate

        result = ab_gate(
            self.PROMPT_TITLE_NOTRAFFIC,
            candidate_text="candidate text",
            db_config=DB_CONFIG,
        )
        self.assertFalse(result["promoted"])
        self.assertEqual(result["reason"], "no traffic")


if __name__ == "__main__":
    unittest.main()
