"""Mechanical A/B/C/D strategy catcher for the AhanaTrade desk.

Detectors run on OHLCV (public data is fine if broker quotes are missing).
Each catch becomes a PLAN CARD sized from desk_risk remaining sleeve.

  A — Premarket gap 7:00–9:20 ET
  B — Open drive 9:30–10:15 (first 15m / opening range)
  C — VWAP reclaim 10:00–15:45
  D — AH follow 16:00–20:00

Peak/valley (trim peaks, buy dips, leave a runner) is a HOLDINGS overlay, not letter D.
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
SETUP_FLATTEN = {"A": "09:20", "B": "11:00", "C": "15:50", "D": "20:00"}
PLAYBOOK = (
    {"letter": "A", "name": "Premarket gap", "window": "07:00–09:20 ET"},
    {"letter": "B", "name": "Open drive", "window": "09:30–10:15 (first 15m / opening range)"},
    {"letter": "C", "name": "VWAP reclaim", "window": "10:00–15:45"},
    {"letter": "D", "name": "AH follow", "window": "16:00–20:00"},
)
PLAYBOOK_CAPTION = (
    "A Premarket gap 7:00–9:20 ET · B Open drive 9:30–10:15 (first 15m / opening range) · "
    "C VWAP reclaim 10:00–15:45 · D AH follow 16:00–20:00. "
    "Peak/valley is a holdings overlay (trim peaks, buy dips, leave a runner). "
    "Kona Latch experimental, default OFF."
)
D_RTH_BAR_RANGE_SKIP = 0.006
D_AH15_RANGE_SKIP = 0.012
GAP_MIN = 0.006
GAP_FADE = 0.012


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


def premarket_7_920_range(rows: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    return range_of(rows, time(7, 0), time(9, 20))


def premarket_7_9_range(rows: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Playbook PM window is 07:00–09:20 ET (kept name for desk overlay import)."""
    return premarket_7_920_range(rows)


def last_close(rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return _ohlc(rows[-1])[3]


def last_ts(rows: List[Dict[str, Any]]) -> Optional[datetime]:
    if not rows:
        return None
    return _to_et(rows[-1].get("ts"))


def _plus_minutes(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    return time((total // 60) % 24, total % 60)


def _clock(rows: List[Dict[str, Any]], now: Any = None) -> Optional[datetime]:
    ts = _to_et(now) if now is not None else None
    return ts or last_ts(rows)


def _in_window(ts: Optional[datetime], start: time, end: time) -> bool:
    if ts is None:
        return False
    t = ts.astimezone(ET).time() if ts.tzinfo else ts.replace(tzinfo=ET).time()
    return start <= t < end


def bars_between(
    rows: List[Dict[str, Any]],
    start: time,
    end: time,
    day=None,
) -> List[Dict[str, Any]]:
    out = []
    for bar in rows:
        ts = _to_et(bar.get("ts"))
        if ts is None:
            continue
        if day is not None and ts.date() != day:
            continue
        if start <= ts.time() < end:
            out.append(bar)
    return out


def first_15m_bars(rows: List[Dict[str, Any]], start: time, day=None) -> List[Dict[str, Any]]:
    return bars_between(rows, start, _plus_minutes(start, 15), day=day)


def prior_rth_close_px(rows: List[Dict[str, Any]], day) -> Optional[float]:
    best_ts = None
    best = None
    for bar in rows:
        ts = _to_et(bar.get("ts"))
        if ts is None or (day is not None and ts.date() >= day):
            continue
        if time(9, 30) <= ts.time() < time(16, 0):
            close = _ohlc(bar)[3]
            if best_ts is None or ts > best_ts:
                best_ts = ts
                best = close
    if best is None or best <= 0:
        return None
    return best


def rth_bars(rows: List[Dict[str, Any]], day=None) -> List[Dict[str, Any]]:
    return bars_between(rows, time(9, 30), time(16, 0), day=day)


def holdings_peak_valley_levels(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if len(rows) < 5:
        return {}
    highs = [_ohlc(b)[1] for b in rows[-20:]]
    lows = [_ohlc(b)[2] for b in rows[-20:]]
    if not highs or not lows:
        return {}
    return {"peak": max(highs), "valley": min(lows)}


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
        flatten_time=SETUP_FLATTEN.get(setup) or str(sized.get("flatten_time") or "15:50"),
        why=why,
        ira_short_note=str(sized.get("ira_short_note") or ""),
        experimental=experimental,
        overlays=overlays,
    )
    card = _annotate(card, price)
    card = _remember(card)
    return card


def detect_a_premarket_gap(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    """A — Premarket gap 7:00–9:20 ET (fade if stall after |gap|>1.2%, else continuation)."""
    now = _clock(rows, kw.get("now"))
    if not _in_window(now, time(7, 15), time(9, 20)):
        return []
    day = now.date()
    prev_c = prior_rth_close_px(rows, day)
    if prev_c is None:
        return []
    f15 = first_15m_bars(rows, time(7, 0), day=day)
    if len(f15) < 2:
        return []
    o700 = _ohlc(f15[0])[0]
    if o700 <= 0:
        return []
    gap_pct = (o700 - prev_c) / prev_c
    if abs(gap_pct) < GAP_MIN:
        return []
    highs = [_ohlc(b)[1] for b in f15]
    lows = [_ohlc(b)[2] for b in f15]
    f15_high, f15_low = max(highs), min(lows)
    f15_close = _ohlc(f15[-1])[3]
    f15_range = max(f15_high - f15_low, 0.0)
    close_loc = (f15_close - f15_low) / f15_range if f15_range > 0 else 0.5
    stall_up = gap_pct > 0 and close_loc <= 0.5
    stall_dn = gap_pct < 0 and close_loc >= 0.5
    hold_up = gap_pct > 0 and f15_low >= prev_c and f15_close >= o700
    hold_dn = gap_pct < 0 and f15_high <= prev_c and f15_close <= o700
    side = None
    style = None
    if abs(gap_pct) > GAP_FADE and ((gap_pct > 0 and stall_up) or (gap_pct < 0 and stall_dn)):
        side = "SELL_SHORT" if gap_pct > 0 else "BUY"
        style = "fade"
    elif (gap_pct > 0 and hold_up) or (gap_pct < 0 and hold_dn):
        side = "BUY" if gap_pct > 0 else "SELL_SHORT"
        style = "continuation"
    else:
        return []
    limit = session_vwap(f15)
    if limit is None or limit <= 0:
        limit = f15_close
    close = last_close(rows)
    pm = premarket_7_920_range(rows) or {"high": f15_high, "low": f15_low}
    if side == "BUY":
        invalidation = min(prev_c, f15_low)
    else:
        invalidation = max(prev_c, f15_high)
    overlays = {
        "vwap": session_vwap(f15),
        "pm_high": pm.get("high"),
        "pm_low": pm.get("low"),
        "prior_rth_close": prev_c,
        "gap_pct": gap_pct,
        "last": close,
        "invalidation": invalidation,
        "style": style,
    }
    why = (
        f"Setup A Premarket gap: {style} {gap_pct:+.2%} vs prior RTH {prev_c:.2f} "
        f"(07:00–09:20 ET); limit {limit:.2f}"
    )
    card = _card(
        symbol=symbol, setup="A", side=side, price=limit,
        invalidation=invalidation, why=why, overlays=overlays, **kw,
    )
    return [card] if card else []


def detect_b_open_drive(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    """B — Open drive 9:30–10:15 (first 15m / opening range break with the gap)."""
    now = _clock(rows, kw.get("now"))
    if not _in_window(now, time(9, 45), time(10, 16)):
        return []
    day = now.date()
    prev_c = prior_rth_close_px(rows, day)
    if prev_c is None:
        return []
    f15 = first_15m_bars(rows, time(9, 30), day=day)
    if len(f15) < 2:
        return []
    o930 = _ohlc(f15[0])[0]
    gap_pct = (o930 - prev_c) / prev_c if prev_c else 0.0
    if gap_pct == 0:
        return []
    rng = opening_15m_range(f15) or opening_15m_range(rows)
    if not rng:
        return []
    orh, orl = rng["high"], rng["low"]
    if orh <= orl:
        return []
    direction_up = gap_pct > 0
    broke = False
    for bar in bars_between(rows, time(9, 45), time(10, 16), day=day):
        cl = _ohlc(bar)[3]
        if direction_up and cl > orh:
            broke = True
            break
        if (not direction_up) and cl < orl:
            broke = True
            break
    if not broke:
        return []
    close = last_close(rows)
    side = "BUY" if direction_up else "SELL_SHORT"
    limit = orh if direction_up else orl
    invalidation = orl if direction_up else orh
    overlays = {
        "or_high": orh,
        "or_low": orl,
        "vwap": session_vwap(rth_bars(rows, day) or rows),
        "prior_rth_close": prev_c,
        "gap_pct": gap_pct,
        "last": close,
        "invalidation": invalidation,
    }
    why = (
        f"Setup B Open drive: {'broke OR high' if direction_up else 'broke OR low'} "
        f"{orh:.2f}/{orl:.2f} with the gap {gap_pct:+.2%} (09:30–10:15; first 15m range)"
    )
    card = _card(
        symbol=symbol, setup="B", side=side, price=limit,
        invalidation=invalidation, why=why, overlays=overlays, **kw,
    )
    return [card] if card else []


def detect_c_vwap(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    """C — VWAP reclaim 10:00–15:45 after >= 4 consecutive closes on the other side."""
    now = _clock(rows, kw.get("now"))
    if not _in_window(now, time(10, 0), time(15, 45)):
        return []
    day = now.date()
    rth = rth_bars(rows, day)
    if len(rth) < 5:
        return []
    consec_below = consec_above = 0
    prev_below = prev_above = 0
    last_vwap = None
    last_close_px = None
    num = den = 0.0
    for bar in rth:
        _o, h, l, c, v = _ohlc(bar)
        typical = (h + l + c) / 3.0 if (h or l or c) else c
        vol = v if v > 0 else 1.0
        num += typical * vol
        den += vol
        if den <= 0:
            continue
        vwap = num / den
        last_vwap = vwap
        last_close_px = c
        prev_below, prev_above = consec_below, consec_above
        if c < vwap:
            consec_below += 1
            consec_above = 0
        elif c > vwap:
            consec_above += 1
            consec_below = 0
        else:
            consec_below = consec_above = 0
    if last_vwap is None or last_close_px is None:
        return []
    side = None
    if last_close_px > last_vwap and prev_below >= 4:
        side = "BUY"
        why = (
            f"Setup C VWAP reclaim: last {last_close_px:.2f} back above VWAP {last_vwap:.2f} "
            f"after {prev_below} closes below (10:00–15:45)"
        )
        invalidation = last_vwap * 0.997
    elif last_close_px < last_vwap and prev_above >= 4:
        side = "SELL_SHORT"
        why = (
            f"Setup C VWAP reject: last {last_close_px:.2f} lost VWAP {last_vwap:.2f} "
            f"after {prev_above} closes above (10:00–15:45)"
        )
        invalidation = last_vwap * 1.003
    else:
        return []
    overlays = {
        "vwap": last_vwap,
        "last": last_close_px,
        "invalidation": invalidation,
        "or_high": (opening_15m_range(rows) or {}).get("high"),
        "or_low": (opening_15m_range(rows) or {}).get("low"),
    }
    card = _card(
        symbol=symbol, setup="C", side=side, price=last_vwap,
        invalidation=invalidation, why=why, overlays=overlays, **kw,
    )
    return [card] if card else []


def detect_d_ah_follow(symbol: str, rows: List[Dict[str, Any]], **kw) -> List[PlanCard]:
    """D — AH follow 16:00–20:00 (RTH close in the extreme 20%, AH first 15m continues)."""
    now = _clock(rows, kw.get("now"))
    if not _in_window(now, time(16, 15), time(20, 0)):
        return []
    day = now.date()
    rth = rth_bars(rows, day)
    ah15 = first_15m_bars(rows, time(16, 0), day=day)
    if not rth or len(ah15) < 2:
        return []
    rth_high = max(_ohlc(b)[1] for b in rth)
    rth_low = min(_ohlc(b)[2] for b in rth)
    rth_close = _ohlc(rth[-1])[3]
    span = rth_high - rth_low
    if span <= 0 or rth_close <= 0:
        return []
    loc = (rth_close - rth_low) / span
    if loc >= 0.80:
        direction_up = True
    elif loc <= 0.20:
        direction_up = False
    else:
        return []
    last_rth = rth[-1]
    _, lh, ll, lc, _ = _ohlc(last_rth)
    if lc > 0 and (lh - ll) / rth_close > D_RTH_BAR_RANGE_SKIP:
        return []
    ah_high = max(_ohlc(b)[1] for b in ah15)
    ah_low = min(_ohlc(b)[2] for b in ah15)
    ah_close = _ohlc(ah15[-1])[3]
    if (ah_high - ah_low) / rth_close > D_AH15_RANGE_SKIP:
        return []
    if direction_up and not (ah_close > rth_close):
        return []
    if (not direction_up) and not (ah_close < rth_close):
        return []
    side = "BUY" if direction_up else "SELL_SHORT"
    invalidation = rth_close
    close = last_close(rows)
    overlays = {
        "last": close,
        "rth_close": rth_close,
        "rth_high": rth_high,
        "rth_low": rth_low,
        "rth_loc": loc,
        "vwap": session_vwap(rth),
        "invalidation": invalidation,
    }
    why = (
        f"Setup D AH follow: RTH close {rth_close:.2f} at {loc:.0%} of the RTH range; "
        f"AH first 15m continues {'higher' if direction_up else 'lower'} (16:00–20:00)"
    )
    card = _card(
        symbol=symbol, setup="D", side=side, price=rth_close,
        invalidation=invalidation, why=why, overlays=overlays, **kw,
    )
    return [card] if card else []


def detect_holdings_peak_valley(
    symbol: str,
    rows: List[Dict[str, Any]],
    holdings: Optional[Dict[str, Any]] = None,
    **kw,
) -> List[PlanCard]:
    """Holdings overlay: trim peaks, buy dips, leave a runner. Not letter D."""
    pos = (holdings or {}).get(symbol.upper()) or (holdings or {}).get(symbol)
    if not isinstance(pos, dict):
        return []
    qty = _as_float(pos.get("qty") or pos.get("quantity"))
    if qty == 0:
        return []
    close = last_close(rows)
    if close <= 0 or len(rows) < 5:
        return []
    levels = holdings_peak_valley_levels(rows)
    peak = levels.get("peak")
    valley = levels.get("valley")
    if peak is None or valley is None:
        return []
    span = max(peak - valley, 0.01)
    overlays = {
        "last": close,
        "peak": peak,
        "valley": valley,
        "vwap": session_vwap(rows),
        "holdings_overlay": True,
    }
    cards = []
    if qty > 0:
        if close >= peak - 0.15 * span:
            runner = max(int(abs(qty) * 0.25), 1)
            trim = max(int(abs(qty) - runner), 1)
            card = _card(
                symbol=symbol, setup="HOLDINGS", side="SELL", price=close,
                invalidation=valley,
                why=f"Holdings overlay peak trim: {symbol} near {peak:.2f}; sell {trim} leave runner {runner}",
                overlays={**overlays, "invalidation": valley},
                **kw,
            )
            if card:
                card.shares = trim
                card.size_usd = round(trim * close, 2)
                cards.append(card)
        elif close <= valley + 0.15 * span:
            card = _card(
                symbol=symbol, setup="HOLDINGS", side="BUY", price=close,
                invalidation=valley * 0.995,
                why=f"Holdings overlay dip buy: {symbol} near valley {valley:.2f}; add under remaining sleeve",
                overlays={**overlays, "invalidation": valley * 0.995},
                **kw,
            )
            if card:
                cards.append(card)
    else:
        if close <= valley + 0.15 * span:
            card = _card(
                symbol=symbol, setup="HOLDINGS", side="BUY_TO_COVER", price=close,
                invalidation=peak,
                why=f"Holdings overlay short cover at valley {valley:.2f}; leave a runner short",
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
    cards.extend(detect_a_premarket_gap(symbol, rows, **kw))
    cards.extend(detect_b_open_drive(symbol, rows, **kw))
    cards.extend(detect_c_vwap(symbol, rows, **kw))
    cards.extend(detect_d_ah_follow(symbol, rows, **kw))
    holdings_cards = detect_holdings_peak_valley(symbol, rows, holdings=holdings, **kw)
    pv_levels = holdings_peak_valley_levels(rows) if holdings else {}
    if holdings_cards:
        src_ov = holdings_cards[0].overlays or {}
        for key in ("peak", "valley"):
            if src_ov.get(key) is not None:
                pv_levels[key] = src_ov[key]
        pv_levels["holdings_overlay"] = True
    if pv_levels:
        for card in cards:
            card.overlays = {**pv_levels, **(card.overlays or {})}
    cards.extend(holdings_cards)
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
