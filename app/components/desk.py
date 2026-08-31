"""AhanaTrade primary desk: chart, plan alerts, budget, E*TRADE ticket."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
DEFAULT_WATCH = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]


def _gate():
    from services.desk_risk import DeskRiskGate
    return DeskRiskGate()


def _demo_bars(symbol: str) -> List[Dict[str, Any]]:
    """Labeled synthetic session bars when public quotes are unavailable."""
    day = datetime(2026, 9, 1, 7, 0, tzinfo=ET)
    bars = []
    price = 100.0
    for i in range(0, 180):
        ts = day + timedelta(minutes=i)
        o = price
        # PM 7-9 range ~ 99.5-101
        if ts.hour < 9:
            h, l, c = o + 0.4, o - 0.3, o + 0.05
        elif ts.hour == 9 and ts.minute < 30:
            h, l, c = o + 0.3, o - 0.2, o
        elif ts.hour == 9 and ts.minute < 45:
            h, l, c = 101.2, 99.8, 100.6
        else:
            h, l, c = o + 0.8, o - 0.4, o + 0.5
            price = c
        bars.append({"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": 10000 + i * 10, "demo": True})
    return bars


def _load_bars(symbol: str) -> List[Dict[str, Any]]:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="1m", prepost=True)
        if hist is None or hist.empty:
            return _demo_bars(symbol)
        rows = []
        for idx, row in hist.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=ET)
            else:
                ts = ts.astimezone(ET)
            rows.append({
                "ts": ts,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume") or 0),
            })
        return rows or _demo_bars(symbol)
    except Exception as exc:
        logger.info("public bars unavailable for %s (%s); using demo tape", symbol, type(exc).__name__)
        return _demo_bars(symbol)


def _positions_from_service(etrade_service) -> Dict[str, Any]:
    try:
        if etrade_service and getattr(etrade_service, "broker", None):
            return etrade_service.broker.get_positions() or {}
    except Exception:
        logger.debug("positions unavailable", exc_info=False)
    return {}


def render_desk(oauth_service=None) -> None:
    import streamlit as st
    from services.desk_risk import (
        DeskRiskGate,
        deployed_out_from_positions,
        name_deployed_from_positions,
        open_name_count,
        is_ira_account,
    )
    from services.strategy_catcher import catch_symbol
    from services.chart_visualizer import ChartVisualizer
    from services.brain_plugin import active_brain, brain_configured
    from services.etrade_config import is_sandbox

    gate = DeskRiskGate()
    clock = gate.hawaii_clock()
    if "desk_alerts" not in st.session_state:
        st.session_state.desk_alerts = []
    if "pending_preview" not in st.session_state:
        st.session_state.pending_preview = None
    if "selected_plan" not in st.session_state:
        st.session_state.selected_plan = None

    etrade_service = st.session_state.get("etrade_service")
    if etrade_service is None:
        try:
            from services.etrade_service import ETradeService
            etrade_service = ETradeService()
            st.session_state.etrade_service = etrade_service
        except Exception as exc:
            logger.warning("E*TRADE service init: %s", exc)

    status = {}
    try:
        status = etrade_service.get_status() if etrade_service else {}
    except Exception:
        status = {}
    sandbox = status.get("sandbox", is_sandbox())
    authenticated = bool(status.get("is_authenticated"))
    positions = _positions_from_service(etrade_service)
    deployed = deployed_out_from_positions(positions)
    sleeve = gate.remaining_sleeve(deployed)
    names = open_name_count(positions)
    account = {}
    try:
        if etrade_service and getattr(etrade_service, "broker", None):
            account = etrade_service.broker.get_account() or {}
    except Exception:
        account = {}
    account_type = account.get("account_type") or ""

    st.markdown("### Desk")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Remaining sleeve", f"${sleeve:,.0f}", f"${deployed:,.0f} out of $10k")
    m2.metric("Phase", clock["phase"], f"{clock['et']} ET / {clock['ht']} HT")
    m3.metric("Names", f"{names}/{gate.max_names_allowed()}", f"per-name ${gate.per_name_cap():,.0f}")
    m4.metric("Env", "Sandbox" if sandbox else "LIVE", status.get("status", "Disconnected"))
    m5.metric("Brain", active_brain(), "plugin" if brain_configured() else "council stub")
    st.caption(
        f"LIMIT only · 07:00–20:00 ET · flatten {gate.flatten_time()} · "
        f"PDT off · crypto off REST · HT = ET-6 in August. "
        + ("IRA — shorts blocked." if is_ira_account(account_type) else "Shorts allowed unless IRA.")
    )

    with st.sidebar:
        st.markdown("#### Watch")
        symbol = st.text_input("Symbol", value=st.session_state.get("desk_symbol", "AAPL")).upper().strip()
        st.session_state.desk_symbol = symbol
        watch = st.multiselect("Scan list", DEFAULT_WATCH, default=[s for s in DEFAULT_WATCH if s != ""])
        kona = st.checkbox("Kona Latch (experimental)", value=False, help="Hypothesis only. Default OFF.")
        scan = st.button("Scan for setups", type="primary", use_container_width=True)
        st.markdown("#### E*TRADE")
        if authenticated:
            st.success(status.get("status") or "Connected")
        else:
            st.warning("Not connected — preview/place stays local until OAuth.")
            st.caption("Start OAuth from Home or complete the verifier in the OAuth controls.")

    bars = _load_bars(symbol)
    demo = any(b.get("demo") for b in bars)
    if demo:
        st.info("Public tape unavailable — chart is a labeled demo session so levels still draw.")

    holdings = positions or {}
    name_dep = name_deployed_from_positions(holdings, symbol)

    if scan:
        cards = []
        targets = list(dict.fromkeys([symbol] + list(watch)))
        for ticker in targets:
            t_bars = bars if ticker == symbol else _load_bars(ticker)
            cards.extend(
                catch_symbol(
                    ticker,
                    t_bars,
                    holdings=holdings,
                    deployed_out=deployed,
                    name_deployed=name_deployed_from_positions(holdings, ticker),
                    account_type=account_type,
                    include_kona=kona,
                )
            )
        st.session_state.desk_alerts = [c.to_dict() for c in cards]
        if cards:
            try:
                from services.audio_alerts import AudioAlerts
                AudioAlerts().get_streamlit_audio_html()
            except Exception:
                pass

    overlays = {}
    selected = st.session_state.get("selected_plan") or {}
    if selected.get("overlays"):
        overlays = selected["overlays"]
    else:
        from services.strategy_catcher import opening_15m_range, premarket_7_9_range, session_vwap, last_close
        rows = bars
        orng = opening_15m_range(rows) or {}
        pm = premarket_7_9_range(rows) or {}
        overlays = {
            "vwap": session_vwap(rows),
            "or_high": orng.get("high"),
            "or_low": orng.get("low"),
            "pm_high": pm.get("high"),
            "pm_low": pm.get("low"),
            "invalidation": (selected or {}).get("invalidation"),
            "last": last_close(rows),
        }

    chart_col, feed_col = st.columns([3, 2])
    with chart_col:
        viz = ChartVisualizer()
        built = viz.create_desk_chart(symbol, bars, overlays=overlays, title=f"{symbol} · levels the catcher is using")
        fig = built.get("figure") if isinstance(built, dict) else None
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(built.get("error") if isinstance(built, dict) else "Chart unavailable")
        if holdings:
            st.caption("Holdings: " + ", ".join(f"{k} {v.get('qty', v.get('quantity'))}" for k, v in holdings.items()))

    with feed_col:
        st.markdown("#### Plan alerts")
        alerts = st.session_state.get("desk_alerts") or []
        if not alerts:
            st.caption("Scan a symbol to catch A/B/C/D setups. Each catch is a plan under the remaining $10k sleeve.")
        for i, plan in enumerate(alerts):
            exp = " · experimental" if plan.get("experimental") else ""
            with st.expander(f"{plan.get('symbol')} · {plan.get('setup')} · {plan.get('side')}{exp}", expanded=i == 0):
                st.write(plan.get("why"))
                st.write(
                    f"Limit {plan.get('limit_lo'):.2f}–{plan.get('limit_hi'):.2f} · "
                    f"{plan.get('shares')} sh / ${plan.get('size_usd'):,.0f} · "
                    f"invalidate {plan.get('invalidation')} · flatten {plan.get('flatten_time')} ET"
                )
                st.caption(plan.get("ira_short_note") or "")
                if plan.get("brain_note"):
                    st.caption(f"Brain ({plan.get('brain')}): {plan.get('brain_note')}")
                similar = plan.get("similar") or []
                if similar:
                    st.caption("Similar past setups: " + "; ".join(
                        f"{s.get('symbol')} {s.get('setup')} {s.get('ts', '')[:16]}" for s in similar[:3]
                    ))
                if st.button("Load ticket", key=f"load_plan_{i}"):
                    st.session_state.selected_plan = plan
                    st.rerun()

    st.markdown("#### Preview then place")
    plan = st.session_state.get("selected_plan") or {}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        order_symbol = st.text_input("Ticket symbol", value=plan.get("symbol") or symbol).upper()
    with c2:
        default_side = plan.get("side") or "BUY"
        sides = ["BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER"]
        idx = sides.index(default_side) if default_side in sides else 0
        order_side = st.selectbox("Side", sides, index=idx)
    with c3:
        order_qty = st.number_input("Shares", min_value=1, value=max(int(plan.get("shares") or 1), 1))
    with c4:
        default_px = float(plan.get("limit_lo") or overlays.get("last") or 1.0)
        order_price = st.number_input("Limit", min_value=0.01, value=max(default_px, 0.01), step=0.01, format="%.2f")

    confirm_live = True
    if not sandbox:
        st.warning("LIVE E*TRADE — preview then place; one-shot place is disabled.")
        confirm_live = st.checkbox("I confirm this LIVE E*TRADE order", value=False, key="desk_confirm_live")

    b1, b2, b3 = st.columns([1, 1, 2])
    account_id = None
    try:
        accounts = etrade_service.get_accounts() if etrade_service and authenticated else []
        if accounts:
            account_id = accounts[0].get("account_id") or accounts[0].get("accountIdKey")
    except Exception:
        accounts = []

    with b1:
        if st.button("Preview", use_container_width=True):
            if not authenticated or not etrade_service:
                st.error("Connect E*TRADE OAuth before preview.")
            else:
                result = etrade_service.place_order(
                    account_id=account_id,
                    symbol=order_symbol,
                    quantity=int(order_qty),
                    side=order_side,
                    order_type="Limit",
                    price=float(order_price),
                    preview=True,
                )
                if result and result.get("status") not in ("ERROR", "error"):
                    st.session_state.pending_preview = result
                    st.success("Preview ok")
                    st.json(result.get("order_data", result))
                    try:
                        from services.ahana_memory import get_ahana_memory
                        get_ahana_memory().ingest({
                            "kind": "alert",
                            "symbol": order_symbol,
                            "payload": {"event": "preview", "result": result},
                        })
                    except Exception:
                        pass
                else:
                    st.session_state.pending_preview = None
                    st.error((result or {}).get("message") or "Preview failed")
    with b2:
        if st.button("Place", use_container_width=True):
            pending = st.session_state.get("pending_preview") or {}
            preview_id = pending.get("preview_id")
            if not preview_id:
                st.error("Preview first. Place is separate from preview; live will not one-shot.")
            elif not sandbox and not confirm_live:
                st.error("LIVE place requires the per-order confirm checkbox.")
            else:
                result = etrade_service.place_order(
                    account_id=account_id,
                    symbol=order_symbol,
                    quantity=int(order_qty),
                    side=order_side,
                    order_type="Limit",
                    price=float(order_price),
                    preview=False,
                    preview_id=preview_id,
                    client_order_id=pending.get("client_order_id"),
                    confirm_live=confirm_live,
                )
                if result and result.get("status") not in ("ERROR", "error"):
                    st.session_state.pending_preview = None
                    st.success("Order placed")
                    st.json(result)
                else:
                    st.error((result or {}).get("message") or "Place failed")

    with st.expander("Advanced · council / tracing"):
        st.caption(
            "Council (Tina / Eddie / Gloria / Victor / Riley) runs when AHANA_BRAIN_URL is unset. "
            "Tracing stays behind OTLP_ENABLED. Leaderboard is not on the primary desk."
        )
        st.write(f"Active brain: {active_brain()}")
        try:
            from services.ahana_memory import get_ahana_memory
            past = get_ahana_memory().retrieve(symbol=symbol, kind="plan", k=5)
            if past:
                st.markdown("Recent plans for this symbol")
                for row in past:
                    st.caption(f"{row.get('ts','')[:19]} {row.get('setup')} {(row.get('payload') or {}).get('why','')[:80]}")
        except Exception:
            pass
