"""Every schema builder the db modules define must be called by the setup path.

This is a drift check, not a behaviour test. setup_db.py and the modules it
imports have diverged three times: skill_sessions and agent_feedback were
defined but never created (so skill sessions could not open at all, and
lifecycle/inactivate.py had no agent_feedback to read), and the materialized
view feedback.py refreshes did not exist either. Each was silent until
something reached for the missing table at runtime.

Static, on purpose. Executing the real setup needs a database and would
happily pass while still skipping a builder.
"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETUP_SCRIPT = ROOT / "scripts" / "setup_db.py"
DB_MODULES = [
    ROOT / "src" / "capillaries" / "db" / "setup.py",
    ROOT / "src" / "capillaries" / "db" / "setup_skills.py",
]

# Builders that intentionally are not part of the default setup path.
# Keep this list short and justified — it is the escape hatch that lets the
# check rot.
EXEMPT: set[str] = set()


def _defined_builders(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and (node.name.startswith("create_") or node.name.startswith("add_"))
    }


def _called_names(path: pathlib.Path) -> set[str]:
    """Names invoked anywhere in the script, plus what they were imported as.

    setup_db.py aliases some imports (`create_indexes as create_skills_indexes`),
    so the original name has to be recovered from the ImportFrom node.
    """
    tree = ast.parse(path.read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    aliases = {
        alias.asname: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname
    }
    return called | {aliases[name] for name in called if name in aliases}


@pytest.mark.parametrize("module", DB_MODULES, ids=lambda p: p.name)
def test_every_builder_is_wired_into_setup(module):
    defined = _defined_builders(module) - EXEMPT
    called = _called_names(SETUP_SCRIPT)
    missing = sorted(defined - called)
    assert not missing, (
        f"{module.name} defines {missing} but scripts/setup_db.py never calls "
        f"them, so a fresh database will not have them. Wire them in, or add "
        f"them to EXEMPT with a reason."
    )


def test_the_check_can_actually_fail():
    """A drift check that cannot fail is worse than none."""
    assert _defined_builders(DB_MODULES[1]), "no builders discovered — parser is broken"
    assert "create_agent_feedback_table" in _defined_builders(DB_MODULES[1])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
