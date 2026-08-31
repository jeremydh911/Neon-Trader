"""Mechanical A/B/C/D strategy catcher for the AhanaTrade desk.

Detectors run on OHLCV (public data is fine if broker quotes are missing).
Each catch becomes a PLAN CARD sized from desk_risk remaining sleeve.

  A — Opening 15-minute range break
  B — VWAP reclaim / reject
  C — Premarket 07:00–09:00 ET range break
  D — Peak/valley on holdings (trim peaks, buy dips, leave a runner)

Kona Latch is an experimental detector, default OFF.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SETUPS = ("A", "B", "C", "D")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_et(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=ET)
        return ts.astimezone(ET)
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=ET)
    text = str(ts)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET)
        return parsed.astimezone(ET)
    except ValueError:
        return None


def _rows(bars: Sequence[Any]) -> List[Dict[str, Any]]:
    if bars is None:
        return []
    if hasattr(bars, "to_dict") and callable(getattr(bars, "reset_index", None)):
        try:
            frame = bars.reset_index()
            recs = frame.to_dict("records")
            out = []
            for rec in recs:
                item = {str(k).lower(): v for k, v in rec.items()}
                ts = item.get("datetime") or item.get("date") or item.get("timestamp") or item.get("index")
                item["ts"] = ts
                out.append(item)
            return out
        except Exception:
            pass
    out = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        item = {str(k).lower(): v for k, v in bar.items()}
        item.setdefault("ts", item.get("datetime") or item.get("date") or item.get("timestamp"))
        out.append(item)
    return out


def _ohlc(bar: Dict[str, Any]) -> tuple:
    o = _as_float(bar.get("open") or bar.get("o"))
    h = _as_float(bar.get("high") or bar.get("h"), o)
    l = _as_float(bar.get("low") or bar.get("l"), o)
    c = _as_float(bar.get("close") or bar.get("c") or bar.get("last"), o)
    v = _as_float(bar.get("volume") or bar.get("v"))
    return o, h, l, c, v


def session_vwap(rows: List[Dict[str, Any]]) -> Optional[float]:
    num = 0.0
    den = 0.0
    for bar in rows:
        o, h, l, c, v = _ohlc(bar)
        typical = (h + l + c) / 3.0 if (h or l or c) else c
        if v <= 0:
            v = 1.0
        num += typical * v
        den += v
    if den <= 0:
        return None
    return num / den


def range_of(rows: List[Dict[str, Any]], start: time, end: time) -> Optional[Dict[str, float]]:
    highs = []
    lows = []
    for bar in rows:
        ts = _to_et(bar.get("ts"))
        if ts is None:
            continue
        t = ts.time()
        if start <= t < end:
            _, h, l, _, _ = _ohlc(bar)
            highs.append(h)
            lows.append(l)
    if not highs or not lows:
        return None
    return {"high": max(highs), "low": min(lows)}


def opening_15m_range(rows: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    return range_of(rows, time(9, 30), time(9, 45))


def premarket_7_9_range(rows: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    return range_of(rows, time(7, 0), time(9, 0))


def last_close(rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return _ohlc(rows[-1])[3]


def last_ts(rows: List[Dict[str, Any]]) -> Optional[datetime]:
    if not rows:
        return None
    return _to_et(rows[-1].get("ts"))


@dataclass
class PlanCard:
    symbol: str
    setup: str
    side: str
    limit_lo: float
    limit_hi: float
    size_usd: float
    shares: int
    remaining_budget: float
    invalidation: float
    flatten_time: str
    why: str
    ira_short_note: str
    brain_note: str = ""
    brain: str = "council"
    similar: List[Dict[str, Any]] = field(default_factory=list)
    experimental: bool = False
    overlays: Dict[str, Any] = field(default_factory=dict)
    record_id: str = ""

    @property
    def limit_zone(self) -> str:
        return f"{self.limit_lo:.2f}–{self.limit_hi:.2f}"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["limit_zone"] = self.limit_zone
        return data


def _gate(now: Optional[datetime] = None, account_type: Optional[str] = None):
    from .desk_risk import DeskRiskGate

    return DeskRiskGate(account_type=account_type)


def _size(symbol: str, side: str, price: float, deployed_out: float, name_deployed: float, now, account_type) -> Dict[str, Any]:
    gate = _gate(now, account_type)
    sized = gate.size_plan(price=price, deployed_out=deployed_out, name_deployed=name_deployed, now=now)
    note = gate.ira_short_note(account_type, side)
    if side in {"SELL_SHORT", "SHORT", "SHORT_SELL"} and not gate.shorts_allowed(account_type):
        sized["shares"] = 0
        sized["sized_usd"] = 0.0
    sized["ira_short_note"] = note
    sized["flatten_time"] = gate.flatten_time(now)
    sized["sleeve"] = gate.remaining_sleeve(deployed_out)
    return sized


def _annotate(card: PlanCard, price: float) -> PlanCard:
    try:
        from .brain_plugin import annotate_catch

        note = annotate_catch(card.to_dict(), current_price=price)
        if note:
            card.brain_note = str(note.get("plan") or note.get("brain_note") or card.brain_note)
            card.brain = str(note.get("brain") or card.brain)
    except Exception:
        logger.debug("brain annotate skipped", exc_info=False)
        if not card.brain_note:
            card.brain_note = "Local detector (council stub): mechanical levels only."
            card.brain = "council"
    return card


def _remember(card: PlanCard) -> PlanCard:
    try:
        from .ahana_memory import get_ahana_memory

        mem = get_ahana_memory()
        similar = mem.similar_setups(card.symbol, card.setup, card.why, k=3)
        card.similar = [
            {
                "id": s.get("id"),
                "symbol": s.get("symbol"),
                "setup": s.get("setup"),
                "ts": s.get("ts"),
                "score": s.get("_score"),
                "why": (s.get("payload") or {}).get("why"),
            }
            for s in similar
            if s.get("id") != card.record_id
        ]
        rec_id = mem.ingest(
            {
                "kind": "plan",
                "symbol": card.symbol,
                "setup": card.setup,
                "payload": card.to_dict(),
            }
        )
        card.record_id = rec_id
        mem.ingest(
            {
                "kind": "alert",
                "symbol": card.symbol,
                "setup": card.setup,
                "payload": {"why": card.why, "side": card.side, "plan_id": rec_id},
            }
        )
    except Exception:
        logger.debug("ahana memory ingest skipped", exc_info=False)
    return card


def _card(
    *,
    symbol: str,
    setup: str,
    side: str,
    price: float,
    invalidation: float,
    why: str,
    overlays: Dict[str, Any],
    deployed_out: float,
    name_deployed: float,
    now,
    account_type: Optional[str],
    experimental: bool = False,
) -> Optional[PlanCard]:
    if price <= 0:
        return None
    tick = 0.01
    if side in {"BUY", "BUY_TO_COVER"}:
        lo, hi = round(price - 2 * tick, 2), round(price + tick, 2)
    else:
        lo, hi = round(price - tick, 2), round(price + 2 * tick, 2)
    sized = _size(symbol, side, price, deployed_out, name_deployed, now, account_type)
    if sized["shares"] <= 0 and side in {"BUY", "SELL_SHORT", "SHORT", "SHORT_SELL"}:
        # Still surface the catch so the operator sees it, with 0 size.
        pass
    card = PlanCard(
        symbol=symbol.upper(),
        setup=setup,
        side=side,
        limit_lo=min(lo, hi),
        limit_hi=max(lo, hi),
        size_usd=float(sized.get("sized_usd") or 0.0),
        shares=int(sized.get("shares") or 0),
        remaining_budget=float(sized.get("sleeve") or 0.0),
        invalidation=round(invalidation, 2),
        flatten_time=str(sized.get("flatten_time") or "15:50"),
        why=why,
        ira_short_note=str(sized.get("ira_short_note") or ""),
        experimental=experimental,
        overlays=overlays,
    )
    card = _annotate(card, price)
    card = _remember(card)
    return card


def detect_a_orb(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    rng = opening_15m_range(rows)
    if not rng:
        return []
    ts = last_ts(rows)
    if ts and ts.time() < time(9, 45):
        return []
    close = last_close(rows)
    vwap = session_vwap(rows)
    overlays = {"or_high": rng["high"], "or_low": rng["low"], "vwap": vwap, "last": close}
    cards = []
    buffer = max((rng["high"] - rng["low"]) * 0.02, 0.01)
    if close > rng["high"] + buffer * 0:
        card = _card(
            symbol=symbol, setup="A", side="BUY", price=close,
            invalidation=rng["low"],
            why=f"Setup A ORB: last {close:.2f} broke opening 15m high {rng['high']:.2f}",
            overlays={**overlays, "invalidation": rng["low"]},
            **kw,
        )
        if card:
            cards.append(card)
    elif close < rng["low"]:
        card = _card(
            symbol=symbol, setup="A", side="SELL_SHORT", price=close,
            invalidation=rng["high"],
            why=f"Setup A ORB: last {close:.2f} broke opening 15m low {rng['low']:.2f}",
            overlays={**overlays, "invalidation": rng["high"]},
            **kw,
        )
        if card:
            cards.append(card)
    return cards


def detect_b_vwap(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    if len(rows) < 3:
        return []
    vwap = session_vwap(rows)
    if vwap is None:
        return []
    prev = _ohlc(rows[-2])[3]
    close = last_close(rows)
    overlays = {"vwap": vwap, "last": close}
    cards = []
    if prev < vwap <= close:
        card = _card(
            symbol=symbol, setup="B", side="BUY", price=close,
            invalidation=vwap * 0.997,
            why=f"Setup B VWAP reclaim: {prev:.2f} -> {close:.2f} crossed VWAP {vwap:.2f}",
            overlays={**overlays, "invalidation": vwap * 0.997},
            **kw,
        )
        if card:
            cards.append(card)
    elif prev > vwap >= close:
        card = _card(
            symbol=symbol, setup="B", side="SELL_SHORT", price=close,
            invalidation=vwap * 1.003,
            why=f"Setup B VWAP reject: {prev:.2f} -> {close:.2f} lost VWAP {vwap:.2f}",
            overlays={**overlays, "invalidation": vwap * 1.003},
            **kw,
        )
        if card:
            cards.append(card)
    return cards


def detect_c_premarket(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    rng = premarket_7_9_range(rows)
    if not rng:
        return []
    ts = last_ts(rows)
    if ts and ts.time() < time(9, 0):
        return []
    close = last_close(rows)
    overlays = {"pm_high": rng["high"], "pm_low": rng["low"], "last": close, "vwap": session_vwap(rows)}
    cards = []
    if close > rng["high"]:
        card = _card(
            symbol=symbol, setup="C", side="BUY", price=close,
            invalidation=rng["low"],
            why=f"Setup C PM range: last {close:.2f} broke 07:00–09:00 high {rng['high']:.2f}",
            overlays={**overlays, "invalidation": rng["low"]},
            **kw,
        )
        if card:
            cards.append(card)
    elif close < rng["low"]:
        card = _card(
            symbol=symbol, setup="C", side="SELL_SHORT", price=close,
            invalidation=rng["high"],
            why=f"Setup C PM range: last {close:.2f} broke 07:00–09:00 low {rng['low']:.2f}",
            overlays={**overlays, "invalidation": rng["high"]},
            **kw,
        )
        if card:
            cards.append(card)
    return cards


def detect_d_peak_valley(
    symbol: str,
    rows: List[Dict[str, Any]],
    holdings: Optional[Dict[str, Any]] = None,
    **kw,
) -> List[PlanCard]:
    pos = (holdings or {}).get(symbol.upper()) or (holdings or {}).get(symbol)
    if not isinstance(pos, dict):
        return []
    qty = _as_float(pos.get("qty") or pos.get("quantity"))
    if qty == 0:
        return []
    close = last_close(rows)
    if close <= 0 or len(rows) < 5:
        return []
    highs = [_ohlc(b)[1] for b in rows[-20:]]
    lows = [_ohlc(b)[2] for b in rows[-20:]]
    peak = max(highs)
    valley = min(lows)
    span = max(peak - valley, 0.01)
    overlays = {"last": close, "peak": peak, "valley": valley, "vwap": session_vwap(rows)}
    cards = []
    # Long holding: trim near peak, leave a runner; buy dips near valley.
    if qty > 0:
        if close >= peak - 0.15 * span:
            runner = max(int(abs(qty) * 0.25), 1)
            trim = max(int(abs(qty) - runner), 1)
            card = _card(
                symbol=symbol, setup="D", side="SELL", price=close,
                invalidation=valley,
                why=f"Setup D peak trim: {symbol} near {peak:.2f}; sell {trim} leave runner {runner}",
                overlays={**overlays, "invalidation": valley},
                **kw,
            )
            if card:
                card.shares = trim
                card.size_usd = round(trim * close, 2)
                cards.append(card)
        elif close <= valley + 0.15 * span:
            card = _card(
                symbol=symbol, setup="D", side="BUY", price=close,
                invalidation=valley * 0.995,
                why=f"Setup D dip buy: {symbol} near valley {valley:.2f}; add under remaining sleeve",
                overlays={**overlays, "invalidation": valley * 0.995},
                **kw,
            )
            if card:
                cards.append(card)
    else:
        # Short holding: cover dips (buy to cover), trim (add short) into peaks.
        if close <= valley + 0.15 * span:
            card = _card(
                symbol=symbol, setup="D", side="BUY_TO_COVER", price=close,
                invalidation=peak,
                why=f"Setup D short cover at valley {valley:.2f}; leave a runner short",
                overlays={**overlays, "invalidation": peak},
                **kw,
            )
            if card:
                cards.append(card)
    return cards


def kona_latch_enabled() -> bool:
    flag = (os.getenv("AHANA_KONA_LATCH") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if flag in ("0", "false", "no", "off"):
        return False
    try:
        from config.config import RISK
        return bool(RISK.get("kona_latch_enabled", False))
    except Exception:
        return False


def detect_kona_latch(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    """Experimental: two-bar inside latch then close through the latch high/low."""
    if not kona_latch_enabled() or len(rows) < 3:
        return []
    a, b, c = rows[-3], rows[-2], rows[-1]
    _, ah, al, ac, _ = _ohlc(a)
    _, bh, bl, bc, _ = _ohlc(b)
    _, ch, cl, cc, _ = _ohlc(c)
    inside = bh <= ah and bl >= al
    if not inside:
        return []
    overlays = {"latch_high": ah, "latch_low": al, "last": cc, "vwap": session_vwap(rows)}
    cards = []
    if cc > ah and bc <= ah:
        card = _card(
            symbol=symbol, setup="KONA", side="BUY", price=cc,
            invalidation=al,
            why=f"Kona Latch (experimental): close {cc:.2f} through latch high {ah:.2f}",
            overlays={**overlays, "invalidation": al},
            experimental=True,
            **kw,
        )
        if card:
            cards.append(card)
    elif cc < al and bc >= al:
        card = _card(
            symbol=symbol, setup="KONA", side="SELL_SHORT", price=cc,
            invalidation=ah,
            why=f"Kona Latch (experimental): close {cc:.2f} through latch low {al:.2f}",
            overlays={**overlays, "invalidation": ah},
            experimental=True,
            **kw,
        )
        if card:
            cards.append(card)
    return cards


def catch_symbol(
    symbol: str,
    bars: Sequence[Any],
    *,
    holdings: Optional[Dict[str, Any]] = None,
    deployed_out: float = 0.0,
    name_deployed: float = 0.0,
    now: Optional[datetime] = None,
    account_type: Optional[str] = None,
    include_kona: Optional[bool] = None,
) -> List[PlanCard]:
    rows = _rows(bars)
    if not rows:
        return []
    kw = dict(
        deployed_out=deployed_out,
        name_deployed=name_deployed,
        now=now or last_ts(rows),
        account_type=account_type,
    )
    cards: List[PlanCard] = []
    cards.extend(detect_a_orb(symbol, rows, **kw))
    cards.extend(detect_b_vwap(symbol, rows, **kw))
    cards.extend(detect_c_premarket(symbol, rows, **kw))
    cards.extend(detect_d_peak_valley(symbol, rows, holdings=holdings, **kw))
    if include_kona if include_kona is not None else kona_latch_enabled():
        cards.extend(detect_kona_latch(symbol, rows, **kw))
    return cards


def catch_watchlist(
    symbols: Iterable[str],
    bars_by_symbol: Dict[str, Sequence[Any]],
    **kw,
) -> List[PlanCard]:
    out: List[PlanCard] = []
    for symbol in symbols:
        bars = bars_by_symbol.get(symbol) or bars_by_symbol.get(symbol.upper()) or []
        out.extend(catch_symbol(symbol, bars, **kw))
    return out
