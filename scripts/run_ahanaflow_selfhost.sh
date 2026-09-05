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
export AHANAFLOW_DATA_ROOT="${AHANAFLOW_DATA_ROOT:-$ROOT/data/ahanaflow}"
export AHANAFLOW_WAL="${AHANAFLOW_WAL:-tim_memory.wal}"

mkdir -p "$AHANAFLOW_DATA_ROOT"

EXTRA=()
if [[ -n "${AHANAFLOW_REQUIRE_AUTH:-}" ]]; then
  EXTRA+=(--require-auth)
fi
if [[ -n "${AHANAFLOW_API_KEYS_FILE:-}" ]]; then
  EXTRA+=(--api-keys-file "$AHANAFLOW_API_KEYS_FILE")
fi
if [[ "${AHANAFLOW_TLS:-0}" =~ ^(1|true|yes|on)$ ]]; then
  EXTRA+=(--tls)
  # Auto-generate self-signed certs if missing
  if [[ ! -f "$AHANAFLOW_DATA_ROOT/tls/server.crt" ]]; then
    echo "TLS enabled but certs missing — generating self-signed material..."
    AHANAFLOW_DATA_ROOT="$AHANAFLOW_DATA_ROOT" "$ROOT/scripts/generate_ahanaflow_tls.sh"
  fi
fi

echo "Starting AhanaFlow self-host on ${AHANAFLOW_HOST}:${AHANAFLOW_PORT} tls=${AHANAFLOW_TLS:-0}"
echo "WAL: $AHANAFLOW_DATA_ROOT/$AHANAFLOW_WAL"
exec python3 "$ROOT/scripts/ahanaflow_selfhost_server.py" \
  --host "$AHANAFLOW_HOST" \
  --port "$AHANAFLOW_PORT" \
  --wal "$AHANAFLOW_WAL" \
  "${EXTRA[@]}"
