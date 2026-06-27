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

if [[ $# -gt 0 ]]; then
  prompt="$*"
else
  prompt="$(cat)"
fi

python3 -m arteries.eval "$prompt"
