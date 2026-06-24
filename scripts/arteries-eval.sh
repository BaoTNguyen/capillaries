#!/usr/bin/env bash
set -euo pipefail

PROMPT_SYSTEM_ROOT="${PROMPT_SYSTEM_ROOT:-.}"
ARTERIES_ROOT="${ARTERIES_ROOT:-../arteries}"
cd "$PROMPT_SYSTEM_ROOT"
export PYTHONPATH="$ARTERIES_ROOT/src:$PROMPT_SYSTEM_ROOT/src:${PYTHONPATH:-}"
export ARTERIES_PROJECT="${ARTERIES_PROJECT:-prompt-system}"
export ARTERIES_AGENT_ID="${ARTERIES_AGENT_ID:-prompt-system-hook}"

if [[ $# -gt 0 ]]; then
  prompt="$*"
else
  prompt="$(cat)"
fi

python3 -m arteries.eval "$prompt"
