"""Tests for capillaries.vascular_paths."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import TestCase, main

from capillaries.vascular_paths import (
    KINDS,
    home,
    journal_dir,
    path,
    repo_dir,
)


class KindConstantsTest(TestCase):
    """KINDS is the single source of truth for path kinds."""

    def test_kind_values(self) -> None:
        self.assertEqual(
            KINDS,
            ("config", "secrets", "state", "spool", "log", "cache", "data", "backups"),
        )

    def test_kind_is_tuple(self) -> None:
        self.assertIsInstance(KINDS, tuple)

    def test_no_unknown_kinds_allowed(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            path("unknown", "comp")
        self.assertIn("unknown kind", str(ctx.exception))
        self.assertIn("'unknown'", str(ctx.exception))


class HomeTest(TestCase):
    """home() resolves $VASCULAR_HOME or falls back to ~/.vascular."""

    def setUp(self) -> None:
        os.environ.pop("VASCULAR_HOME", None)

    def tearDown(self) -> None:
        os.environ.pop("VASCULAR_HOME", None)

    def test_defaults_to_homedir(self) -> None:
        result = home()
        self.assertEqual(result, Path.home() / ".vascular")

    def test_uses_env_var(self) -> None:
        os.environ["VASCULAR_HOME"] = "/tmp/custom-vascular"
        self.assertEqual(home(), Path("/tmp/custom-vascular"))


class PathFunctionTest(TestCase):
    """path(kind, component, *parts) builds the expected Path."""

    def setUp(self) -> None:
        os.environ.pop("VASCULAR_HOME", None)

    def tearDown(self) -> None:
        os.environ.pop("VASCULAR_HOME", None)

    def test_basic_structure(self) -> None:
        result = path("config", "heart", "settings.yaml")
        self.assertIn(".vascular/config/heart/settings.yaml", str(result))

    def test_multiple_parts(self) -> None:
        result = path("state", "heart", "events", "2024", "01")
        self.assertIn(".vascular/state/heart/events/2024/01", str(result))

    def test_no_directory_created(self) -> None:
        result = path("cache", "test-comp", "nonexistent")
        self.assertFalse(result.exists())

    def test_custom_vascular_home(self) -> None:
        os.environ["VASCULAR_HOME"] = "/tmp/v"
        result = path("data", "comp", "file.txt")
        self.assertEqual(result, Path("/tmp/v/data/comp/file.txt"))

    def test_new_kinds_build_under_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["VASCULAR_HOME"] = tmp
            for kind in ("secrets", "spool", "log"):
                self.assertEqual(path(kind, "x"), Path(tmp) / kind / "x")


class JournalDirTest(TestCase):
    """journal_dir() resolves $EVENT_JOURNAL_DIR or falls back."""

    def setUp(self) -> None:
        os.environ.pop("EVENT_JOURNAL_DIR", None)
        os.environ.pop("VASCULAR_HOME", None)

    def tearDown(self) -> None:
        os.environ.pop("EVENT_JOURNAL_DIR", None)
        os.environ.pop("VASCULAR_HOME", None)

    def test_defaults_to_spool_events(self) -> None:
        result = journal_dir()
        self.assertEqual(
            result,
            Path.home() / ".vascular" / "spool" / "events",
        )

    def test_uses_env_var(self) -> None:
        os.environ["EVENT_JOURNAL_DIR"] = "/tmp/my-journal"
        self.assertEqual(journal_dir(), Path("/tmp/my-journal"))

    def test_uses_vascular_home_env(self) -> None:
        os.environ["VASCULAR_HOME"] = "/tmp/vh"
        result = journal_dir()
        self.assertEqual(
            result,
            Path("/tmp/vh/spool/events"),
        )


class RepoDirTest(TestCase):
    """repo_dir(root, component) returns <root>/.vascular/<component>."""

    def test_with_string_root(self) -> None:
        result = repo_dir("/tmp/repo", "mycomp")
        self.assertEqual(result, Path("/tmp/repo/.vascular/mycomp"))

    def test_with_path_root(self) -> None:
        result = repo_dir(Path("/tmp/repo"), "mycomp")
        self.assertEqual(result, Path("/tmp/repo/.vascular/mycomp"))

    def test_relative_root(self) -> None:
        result = repo_dir("myrepo", "svc")
        self.assertEqual(result, Path("myrepo/.vascular/svc"))


if __name__ == "__main__":
    main()
