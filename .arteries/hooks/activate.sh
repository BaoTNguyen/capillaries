#!/usr/bin/env bash
set -euo pipefail

ARTERIES_ROOT="${ARTERIES_ROOT:-/home/bao-tn/Coding/Projects/arteries}"
CAPILLARIES_ROOT="${CAPILLARIES_ROOT:-/home/bao-tn/Coding/Projects/capillaries}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/bao-tn/Coding/Projects/capillaries}"
export PYTHONPATH="$ARTERIES_ROOT/src:$CAPILLARIES_ROOT/src:$PROJECT_ROOT/src:${PYTHONPATH:-}"
export ARTERIES_PROJECT="${ARTERIES_PROJECT:-capillaries}"
export ARTERIES_AGENT_ID="${ARTERIES_AGENT_ID:-capillaries-hook}"
export ARTERIES_CLI="${ARTERIES_CLI:-generic}"
export ARTERIES_REPO="${ARTERIES_REPO:-$PROJECT_ROOT}"

python3 -m arteries.runs start --project "$ARTERIES_PROJECT" --agent "$ARTERIES_AGENT_ID" --cli "$ARTERIES_CLI" --repo "$ARTERIES_REPO" >/dev/null 2>&1 || true

cat <<'EOF'
ARTERIES MEMORY SYSTEM ACTIVE.

This repo is connected to arteries project `capillaries`.
Arteries observes turns, builds ephemeral/persistent/evergreen memory, and may surface retrieved prompts as visible context.
EOF
