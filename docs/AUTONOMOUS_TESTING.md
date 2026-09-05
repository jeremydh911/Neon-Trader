# Autonomous Trading Smoke Test

Prefer the full paper readiness path:

```bash
./scripts/run_paper_test_today.sh
```

Details: [TEST_TODAY.md](TEST_TODAY.md)

## Quick smoke only

```bash
export PAPER_MODE=1 USE_MOCK_BROKER=1 OTLP_ENABLED=false PYTHONPATH=.
python3 scripts/smoke_autonomous_trade.py
```

Expected:
- Mock BUY fill
- Protective STOP armed

## Full paper cycle

```bash
python3 scripts/paper_cycle.py
```

Expected:
- Dip rejected
- Momentum BUY
- Stop armed
- Stop hit → market SELL
- Position closed

## Pytest

```bash
pytest -q tests
```

Notes:
- Uses `MockBroker` + `FundingService` — no external broker APIs.
- Live capital stays OFF in this path.
