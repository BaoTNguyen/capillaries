#!/usr/bin/env bash
# Guard test for scripts/teardown.sh.
#
# safe_rm is the only function in this repo that runs `rm -rf` on a path built
# from user-editable input (.env). These assertions are what stands between a
# malformed PROMPTS_PATH and someone's home directory.
#
#   ./tests/test_teardown.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TEARDOWN_LIB=1 source "$PROJECT_DIR/scripts/teardown.sh"

fails=0
refuses() {
    if safe_rm "$1" 2>/dev/null; then
        echo "FAIL: safe_rm accepted $2 ('$1')"
        fails=$((fails + 1))
    else
        echo "ok: refused $2"
    fi
}

refuses ""              "an empty path"
refuses "relative/dir"  "a relative path"
refuses "/"             "root"
refuses "$HOME"         "\$HOME itself"
refuses "/etc"          "a root-level directory"
refuses "/var/lib/pgsql" "a path outside \$HOME and the project"

# The positive case: a real directory under $HOME is removed.
victim="$(mktemp -d "$HOME/.capillaries-teardown-test.XXXXXX")"
touch "$victim/file"
DRY_RUN=false safe_rm "$victim" >/dev/null
if [[ -e "$victim" ]]; then
    echo "FAIL: safe_rm did not remove a valid path"
    fails=$((fails + 1))
    rm -rf -- "$victim"
else
    echo "ok: removed a valid path under \$HOME"
fi

# --dry-run must not delete, even for a path that passes every guard.
victim2="$(mktemp -d "$HOME/.capillaries-teardown-test.XXXXXX")"
DRY_RUN=true safe_rm "$victim2" >/dev/null
if [[ -e "$victim2" ]]; then
    echo "ok: --dry-run left the path alone"
    rm -rf -- "$victim2"
else
    echo "FAIL: --dry-run deleted $victim2"
    fails=$((fails + 1))
fi

echo
if (( fails )); then
    echo "$fails failure(s)"
    exit 1
fi
echo "all teardown guards pass"
