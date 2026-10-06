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
    assert f'local vroot="{HOME}"' in teardown
    assert '"$HOME"/*|"$PROJECT_DIR"/*|"$vroot"/*) ;;' in teardown
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


def test_a_shallow_vascular_home_cannot_widen_teardown():
    """safe_rm guards rm -rf. VASCULAR_HOME=/ or /usr must not make /usr/lib removable."""
    import subprocess
    script = (ROOT / "scripts" / "teardown.sh").read_text()
    fn = script[script.index("safe_rm() {"):]
    fn = fn[:fn.index("\n}\n") + 3]
    harness = ('err(){ echo "REFUSED $*"; }; info(){ :; }; ok(){ :; }; '
               'run(){ echo "WOULD $*"; }; ' + fn + ' safe_rm /usr/lib/x; safe_rm "$VASCULAR_HOME/data/x"')
    for vh, allowed in (("/", False), ("/usr", False)):
        out = subprocess.run(["bash", "-c", harness], capture_output=True, text=True,
                             env={"VASCULAR_HOME": vh, "HOME": "/home/x", "PROJECT_DIR": "/p",
                                  "DRY_RUN": "true", "PATH": "/usr/bin:/bin"}).stdout
        assert "REFUSED" in out.splitlines()[0], (vh, out)
