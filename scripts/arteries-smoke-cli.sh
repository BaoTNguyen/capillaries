#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
prompt="${1:-thanks}"

echo '== arteries eval =='
output="$(bash scripts/arteries-eval.sh "$prompt")"
if [[ -n "$output" ]]; then
  printf '%s
' "$output"
else
  echo '(no retrieved prompt)'
fi

echo '== generic observe =='
generic="$(bash scripts/arteries-generic-observe.sh "$prompt")"
if [[ -n "$generic" ]]; then
  printf '%s
' "$generic"
else
  echo '(no generic context)'
fi

echo '== claude/codex observe hook =='
bash scripts/arteries-hook-observe-smoke.sh "$prompt"

echo '== session start hook =='
bash scripts/arteries-hook-activate-smoke.sh
