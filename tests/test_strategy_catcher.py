from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.strategy_catcher import (
    catch_symbol,
    detect_a_orb,
    detect_b_vwap,
    detect_c_premarket,
    detect_d_peak_valley,
    detect_kona_latch,
    kona_latch_enabled,
)

ET = ZoneInfo("America/New_York")


def _bar(day, hour, minute, o, h, l, c, volume=1000):
    return {
        "ts": datetime(2026, 9, 1, hour, minute, tzinfo=ET),
        "open": o, "high": h, "low": l, "close": c, "volume": volume,
    }


def test_orb_long_on_synthetic_bars(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AHANA_BRAIN_URL", raising=False)
    rows = []
    for m in range(30, 45):
        rows.append(_bar(None, 9, m, 100.0, 101.0, 99.8, 100.5))
    rows.append(_bar(None, 9, 50, 101.2, 102.4, 101.0, 102.2))
    cards = detect_a_orb("AAPL", rows, deployed_out=0.0, name_deployed=0.0, now=rows[-1]["ts"], account_type="CASH")
    assert cards
    assert cards[0].setup == "A"
    assert cards[0].side == "BUY"
    assert cards[0].shares >= 1
    assert cards[0].invalidation <= 99.8 + 0.01


def test_vwap_reclaim_on_synthetic_bars(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = [
        _bar(None, 10, 0, 100, 100, 100, 100, 100),
        _bar(None, 10, 1, 99, 99, 99, 99, 100),
        _bar(None, 10, 2, 102, 102, 102, 102, 1),
    ]
    cards = detect_b_vwap("MSFT", rows, deployed_out=0.0, name_deployed=0.0, now=rows[-1]["ts"], account_type="CASH")
    assert cards
    assert cards[0].setup == "B"
    assert cards[0].side == "BUY"


def test_premarket_range_break(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = []
    for m in range(0, 60, 5):
        rows.append(_bar(None, 7, m, 50.0, 51.0, 49.5, 50.2))
        rows.append(_bar(None, 8, m, 50.0, 51.0, 49.5, 50.1))
    rows.append(_bar(None, 9, 35, 51.5, 52.4, 51.4, 52.2))
    cards = detect_c_premarket("NVDA", rows, deployed_out=0.0, name_deployed=0.0, now=rows[-1]["ts"], account_type="CASH")
    assert cards
    assert cards[0].setup == "C"
    assert cards[0].side == "BUY"


def test_peak_trim_leaves_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = []
    px = 100.0
    for i in range(20):
        px = 100 + i
        rows.append(_bar(None, 11, i, px, px + 0.5, px - 0.2, px))
    holdings = {"AAPL": {"qty": 8, "price": 100, "market_value": 800}}
    cards = detect_d_peak_valley(
        "AAPL", rows, holdings=holdings,
        deployed_out=800, name_deployed=800, now=rows[-1]["ts"], account_type="CASH",
    )
    assert cards
    assert cards[0].setup == "D"
    assert cards[0].side == "SELL"
    assert cards[0].shares < 8
    assert "runner" in cards[0].why.lower()


def test_kona_latch_default_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AHANA_KONA_LATCH", raising=False)
    assert kona_latch_enabled() is False
    rows = [
        _bar(None, 10, 0, 10, 11, 9, 10),
        _bar(None, 10, 1, 10.2, 10.8, 9.2, 10.1),
        _bar(None, 10, 2, 10.5, 11.4, 10.4, 11.3),
    ]
    assert detect_kona_latch("SPY", rows, deployed_out=0, name_deployed=0, now=rows[-1]["ts"], account_type="CASH") == []
    monkeypatch.setenv("AHANA_KONA_LATCH", "1")
    cards = detect_kona_latch("SPY", rows, deployed_out=0, name_deployed=0, now=rows[-1]["ts"], account_type="CASH")
    assert cards
    assert cards[0].experimental is True
    assert cards[0].setup == "KONA"


def test_catch_symbol_sizes_under_sleeve(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = []
    for m in range(30, 45):
        rows.append(_bar(None, 9, m, 100.0, 101.0, 99.8, 100.5))
    rows.append(_bar(None, 10, 0, 102, 103, 101.5, 102.5))
    cards = catch_symbol("AAPL", rows, deployed_out=8000, account_type="CASH")
    assert cards
    for card in cards:
        if card.side == "BUY":
            assert card.size_usd <= 2000 + 1
            assert card.remaining_budget == 2000
