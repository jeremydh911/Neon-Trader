#!/usr/bin/env bash
# One-command paper readiness check for today.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PAPER_MODE=1
export USE_MOCK_BROKER=1
export OTLP_ENABLED=false
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "==> Installing deps (if needed)"
python3 -m pip install -q -r requirements.txt

echo "==> Unit tests"
python3 -m pytest -q tests

echo "==> Smoke (BUY + stop arm)"
python3 scripts/smoke_autonomous_trade.py

echo "==> Full paper cycle (BUY → stop → SELL)"
python3 scripts/paper_cycle.py

echo
echo "All paper checks passed."
echo "Optional UI (no OAuth required for funding page):"
echo "  OTLP_ENABLED=false PYTHONPATH=$ROOT streamlit run app/main.py"
echo "Keep live capital OFF. Paper/mock only."
