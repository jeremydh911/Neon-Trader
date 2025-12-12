# Autonomous Trading Smoke Test

This document explains how to run a local smoke test to verify autonomous trading works in sandbox mode (no real broker required).

Steps:

1. Ensure your virtualenv is activated and project dependencies are installed.

2. Run the smoke script:

```bash
python scripts/smoke_autonomous_trade.py
```

Expected output:
- `Before execution: trades= []`
- `After execution: trades= [...]` with at least one `MockTrade`
- `Trade history:` showing an executed trade record

3) Run the project's tests (from project root):

```bash
cd ~/Desktop/neon-trader-gpu
pytest -q tests
```

3. Run the project's tests (from project root):

```bash
cd ~/Desktop/neon-trader-gpu
pytest -q tests
```

Notes:
- The smoke script uses `MockBroker` and `FundingService` and does not touch any external APIs.
- If you want a full streamlit run, start the app and ensure `FundingService`'s `funding.json` has allocation available for trades.
