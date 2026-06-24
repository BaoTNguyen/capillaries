#!/usr/bin/env bash
set -euo pipefail

ARTERIES_ROOT="${ARTERIES_ROOT:-../arteries}"
PROJECT_ROOT="${PROJECT_ROOT:-.}"
export PYTHONPATH="$ARTERIES_ROOT/src:$PROJECT_ROOT/src:${PYTHONPATH:-}"
export ARTERIES_PROJECT="${ARTERIES_PROJECT:-prompt-system}"
export ARTERIES_AGENT_ID="${ARTERIES_AGENT_ID:-prompt-system-hook}"
export ARTERIES_CLI="${ARTERIES_CLI:-codex}"
export ARTERIES_REPO="${ARTERIES_REPO:-$PROJECT_ROOT}"

python3 -m arteries.runs start --project "$ARTERIES_PROJECT" --agent "$ARTERIES_AGENT_ID" --cli "$ARTERIES_CLI" --repo "$ARTERIES_REPO" >/dev/null 2>&1 || true

cat <<'EOF'
ARTERIES MEMORY SYSTEM ACTIVE.

This repo is connected to arteries project `prompt-system`.
Arteries observes turns, builds ephemeral/persistent/evergreen memory, and may surface retrieved prompts as visible context.
EOF
