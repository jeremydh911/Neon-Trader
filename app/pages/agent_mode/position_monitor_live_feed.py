"""Live decision feed helpers for agent-mode position monitor."""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st


def render_live_decisions(agent_mode_active: bool) -> None:
    """Render the live decision stream showing real-time agent activity."""
    st.write("**Live Agent Activity:**")

    if agent_mode_active:
        decisions = get_live_decisions()
        for decision in decisions:
            render_decision_card(decision)
    else:
        st.info("⏸️ Agents paused - activate to see live feed")


def get_live_decisions() -> List[Dict[str, Any]]:
    """Return simulated live decision feed."""
    return [
        {
            "time": "14:32:15",
            "agent": "TurboTrade Tina",
            "symbol": "NVDA",
            "action": "BUY",
            "confidence": 0.78,
            "reasoning": "RSI oversold (28), MACD crossover bullish, volume surge 1.4x",
            "status": "analyzing",
        },
        {
            "time": "14:31:42",
            "agent": "DeepValue Dan",
            "symbol": "AAPL",
            "action": "BUY",
            "confidence": 0.82,
            "reasoning": "P/E 24.5 below sector avg, strong free cash flow, analyst upgrades",
            "status": "pending_approval",
        },
        {
            "time": "14:30:18",
            "agent": "QuantQueen Quinn",
            "symbol": "TSLA",
            "action": "SELL",
            "confidence": 0.71,
            "reasoning": "Statistical mean reversion model triggered, RSI 73, upper BB breach",
            "status": "pending_approval",
        },
        {
            "time": "14:28:55",
            "agent": "SectorSwift Sam",
            "symbol": "XLE",
            "action": "BUY",
            "confidence": 0.65,
            "reasoning": "Sector rotation signal: Energy outperforming, WTI crude +3%",
            "status": "council_review",
        },
        {
            "time": "14:27:03",
            "agent": "GrowthGuru Greg",
            "symbol": "META",
            "action": "HOLD",
            "confidence": 0.55,
            "reasoning": "Mixed signals: earnings beat but guidance weak, wait for clarity",
            "status": "completed",
        },
    ]


def render_decision_card(decision: Dict[str, Any]) -> None:
    """Render a single decision card with approval buttons if needed."""

    # Color coding by status
    status_colors = {
        "pending_approval": ("🟡", "#3d3d00"),
        "analyzing": ("🔵", "#002244"),
        "council_review": ("🟣", "#2d1b3d"),
        "completed": ("🟢", "#003300"),
    }

    status_color, bg_color = status_colors.get(decision["status"], ("⚪", "#333333"))

    with st.container():
        st.markdown(
            f"""
        <div style='background-color: {bg_color}; padding: 10px; border-radius: 5px; margin-bottom: 10px;'>
        <b>{status_color} {decision['time']}</b> - <b>{decision['agent']}</b><br>
        <b>{decision['action']} {decision['symbol']}</b> (Confidence: {decision['confidence']*100:.0f}%)<br>
        <i>{decision['reasoning']}</i>
        </div>
        """,
            unsafe_allow_html=True,
        )

        if decision["status"] == "pending_approval":
            col_approve, col_reject, col_modify = st.columns(3)
            with col_approve:
                if st.button(
                    "✅ Approve",
                    key=f"approve_{decision['time']}",
                    use_container_width=True,
                ):
                    st.success(f"✅ {decision['action']} {decision['symbol']} approved!")
            with col_reject:
                if st.button(
                    "❌ Reject",
                    key=f"reject_{decision['time']}",
                    use_container_width=True,
                ):
                    st.warning(f"❌ {decision['action']} {decision['symbol']} rejected")
            with col_modify:
                if st.button(
                    "✏️ Modify",
                    key=f"modify_{decision['time']}",
                    use_container_width=True,
                ):
                    st.info("Opening modification dialog...")
