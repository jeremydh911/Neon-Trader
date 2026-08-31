from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.strategy_catcher import (
    PLAYBOOK,
    PLAYBOOK_CAPTION,
    catch_symbol,
    detect_a_premarket_gap,
    detect_b_open_drive,
    detect_c_vwap,
    detect_d_ah_follow,
    detect_holdings_peak_valley,
    detect_kona_latch,
    kona_latch_enabled,
)

ET = ZoneInfo("America/New_York")
PRIOR = datetime(2026, 8, 31).date()


def _bar(day, hour, minute, o, h, l, c, volume=1000):
    if day is None:
        y, mo, d = 2026, 9, 1
    else:
        y, mo, d = day.year, day.month, day.day
    return {
        "ts": datetime(y, mo, d, hour, minute, tzinfo=ET),
        "open": o, "high": h, "low": l, "close": c, "volume": volume,
    }


def _prior_rth(close=100.0):
    return _bar(PRIOR, 15, 55, close, close + 0.1, close - 0.1, close)


def _kw(rows, **extra):
    kw = dict(deployed_out=0.0, name_deployed=0.0, now=rows[-1]["ts"], account_type="CASH")
    kw.update(extra)
    return kw


def test_playbook_letters_locked():
    letters = [row["letter"] for row in PLAYBOOK]
    assert letters == ["A", "B", "C", "D"]
    assert PLAYBOOK[0]["name"] == "Premarket gap"
    assert "7:00–9:20" in PLAYBOOK[0]["window"] or "07:00–09:20" in PLAYBOOK[0]["window"]
    assert "Open drive" in PLAYBOOK[1]["name"]
    assert "VWAP reclaim" in PLAYBOOK[2]["name"]
    assert "AH follow" in PLAYBOOK[3]["name"]
    cap = PLAYBOOK_CAPTION.lower()
    assert "premarket gap" in cap
    assert "open drive" in cap
    assert "vwap reclaim" in cap
    assert "ah follow" in cap
    assert "holdings overlay" in cap
    assert "kona latch" in cap


def test_a_premarket_gap_continuation(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AHANA_BRAIN_URL", raising=False)
    rows = [_prior_rth(100.0)]
    for m in range(0, 15):
        rows.append(_bar(None, 7, m, 101.0, 101.4, 100.2, 101.2))
    rows.append(_bar(None, 8, 0, 101.3, 101.5, 101.1, 101.4))
    cards = detect_a_premarket_gap("AAPL", rows, **_kw(rows))
    assert cards
    assert cards[0].setup == "A"
    assert cards[0].side == "BUY"
    assert cards[0].flatten_time == "09:20"
    assert "Premarket gap" in cards[0].why
    assert "continuation" in cards[0].why.lower()


def test_b_open_drive_orb_break(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = [_prior_rth(100.0)]
    for m in range(30, 45):
        rows.append(_bar(None, 9, m, 100.5, 101.0, 99.8, 100.6))
    rows.append(_bar(None, 9, 50, 101.2, 102.4, 101.0, 102.2))
    cards = detect_b_open_drive("AAPL", rows, **_kw(rows))
    assert cards
    assert cards[0].setup == "B"
    assert cards[0].side == "BUY"
    assert cards[0].shares >= 1
    assert cards[0].invalidation <= 99.8 + 0.01
    assert cards[0].flatten_time == "11:00"
    assert "Open drive" in cards[0].why


def test_c_vwap_reclaim(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = []
    for i in range(4):
        rows.append(_bar(None, 10, i, 98.0, 99.0, 97.0, 97.5, 1000))
    rows.append(_bar(None, 10, 5, 102.0, 102.4, 101.8, 102.0, 100))
    cards = detect_c_vwap("MSFT", rows, **_kw(rows))
    assert cards
    assert cards[0].setup == "C"
    assert cards[0].side == "BUY"
    assert cards[0].flatten_time == "15:50"
    assert "VWAP reclaim" in cards[0].why


def test_d_ah_follow(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = [
        _bar(None, 9, 30, 100.0, 110.0, 100.0, 104.0),
        _bar(None, 15, 55, 108.80, 108.90, 108.70, 108.80),
    ]
    for m in range(0, 15):
        rows.append(_bar(None, 16, m, 109.0, 109.15, 108.90, 109.10))
    rows.append(_bar(None, 16, 20, 109.1, 109.2, 109.0, 109.15))
    cards = detect_d_ah_follow("NVDA", rows, **_kw(rows))
    assert cards
    assert cards[0].setup == "D"
    assert cards[0].side == "BUY"
    assert cards[0].flatten_time == "20:00"
    assert "AH follow" in cards[0].why
    assert "peak" not in cards[0].why.lower()
    assert "valley" not in cards[0].why.lower()


def test_peak_valley_is_holdings_overlay_not_d(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = []
    px = 100.0
    for i in range(20):
        px = 100 + i
        rows.append(_bar(None, 11, i, px, px + 0.5, px - 0.2, px))
    holdings = {"AAPL": {"qty": 8, "price": 100, "market_value": 800}}
    cards = detect_holdings_peak_valley(
        "AAPL", rows, holdings=holdings,
        deployed_out=800, name_deployed=800, now=rows[-1]["ts"], account_type="CASH",
    )
    assert cards
    assert cards[0].setup == "HOLDINGS"
    assert cards[0].setup != "D"
    assert cards[0].side == "SELL"
    assert cards[0].shares < 8
    assert "runner" in cards[0].why.lower()
    assert "holdings overlay" in cards[0].why.lower()


def test_letters_are_not_the_old_swapped_map(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    # Opening-range break at 9:50 is B (open drive), not A.
    orb_rows = [_prior_rth(100.0)]
    for m in range(30, 45):
        orb_rows.append(_bar(None, 9, m, 100.5, 101.0, 99.8, 100.6))
    orb_rows.append(_bar(None, 9, 50, 101.2, 102.4, 101.0, 102.2))
    assert detect_a_premarket_gap("AAPL", orb_rows, **_kw(orb_rows)) == []
    b_cards = detect_b_open_drive("AAPL", orb_rows, **_kw(orb_rows))
    assert b_cards and b_cards[0].setup == "B"

    # VWAP reclaim at 10:05 is C, not B.
    vwap_rows = []
    for i in range(4):
        vwap_rows.append(_bar(None, 10, i, 98.0, 99.0, 97.0, 97.5, 1000))
    vwap_rows.append(_bar(None, 10, 5, 102.0, 102.4, 101.8, 102.0, 100))
    assert detect_b_open_drive("MSFT", vwap_rows, **_kw(vwap_rows)) == []
    c_cards = detect_c_vwap("MSFT", vwap_rows, **_kw(vwap_rows))
    assert c_cards and c_cards[0].setup == "C"

    # Peak trim is HOLDINGS, never D.
    peak_rows = []
    for i in range(20):
        px = 100 + i
        peak_rows.append(_bar(None, 11, i, px, px + 0.5, px - 0.2, px))
    holdings = {"AAPL": {"qty": 8, "price": 100, "market_value": 800}}
    assert detect_d_ah_follow("AAPL", peak_rows, holdings=holdings, **_kw(peak_rows)) == []
    pv = detect_holdings_peak_valley("AAPL", peak_rows, holdings=holdings, **_kw(peak_rows))
    assert pv and pv[0].setup == "HOLDINGS"


def test_kona_latch_default_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AHANA_KONA_LATCH", raising=False)
    assert kona_latch_enabled() is False
    rows = [
        _bar(None, 10, 0, 10, 11, 9, 10),
        _bar(None, 10, 1, 10.2, 10.8, 9.2, 10.1),
        _bar(None, 10, 2, 10.5, 11.4, 10.4, 11.3),
    ]
    assert detect_kona_latch("SPY", rows, **_kw(rows)) == []
    monkeypatch.setenv("AHANA_KONA_LATCH", "1")
    cards = detect_kona_latch("SPY", rows, **_kw(rows))
    assert cards
    assert cards[0].experimental is True
    assert cards[0].setup == "KONA"


def test_catch_symbol_sizes_under_sleeve(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    rows = [_prior_rth(100.0)]
    for m in range(30, 45):
        rows.append(_bar(None, 9, m, 100.5, 101.0, 99.8, 100.6))
    rows.append(_bar(None, 10, 0, 102, 103, 101.5, 102.5))
    cards = catch_symbol("AAPL", rows, deployed_out=8000, account_type="CASH")
    assert cards
    assert any(card.setup == "B" for card in cards)
    assert all(card.setup != "D" or "AH follow" in card.why for card in cards)
    for card in cards:
        if card.side == "BUY":
            assert card.size_usd <= 2000 + 1
            assert card.remaining_budget == 2000
