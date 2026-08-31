"""After-hours working-order follow and premarket cancel-before-roll.

Premarket leftovers are cancelled ~9:28am ET so EXTENDED GFD orders do not
auto-roll into the regular session. During 16:00–20:00 ET, unfilled LIMIT
orders are repriced toward the tape (bid for buys, ask for sells).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def next_follow_limit(
    side: str,
    working_limit: Optional[float],
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    last: Optional[float] = None,
    tick: float = 0.01,
) -> Optional[float]:
    """Return a new LIMIT if the tape has moved enough to reprice."""
    action = (side or "").upper()
    if action in ("BUY", "BUY_TO_COVER"):
        target = bid if bid and bid > 0 else last
    else:
        target = ask if ask and ask > 0 else last
    target = _as_float(target)
    if target is None or target <= 0:
        return None
    target = round(float(target), 2)
    current = _as_float(working_limit)
    if current is not None and abs(target - current) < float(tick or 0.01):
        return None
    return target


def normalize_open_orders(payload: Any) -> List[Dict[str, Any]]:
    """Flatten an E*TRADE list_orders payload into working-order dicts."""
    if payload is None:
        return []
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        node = payload.get("OrdersResponse", payload)
        raw = node.get("Order") if isinstance(node, dict) else node
        if raw is None:
            raw = []
        if isinstance(raw, dict):
            raw = [raw]
    else:
        raw = []

    out: List[Dict[str, Any]] = []
    for order in raw:
        if not isinstance(order, dict):
            continue
        details = order.get("OrderDetail") or order
        if isinstance(details, list):
            details = details[0] if details else {}
        instruments = details.get("Instrument") or []
        if isinstance(instruments, dict):
            instruments = [instruments]
        inst = instruments[0] if instruments else {}
        product = inst.get("Product") or {}
        symbol = (
            product.get("symbol")
            or inst.get("symbol")
            or details.get("symbol")
            or order.get("symbol")
        )
        side = (
            inst.get("orderAction")
            or details.get("orderAction")
            or order.get("orderAction")
            or ""
        )
        qty = inst.get("orderedQuantity") or inst.get("quantity") or details.get("quantity") or 0
        session = (
            details.get("marketSession")
            or order.get("marketSession")
            or "REGULAR"
        )
        out.append(
            {
                "order_id": order.get("orderId") or order.get("order_id") or details.get("orderId"),
                "symbol": (symbol or "").upper(),
                "side": str(side).upper(),
                "qty": int(float(qty or 0)),
                "limit_price": _as_float(details.get("limitPrice") or inst.get("limitPrice")),
                "market_session": str(session).upper(),
                "status": str(order.get("orderStatus") or details.get("status") or "OPEN").upper(),
                "price_type": str(details.get("priceType") or "LIMIT").upper(),
                "raw": order,
            }
        )
    return out


def follow_instructions(
    orders: Iterable[Dict[str, Any]],
    quotes: Dict[str, Dict[str, Any]],
    tick: float = 0.01,
    extended_only: bool = True,
) -> List[Dict[str, Any]]:
    """Build cancel/replace instructions for working LIMITs that lagged the tape."""
    instructions = []
    for order in orders:
        if extended_only and str(order.get("market_session") or "").upper() != "EXTENDED":
            continue
        if str(order.get("price_type") or "LIMIT").upper() != "LIMIT":
            continue
        symbol = order.get("symbol")
        quote = quotes.get(symbol) or quotes.get((symbol or "").upper()) or {}
        new_limit = next_follow_limit(
            side=order.get("side") or "",
            working_limit=order.get("limit_price"),
            bid=_as_float(quote.get("bid")),
            ask=_as_float(quote.get("ask")),
            last=_as_float(quote.get("last") or quote.get("price")),
            tick=tick,
        )
        if new_limit is None:
            continue
        instructions.append(
            {
                "action": "replace",
                "order_id": order.get("order_id"),
                "symbol": symbol,
                "side": order.get("side"),
                "qty": order.get("qty"),
                "old_limit": order.get("limit_price"),
                "new_limit": new_limit,
                "market_session": "EXTENDED",
                "price_type": "LIMIT",
                "order_term": "GOOD_FOR_DAY",
            }
        )
    return instructions
