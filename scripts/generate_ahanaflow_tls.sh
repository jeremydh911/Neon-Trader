#!/usr/bin/env bash
# Generate self-signed TLS material for AhanaFlow self-host (Tim memory).
# Certs land under AHANAFLOW_DATA_ROOT/tls/ (default: data/ahanaflow/tls/).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${AHANAFLOW_DATA_ROOT:-$ROOT/data/ahanaflow}"
TLS_DIR="$DATA_ROOT/tls"
DAYS="${AHANAFLOW_TLS_DAYS:-825}"
CN="${AHANAFLOW_TLS_CN:-localhost}"

mkdir -p "$TLS_DIR"
CERT="$TLS_DIR/server.crt"
KEY="$TLS_DIR/server.key"

if [[ -f "$CERT" && -f "$KEY" && "${AHANAFLOW_TLS_FORCE:-0}" != "1" ]]; then
  echo "TLS material already exists:"
  echo "  cert: $CERT"
  echo "  key:  $KEY"
  echo "Set AHANAFLOW_TLS_FORCE=1 to regenerate."
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" \
  -out "$CERT" \
  -days "$DAYS" \
  -subj "/CN=${CN}" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 "$KEY"
chmod 644 "$CERT"

echo "Generated AhanaFlow TLS material:"
echo "  AHANAFLOW_TLS=1"
echo "  AHANAFLOW_TLS_CERT=tls/server.crt"
echo "  AHANAFLOW_TLS_KEY=tls/server.key"
echo "  AHANAFLOW_TLS_CA=tls/server.crt   # self-signed trust anchor"
echo "  AHANAFLOW_DATA_ROOT=$DATA_ROOT"
echo
echo "Start server:  AHANAFLOW_TLS=1 ./scripts/run_ahanaflow_selfhost.sh"
echo "Client:        export AHANAFLOW_TLS=1 AHANAFLOW_TLS_CA=tls/server.crt"
