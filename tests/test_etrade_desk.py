import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.desk_risk import DeskRiskGate, DeskRiskState, deployed_out_from_positions, is_ira_account
from app.services.etrade_config import is_sandbox, etrade_hosts, allow_market_orders
from app.services.working_order_follower import next_follow_limit, follow_instructions, normalize_open_orders
from app.services import broker as broker_mod
from app.services.broker import ETradeBroker


ET = ZoneInfo("America/New_York")


def _et(hour, minute=0, day=3):
    # Tuesday 2026-09-01 is a weekday
    return datetime(2026, 9, 1, hour, minute, tzinfo=ET)


def test_default_sandbox(monkeypatch):
    monkeypatch.delenv("ETRADE_ENV", raising=False)
    monkeypatch.delenv("ETRADE_SANDBOX", raising=False)
    assert is_sandbox() is True
    hosts = etrade_hosts()
    assert hosts["host"] == "https://apisb.etrade.com"
    assert hosts["api_v1"] == "https://apisb.etrade.com/v1"
    assert "etwssandbox" not in hosts["host"]


def test_production_only_with_env(monkeypatch):
    monkeypatch.setenv("ETRADE_ENV", "production")
    assert is_sandbox() is False
    assert etrade_hosts()["host"] == "https://api.etrade.com"


def test_no_stale_sandbox_host():
    src = open("app/services/broker.py").read() + open("app/services/etrade_config.py").read()
    assert "etwssandbox" not in src


def test_market_orders_disabled():
    assert allow_market_orders() is False
    gate = DeskRiskGate()
    result = gate.evaluate(
        symbol="AAPL", qty=1, side="BUY", order_type="MARKET", price=100,
        now=_et(10, 0), skip_session_check=True,
    )
    assert result["ok"] is False
    assert "LIMIT" in result["message"]


def test_session_phases_and_flags():
    gate = DeskRiskGate()
    assert gate.phase(_et(5, 0)) == "blackout"
    assert gate.phase(_et(7, 30)) == "premarket"
    assert gate.phase(_et(10, 0)) == "regular"
    assert gate.phase(_et(17, 0)) == "afterhours"
    assert gate.phase(_et(21, 0)) == "overnight"
    assert gate.order_session_flags(_et(7, 30))["marketSession"] == "EXTENDED"
    assert gate.order_session_flags(_et(10, 0))["marketSession"] == "REGULAR"
    assert gate.order_session_flags(_et(17, 0))["marketSession"] == "EXTENDED"
    for flags in (
        gate.order_session_flags(_et(7, 30)),
        gate.order_session_flags(_et(17, 0)),
    ):
        assert flags["priceType"] == "LIMIT"
        assert flags["orderTerm"] == "GOOD_FOR_DAY"
        assert flags["extended"] is True


def test_blackout_and_overnight_block_orders():
    gate = DeskRiskGate()
    blackout = gate.evaluate(symbol="AAPL", qty=1, side="BUY", order_type="LIMIT", price=10, now=_et(5, 30))
    assert blackout["ok"] is False and "blackout" in blackout["message"].lower()
    overnight = gate.evaluate(symbol="AAPL", qty=1, side="BUY", order_type="LIMIT", price=10, now=_et(21, 0))
    assert overnight["ok"] is False and "overnight" in overnight["message"].lower()


def test_cancel_before_roll_window():
    gate = DeskRiskGate()
    assert gate.in_cancel_before_roll_window(_et(9, 28)) is True
    assert gate.in_cancel_before_roll_window(_et(9, 29)) is True
    assert gate.in_cancel_before_roll_window(_et(9, 30)) is False
    assert gate.in_cancel_before_roll_window(_et(9, 0)) is False


def test_hawaii_offset_et_minus_6_in_august():
    gate = DeskRiskGate()
    clock = gate.hawaii_clock(_et(13, 0))  # 1pm ET -> 7am HT
    assert clock["et"] == "13:00"
    assert clock["ht"] == "07:00"
    assert "ET-6" in clock["offset_note"]


def test_no_crypto_on_rest_order_api():
    gate = DeskRiskGate()
    for sym in ("BTC", "ETH", "BTC/USD", "ETH-USD", "BTCUSD"):
        result = gate.evaluate(
            symbol=sym, qty=1, side="BUY", order_type="LIMIT", price=100,
            now=_et(10, 0),
        )
        assert result["ok"] is False
        assert "crypto" in result["message"].lower()
    ok = gate.evaluate(symbol="AAPL", qty=1, side="BUY", order_type="LIMIT", price=100, now=_et(10, 0))
    assert ok["ok"] is True


def test_ten_k_aggregate_out_cap():
    gate = DeskRiskGate()
    ok = gate.evaluate(
        symbol="AAPL", qty=40, side="BUY", order_type="LIMIT", price=100,
        deployed_out=6000, now=_et(10, 0),
    )
    assert ok["ok"] is True
    blocked = gate.evaluate(
        symbol="MSFT", qty=50, side="BUY", order_type="LIMIT", price=100,
        deployed_out=6000, now=_et(10, 0),
    )
    assert blocked["ok"] is False
    assert "10000" in blocked["message"] or "10,000" in blocked["message"]
    # Exits are not capped by deployed-out
    sell = gate.evaluate(
        symbol="AAPL", qty=50, side="SELL", order_type="LIMIT", price=100,
        deployed_out=10000, now=_et(10, 0), is_new_entry=False,
    )
    assert sell["ok"] is True


def test_pdt_not_enforced_day_trades_allowed():
    gate = DeskRiskGate()
    policy = gate.pdt_policy()
    assert policy["enforce_pdt"] is False
    assert policy["refuse_day_trades"] is False
    first = gate.evaluate(symbol="AAPL", qty=1, side="BUY", order_type="LIMIT", price=50, now=_et(10, 0))
    second = gate.evaluate(symbol="AAPL", qty=1, side="SELL", order_type="LIMIT", price=51, now=_et(11, 0), is_new_entry=False)
    third = gate.evaluate(symbol="AAPL", qty=1, side="BUY", order_type="LIMIT", price=52, now=_et(12, 0))
    assert first["ok"] and second["ok"] and third["ok"]
    assert first["pdt_enforced"] is False


def test_daily_loss_halt_new_entries_only():
    state = DeskRiskState(daily_realized_pnl=-250)
    gate = DeskRiskGate(state=state)
    buy = gate.evaluate(symbol="AAPL", qty=1, side="BUY", order_type="LIMIT", price=50, equity=10000, now=_et(10, 0))
    sell = gate.evaluate(symbol="AAPL", qty=1, side="SELL", order_type="LIMIT", price=50, equity=10000, now=_et(10, 0), is_new_entry=False)
    assert buy["ok"] is False
    assert sell["ok"] is True


def test_follow_afterhours_reprice():
    new_px = next_follow_limit("BUY", working_limit=10.00, bid=10.05, ask=10.07, last=10.06)
    assert new_px == 10.05
    unchanged = next_follow_limit("BUY", working_limit=10.00, bid=10.00, ask=10.02, last=10.01)
    assert unchanged is None
    orders = [{
        "order_id": "1", "symbol": "AAPL", "side": "BUY", "qty": 10,
        "limit_price": 10.0, "market_session": "EXTENDED", "price_type": "LIMIT",
    }]
    quotes = {"AAPL": {"bid": 10.12, "ask": 10.14, "last": 10.13}}
    inst = follow_instructions(orders, quotes)
    assert len(inst) == 1
    assert inst[0]["new_limit"] == 10.12
    assert inst[0]["market_session"] == "EXTENDED"
    assert inst[0]["order_term"] == "GOOD_FOR_DAY"


def test_normalize_open_orders():
    payload = {
        "OrdersResponse": {
            "Order": {
                "orderId": 99,
                "OrderDetail": [{
                    "limitPrice": 12.3,
                    "marketSession": "EXTENDED",
                    "priceType": "LIMIT",
                    "Instrument": [{"orderAction": "BUY", "quantity": 5, "Product": {"symbol": "MSFT"}}],
                }],
            }
        }
    }
    orders = normalize_open_orders(payload)
    assert orders[0]["symbol"] == "MSFT"
    assert orders[0]["market_session"] == "EXTENDED"


class _FakeOrderClient:
    def __init__(self):
        self.previews = []
        self.places = []

    def preview_equity_order(self, **kwargs):
        self.previews.append(kwargs)
        assert kwargs["priceType"] == "LIMIT"
        assert kwargs["orderTerm"] == "GOOD_FOR_DAY"
        assert "previewId" not in kwargs
        return {"PreviewOrderResponse": {"PreviewIds": {"previewId": "PV-1"}}}

    def place_equity_order(self, **kwargs):
        self.places.append(kwargs)
        assert "previewId" in kwargs
        return {"PlaceOrderResponse": {"OrderIds": [{"orderId": "OID-1"}]}}

    def list_orders(self, *args, **kwargs):
        return {"OrdersResponse": {"Order": []}}


def _connected_broker(monkeypatch, sandbox=True):
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "ck")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "cs")
    monkeypatch.setenv("ETRADE_ACCESS_TOKEN", "at")
    monkeypatch.setenv("ETRADE_ACCESS_TOKEN_SECRET", "ats")
    monkeypatch.setenv("ETRADE_ENV", "sandbox" if sandbox else "production")
    broker_mod.reset_broker_singleton()
    b = ETradeBroker(use_sandbox=sandbox)
    b.connected = True
    b.order_client = _FakeOrderClient()
    b.client = object()
    b._account_id_key = "acct"
    b.get_account = lambda: {"portfolio_value": 20000, "cash": 20000}
    b.get_positions = lambda: {}
    b.count_open_orders = lambda: 0
    return b


def test_preview_separate_from_place(monkeypatch):
    b = _connected_broker(monkeypatch, sandbox=True)
    preview = b.preview_order(
        symbol="AAPL", qty=1, side="BUY", order_type="limit",
        limit_price=10, now=_et(10, 0),
    )
    assert preview["status"] == "PREVIEW"
    assert preview["preview_id"] == "PV-1"
    assert b.order_client.places == []
    denied = b.place_order(
        symbol="AAPL", qty=1, side="BUY", order_type="limit",
        limit_price=10, now=_et(10, 0),
    )
    assert denied["status"] == "ERROR"
    assert "preview_id" in denied["message"]
    placed = b.place_order(
        symbol="AAPL", qty=1, side="BUY", order_type="limit",
        limit_price=10, preview_id="PV-1", now=_et(10, 0),
    )
    assert placed["status"] == "PLACED"
    assert b.order_client.places[0]["previewId"] == "PV-1"
    assert b.order_client.places[0]["marketSession"] == "REGULAR"


def test_premarket_uses_extended_gfd(monkeypatch):
    b = _connected_broker(monkeypatch)
    preview = b.preview_order(
        symbol="AAPL", qty=1, side="BUY", order_type="limit",
        limit_price=10, now=_et(8, 0),
    )
    assert preview["status"] == "PREVIEW"
    assert b.order_client.previews[0]["marketSession"] == "EXTENDED"
    assert b.order_client.previews[0]["orderTerm"] == "GOOD_FOR_DAY"
    assert b.order_client.previews[0]["priceType"] == "LIMIT"


def test_live_place_requires_confirm(monkeypatch):
    b = _connected_broker(monkeypatch, sandbox=False)
    result = b.place_order(
        symbol="AAPL", qty=1, side="BUY", order_type="limit",
        limit_price=10, preview_id="PV-1", confirm_live=False, now=_et(10, 0),
    )
    assert result["status"] == "ERROR"
    assert "confirm" in result["message"].lower()
    placed = b.place_order(
        symbol="AAPL", qty=1, side="BUY", order_type="limit",
        limit_price=10, preview_id="PV-1", confirm_live=True, now=_et(10, 0),
    )
    assert placed["status"] == "PLACED"


def test_gitignore_covers_etrade_env():
    gi = open(".gitignore").read()
    assert "etrade.env" in gi
    assert ".secrets/" in gi


def test_client_order_id_shape():
    b = ETradeBroker.__new__(ETradeBroker)
    cid = ETradeBroker.generate_client_order_id(b)
    assert cid.isalnum()
    assert 1 <= len(cid) <= 20


def test_deployed_out_helper():
    total = deployed_out_from_positions({
        "AAPL": {"qty": 10, "price": 100, "market_value": 1000},
        "MSFT": {"qty": 5, "price": 400},
    })
    assert total == 3000


def test_shorts_allowed_on_cash_blocked_on_ira():
    gate = DeskRiskGate()
    cash = gate.evaluate(
        symbol="AAPL", qty=1, side="SELL_SHORT", order_type="LIMIT", price=100,
        now=_et(10, 0), account_type="CASH",
    )
    assert cash["ok"] is True
    ira = gate.evaluate(
        symbol="AAPL", qty=1, side="SELL_SHORT", order_type="LIMIT", price=100,
        now=_et(10, 0), account_type="ROTH_IRA",
    )
    assert ira["ok"] is False
    assert "IRA" in ira["message"]
    assert is_ira_account("ROTH IRA") is True
    assert is_ira_account("INDIVIDUAL") is False


def test_per_name_and_max_names_caps():
    gate = DeskRiskGate()
    # RTH $5k/name
    ok = gate.evaluate(
        symbol="AAPL", qty=40, side="BUY", order_type="LIMIT", price=100,
        now=_et(10, 0), deployed_out=0, name_deployed=0,
    )
    assert ok["ok"] is True
    blocked = gate.evaluate(
        symbol="AAPL", qty=60, side="BUY", order_type="LIMIT", price=100,
        now=_et(10, 0), deployed_out=0, name_deployed=0,
    )
    assert blocked["ok"] is False
    assert "per-name" in blocked["message"]
    # PM $3.5k/name
    pm_block = gate.evaluate(
        symbol="MSFT", qty=40, side="BUY", order_type="LIMIT", price=100,
        now=_et(8, 0), deployed_out=0, name_deployed=0,
    )
    assert pm_block["ok"] is False
    names = gate.evaluate(
        symbol="NVDA", qty=1, side="BUY", order_type="LIMIT", price=100,
        now=_et(8, 0), open_names=2, name_deployed=0, is_new_name=True,
    )
    assert names["ok"] is False
    assert "names" in names["message"]


def test_plan_sizing_vs_caps():
    gate = DeskRiskGate()
    sized = gate.size_plan(price=100, deployed_out=7000, name_deployed=0, now=_et(10, 0))
    assert sized["sleeve"] == 3000
    assert sized["name_cap"] == 5000
    assert sized["budget_usd"] == 3000
    assert sized["shares"] == 30
    pm = gate.size_plan(price=100, deployed_out=0, name_deployed=0, now=_et(8, 0))
    assert pm["name_cap"] == 3500
    assert pm["shares"] == 35
    assert gate.flatten_time(_et(10, 0)) == "15:50"
    assert gate.flatten_time(_et(17, 0)) == "20:00"


def test_rag_memory_has_no_pickle():
    src = open("app/services/rag_memory.py").read()
    assert "import pickle" not in src
    assert "pickle." not in src
    assert "embeddings.json.gz" in src
