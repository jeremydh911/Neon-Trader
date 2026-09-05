"""Tim P0: momentum entries, broker-backed exits, daily loss, status normalize."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.momentum_engine import (
    evaluate_momentum_entry,
    compute_stop_and_target,
    risk_based_shares,
    MomentumConfig,
)
from app.services.stop_loss_manager import StopLossManager, StopLossConfig
from app.services.autonomous_trader import AutonomousTrader
from app.services.background_trader import BackgroundTraderService
from app.services.mock_broker import MockBroker
from app.services.funding_service import FundingService


def _strong_momentum_indicators(price=100.0):
    return {
        "price": price,
        "sma_20": 98.0,
        "sma_50": 95.0,
        "rsi": 58.0,
        "macd": 0.5,
        "volume_ratio": 2.0,
        "momentum_pct": 75.0,
        "vwap": 99.0,
        "atr": 1.5,
    }


def test_momentum_buys_strength_not_oversold():
    # Classic oversold mean-reversion setup must NOT buy
    weak = {
        "sma_20": 100,
        "sma_50": 105,
        "rsi": 28,
        "macd": 0.1,
        "volume_ratio": 0.8,
        "momentum_pct": 20,
        "vwap": 102,
    }
    action, conf, reason = evaluate_momentum_entry(99, weak)
    assert action == "HOLD", f"should not dip-buy: {reason}"

    strong = _strong_momentum_indicators()
    action, conf, reason = evaluate_momentum_entry(100, strong)
    assert action == "BUY", reason
    assert conf >= 0.55


def test_trailing_stop_never_loosens_below_initial():
    mgr = StopLossManager(StopLossConfig(use_trailing=True, trailing_percent=1.5, default_percent=2.0))
    pos = mgr.open_position("AAA", entry_price=100.0, quantity=10, stop_loss_percent=2.0)
    initial = pos.initial_stop_loss
    # Price dips below entry — trailing must not undercut hard stop
    exited, _ = mgr.update_position("AAA", 99.0)
    assert not exited
    pos = mgr.positions["AAA"]
    assert pos.effective_stop() >= initial - 1e-9


def test_take_profit_triggers_exit():
    mgr = StopLossManager(StopLossConfig(default_take_profit_percent=3.0, use_trailing=False))
    mgr.open_position("BBB", entry_price=100.0, quantity=5, take_profit_percent=3.0)
    exited, msg = mgr.update_position("BBB", 103.5)
    assert exited
    assert "TAKE PROFIT" in msg
    assert "BBB" not in mgr.positions


def test_stop_triggers_and_broker_sells():
    broker = MockBroker()
    trader = AutonomousTrader(memory_service=None, council=None, use_sandbox=True)
    trader.broker = broker
    trader.open_position_with_stop_loss("CCC", entry_price=100.0, quantity=10, stop_loss_percent=2.0)
    # buy + protective stop
    assert len(broker.get_trades()) >= 1
    assert any(t.order_type == "stop" for t in broker.get_trades())

    exited, msg = trader.update_position_price("CCC", 97.0, execute_exit=True)
    assert exited
    sells = [t for t in broker.get_trades() if t.side.lower() == "sell" and t.order_type == "market"]
    assert len(sells) >= 1
    assert trader._daily_pnl < 0


def test_daily_loss_blocks_new_entries():
    trader = AutonomousTrader(memory_service=None, council=None, use_sandbox=True)
    trader.broker = MockBroker()
    trader._roll_daily_pnl(10_000)
    trader._starting_capital_today = 10_000
    trader._daily_pnl = -250  # 2.5% > 2% max
    assert trader._passes_risk_check("DDD", "BUY", 10_000) is False


def test_placed_status_normalizes_to_success():
    trader = AutonomousTrader(memory_service=None, council=None, use_sandbox=True)

    class PlacedBroker:
        connected = True

        def place_order(self, **kwargs):
            return {"status": "PLACED", "order_id": "E-1"}

    trader.broker = PlacedBroker()
    result = trader.execute_order("EEE", "BUY", 1)
    assert result["status"] == "SUCCESS"
    assert result["broker_status"] == "PLACED"


def test_risk_based_shares_caps_loss():
    shares = risk_based_shares(capital=10_000, entry_price=100, stop_price=98, risk_fraction=0.01)
    # $100 risk / $2 per share = 50, also capped by 5% notional = 5 shares
    assert shares == 5


def test_background_arms_stop_after_buy(tmp_path):
    fs = FundingService(data_file=tmp_path / "funding.json")
    fs.add_funds(5000.0)
    fs.allocate_to_portfolio(2000.0)

    broker = MockBroker()
    trader = AutonomousTrader(memory_service=None, council=None, use_sandbox=True)
    trader.broker = broker

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
        "symbol": "MOM",
        "action_recommended": "BUY",
        "price": 20.0,
        "indicators": _strong_momentum_indicators(20.0),
        "technical_indicators": _strong_momentum_indicators(20.0),
        "confidence": 90,
    })
    bg._execution_phase()

    trades = bg.get_trade_history()
    assert len(trades) >= 1
    assert "MOM" in trader.get_positions_status()
    # Market buy + broker stop
    assert len(broker.get_trades()) >= 2
    assert any(t.order_type == "stop" for t in broker.get_trades())


def test_perform_research_exists():
    trader = AutonomousTrader(memory_service=None, council=None, use_sandbox=True)
    trader.broker = MockBroker()
    result = trader.perform_research("AAPL")
    assert "indicators" in result
    assert "confidence" in result


def test_compute_stop_and_target_uses_atr():
    levels = compute_stop_and_target(100.0, {"atr": 2.0}, MomentumConfig(use_atr_stops=True, atr_stop_multiplier=1.5))
    assert levels["stop_loss_price"] < 100
    assert levels["take_profit_price"] > 100
    assert levels["take_profit_pct"] >= levels["stop_loss_pct"]
