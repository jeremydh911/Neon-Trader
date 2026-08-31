"""Day-trading desk risk gate for Neon Trader's E*TRADE path.

$10,000 aggregate capital-out cap. Session 07:00–20:00 America/New_York
(pre-market through after-hours). LIMIT-only. Overnight out.
Does NOT enforce FINRA PDT or a $25k equity minimum.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

try:
    from config.config import RISK as DEFAULT_RISK
except Exception:  # pragma: no cover
    try:
        import sys
        from pathlib import Path as _Path

        sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        from config.config import RISK as DEFAULT_RISK
    except Exception:
        DEFAULT_RISK = {
            "max_deployed_out_usd": 10000.0,
            "max_open_orders": 3,
            "daily_loss_halt_usd": 250.0,
            "daily_loss_halt_pct_equity": 0.025,
            "session_timezone": "America/New_York",
            "session_open": "07:00",
            "session_close": "20:00",
            "regular_open": "09:30",
            "regular_close": "16:00",
            "afterhours_open": "16:00",
            "afterhours_close": "20:00",
            "include_premarket": True,
            "include_afterhours": True,
            "limit_only": True,
            "long_only": True,
            "restrict_us_listed_only": False,
            "enforce_pdt": False,
            "overnight_out": True,
            "follow_min_tick": 0.01,
        }

# Equities/ETFs on the REST Order API. No crypto pairs (BTC/USD, ETH-USD, …).
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
CRYPTO_TICKERS = {
    "BTC", "ETH", "DOGE", "SOL", "ADA", "XRP", "AVAX", "DOT", "MATIC", "SHIB",
    "LTC", "BCH", "UNI", "LINK", "ATOM", "XLM", "ALGO", "PEPE", "NEAR", "APT",
    "BTCUSD", "ETHUSD", "DOGEUSD", "SOLUSD",
}
SHORT_SIDES = {"SELL_SHORT", "SHORT", "SHORT_SELL"}
BUY_SIDES = {"BUY", "BUY_TO_COVER"}
SELL_SIDES = {"SELL"}
MARKET_TYPES = {"MARKET", "MKT", "MARKET_ON_CLOSE"}
LIMIT_TYPES = {"LIMIT"}


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def deployed_out_from_positions(positions: Optional[Dict[str, Any]]) -> float:
    """Gross long notional currently deployed across all positions."""
    total = 0.0
    for pos in (positions or {}).values():
        if not isinstance(pos, dict):
            continue
        qty = _as_float(pos.get("qty") or pos.get("quantity"), 0.0)
        if qty <= 0:
            continue
        mv = pos.get("market_value")
        if mv is not None:
            total += abs(_as_float(mv, 0.0))
            continue
        px = _as_float(pos.get("price") or pos.get("avg_fill_price"), 0.0)
        total += abs(qty * px)
    return total


def et_now(now: Optional[datetime] = None) -> datetime:
    tz = ZoneInfo("America/New_York")
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


@dataclass
class DeskRiskState:
    daily_realized_pnl: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


class DeskRiskGate:
    def __init__(
        self,
        limits: Optional[Dict[str, Any]] = None,
        state: Optional[DeskRiskState] = None,
        include_afterhours: bool = True,
        allow_market: bool = False,
    ):
        self.limits = {**DEFAULT_RISK, **(limits or {})}
        self.state = state or DeskRiskState()
        self.include_afterhours = True if include_afterhours is None else bool(
            include_afterhours or self.limits.get("include_afterhours", True)
        )
        # Desk is LIMIT-only. The allow_market flag is ignored.
        self.allow_market = False

    @property
    def extended_hours(self) -> bool:
        return True

    def pdt_policy(self) -> Dict[str, Any]:
        return {
            "enforce_pdt": False,
            "min_equity_usd": None,
            "refuse_day_trades": False,
            "note": (
                "FINRA PDT / $25k is not enforced by Neon Trader. "
                "Day trades are allowed; brokerage rejections are surfaced."
            ),
        }

    def session_window(self) -> tuple:
        return (
            _parse_hhmm(str(self.limits.get("session_open") or "07:00")),
            _parse_hhmm(str(self.limits.get("session_close") or "20:00")),
        )

    def phase(self, now: Optional[datetime] = None) -> str:
        """overnight | blackout | premarket | regular | afterhours

        Weekday clock (ET):
          00:00–04:00 overnight
          04:00–07:00 blackout (no orders)
          07:00–09:30 premarket (EXTENDED + LIMIT + GFD)
          09:28–09:30 cancel-before-roll window
          09:30–16:00 regular (REGULAR + LIMIT + GFD)
          16:00–20:00 after-hours (EXTENDED + LIMIT + GFD)
          20:00–24:00 overnight out
        """
        current = et_now(now)
        if current.weekday() >= 5:
            return "overnight"
        t = current.time()
        blackout = _parse_hhmm(str(self.limits.get("blackout_start") or "04:00"))
        pre = _parse_hhmm(str(self.limits.get("session_open") or "07:00"))
        reg = _parse_hhmm(str(self.limits.get("regular_open") or "09:30"))
        ah = _parse_hhmm(str(self.limits.get("afterhours_open") or "16:00"))
        close = _parse_hhmm(str(self.limits.get("session_close") or "20:00"))
        if t >= close or t < blackout:
            return "overnight"
        if t < pre:
            return "blackout"
        if t < reg:
            return "premarket"
        if t < ah:
            return "regular"
        return "afterhours"

    def is_session_open(self, now: Optional[datetime] = None) -> bool:
        return self.phase(now) in ("premarket", "regular", "afterhours")

    def is_blackout(self, now: Optional[datetime] = None) -> bool:
        return self.phase(now) == "blackout"

    def in_cancel_before_roll_window(self, now: Optional[datetime] = None) -> bool:
        """~9:28am ET: cancel premarket-only leftovers so they do not auto-roll."""
        current = et_now(now)
        if current.weekday() >= 5:
            return False
        t = current.time()
        start = _parse_hhmm(str(self.limits.get("cancel_before_roll") or "09:28"))
        regular = _parse_hhmm(str(self.limits.get("regular_open") or "09:30"))
        return start <= t < regular

    def hawaii_clock(self, now: Optional[datetime] = None) -> Dict[str, str]:
        """Hawaii UI is ET-6 in August (HST vs EDT)."""
        et = et_now(now)
        ht = et.astimezone(ZoneInfo("Pacific/Honolulu"))
        return {
            "et": et.strftime("%H:%M"),
            "ht": ht.strftime("%H:%M"),
            "et_iso": et.isoformat(),
            "ht_iso": ht.isoformat(),
            "offset_note": "HT = ET-6 in August (HST vs EDT)",
            "phase": self.phase(et),
        }

    def is_regular_hours(self, now: Optional[datetime] = None) -> bool:
        return self.phase(now) == "regular"

    def is_afterhours(self, now: Optional[datetime] = None) -> bool:
        return self.phase(now) == "afterhours"

    def is_overnight(self, now: Optional[datetime] = None) -> bool:
        return self.phase(now) == "overnight"

    def market_session(self, now: Optional[datetime] = None) -> str:
        """E*TRADE marketSession flag: REGULAR vs EXTENDED."""
        return "REGULAR" if self.phase(now) == "regular" else "EXTENDED"

    def order_session_flags(self, now: Optional[datetime] = None) -> Dict[str, str]:
        """E*TRADE LIMIT + TIF / EXT flags for the current session."""
        session = self.market_session(now=now)
        return {
            "priceType": "LIMIT",
            "orderTerm": "GOOD_FOR_DAY",
            "marketSession": session,
            "extended": session == "EXTENDED",
        }

    def is_crypto_symbol(self, symbol: str) -> bool:
        raw = (symbol or "").strip().upper()
        if not raw:
            return False
        if "/" in raw or raw.endswith("-USD") or raw.endswith("USDT"):
            return True
        compact = raw.replace("-", "").replace("/", "")
        if raw in CRYPTO_TICKERS or compact in CRYPTO_TICKERS:
            return True
        if compact.endswith("USD") and compact[:-3] in CRYPTO_TICKERS:
            return True
        return False

    def is_allowed_symbol(self, symbol: str) -> bool:
        ticker = (symbol or "").strip().upper()
        if not ticker or self.is_crypto_symbol(ticker):
            return False
        return bool(SYMBOL_RE.match(ticker))

    def daily_loss_halt_amount(self, equity: float) -> float:
        usd = _as_float(self.limits.get("daily_loss_halt_usd"), 250.0)
        pct = _as_float(self.limits.get("daily_loss_halt_pct_equity"), 0.025)
        equity = max(_as_float(equity, 0.0), 0.0)
        if equity <= 0:
            return usd
        return min(usd, equity * pct)

    def max_deployed_out(self) -> float:
        return _as_float(self.limits.get("max_deployed_out_usd"), 10000.0)

    def evaluate(
        self,
        *,
        symbol: str,
        qty: int,
        side: str,
        order_type: str,
        price: Optional[float],
        equity: float = 0.0,
        deployed_out: float = 0.0,
        open_orders: int = 0,
        is_new_entry: Optional[bool] = None,
        now: Optional[datetime] = None,
        skip_session_check: bool = False,
    ) -> Dict[str, Any]:
        ticker = (symbol or "").strip().upper()
        action = (side or "").strip().upper()
        price_type = (order_type or "LIMIT").strip().upper()
        quantity = int(qty or 0)
        px = _as_float(price, 0.0)
        phase = self.phase(now)

        if quantity <= 0:
            return self._reject("quantity must be > 0")
        if self.is_crypto_symbol(ticker):
            return self._reject(
                f"{ticker} is crypto; E*TRADE REST Order API does not support crypto"
            )
        if not self.is_allowed_symbol(ticker):
            return self._reject(f"{ticker or '(blank)'} is not a valid tradable symbol")
        if bool(self.limits.get("long_only", True)) and action in SHORT_SIDES:
            return self._reject("short sales are not allowed (long-only desk)")
        if action not in BUY_SIDES | SELL_SIDES | SHORT_SIDES:
            return self._reject(f"unsupported side {action}")

        if is_new_entry is None:
            is_new_entry = action in BUY_SIDES

        if price_type in MARKET_TYPES or price_type not in LIMIT_TYPES:
            return self._reject("desk is LIMIT-only; market/stop orders are disabled")
        if px <= 0:
            return self._reject("LIMIT orders require a positive limit price")

        if not skip_session_check:
            if phase == "blackout":
                return self._reject("blackout 04:00–07:00 ET — no orders")
            if phase == "overnight":
                return self._reject(
                    "overnight out: desk is closed 20:00–07:00 ET (no overnight risk)"
                )
            if not self.is_session_open(now=now):
                return self._reject("outside desk session (07:00–20:00 ET)")

        notional = quantity * px
        cap = self.max_deployed_out()
        current_out = max(_as_float(deployed_out, 0.0), 0.0)
        if is_new_entry:
            projected = current_out + notional
            if projected > cap:
                room = max(cap - current_out, 0.0)
                return self._reject(
                    f"aggregate deployed-out ${projected:,.2f} would exceed ${cap:,.2f} cap "
                    f"(currently ${current_out:,.2f} out, ${room:,.2f} remaining)"
                )

        max_open = int(self.limits.get("max_open_orders") or 3)
        if open_orders >= max_open:
            return self._reject(f"max {max_open} open orders already reached")

        if is_new_entry:
            halt = self.daily_loss_halt_amount(equity)
            if self.state.daily_realized_pnl <= -halt:
                return self._reject(
                    f"daily-loss halt: realized PnL ${self.state.daily_realized_pnl:,.2f} "
                    f"hit min($250, 2.5% equity)=${halt:,.2f}; new entries blocked "
                    "(exits still allowed)"
                )

        flags = self.order_session_flags(now=now)
        return {
            "ok": True,
            "status": "OK",
            "symbol": ticker,
            "qty": quantity,
            "side": action,
            "order_type": "LIMIT",
            "notional": notional,
            "deployed_out": current_out,
            "projected_out": current_out + notional if is_new_entry else current_out,
            "is_new_entry": is_new_entry,
            "pdt_enforced": False,
            "phase": phase,
            "market_session": flags["marketSession"],
            "order_term": flags["orderTerm"],
            "extended": flags["extended"],
        }

    def record_realized_pnl(self, amount: float) -> None:
        self.state.daily_realized_pnl += _as_float(amount, 0.0)

    def _reject(self, message: str) -> Dict[str, Any]:
        return {"ok": False, "status": "ERROR", "message": message, "pdt_enforced": False}
