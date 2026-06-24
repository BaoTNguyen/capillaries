#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ $# -gt 0 ]]; then
  prompt="$*"
else
  prompt="$(cat)"
fi

result="$($script_dir/observe.sh "$prompt")"
if [[ -n "$result" ]]; then
  printf 'ARTERIES RETRIEVED PROMPT - use this to guide your response:

%s
' "$result"
fi
