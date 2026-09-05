#!/usr/bin/env python3
"""
Paper cycle for TODAY — no OAuth, no live capital.

Runs: fund → momentum BUY → mock fill → broker stop armed → stop hit → market SELL.

Usage:
  ./scripts/run_paper_test_today.sh
  # or:
  PAPER_MODE=1 USE_MOCK_BROKER=1 PYTHONPATH=. python3 scripts/paper_cycle.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PAPER_MODE", "1")
os.environ.setdefault("USE_MOCK_BROKER", "1")
os.environ.setdefault("OTLP_ENABLED", "false")

from app.services.funding_service import FundingService
from app.services.autonomous_trader import AutonomousTrader
from app.services.background_trader import BackgroundTraderService
from app.services.mock_broker import MockBroker
from app.services.momentum_engine import evaluate_momentum_entry


def _strong_indicators(price: float = 50.0) -> dict:
    return {
        "price": price,
        "sma_20": price * 0.98,
        "sma_50": price * 0.95,
        "rsi": 58.0,
        "macd": 0.4,
        "volume_ratio": 2.1,
        "momentum_pct": 72.0,
        "vwap": price * 0.99,
        "atr": price * 0.015,
    }


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"OK:   {msg}")


def main() -> int:
    print("=" * 60)
    print("NEON TRADER — PAPER CYCLE (mock broker, no live money)")
    print("=" * 60)

    funding_path = Path("/tmp/neon_paper_cycle_funding.json")
    if funding_path.exists():
        funding_path.unlink()

    fs = FundingService(data_file=funding_path)
    fs.add_funds(10_000.0)
    fs.allocate_to_portfolio(5_000.0)
    summary = fs.get_balance_summary()
    _ok(f"Funded paper account — allocated ${summary.get('allocated_to_portfolio', 0):,.2f}")

    weak = evaluate_momentum_entry(99, {
        "sma_20": 100, "sma_50": 105, "rsi": 28, "macd": 0.1,
        "volume_ratio": 0.8, "momentum_pct": 20, "vwap": 102,
    })
    if weak[0] == "BUY":
        _fail(f"Momentum engine bought a dip: {weak}")
    _ok(f"Dip rejected → {weak[0]} ({weak[2]})")

    price = 50.0
    indicators = _strong_indicators(price)
    strong = evaluate_momentum_entry(price, indicators)
    if strong[0] != "BUY":
        _fail(f"Expected BUY on stacked momentum, got {strong}")
    _ok(f"Momentum BUY → conf={strong[1]:.2f} ({strong[2]})")

    broker = MockBroker()
    trader = AutonomousTrader(
        memory_service=None,
        llm_service=None,
        council=None,
        broker_type="mock",
        use_sandbox=True,
    )
    trader.broker = broker
    trader.enable_autonomous_trading(True)

    bg = BackgroundTraderService(
        autonomous_trader=trader,
        oauth_service=None,
        pricing_service=None,
        trader_tools=None,
        funding_service=fs,
        use_sandbox=True,
    )
    bg.config["require_oauth"] = False
    bg.config["allow_start_without_oauth"] = True
    bg.config["min_council_approval"] = 50

    bg.research_history.append({
        "symbol": "PAPER",
        "action_recommended": "BUY",
        "price": price,
        "confidence": 90,
        "indicators": indicators,
        "technical_indicators": indicators,
    })

    print("-" * 60)
    print("Before BUY:", broker.get_trades())
    bg._execution_phase()
    trades_after_buy = broker.get_trades()
    print("After BUY:", trades_after_buy)

    buys = [t for t in trades_after_buy if t.side.lower() == "buy"]
    stops = [t for t in trades_after_buy if str(t.order_type).lower() == "stop"]
    if not buys:
        _fail("No BUY fill on mock broker")
    if not stops:
        _fail("Protective stop was NOT armed after fill — cannot test today safely")
    _ok(f"BUY filled ({len(buys)}) + protective STOP armed ({len(stops)}) @ {stops[-1].stop_price}")

    positions = trader.get_positions_status()
    if "PAPER" not in positions:
        _fail("Position not tracked in stop-loss manager after fill")
    stop_px = float(positions["PAPER"].get("stop_loss_price") or stops[-1].stop_price)
    _ok(f"Managed position PAPER stop={stop_px}")

    exit_px = stop_px - 0.05
    results = trader.manage_open_positions({"PAPER": exit_px})
    print("Exit results:", results)
    if not results or not results[0].get("exited"):
        _fail("Stop did not trigger / exit sell did not fire")

    sells = [
        t for t in broker.get_trades()
        if t.side.lower() == "sell" and str(t.order_type).lower() == "market"
    ]
    if not sells:
        _fail("No market SELL after stop — still riding the loser")
    _ok(f"Stop hit → market SELL executed ({len(sells)} sell(s))")

    if "PAPER" in trader.get_positions_status():
        _fail("Position still open after stop exit")
    _ok("Position closed — no rider left")

    print("-" * 60)
    print("Trade history:", bg.get_trade_history())
    print("Broker tape:", broker.get_trades())
    print("=" * 60)
    print("PAPER CYCLE PASS — ready to test today (mock / sandbox only)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
