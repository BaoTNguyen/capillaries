#!/usr/bin/env bash
set -euo pipefail

PROMPT_SYSTEM_ROOT="${PROMPT_SYSTEM_ROOT:-.}"
cd "$PROMPT_SYSTEM_ROOT"

if [[ $# -gt 0 ]]; then
  prompt="$*"
else
  prompt="$(cat)"
fi

result="$(bash scripts/arteries-eval.sh "$prompt")"
if [[ -n "$result" ]]; then
  printf 'ARTERIES RETRIEVED PROMPT - use this to guide your response:

%s
' "$result"
fi
