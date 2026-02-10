"""
Performance Metrics Module

Handles performance analytics, win rate tracking, Sharpe ratio, and performance charts.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict, Any, List
from datetime import datetime, timedelta


def calculate_performance_metrics() -> Dict[str, Any]:
    """Calculate aggregated performance metrics across all agents."""
    # Mock data - in production, fetch from database
    return {
        'total_trades': 279,
        'total_wins': 186,
        'total_losses': 93,
        'win_rate': 66.67,
        'total_pnl': 24567.89,
        'sharpe_ratio': 1.85,
        'max_drawdown': -2345.67,
        'avg_win': 245.30,
        'avg_loss': -132.45,
        'profit_factor': 1.85,
        'avg_hold_time': '2.3 days'
    }


def render_performance_dashboard() -> None:
    """Render comprehensive performance dashboard with key metrics."""
    st.subheader("📊 Performance Dashboard")
    
    metrics = calculate_performance_metrics()
    
    # Top-level metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades", metrics['total_trades'])
        st.metric("Win Rate", f"{metrics['win_rate']:.1f}%")
    
    with col2:
        st.metric("Total P&L", f"${metrics['total_pnl']:,.2f}")
        st.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
    
    with col3:
        st.metric("Wins", metrics['total_wins'], delta=f"+{metrics['total_wins'] - metrics['total_losses']}")
        st.metric("Avg Win", f"${metrics['avg_win']:.2f}")
    
    with col4:
        st.metric("Losses", metrics['total_losses'])
        st.metric("Avg Loss", f"${metrics['avg_loss']:.2f}")
    
    st.divider()
    
    # Advanced metrics
    col5, col6, col7 = st.columns(3)
    
    with col5:
        st.metric("Max Drawdown", f"${metrics['max_drawdown']:,.2f}")
    with col6:
        st.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")
    with col7:
        st.metric("Avg Hold Time", metrics['avg_hold_time'])


def render_equity_curve() -> None:
    """Render equity curve chart showing portfolio value over time."""
    st.subheader("📈 Equity Curve")
    
    # Generate mock equity curve data
    dates = pd.date_range(end=datetime.now(), periods=90, freq='D')
    equity = [100000]
    
    for i in range(1, 90):
        change = equity[-1] * (0.01 * (0.5 - (i % 10) / 20))  # Mock variation
        equity.append(equity[-1] + change)
    
    df = pd.DataFrame({
        'Date': dates,
        'Equity': equity
    })
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['Date'],
        y=df['Equity'],
        mode='lines',
        name='Portfolio Value',
        line=dict(color='#00ff00', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 255, 0, 0.1)'
    ))
    
    fig.update_layout(
        title="Portfolio Equity Over Time",
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        height=400,
        template="plotly_dark",
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True, key="equity_curve")


def render_win_rate_chart() -> None:
    """Render win rate comparison chart across agents."""
    st.subheader("📊 Agent Win Rate Comparison")
    
    agents_data = [
        {"name": "QuantQueen Quinn", "win_rate": 75, "trades": 41},
        {"name": "DeepValue Dan", "win_rate": 72, "trades": 23},
        {"name": "TechTitan Tara", "win_rate": 71, "trades": 34},
        {"name": "SectorSwift Sam", "win_rate": 69, "trades": 31},
        {"name": "TurboTrade Tina", "win_rate": 68, "trades": 45},
        {"name": "EcoEdge Eddie", "win_rate": 65, "trades": 18},
        {"name": "GrowthGuru Greg", "win_rate": 64, "trades": 29},
        {"name": "GlobalGains Gina", "win_rate": 62, "trades": 27},
        {"name": "DividendDuke Doug", "win_rate": 58, "trades": 12},
        {"name": "RiskRush Riley", "win_rate": 52, "trades": 19}
    ]
    
    df = pd.DataFrame(agents_data)
    
    fig = go.Figure(data=[
        go.Bar(
            x=df['name'],
            y=df['win_rate'],
            marker_color=['#00ff00' if w > 65 else '#ffaa00' if w > 55 else '#ff0000' for w in df['win_rate']],
            text=df['win_rate'],
            texttemplate='%{text}%',
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>Win Rate: %{y}%<br>Trades: %{customdata}<extra></extra>',
            customdata=df['trades']
        )
    ])
    
    fig.update_layout(
        xaxis_title="Agent",
        yaxis_title="Win Rate (%)",
        height=400,
        template="plotly_dark",
        showlegend=False,
        yaxis=dict(range=[0, 100])
    )
    
    st.plotly_chart(fig, use_container_width=True, key="win_rate_chart")


def render_pnl_by_agent() -> None:
    """Render P&L breakdown by agent."""
    st.subheader("💰 P&L by Agent")
    
    pnl_data = pd.DataFrame({
        'Agent': ['TurboTrade Tina', 'QuantQueen Quinn', 'DeepValue Dan', 'TechTitan Tara', 
                  'SectorSwift Sam', 'GrowthGuru Greg', 'GlobalGains Gina', 'EcoEdge Eddie',
                  'RiskRush Riley', 'DividendDuke Doug'],
        'P&L': [5234.50, 4892.30, 4123.45, 3876.20, 3145.80, 2567.90, 1923.45, 1456.70, -345.20, -567.30],
        'Trades': [45, 41, 23, 34, 31, 29, 27, 18, 19, 12]
    })
    
    fig = go.Figure(data=[
        go.Bar(
            x=pnl_data['Agent'],
            y=pnl_data['P&L'],
            marker_color=['green' if p > 0 else 'red' for p in pnl_data['P&L']],
            text=[f'${p:,.0f}' for p in pnl_data['P&L']],
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<br>Trades: %{customdata}<extra></extra>',
            customdata=pnl_data['Trades']
        )
    ])
    
    fig.update_layout(
        xaxis_title="Agent",
        yaxis_title="Profit/Loss ($)",
        height=400,
        template="plotly_dark",
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True, key="pnl_chart")


def render_agent_comparison() -> None:
    """Render detailed agent comparison table."""
    st.subheader("🔍 Detailed Agent Comparison")
    
    comparison_df = pd.DataFrame({
        'Agent': ['TurboTrade Tina', 'QuantQueen Quinn', 'DeepValue Dan', 'TechTitan Tara'],
        'Specialty': ['Momentum', 'Quant', 'Value', 'Tech'],
        'Win Rate': ['68%', '75%', '72%', '71%'],
        'Trades': [45, 41, 23, 34],
        'P&L': ['$5,234.50', '$4,892.30', '$4,123.45', '$3,876.20'],
        'Sharpe': [1.85, 2.12, 1.95, 1.78],
        'Max DD': ['-$432', '-$289', '-$356', '-$512']
    })
    
    st.dataframe(
        comparison_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Win Rate": st.column_config.ProgressColumn(
                "Win Rate",
                format="%s",
                min_value=0,
                max_value=100,
            ),
        }
    )


def render_performance_metrics() -> None:
    """Main function to render all performance metrics."""
    render_performance_dashboard()
    st.divider()
    render_equity_curve()
    st.divider()
    render_win_rate_chart()
    st.divider()
    render_pnl_by_agent()
