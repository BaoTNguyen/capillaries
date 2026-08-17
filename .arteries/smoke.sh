#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"

# --write opts into real memory. Without it the smoke run is a dry run:
# ARTERIES_EPHEMERAL=discard exercises every code path but keeps the writes in
# an in-process buffer, so testing the observer no longer leaves permanent
# "memories" behind. It used to, and a good share of one project's stored facts
# were this script talking to itself.
dry=" (dry run; --write to persist)"
if [[ "${1:-}" == "--write" ]]; then
  shift
  dry=""
else
  export ARTERIES_EPHEMERAL=discard
fi
prompt="${1:-thanks}"

echo "== observe ==$dry"
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
