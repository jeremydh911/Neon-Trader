#!/usr/bin/env bash
# Start a self-hosted AhanaFlow vector server for Neon Trader / Tim memory.
# Preferred over cloud API — trade memory stays on your box.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AHANA="${ROOT}/vendor/AhanaFlow"
WAL="${AHANAFLOW_WAL:-${ROOT}/data/ahanaflow/tim_memory.wal}"
HOST="${AHANAFLOW_HOST:-127.0.0.1}"
PORT="${AHANAFLOW_PORT:-9634}"

if [[ ! -d "$AHANA" ]]; then
  echo "Missing vendor/AhanaFlow — run: git submodule update --init vendor/AhanaFlow" >&2
  exit 1
fi

mkdir -p "$(dirname "$WAL")"
export PYTHONPATH="${AHANA}:${PYTHONPATH:-}"

echo "Starting AhanaFlow vector server on ${HOST}:${PORT}"
echo "WAL: ${WAL}"
echo "Then: export AHANAFLOW_MODE=selfhosted AHANAFLOW_HOST=${HOST} AHANAFLOW_PORT=${PORT}"

exec python3 -m backend.vector_server.cli serve --wal "$WAL" --host "$HOST" --port "$PORT"
