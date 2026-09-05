# Test Today — Paper / Mock Only

**Live capital stays OFF.** This path uses `MockBroker` + `FundingService`.

## One command

```bash
chmod +x scripts/run_paper_test_today.sh
./scripts/run_paper_test_today.sh
```

That installs deps, runs pytest, smoke (BUY + stop arm), and the full paper cycle (BUY → stop → market SELL).

## What “ready to test today” means

| Check | Expected |
|-------|----------|
| Momentum refuses RSI dip | HOLD |
| Momentum stacked strength | BUY |
| Execution | Mock BUY fill |
| Protection | Broker STOP armed on fill |
| Stop hit | Market SELL, position closed |
| Daily loss kill | Blocks new BUYs (unit tested) |

## Manual pieces

```bash
export PAPER_MODE=1 USE_MOCK_BROKER=1 OTLP_ENABLED=false PYTHONPATH=.

# Unit tests
pytest -q tests

# Smoke only
python3 scripts/smoke_autonomous_trade.py

# Full cycle
python3 scripts/paper_cycle.py

# Optional UI (funding page; no OAuth required in paper mode)
streamlit run app/main.py
```

## Env flags

| Var | Purpose |
|-----|---------|
| `PAPER_MODE=1` | Sandbox defaults, OAuth not required to start background trader |
| `USE_MOCK_BROKER=1` | Force `MockBroker` (no E*TRADE / Alpaca) |
| `OTLP_ENABLED=false` | Skip tracing noise locally |

## Do not do today

- Flip sandbox off / live broker
- Skip the protective-stop assertion
- Trust research without yfinance unless you install it (`pip install yfinance`) for live quotes

When the paper cycle prints `PAPER CYCLE PASS`, you are clear to exercise Tim’s P0 rules in mock today.

## Tim Cockpit (AI + engines)

```bash
export PAPER_MODE=1 USE_MOCK_BROKER=1 OTLP_ENABLED=false PYTHONPATH=.
streamlit run app/main.py
```

Default home is **Tim Cockpit**:
- Chat Tim (`analyze NVDA`, `snipe AAPL`, `show risk`)
- Momentum gate checklist + confidence
- **PAPER SNIPE** arms broker stop on fill
- Persistent risk strip (capital · daily PnL · open · mode)

Engines decide. AI narrates. Council stays secondary.
