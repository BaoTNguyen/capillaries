#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
prompt="${1:-thanks}"

echo '== generic observe =='
out="$(bash "$script_dir/hooks/generic-observe.sh" "$prompt")"
if [[ -n "$out" ]]; then
  printf '%s
' "$out"
else
  echo '(no generic context)'
fi

echo '== activate =='
bash "$script_dir/hooks/activate.sh"
