"""

Council Dashboard - Streamlit UI for Trading Council

Displays council voting history, decisions, and statistics

"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))




import streamlit as st

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def render_council_dashboard(council, autonomous_trader=None):
    """
    Render the trading council dashboard
    
    Args:
        council: TradingCouncil instance
        autonomous_trader: AutonomousTrader instance
    """
    
    st.title("🏛️ Trading Council Dashboard")
    
    # Council Overview
    st.header("Council Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Council Members", len(council.council_members))
    
    with col2:
        st.metric("Total Decisions", len(council.voting_history))
    
    stats = council.get_council_statistics()
    
    with col3:
        approval_rate = stats.get("approval_rate", 0) * 100
        st.metric("Approval Rate", f"{approval_rate:.1f}%")
    
    with col4:
        avg_confidence = stats.get("average_confidence", 0) * 100
        st.metric("Avg Confidence", f"{avg_confidence:.1f}%")
    
    # Council Members Section
    st.header("Council Members")
    
    cols = st.columns(len(council.council_members))
    
    for idx, (key, member) in enumerate(council.council_members.items()):
        with cols[idx]:
            st.write(f"**{member['role'].value.replace('_', ' ').title()}**")
            st.caption(member['description'])
            st.write(f"Expertise: {', '.join(member['expertise'][:2])}")
    
    # Recent Decisions Section
    st.header("Recent Trading Decisions")
    
    if council.voting_history:
        # Get recent decisions
        recent_decisions = council.get_council_history(limit=10)
        
        # Create a DataFrame for better visualization
        df_decisions = []
        for decision in recent_decisions:
            df_decisions.append({
                "Symbol": decision["symbol"],
                "Action": decision["action"],
                "Approved": "✅ Yes" if decision["approved"] else "❌ No",
                "Approval %": f"{decision['approval_percentage']:.0f}%",
                "Confidence": f"{decision['final_confidence']:.1%}",
                "Consensus": "🎯 Yes" if decision["consensus_achieved"] else "⚠️ No",
                "Time": decision["timestamp"][:19]
            })
        
        df = pd.DataFrame(df_decisions)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No voting history yet. Trades will be logged here when made.")
    
    # Decision Statistics
    st.header("Decision Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Approval Rate Over Time")
        
        if council.voting_history:
            decisions = council.voting_history
            
            # Calculate cumulative approval rate
            approval_running = []
            for i in range(len(decisions)):
                approved_count = sum(1 for d in decisions[:i+1] if d.approved)
                approval_pct = (approved_count / (i + 1)) * 100
                approval_running.append(approval_pct)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=approval_running,
                mode='lines+markers',
                name='Approval Rate',
                line=dict(color='#00d4ff', width=2),
                marker=dict(size=6)
            ))
            
            fig.update_layout(
                title="Cumulative Approval Rate",
                yaxis_title="Approval %",
                xaxis_title="Decision #",
                hovermode='x unified',
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data yet")
    
    with col2:
        st.subheader("Vote Distribution")
        
        if council.voting_history:
            decisions = council.voting_history
            total_approved = sum(1 for d in decisions if d.approved)
            total_rejected = sum(1 for d in decisions if not d.approved)
            
            fig = go.Figure(data=[
                go.Pie(
                    labels=['Approved', 'Rejected'],
                    values=[total_approved, total_rejected],
                    marker=dict(colors=['#00d4ff', '#ff6b6b']),
                    hole=0.3
                )
            ])
            
            fig.update_layout(title="Decision Distribution", height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data yet")
    
    # Member Voting Patterns
    st.header("Council Member Voting Patterns")
    
    if council.voting_history:
        member_stats = {
            "Technical Analyst": {"approve": 0, "reject": 0, "abstain": 0},
            "Sentiment Analyst": {"approve": 0, "reject": 0, "abstain": 0},
            "Risk Manager": {"approve": 0, "reject": 0, "abstain": 0},
            "Memory Curator": {"approve": 0, "reject": 0, "abstain": 0}
        }
        
        # Aggregate votes by member
        for decision in council.voting_history:
            for vote in decision.council_votes:
                member_name = vote.member_name
                if member_name in member_stats:
                    if vote.decision.value == "approve":
                        member_stats[member_name]["approve"] += 1
                    elif vote.decision.value == "reject":
                        member_stats[member_name]["reject"] += 1
                    else:
                        member_stats[member_name]["abstain"] += 1
        
        # Create voting pattern chart
        members = list(member_stats.keys())
        approvals = [member_stats[m]["approve"] for m in members]
        rejections = [member_stats[m]["reject"] for m in members]
        abstentions = [member_stats[m]["abstain"] for m in members]
        
        fig = go.Figure(data=[
            go.Bar(name='Approve', x=members, y=approvals, marker_color='#00d4ff'),
            go.Bar(name='Reject', x=members, y=rejections, marker_color='#ff6b6b'),
            go.Bar(name='Abstain', x=members, y=abstentions, marker_color='#ffa500')
        ])
        
        fig.update_layout(
            barmode='group',
            title="Member Voting Patterns",
            yaxis_title="Number of Votes",
            xaxis_title="Council Member",
            hovermode='x unified',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No voting history yet")
    
    # Confidence Distribution
    st.header("Council Confidence Distribution")
    
    if council.voting_history:
        confidences = [d.final_confidence * 100 for d in council.voting_history]
        
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=confidences,
            nbinsx=10,
            marker=dict(color='#00d4ff'),
            name='Confidence'
        ))
        
        fig.update_layout(
            title="Distribution of Council Confidence Levels",
            xaxis_title="Confidence %",
            yaxis_title="Frequency",
            height=300
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No voting history yet")
    
    # Detailed Vote Analysis
    st.header("Detailed Vote Analysis")
    
    if council.voting_history:
        selected_decision_idx = st.slider(
            "Select decision to analyze",
            0,
            len(council.voting_history) - 1,
            len(council.voting_history) - 1
        )
        
        decision = council.voting_history[selected_decision_idx]
        
        st.subheader(f"{decision.symbol} - {decision.action}")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Approved", "✅ Yes" if decision.approved else "❌ No")
        
        with col2:
            st.metric("Approval %", f"{decision.approval_percentage:.1f}%")
        
        with col3:
            st.metric("Confidence", f"{decision.final_confidence:.1%}")
        
        with col4:
            st.metric("Consensus", "🎯 Yes" if decision.consensus_achieved else "⚠️ No")
        
        st.write("**Discussion Summary:**")
        st.write(decision.discussion_summary)
        
        st.write("**Member Votes:**")
        
        vote_data = []
        for vote in decision.council_votes:
            vote_data.append({
                "Member": vote.member_name,
                "Role": vote.role.value,
                "Vote": vote.decision.value.upper(),
                "Confidence": f"{vote.confidence:.1%}",
                "Reasoning": vote.reasoning
            })
        
        df_votes = pd.DataFrame(vote_data)
        st.dataframe(df_votes, use_container_width=True, hide_index=True)
    else:
        st.info("No voting history yet. Make some trades with council approval enabled.")
    
    # Council Settings
    st.header("Council Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**Approval Threshold:** {council.approval_threshold * 100:.0f}%")
        st.caption("Minimum approval needed for trade authorization")
    
    with col2:
        st.write(f"**Consensus Threshold:** {council.consensus_threshold * 100:.0f}%")
        st.caption("Vote agreement level to achieve consensus")
    
    # Council Status
    st.header("Council Status")
    
    if autonomous_trader and hasattr(autonomous_trader, 'council'):
        if autonomous_trader.council:
            st.success("✅ Council integrated with autonomous trader")
            st.write("Council approval is **required** for all trades")
        else:
            st.warning("⚠️ Council not integrated with autonomous trader")
    else:
        st.info("ℹ️ Council is standalone - integration with trader not detected")


def create_council_page():
    """Create a Streamlit page for the council dashboard"""
    
    st.set_page_config(
        page_title="Council Dashboard",
        page_icon="🏛️",
        layout="wide"
    )
    
    # Import council if available
    try:
        from services.trading_council import TradingCouncil
        
        # Initialize session state
        if 'council' not in st.session_state:
            st.session_state.council = TradingCouncil()
        
        render_council_dashboard(st.session_state.council)
    
    except ImportError as e:
        st.error(f"Error loading council: {e}")


if __name__ == "__main__":
    create_council_page()
