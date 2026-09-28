"""The shell scripts can't import vascular_paths, so they spell the layout out.
Pin the spelled-out paths to the same layout, statically: no bash is launched."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = "${VASCULAR_HOME:-$HOME/.vascular}"


def read(rel):
    return (ROOT / rel).read_text()


def test_setup_defaults_follow_vascular_home():
    setup = read("scripts/setup.sh")
    assert f'DEFAULT_PROMPTS="{HOME}/data/capillaries/prompts"' in setup
    assert f'DEFAULT_SKILLS="{HOME}/data/capillaries/skills"' in setup
    for key, leaf in (("PROMPTS_PATH", "prompts"), ("SKILLS_PATH", "skills")):
        # set -euo pipefail: a missing key must not abort the assignment.
        assert f"{key}=\"$(grep '^{key}=' \"$ENV_FILE\" 2>/dev/null | cut -d= -f2- || true)\"" in setup
        assert f'{key}="${{{key}:-{HOME}/data/capillaries/{leaf}}}"' in setup


def test_teardown_defaults_and_guard_follow_vascular_home():
    teardown = read("scripts/teardown.sh")
    assert f'BACKUP_DIR="${{CAPILLARIES_BACKUP_DIR:-{HOME}/backups/capillaries}}"' in teardown
    assert f'PROMPTS_PATH="${{PROMPTS_PATH:-{HOME}/data/capillaries/prompts}}"' in teardown
    assert f'SKILLS_PATH="${{SKILLS_PATH:-{HOME}/data/capillaries/skills}}"' in teardown
    assert f'"$HOME"/*|"$PROJECT_DIR"/*|"{HOME}"/*) ;;' in teardown
    # The pre-existing refusals stay.
    for guard in ('[[ "$path" != "$HOME" ]]', '[[ "$(dirname "$path")" != "/" ]]'):
        assert guard in teardown


def test_no_old_paths_left():
    for rel in ("scripts/setup.sh", "scripts/teardown.sh", "README.md",
                "docs/quick_start_guide.md", ".env.example"):
        text = read(rel)
        for old in (".capillaries/", ".local/state/capillaries", ".local/share/heart"):
            assert old not in text, (rel, old)


def test_prose_names_new_locations():
    assert "~/.vascular/backups/capillaries/" in read("README.md")
    for rel in ("docs/quick_start_guide.md", ".env.example"):
        text = read(rel)
        assert "~/.vascular/data/capillaries/prompts/" in text, rel
        assert "~/.vascular/data/capillaries/skills/" in text, rel
        assert "VASCULAR_HOME" in text, rel
