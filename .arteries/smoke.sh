#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
prompt="${1:-thanks}"

echo '== observe =='
out="$(bash "$script_dir/hooks/generic-observe.sh" "$prompt")"
if [[ -n "$out" ]]; then
  printf '%s
' "$out"
else
  echo '(no context)'
fi

echo '== compact packet =='
bash "$script_dir/hooks/compact-packet.sh" smoke

echo '== activate =='
bash "$script_dir/hooks/activate.sh"
