"""
Agent Status Display Module

Handles agent status cards, health indicators, and performance summary displays.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict, Any, List
from datetime import datetime


def get_agent_roster() -> List[Dict[str, Any]]:
    """Return the list of all agents with their current status and metrics."""
    return [
        {"name": "TurboTrade Tina", "specialty": "Momentum", "status": "🟢 Active", "win_rate": 68, "trades": 45},
        {"name": "DeepValue Dan", "specialty": "Value", "status": "🟢 Active", "win_rate": 72, "trades": 23},
        {"name": "EcoEdge Eddie", "specialty": "ESG", "status": "🟢 Active", "win_rate": 65, "trades": 18},
        {"name": "TechTitan Tara", "specialty": "Tech", "status": "🟢 Active", "win_rate": 71, "trades": 34},
        {"name": "DividendDuke Doug", "specialty": "Income", "status": "🟡 Idle", "win_rate": 58, "trades": 12},
        {"name": "GlobalGains Gina", "specialty": "International", "status": "🟢 Active", "win_rate": 62, "trades": 27},
        {"name": "SectorSwift Sam", "specialty": "Rotation", "status": "🟢 Active", "win_rate": 69, "trades": 31},
        {"name": "GrowthGuru Greg", "specialty": "Growth", "status": "🟢 Active", "win_rate": 64, "trades": 29},
        {"name": "QuantQueen Quinn", "specialty": "Quant", "status": "🟢 Active", "win_rate": 75, "trades": 41},
        {"name": "RiskRush Riley", "specialty": "High-Risk", "status": "🔴 Halted", "win_rate": 52, "trades": 19}
    ]


def render_agent_card(agent: Dict[str, Any], memory_system: Any) -> None:
    """Render an individual agent status card with metrics and actions."""
    with st.expander(f"{agent['status']} **{agent['name']}** ({agent['specialty']})", expanded=False):
        col_stat1, col_stat2 = st.columns(2)
        
        with col_stat1:
            st.metric("Win Rate", f"{agent['win_rate']}%")
        with col_stat2:
            st.metric("Trades", agent['trades'])
        
        # View memory button
        if st.button(f"📚 View Memory", key=f"memory_{agent['name']}", use_container_width=True):
            st.info(f"Loading {agent['name']}'s experiences...")
            
            # Retrieve agent memory
            memories = memory_system.recall_similar_situations(
                agent_name=agent['name'],
                current_conditions={'looking_at': 'all_experiences'}
            )
            
            if memories:
                st.write(f"**Recent Experiences** ({len(memories)} total):")
                for mem in memories[:3]:
                    st.write(f"- {mem.get('symbol')} {mem.get('action')}: {mem.get('outcome')} ({mem.get('timestamp', '')[:10]})")
            else:
                st.write("No experiences recorded yet")
        
        # Chat with agent button
        if st.button(f"💬 Chat", key=f"chat_{agent['name']}", use_container_width=True):
            st.session_state[f"show_chat_{agent['name']}"] = True


def render_agent_status(memory_system: Any) -> None:
    """Render the agent status section with all agent cards."""
    st.subheader("🤖 Active Agents")
    
    agents = get_agent_roster()
    
    # Render each agent card
    for agent in agents:
        render_agent_card(agent, memory_system)


def render_performance_summary() -> None:
    """Render the performance summary section with aggregated metrics and chart."""
    st.divider()
    st.subheader("📊 Performance Summary")
    
    agents = get_agent_roster()
    total_trades = sum(a['trades'] for a in agents)
    avg_win_rate = sum(a['win_rate'] for a in agents) / len(agents)
    
    col_perf1, col_perf2 = st.columns(2)
    with col_perf1:
        st.metric("Total Trades", total_trades)
    with col_perf2:
        st.metric("Avg Win Rate", f"{avg_win_rate:.1f}%")
    
    # Performance chart
    perf_df = pd.DataFrame({
        'Agent': [a['name'].split()[0] for a in agents],
        'Win Rate': [a['win_rate'] for a in agents]
    })
    
    fig = go.Figure(data=[
        go.Bar(
            x=perf_df['Agent'],
            y=perf_df['Win Rate'],
            marker_color=['green' if w > 65 else 'orange' if w > 55 else 'red' for w in perf_df['Win Rate']],
            text=perf_df['Win Rate'],
            textposition='auto'
        )
    ])
    fig.update_layout(
        title="Agent Win Rates",
        xaxis_title="Agent",
        yaxis_title="Win Rate (%)",
        height=300,
        template="plotly_dark",
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True, key="agent_perf_chart")


def render_system_status() -> None:
    """Render system health status indicators."""
    st.write("**System Status:**")
    st.write("- 🟢 All agents operational")
    st.write("- 🟢 Data feed: Real-time")
    st.write("- 🟢 Broker connection: Active")
    st.write("- 🟢 Risk limits: Normal")
