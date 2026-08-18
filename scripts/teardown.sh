#!/usr/bin/env bash
# Remove everything scripts/setup.sh created.
#
# Drops the database, deletes .env, removes the prompts/skills directories,
# uninstalls the editable package, and kills the service session. Tracked
# source is never touched — this undoes setup, it does not delete the repo.
#
# Usage:
#   ./scripts/teardown.sh --dry-run     # print the plan, change nothing
#   ./scripts/teardown.sh               # ask before each destructive step
#   ./scripts/teardown.sh --force       # no prompts (CI)
#   ./scripts/teardown.sh --models      # also delete the HuggingFace model cache
#   ./scripts/teardown.sh --database X  # name the database explicitly
#   ./scripts/teardown.sh --no-backup   # skip the pre-drop dump (unrecoverable)
#
# Two safety rules, both learned by breaking them:
#
#   The database is never guessed. Without a DB_NAME in .env, the drop is
#   skipped; --database is the only way to name one. A default here once meant
#   a second run — .env already deleted by the first — dropped production.
#
#   The database is always dumped before it is dropped. Seconds and ~18 MB
#   against an unrecoverable loss. A failed dump aborts the drop.
#
# --models is opt-in because the HF cache is shared with every other project
# on the machine.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

DRY_RUN=false
FORCE=false
DROP_MODELS=false

usage() { sed -n '2,25p' "$0" | sed 's/^# \?//'; exit "${1:-0}"; }

DB_NAME_OVERRIDE=""
NO_BACKUP=false
BACKUP_DIR="${CAPILLARIES_BACKUP_DIR:-$HOME/.capillaries/backups}"

while (( $# )); do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --force)   FORCE=true ;;
        --models)  DROP_MODELS=true ;;
        --no-backup) NO_BACKUP=true ;;
        --database) shift; DB_NAME_OVERRIDE="${1:-}"
                    [[ -n "$DB_NAME_OVERRIDE" ]] || { echo "--database needs a name" >&2; exit 1; } ;;
        --database=*) DB_NAME_OVERRIDE="${1#*=}" ;;
        -h|--help) usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 1 ;;
    esac
    shift
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLUE}▸${NC} $*"; }
ok()   { echo -e "${GREEN}✔${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✖${NC} $*" >&2; }

# Every destructive step routes through here. --dry-run short-circuits before
# the command runs, so a dry run cannot delete anything even if a step below
# is written wrong.
run() {
    if $DRY_RUN; then
        echo "    would run: $*"
    else
        "$@"
    fi
}

confirm() {
    $FORCE && return 0
    $DRY_RUN && return 0
    local yn
    read -rp "$(echo -e "${BLUE}?${NC} $1 [y/N] ")" yn
    [[ "${yn,,}" == y* ]]
}

# A path is only safe to rm -rf if it is non-empty, absolute, not $HOME, not a
# root-level directory, and sits under $HOME or the project. Anything else is
# a bug in this script or a corrupted .env, and we refuse rather than guess.
safe_rm() {
    local path="$1"
    [[ -n "$path" ]]                     || { err "refusing: empty path"; return 1; }
    [[ "$path" = /* ]]                   || { err "refusing non-absolute path: $path"; return 1; }
    [[ "$path" != "/" ]]                 || { err "refusing: /"; return 1; }
    [[ "$path" != "$HOME" ]]             || { err "refusing: \$HOME"; return 1; }
    [[ "$(dirname "$path")" != "/" ]]    || { err "refusing root-level path: $path"; return 1; }
    case "$path" in
        "$HOME"/*|"$PROJECT_DIR"/*) ;;
        *) err "refusing path outside \$HOME and the project: $path"; return 1 ;;
    esac
    [[ -e "$path" ]] || { info "already gone: $path"; return 0; }
    run rm -rf -- "$path"
    $DRY_RUN || ok "removed $path"
}

# Read a key out of .env without sourcing it — .env is user-edited and
# sourcing it would execute whatever is in there.
env_get() {
    [[ -f "$PROJECT_DIR/.env" ]] || return 0
    grep -E "^$1=" "$PROJECT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

expand_home() { echo "${1/#\~/$HOME}"; }

# The database name is NEVER guessed. An earlier version defaulted to
# `capillaries` when .env was absent, which made a second teardown run — .env
# having been deleted by the first — silently drop the default-named production
# database. Destroying data on a fallback value is not a defensible default, so
# a missing name now means the drop is skipped, and --database is the only way
# to name one explicitly.
DB_NAME="${DB_NAME_OVERRIDE:-$(env_get DB_NAME)}"

PROMPTS_PATH="$(expand_home "$(env_get PROMPTS_PATH)")"
SKILLS_PATH="$(expand_home "$(env_get SKILLS_PATH)")"
# Path defaults are safe to guess: safe_rm refuses anything outside $HOME or the
# project, and a nonexistent path is a no-op. A DROP DATABASE has neither guard.
PROMPTS_PATH="${PROMPTS_PATH:-$HOME/.capillaries/prompts}"
SKILLS_PATH="${SKILLS_PATH:-$HOME/.capillaries/skills}"

# Lets the test source this file to exercise safe_rm's guards without running
# a teardown. Nothing above this line touches the filesystem.
[[ -n "${TEARDOWN_LIB:-}" ]] && return 0

echo
echo "Teardown plan for $PROJECT_DIR"
echo "  service session : prompt-search (tmux)"
if [[ -n "$DB_NAME" ]]; then
    echo "  database        : $DB_NAME"
else
    echo "  database        : (none named — SKIPPED, see below)"
fi
echo "  env file        : $PROJECT_DIR/.env"
echo "  prompts dir     : $PROMPTS_PATH"
echo "  skills dir      : $SKILLS_PATH"
echo "  editable install: capillaries"
$DROP_MODELS && echo "  model cache     : ${HF_HOME:-$HOME/.cache/huggingface}"
echo "  NOT touched     : tracked source, git history, public_prompts/"
echo

$DRY_RUN && warn "Dry run — nothing will be changed."

if ! $DRY_RUN && ! $FORCE; then
    read -rp "$(echo -e "${RED}!${NC} Type 'teardown' to continue: ")" answer
    [[ "$answer" == "teardown" ]] || { info "Aborted."; exit 0; }
fi

# ── 1. Stop the service ─────────────────────────────────────────────────────
if tmux has-session -t prompt-search 2>/dev/null; then
    info "Stopping the prompt-search service..."
    run tmux kill-session -t prompt-search
    ok "Service stopped."
else
    info "Service not running."
fi

# ── 2. Drop the database ────────────────────────────────────────────────────
if [[ -z "$DB_NAME" ]]; then
    warn "No database name found — skipping the database drop."
    info "DB_NAME is read from $PROJECT_DIR/.env, which is absent or has no"
    info "DB_NAME line. This is the case after a previous teardown deleted it."
    info "To drop one anyway, name it explicitly:"
    echo "    ./scripts/teardown.sh --database <name>"
elif command -v psql &>/dev/null && psql -lqt 2>/dev/null | cut -d\| -f1 | grep -qw "$DB_NAME"; then
    if confirm "Drop the '$DB_NAME' database and all prompts/skills in it?"; then
        # Dump before dropping, always, unless explicitly told not to. A full
        # corpus is ~18 MB compressed and takes seconds; the alternative, learned
        # the hard way, is that a wrong database name is unrecoverable. The dump
        # is written before the drop so a failure here aborts the drop.
        if ! $NO_BACKUP && ! $DRY_RUN; then
            mkdir -p "$BACKUP_DIR"
            backup_file="$BACKUP_DIR/${DB_NAME}-$(date +%Y%m%d-%H%M%S).dump"
            info "Backing up '$DB_NAME' first..."
            if pg_dump -Fc -d "$DB_NAME" -f "$backup_file" 2>/dev/null; then
                ok "Backup: $backup_file ($(du -h "$backup_file" | cut -f1))"
                echo "    restore: pg_restore -d $DB_NAME --clean --if-exists $backup_file"
            else
                err "Backup failed — refusing to drop '$DB_NAME'."
                info "Pass --no-backup to drop without one."
                exit 1
            fi
        elif $NO_BACKUP && ! $DRY_RUN; then
            warn "--no-backup: dropping '$DB_NAME' with no dump. This is unrecoverable."
        fi

        # dropdb over "DROP DATABASE" so the name is an argument, never
        # interpolated into SQL.
        if $DRY_RUN; then
            echo "    would run: pg_dump -Fc -d $DB_NAME -f $BACKUP_DIR/${DB_NAME}-<timestamp>.dump"
            echo "    would run: dropdb $DB_NAME"
        elif dropdb --if-exists "$DB_NAME" 2>/dev/null \
             || sudo -n -u postgres dropdb --if-exists "$DB_NAME" 2>/dev/null; then
            ok "Dropped database '$DB_NAME'."
        else
            err "Could not drop '$DB_NAME' — drop it manually: dropdb $DB_NAME"
        fi
    else
        info "Database kept."
    fi
else
    info "Database '$DB_NAME' not found (or psql unavailable)."
fi

# ── 3. Remove .env ──────────────────────────────────────────────────────────
if [[ -f "$PROJECT_DIR/.env" ]]; then
    if confirm "Delete .env (contains your API keys and DB credentials)?"; then
        safe_rm "$PROJECT_DIR/.env"
    else
        info ".env kept."
    fi
fi

# ── 4. Remove prompt and skill directories ──────────────────────────────────
# These hold the user's own written prompts, which setup.sh only created empty.
# Anything in them now was put there by hand — hence the separate prompt and
# the file count in it.
for dir in "$PROMPTS_PATH" "$SKILLS_PATH"; do
    [[ -d "$dir" ]] || continue
    count="$(find "$dir" -type f 2>/dev/null | wc -l)"
    if confirm "Delete $dir ($count files)?"; then
        safe_rm "$dir"
    else
        info "Kept $dir"
    fi
done

# ── 5. Uninstall the package ────────────────────────────────────────────────
# `python3 -m pip` rather than bare `pip`: the two can resolve to different
# environments, and an unqualified `pip uninstall` will happily remove
# capillaries from whichever env happens to be on PATH — not necessarily the one
# setup.sh installed into. Naming the interpreter makes the target visible in
# the prompt instead of a guess.
PY_BIN="$(command -v python3 || true)"
if [[ -n "$PY_BIN" ]] && confirm "Uninstall 'capillaries' from $PY_BIN?"; then
    if $DRY_RUN; then
        echo "    would run: $PY_BIN -m pip uninstall -y capillaries"
    elif "$PY_BIN" -m pip show capillaries &>/dev/null; then
        "$PY_BIN" -m pip uninstall -y capillaries >/dev/null
        ok "Uninstalled capillaries from $PY_BIN."
    else
        # Not an error: a fresh clone, or the wrong venv is active. Say which,
        # because "uninstalled" when nothing happened sends people looking in
        # the wrong place later.
        info "capillaries not installed in $PY_BIN — nothing to uninstall."
        info "If you installed it elsewhere, activate that environment and run:"
        echo "    pip uninstall capillaries"
    fi
    safe_rm "$PROJECT_DIR/src/capillaries.egg-info"
fi

# ── 6. Generated and transient files ────────────────────────────────────────
info "Removing caches and transient reports..."
for f in .pytest_cache chain_report.txt eval_report.txt workflow_eval.txt \
         classification.log obsidian_sync.log; do
    [[ -e "$PROJECT_DIR/$f" ]] && safe_rm "$PROJECT_DIR/$f"
done
if ! $DRY_RUN; then
    find "$PROJECT_DIR" -type d -name __pycache__ -not -path '*/.venv/*' \
        -exec rm -rf -- {} + 2>/dev/null || true
    ok "Removed __pycache__ directories."
else
    echo "    would run: find $PROJECT_DIR -type d -name __pycache__ -delete"
fi

# ── 7. Model cache (opt-in) ─────────────────────────────────────────────────
if $DROP_MODELS; then
    HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"
    warn "The HuggingFace cache is shared with every other project on this machine."
    if confirm "Delete $HF_CACHE?"; then
        safe_rm "$HF_CACHE"
    fi
fi

echo
if $DRY_RUN; then
    ok "Dry run complete — nothing was changed."
else
    ok "Teardown complete."
    echo "  Re-create everything with: ./scripts/setup.sh"
fi
