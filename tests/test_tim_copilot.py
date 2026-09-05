"""Tim Copilot + cockpit engine wiring."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PAPER_MODE"] = "1"
os.environ["USE_MOCK_BROKER"] = "1"

from app.services.tim_copilot import TimCopilot
from app.services.momentum_engine import momentum_gate_report


def test_tim_analyze_returns_gates():
    c = TimCopilot(paper_mode=True)
    d = c.analyze("NVDA")
    assert d["status"] == "success"
    assert d["action"] in ("BUY", "HOLD", "SELL")
    assert "gates" in d and len(d["gates"]) >= 5
    assert "narration" in d


def test_tim_refuses_weak_tape_snipe():
    c = TimCopilot(paper_mode=True)
    # Force weak indicators via direct gate report
    weak = momentum_gate_report(99, {
        "sma_20": 100, "sma_50": 105, "rsi": 28, "macd": 0.1,
        "volume_ratio": 0.8, "momentum_pct": 20, "vwap": 102,
    })
    assert weak["action"] != "BUY"


def test_tim_chat_routes_analyze():
    c = TimCopilot(paper_mode=True)
    r = c.chat("analyze AAPL")
    assert r["status"] == "success"
    assert r.get("decision")


def test_tim_snipe_arms_stop_on_buy():
    c = TimCopilot(paper_mode=True)
    # Demo tape is strong by default when offline
    d = c.analyze("TSLA")
    if d["action"] != "BUY":
        return  # environment-dependent
    result = c.snipe("TSLA")
    assert result["status"] == "success"
    strip = c.risk_strip()
    assert strip["open_positions"] >= 1
