#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ARTERIES_ROOT:-}" ]]; then
  echo "ARTERIES_ROOT not set." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CAPILLARIES_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$CAPILLARIES_ROOT"
export PYTHONPATH="$ARTERIES_ROOT/src:$CAPILLARIES_ROOT/src:${PYTHONPATH:-}"
export ARTERIES_PROJECT="${ARTERIES_PROJECT:-capillaries}"
export ARTERIES_AGENT_ID="${ARTERIES_AGENT_ID:-capillaries-hook}"

if [[ $# -gt 0 ]]; then
  prompt="$*"
else
  prompt="$(cat)"
fi

python3 -m arteries.eval "$prompt"
