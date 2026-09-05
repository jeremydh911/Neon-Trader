"""
Tim Cockpit — AI-centric trading desk.

One composition: Tim + engines + one decision + one snipe.
Brand: NEON / TIM. Engines decide. AI narrates.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import streamlit as st


TIM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@400;500;600&display=swap');

:root {
  --ink: #071018;
  --panel: rgba(10, 22, 32, 0.72);
  --line: rgba(94, 234, 212, 0.18);
  --mint: #5eead4;
  --amber: #f5b942;
  --coral: #ff6b4a;
  --fog: #9fb3c8;
  --white: #eef6f8;
}

.stApp {
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(94,234,212,0.16), transparent 55%),
    radial-gradient(900px 500px at 100% 0%, rgba(245,185,66,0.10), transparent 50%),
    linear-gradient(165deg, #050b11 0%, #0a1620 45%, #0c1a14 100%);
  color: var(--white);
  font-family: 'DM Sans', sans-serif;
}

/* Hide default chrome noise */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

.tim-brand {
  font-family: 'Syne', sans-serif;
  font-weight: 800;
  font-size: clamp(2.4rem, 5vw, 3.6rem);
  letter-spacing: -0.04em;
  line-height: 0.95;
  margin: 0;
  background: linear-gradient(120deg, #eef6f8 20%, #5eead4 55%, #f5b942 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.tim-tag {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.78rem;
  color: var(--fog);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-top: 0.55rem;
}
.tim-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.75rem;
  margin: 1.25rem 0 1.5rem;
}
@media (max-width: 900px) {
  .tim-strip { grid-template-columns: repeat(2, 1fr); }
}
.tim-chip {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.85rem 1rem;
  backdrop-filter: blur(10px);
}
.tim-chip .k {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.68rem;
  color: var(--fog);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.tim-chip .v {
  font-family: 'Syne', sans-serif;
  font-size: 1.35rem;
  font-weight: 700;
  margin-top: 0.2rem;
}
.tim-chip .v.pos { color: var(--mint); }
.tim-chip .v.neg { color: var(--coral); }
.tim-chip .v.warn { color: var(--amber); }

.decision-shell {
  background: linear-gradient(145deg, rgba(14,28,38,0.9), rgba(8,18,26,0.85));
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 1.4rem 1.5rem 1.2rem;
  position: relative;
  overflow: hidden;
}
.decision-shell::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: linear-gradient(180deg, var(--mint), var(--amber));
}
.action-buy { color: var(--mint); }
.action-hold { color: var(--amber); }
.action-sell { color: var(--coral); }
.action-xl {
  font-family: 'Syne', sans-serif;
  font-size: 2.6rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  margin: 0.2rem 0 0.4rem;
}
.reason-mono {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.86rem;
  color: var(--fog);
  line-height: 1.45;
}
.gate-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  font-size: 0.9rem;
}
.gate-pass { color: var(--mint); font-family: 'IBM Plex Mono', monospace; }
.gate-fail { color: var(--coral); font-family: 'IBM Plex Mono', monospace; }
.narration-box {
  margin-top: 0.85rem;
  padding: 0.9rem 1rem;
  border-radius: 14px;
  background: rgba(94,234,212,0.06);
  border: 1px solid rgba(94,234,212,0.14);
  font-size: 0.95rem;
  line-height: 1.5;
}
.chat-bubble-user {
  background: rgba(245,185,66,0.12);
  border: 1px solid rgba(245,185,66,0.25);
  border-radius: 16px 16px 4px 16px;
  padding: 0.75rem 1rem;
  margin: 0.45rem 0;
  font-size: 0.95rem;
}
.chat-bubble-tim {
  background: rgba(94,234,212,0.08);
  border: 1px solid rgba(94,234,212,0.2);
  border-radius: 16px 16px 16px 4px;
  padding: 0.75rem 1rem;
  margin: 0.45rem 0;
  font-size: 0.95rem;
}
.section-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--fog);
  margin-bottom: 0.5rem;
}
div[data-testid="stButton"] > button {
  border-radius: 12px !important;
  font-family: 'Syne', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
}
</style>
"""


def _ensure_copilot(funding_service=None):
    if "tim_copilot" not in st.session_state:
        os.environ.setdefault("PAPER_MODE", "1")
        os.environ.setdefault("USE_MOCK_BROKER", "1")
        try:
            from services.tim_copilot import get_tim_copilot
        except Exception:
            from app.services.tim_copilot import get_tim_copilot
        st.session_state.tim_copilot = get_tim_copilot(funding_service=funding_service)
    if "tim_chat" not in st.session_state:
        st.session_state.tim_chat = []
    if "tim_decision" not in st.session_state:
        st.session_state.tim_decision = None
    return st.session_state.tim_copilot


def _action_class(action: str) -> str:
    a = (action or "HOLD").upper()
    if a == "BUY":
        return "action-buy"
    if a == "SELL":
        return "action-sell"
    return "action-hold"


def _render_risk_strip(strip: Dict[str, Any]) -> None:
    pnl = float(strip.get("daily_pnl") or 0)
    pnl_cls = "pos" if pnl >= 0 else "neg"
    mode = "PAPER" if strip.get("paper_mode") else "LIVE"
    mem_backend = (strip.get("memory_backend") or "—").upper()
    if mem_backend.startswith("AHANA"):
        mem_backend = "AHANA"
    mem_n = strip.get("memory_vectors") or 0
    st.markdown(
        f"""
        <div class="tim-strip">
          <div class="tim-chip"><div class="k">Capital</div><div class="v">${strip.get('capital', 0):,.0f}</div></div>
          <div class="tim-chip"><div class="k">Daily PnL</div><div class="v {pnl_cls}">${pnl:,.2f}</div></div>
          <div class="tim-chip"><div class="k">Open</div><div class="v">{strip.get('open_positions', 0)}</div></div>
          <div class="tim-chip"><div class="k">Memory</div><div class="v warn">{mem_backend} · {mem_n}</div></div>
          <div class="tim-chip"><div class="k">Mode</div><div class="v warn">{mode}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_decision(decision: Optional[Dict[str, Any]]) -> None:
    if not decision:
        st.markdown(
            """
            <div class="decision-shell">
              <div class="section-label">Live decision</div>
              <div class="action-xl action-hold">WAITING</div>
              <div class="reason-mono">Ask Tim to analyze a ticker — engines stack gates before anything fires.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    action = (decision.get("action") or "HOLD").upper()
    cls = _action_class(action)
    conf = float(decision.get("confidence") or 0)
    symbol = decision.get("symbol", "—")
    reason = decision.get("reason", "")
    narration = decision.get("narration", "")
    levels = decision.get("levels") or {}
    gates = decision.get("gates") or []
    passed = decision.get("gates_passed", 0)
    total = decision.get("gates_total", 0)

    st.markdown(
        f"""
        <div class="decision-shell">
          <div class="section-label">{symbol} · engine verdict</div>
          <div class="action-xl {cls}">{action}</div>
          <div class="reason-mono">Confidence {conf:.0%} · Gates {passed}/{total}<br/>{reason}</div>
          <div class="reason-mono" style="margin-top:0.6rem">
            Stop ${levels.get('stop_loss_price', '—')} ({levels.get('stop_loss_pct', '—')}%)
            · Target ${levels.get('take_profit_price', '—')} ({levels.get('take_profit_pct', '—')}%)
            · Size {decision.get('shares', 0)} sh
          </div>
          <div class="narration-box">{narration.replace(chr(10), '<br/>')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label" style="margin-top:1rem">Momentum gates</div>', unsafe_allow_html=True)
    for g in gates:
        mark = "PASS" if g.get("passed") else "FAIL"
        klass = "gate-pass" if g.get("passed") else "gate-fail"
        st.markdown(
            f'<div class="gate-row"><span>{g.get("label")}</span>'
            f'<span class="{klass}">{mark} · {g.get("value")}</span></div>',
            unsafe_allow_html=True,
        )


def render_tim_cockpit(funding_service=None, oauth_status: Optional[Dict] = None) -> None:
    """Primary AI-centric page."""
    st.markdown(TIM_CSS, unsafe_allow_html=True)
    copilot = _ensure_copilot(funding_service)

    # Hero — brand first
    st.markdown(
        """
        <p class="tim-brand">TIM</p>
        <p class="tim-tag">Neon · AI sniper desk · engines + copilot</p>
        """,
        unsafe_allow_html=True,
    )

    strip = copilot.risk_strip()
    _render_risk_strip(strip)

    left, right = st.columns([1.05, 1.35], gap="large")

    with left:
        st.markdown('<div class="section-label">Talk to Tim</div>', unsafe_allow_html=True)

        for turn in st.session_state.tim_chat[-8:]:
            role = turn.get("role")
            css = "chat-bubble-user" if role == "user" else "chat-bubble-tim"
            who = "You" if role == "user" else "Tim"
            st.markdown(
                f'<div class="{css}"><strong>{who}</strong><br/>{turn.get("text","")}</div>',
                unsafe_allow_html=True,
            )

        prompt = st.chat_input("analyze NVDA · snipe AAPL · show risk")
        if prompt:
            st.session_state.tim_chat.append({"role": "user", "text": prompt})
            with st.spinner("Engines + Tim…"):
                reply = copilot.chat(prompt)
            text = reply.get("response") or reply.get("message") or str(reply)
            st.session_state.tim_chat.append({"role": "tim", "text": text})
            if reply.get("decision"):
                st.session_state.tim_decision = reply["decision"]
            st.rerun()

        st.markdown('<div class="section-label" style="margin-top:1rem">Quick symbols</div>', unsafe_allow_html=True)
        q1, q2, q3, q4 = st.columns(4)
        for col, sym in zip((q1, q2, q3, q4), ("NVDA", "AAPL", "TSLA", "SPY")):
            if col.button(sym, use_container_width=True, key=f"quick_{sym}"):
                decision = copilot.analyze(sym)
                st.session_state.tim_decision = decision
                st.session_state.tim_chat.append({"role": "user", "text": f"analyze {sym}"})
                st.session_state.tim_chat.append({"role": "tim", "text": decision.get("narration") or decision.get("reason")})
                st.rerun()

    with right:
        decision = st.session_state.tim_decision
        _render_decision(decision)

        st.write("")
        c1, c2, c3 = st.columns([1.2, 1, 1])
        can_snipe = bool(decision and decision.get("action") == "BUY")

        with c1:
            if st.button(
                "⚡ PAPER SNIPE",
                type="primary",
                use_container_width=True,
                disabled=not can_snipe,
                help="Engines must say BUY. Arms broker stop on fill.",
            ):
                sym = decision["symbol"]
                with st.spinner(f"Sniping {sym}…"):
                    result = copilot.snipe(sym)
                if result.get("status") == "success":
                    st.success(result.get("message"))
                    st.session_state.tim_chat.append({"role": "tim", "text": result.get("message")})
                    if result.get("decision"):
                        st.session_state.tim_decision = result["decision"]
                else:
                    st.warning(result.get("message") or "Snipe blocked")
                st.rerun()

        with c2:
            if st.button("Refresh", use_container_width=True, disabled=not decision):
                if decision:
                    st.session_state.tim_decision = copilot.analyze(decision["symbol"])
                    st.rerun()

        with c3:
            if st.button("Clear", use_container_width=True):
                st.session_state.tim_decision = None
                st.rerun()

        if decision and decision.get("demo"):
            st.caption("Demo tape active — live quotes offline. Gates still enforce Tim’s rules.")

        mem = strip.get("memory") or {}
        with st.expander("AhanaFlow memory (compressed RAG)"):
            st.write(
                f"Backend: **{strip.get('memory_backend', '—')}** · "
                f"vectors **{strip.get('memory_vectors', 0)}** · "
                f"WAL **{mem.get('wal_size_bytes', '—')}** bytes"
            )
            st.caption(
                "Decisions and snipes land in AhanaFlow VectorStateEngineV2 "
                "(https://www.ahanaflow.com). Query path uses compress_results for compact RAG."
            )
            if decision and decision.get("memory_context"):
                st.code(decision["memory_context"], language=None)

        # Secondary: council / oauth status — not the hero
        with st.expander("Council & broker (secondary)"):
            auth = "connected" if (oauth_status or {}).get("is_authenticated") else "paper / disconnected"
            st.write(f"Broker auth: **{auth}**")
            st.write("Council is optional confirmation. Tim’s momentum gates fire first.")
            st.caption("Hot path stays engine-first. LLM only narrates.")


def create_tim_cockpit_page(funding_service=None, oauth_status=None):
    render_tim_cockpit(funding_service=funding_service, oauth_status=oauth_status)
