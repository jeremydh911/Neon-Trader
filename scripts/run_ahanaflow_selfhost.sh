#!/usr/bin/env bash
# Start a self-hosted AhanaFlow vector server for Neon Trader / Tim memory.
# Preferred over cloud API — trade memory stays on your box.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/vendor/AhanaFlow" ]]; then
  echo "Missing vendor/AhanaFlow — run: git submodule update --init vendor/AhanaFlow" >&2
  exit 1
fi

export AHANAFLOW_HOST="${AHANAFLOW_HOST:-127.0.0.1}"
export AHANAFLOW_PORT="${AHANAFLOW_PORT:-9634}"
export AHANAFLOW_WAL="${AHANAFLOW_WAL:-$ROOT/data/ahanaflow/tim_memory.wal}"

mkdir -p "$(dirname "$AHANAFLOW_WAL")"

echo "Starting AhanaFlow self-host on ${AHANAFLOW_HOST}:${AHANAFLOW_PORT}"
echo "WAL: ${AHANAFLOW_WAL}"
exec python3 "$ROOT/scripts/ahanaflow_selfhost_server.py" \
  --host "$AHANAFLOW_HOST" \
  --port "$AHANAFLOW_PORT" \
  --wal "$AHANAFLOW_WAL" \
  ${AHANAFLOW_REQUIRE_AUTH:+--require-auth} \
  ${AHANAFLOW_API_KEYS_FILE:+--api-keys-file "$AHANAFLOW_API_KEYS_FILE"}
