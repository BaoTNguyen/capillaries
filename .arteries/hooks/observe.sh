#!/usr/bin/env bash
set -euo pipefail

ARTERIES_ROOT="${ARTERIES_ROOT:-../arteries}"
PROJECT_ROOT="${PROJECT_ROOT:-.}"
export PYTHONPATH="$ARTERIES_ROOT/src:$PROJECT_ROOT/src:${PYTHONPATH:-}"
export ARTERIES_PROJECT="${ARTERIES_PROJECT:-prompt-system}"
export ARTERIES_AGENT_ID="${ARTERIES_AGENT_ID:-prompt-system-hook}"
export ARTERIES_CLI="${ARTERIES_CLI:-codex}"
export ARTERIES_REPO="${ARTERIES_REPO:-$PROJECT_ROOT}"

if [[ $# -gt 0 ]]; then
  prompt="$*"
else
  prompt="$(cat)"
fi

python3 -m arteries.eval "$prompt"
