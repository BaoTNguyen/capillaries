#!/usr/bin/env bash
set -euo pipefail

ARTERIES_ROOT="${ARTERIES_ROOT:-/home/bao-tn/Coding/Projects/arteries}"
CAPILLARIES_ROOT="${CAPILLARIES_ROOT:-/home/bao-tn/Coding/Projects/capillaries}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/bao-tn/Coding/Projects/capillaries}"
export PYTHONPATH="$ARTERIES_ROOT/src:$CAPILLARIES_ROOT/src:$PROJECT_ROOT/src:${PYTHONPATH:-}"
export ARTERIES_PROJECT="${ARTERIES_PROJECT:-capillaries}"
export ARTERIES_AGENT_ID="${ARTERIES_AGENT_ID:-capillaries-hook}"
export ARTERIES_CLI="${ARTERIES_CLI:-claude}"
export ARTERIES_REPO="${ARTERIES_REPO:-$PROJECT_ROOT}"
# capillaries' cross-encoder defaults to CPU, where a warm rerank costs ~1.7s
# against a 10s hook budget; on GPU the same call is ~0.12s. Cold start is
# ~4.5s either way, so this only pays off once something stays warm — but it
# costs nothing to set, and it is what makes a warm path worth building.
export RERANKER_DEVICE="${RERANKER_DEVICE:-cuda}"
# Per-repo policy, e.g. ARTERIES_EPHEMERAL=keep. Lives outside the generated
# block so `art setup` can regenerate hooks without discarding it — hand-edited
# hook commands do not survive a sync. Precedence: caller env, then this file,
# then the defaults above.
if [[ -f "$PROJECT_ROOT/.arteries/env" ]]; then
  while IFS='=' read -r _k _v; do
    [[ "$_k" =~ ^[A-Z][A-Z0-9_]*$ ]] || continue
    [[ -n "${!_k:-}" ]] || export "$_k=$_v"
  done < "$PROJECT_ROOT/.arteries/env"
fi

format="${ARTERIES_PACKET_FORMAT:-markdown}"
message="${1:-context-pressure}"
python3 -m arteries.packet --format "$format" --message "$message" --budget "${ARTERIES_PACKET_BUDGET:-6000}"
