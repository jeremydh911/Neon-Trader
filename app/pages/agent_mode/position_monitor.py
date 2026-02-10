"""
Position Monitor Module

Handles trading position tracking, P&L monitoring, and risk metrics display.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime

from .position_monitor_live_feed import render_live_decisions


def _ensure_pending_review_state() -> None:
    if 'agent_mode_council_reviews' not in st.session_state:
        # key -> council_decision dict
        st.session_state.agent_mode_council_reviews = {}
    if 'agent_mode_orchestrator_reviews' not in st.session_state:
        # key -> orchestrator run_cycle result dict
        st.session_state.agent_mode_orchestrator_reviews = {}


def _approval_key(approval: Dict[str, Any]) -> str:
    """Stable-ish key for caching council reviews across reruns."""
    proposal_id = approval.get('proposal_id') or approval.get('id')
    if proposal_id:
        return str(proposal_id)
    # Fall back to a composite key for demo/session-state items
    symbol = str(approval.get('symbol', ''))
    action = str(approval.get('action', ''))
    price = str(approval.get('price', approval.get('estimated_price', '')))
    ts = str(approval.get('timestamp', ''))
    agent = str(approval.get('agent', ''))
    return f"{symbol}:{action}:{price}:{agent}:{ts}".strip(":")


def _load_pending_approvals() -> List[Dict[str, Any]]:
    """Best-effort load of pending approvals.

    Priority:
    1) `st.session_state.approval_queue` if populated by another workflow
    2) `services.trade_approval` pending proposals (if used elsewhere)
    3) Demo placeholders
    """

    # 1) Session-state queue
    queue = st.session_state.get('approval_queue')
    if isinstance(queue, list) and queue:
        return [q for q in queue if isinstance(q, dict)]

    # 2) Trade approval manager proposals
    try:
        from services.trade_approval import get_approval_manager
        manager = get_approval_manager()
        proposals = manager.get_pending_proposals()
        approvals: List[Dict[str, Any]] = []
        for p in proposals:
            # Normalize to the dict shape expected by the UI
            approvals.append(
                {
                    "proposal_id": getattr(p, "proposal_id", None),
                    "symbol": getattr(p, "symbol", None),
                    "agent": "AI Research",
                    "action": getattr(p, "action", None),
                    "shares": getattr(p, "quantity", None),
                    "price": getattr(p, "estimated_price", None),
                    "confidence": None,
                    "reasoning": getattr(p, "rationale", ""),
                    "order_type": getattr(p, "order_type", "MARKET"),
                    "timestamp": getattr(p, "timestamp", None).isoformat() if getattr(p, "timestamp", None) else None,
                }
            )
        if approvals:
            return approvals
    except Exception:
        # If this service isn't wired, just fall back to demo content.
        pass

    # 3) Demo placeholders
    return [
        {
            'symbol': 'AAPL',
            'agent': 'DeepValue Dan',
            'action': 'BUY',
            'shares': 100,
            'price': 182.50,
            'confidence': 0.82,
            'reasoning': 'Strong value play: P/E 24.5, ROE 147%, free cash flow $99B',
            'is_demo': True,
        },
        {
            'symbol': 'TSLA',
            'agent': 'QuantQueen Quinn',
            'action': 'SELL',
            'shares': 50,
            'price': 238.45,
            'confidence': 0.71,
            'reasoning': 'Statistical reversal: 2.5σ above mean, RSI 73, upper BB',
            'is_demo': True,
        }
    ]


def render_pending_approvals(
    council: Optional[Any] = None,
    orchestrator: Optional[Any] = None,
    automation_enabled: bool = False,
) -> None:
    """Render trades awaiting approval and (optionally) auto-route to council for a vote.

    Note: This component does not execute trades on its own. It only adds a
    council review layer to improve safety/consistency.
    """

    _ensure_pending_review_state()

    st.write("**Agent research deals ready to approve:**")

    pending_approvals = _load_pending_approvals()
    if not pending_approvals:
        st.info("No pending items.")
        return

    if any(a.get('is_demo') for a in pending_approvals):
        st.caption("Showing demo/sample items (not coming from a live queue).")

    mode = st.radio(
        "Routing",
        options=["Council only", "Full orchestrator"],
        horizontal=True,
        help="Council only = vote on the existing recommendation. Full orchestrator = agents research -> council vote -> optional execution.",
    )

    col_left, col_right = st.columns([2, 1])
    with col_left:
        auto_route = st.checkbox(
            "Auto-route pending items",
            value=bool(automation_enabled),
            help="When enabled, each pending item is routed through the selected pipeline and the result is shown here.",
        )
    with col_right:
        majority_threshold = st.slider(
            "Council approval %",
            min_value=50,
            max_value=90,
            value=50,
            step=5,
            help="Required approval percentage for the council to approve an item.",
        )

    if mode == "Full orchestrator":
        st.caption("Orchestrator mode is deliberation-only here (no execution).")

    # Lazy-create needed services if caller didn't pass them in.
    if auto_route and mode == "Council only" and council is None:
        try:
            from services.trading_council import TradingCouncil
            council = TradingCouncil()
        except Exception:
            council = None

    if auto_route and mode == "Full orchestrator" and orchestrator is None:
        try:
            from services.orchestrator_setup import get_orchestrator
            orchestrator = get_orchestrator()
        except Exception:
            orchestrator = None

    # Never execute trades from this page; execution is handled by the autonomous trader workflows.

    for approval in pending_approvals:
        key = _approval_key(approval)

        # Route & cache
        if auto_route and mode == "Council only" and council is not None and key not in st.session_state.agent_mode_council_reviews:
            symbol = approval.get('symbol')
            action = (approval.get('action') or 'HOLD')
            try:
                current_price = float(approval.get('price') or approval.get('estimated_price') or 0.0)
            except Exception:
                current_price = 0.0

            indicators = approval.get('indicators') if isinstance(approval.get('indicators'), dict) else {}
            available_capital = float(approval.get('available_capital') or 10000.0)

            try:
                decision, approved = council.discuss_trade(
                    symbol=str(symbol),
                    action=str(action).upper(),
                    current_price=current_price,
                    indicators=indicators,
                    available_capital=available_capital,
                    market_sentiment=str(approval.get('market_sentiment') or 'neutral'),
                    majority_threshold=int(majority_threshold),
                )
                st.session_state.agent_mode_council_reviews[key] = {
                    "mode": "council",
                    "approved": bool(approved),
                    "decision": decision.to_dict() if decision else None,
                    "reviewed_at": datetime.utcnow().isoformat(),
                }
            except Exception as e:
                st.session_state.agent_mode_council_reviews[key] = {
                    "mode": "council",
                    "approved": False,
                    "decision": None,
                    "error": str(e),
                    "reviewed_at": datetime.utcnow().isoformat(),
                }

        if auto_route and mode == "Full orchestrator" and orchestrator is not None and key not in st.session_state.agent_mode_orchestrator_reviews:
            symbol = approval.get('symbol')
            try:
                current_price = float(approval.get('price') or approval.get('estimated_price') or 0.0)
            except Exception:
                current_price = 0.0

            indicators = approval.get('indicators') if isinstance(approval.get('indicators'), dict) else {}
            available_capital = float(approval.get('available_capital') or 10000.0)
            market_sentiment = str(approval.get('market_sentiment') or 'neutral')

            try:
                result = orchestrator.run_cycle(
                    symbol=str(symbol),
                    current_price=current_price,
                    indicators=indicators,
                    available_capital=available_capital,
                    market_sentiment=market_sentiment,
                    execute_backend=False,
                )
                # Add a couple of useful UI fields
                st.session_state.agent_mode_orchestrator_reviews[key] = {
                    "mode": "orchestrator",
                    "result": result,
                    "reviewed_at": datetime.utcnow().isoformat(),
                }
            except Exception as e:
                st.session_state.agent_mode_orchestrator_reviews[key] = {
                    "mode": "orchestrator",
                    "error": str(e),
                    "reviewed_at": datetime.utcnow().isoformat(),
                }

        review = None
        if mode == "Council only":
            review = st.session_state.agent_mode_council_reviews.get(key)
        else:
            review = st.session_state.agent_mode_orchestrator_reviews.get(key)

        render_approval_card(approval, council_review=review)


def render_approval_card(approval: Dict[str, Any], council_review: Optional[Dict[str, Any]] = None) -> None:
    """Render a single approval card with trade details (and optional council/orchestrator review)."""
    action = approval.get('action', 'HOLD')
    symbol = approval.get('symbol', '')
    agent = approval.get('agent', 'Unknown Agent')
    with st.expander(f"**{action} {symbol}** by {agent}", expanded=True):
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            shares = approval.get('shares')
            price = approval.get('price')
            st.write(f"**Shares:** {shares}")
            try:
                st.write(f"**Price:** ${float(price):.2f}")
            except Exception:
                st.write(f"**Price:** {price}")
            try:
                st.write(f"**Value:** ${float(shares) * float(price):,.2f}")
            except Exception:
                pass
        
        with col_info2:
            conf = approval.get('confidence')
            if isinstance(conf, (int, float)):
                st.metric("Confidence", f"{float(conf)*100:.0f}%")
            else:
                st.metric("Confidence", "—")
            st.write(f"**Agent:** {agent}")
        
        st.write(f"**Reasoning:**")
        st.info(approval.get('reasoning', ''))

        if council_review is not None:
            st.divider()
            mode = council_review.get('mode')
            if mode == 'orchestrator':
                st.write("**🎭 Orchestrator Review (Agents → Council → Execution):**")
                if council_review.get('error'):
                    st.warning(f"Orchestrator review failed: {council_review.get('error')}")
                else:
                    result = council_review.get('result') or {}
                    proposal = result.get('proposal') or {}
                    council_decision = result.get('council_decision') or {}

                    # Show what the orchestrator's agents recommended (top proposal)
                    prop_action = proposal.get('action')
                    prop_agent = proposal.get('agent')
                    prop_conf = proposal.get('confidence')
                    st.write(f"Top proposal: **{prop_action}** ({prop_agent})")
                    if isinstance(prop_conf, (int, float)):
                        st.write(f"Proposal confidence: {float(prop_conf) * 100:.0f}%")

                    # Show council decision
                    approved = bool(result.get('approved'))
                    if approved:
                        st.success("Council: APPROVED")
                    else:
                        st.error("Council: REJECTED")

                    approval_pct = council_decision.get('approval_percentage')
                    final_conf = council_decision.get('final_confidence')
                    if approval_pct is not None:
                        try:
                            st.write(f"Council approval: {float(approval_pct):.1f}%")
                        except Exception:
                            pass
                    if final_conf is not None:
                        try:
                            st.write(f"Council final confidence: {float(final_conf) * 100:.0f}%")
                        except Exception:
                            pass

                    # Show execution (if any)
                    if result.get('execution') is not None:
                        exec_result = result.get('execution')
                        st.write("**Execution:**")
                        if isinstance(exec_result, dict):
                            if exec_result.get('status') == 'success':
                                st.success("Execution: SUCCESS")
                            else:
                                st.info(f"Execution: {exec_result.get('status', 'unknown')}")
                            st.json(exec_result)
                        else:
                            st.write(exec_result)
            else:
                st.write("**🏛️ Council Review:**")
                if council_review.get('error'):
                    st.warning(f"Council review failed: {council_review.get('error')}")
                else:
                    approved = bool(council_review.get('approved'))
                    if approved:
                        st.success("Council: APPROVED")
                    else:
                        st.error("Council: REJECTED")

                    decision = council_review.get('decision') or {}
                    approval_pct = decision.get('approval_percentage')
                    final_conf = decision.get('final_confidence')
                    if approval_pct is not None:
                        try:
                            st.write(f"Approval: {float(approval_pct):.1f}%")
                        except Exception:
                            pass
                    if final_conf is not None:
                        try:
                            st.write(f"Final confidence: {float(final_conf) * 100:.0f}%")
                        except Exception:
                            pass
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✅ Approve Trade", key=f"approve_pending_{symbol}", 
                        use_container_width=True, type="primary"):
                st.success(f"✅ Trade approved! Executing {approval['action']} {approval['shares']} {approval['symbol']}")
                st.balloons()
        with col_btn2:
            if st.button("❌ Reject Trade", key=f"reject_pending_{symbol}", 
                        use_container_width=True):
                st.warning(f"❌ Trade rejected. Notifying {approval['agent']}")


def render_market_overview() -> None:
    """Render market snapshot with major indices."""
    st.write("**Market Snapshot:**")
    market_data = pd.DataFrame({
        'Index': ['S&P 500', 'NASDAQ', 'DOW', 'Russell 2000'],
        'Value': [4825.32, 15234.87, 38125.45, 2045.23],
        'Change': ['+0.45%', '+0.82%', '+0.23%', '-0.15%']
    })
    st.dataframe(market_data, use_container_width=True, hide_index=True)
