"""
E*TRADE Dashboard - Streamlit Page
Real-time account monitoring, portfolio tracking, and order management
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import logging
from typing import Dict, List
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.etrade_service import ETradeService
from services.stonks_backup import get_stonks_backup_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="E*TRADE Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .positive {
        color: #28a745;
    }
    .negative {
        color: #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("📊 E*TRADE Dashboard")
st.markdown("Real-time account monitoring, portfolio tracking, and order management")

# Initialize session state
if 'etrade_service' not in st.session_state:
    st.session_state.etrade_service = ETradeService()
    logger.info("E*TRADE service initialized")

etrade_service = st.session_state.etrade_service

# Check authentication status
service_status = etrade_service.get_status()

if not service_status['is_authenticated']:
    st.warning("⚠️ E*TRADE Not Connected")
    st.info("""
    To connect E*TRADE:
    1. Navigate to the OAuth Manager page
    2. Complete the authentication flow
    3. Return to this dashboard
    
    Until then, you're using paper trading mode.
    """)
else:
    env_label = service_status.get("environment", "Sandbox")
    st.success(f"E*TRADE Connected ({env_label})")
    try:
        from services.desk_risk import DeskRiskGate
        clock = DeskRiskGate().hawaii_clock()
        st.caption(
            f"Session clock {clock['et']} ET / {clock['ht']} HT "
            f"({clock['offset_note']}) — phase {clock['phase']}"
        )
    except Exception:
        st.caption("Session 07:00–20:00 ET (HT = ET-6 in August). Blackout 04:00–07:00 ET.")

# Sidebar
with st.sidebar:
    st.header("🔧 Controls")
    
    # Refresh button
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()
    
    st.divider()
    
    # Status indicator
    st.subheader("Connection Status")
    if service_status['is_authenticated']:
        st.success(f"Connected ({service_status.get('environment', 'Sandbox')})")
    else:
        st.error("❌ Not Connected")
    
    st.caption(service_status['status'])
    
    st.divider()
    
    # Quick actions
    st.subheader("📌 Quick Actions")
    tab1, tab2 = st.tabs(["Account", "Trading"])
    
    with tab1:
        selected_account = st.selectbox(
            "Select Account:",
            options=["ACC123456", "ACC234567"],  # Placeholder
            key="sidebar_account"
        )
    
    with tab2:
        st.button("Place Order", use_container_width=True, key="quick_order")
        st.button("View Orders", use_container_width=True, key="view_orders")

# Main content
if service_status['is_authenticated']:
    
    # Get accounts
    accounts = etrade_service.get_accounts()
    
    if not accounts:
        st.warning("No accounts found. Please authenticate first.")
    else:
        # Account selection
        account_names = [f"{acc['account_name']} ({acc['account_id']})" for acc in accounts]
        selected_account_idx = st.selectbox(
            "Select Account:",
            range(len(accounts)),
            format_func=lambda i: account_names[i],
            key="main_account"
        )
        
        selected_account = accounts[selected_account_idx]
        account_id = selected_account['account_id']
        
        st.divider()
        
        # Account Overview Section
        st.subheader("💰 Account Overview")
        
        # Get account balance
        balance = etrade_service.get_account_balance(account_id)
        
        if balance:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Cash Balance",
                    f"${balance['cash']:,.2f}",
                    delta=None
                )
            
            with col2:
                st.metric(
                    "Portfolio Value",
                    f"${balance['portfolio_value']:,.2f}",
                    delta=None
                )
            
            with col3:
                st.metric(
                    "Total Value",
                    f"${balance['total_value']:,.2f}",
                    delta=None
                )
            
            with col4:
                st.metric(
                    "Buying Power",
                    f"${balance['buying_power']:,.2f}",
                    delta=None
                )
        
        st.divider()
        
        # Portfolio Section
        st.subheader("📈 Portfolio Holdings")
        
        positions = etrade_service.get_portfolio(account_id)
        
        if positions:
            # Create portfolio DataFrame
            portfolio_data = []
            for pos in positions:
                portfolio_data.append({
                    'Symbol': pos['symbol'],
                    'Quantity': pos['quantity'],
                    'Price': f"${pos['price']:.2f}",
                    'Value': f"${pos['position_value']:,.2f}",
                    'Gain/Loss': f"${pos['gain_loss']:.2f}",
                    'Gain/Loss %': f"{pos['gain_loss_percent']:.2f}%"
                })
            
            portfolio_df = pd.DataFrame(portfolio_data)
            st.dataframe(
                portfolio_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'Symbol': st.column_config.TextColumn(width="small"),
                    'Quantity': st.column_config.NumberColumn(width="small"),
                    'Price': st.column_config.TextColumn(width="medium"),
                    'Value': st.column_config.TextColumn(width="medium"),
                    'Gain/Loss': st.column_config.TextColumn(width="medium"),
                    'Gain/Loss %': st.column_config.TextColumn(width="medium")
                }
            )
            
            # Portfolio visualization
            st.markdown("### Position Distribution")
            
            symbols = [pos['symbol'] for pos in positions]
            values = [pos['position_value'] for pos in positions]
            
            fig = go.Figure(data=[go.Pie(
                labels=symbols,
                values=values,
                hovertemplate="<b>%{label}</b><br>Value: $%{value:,.2f}<br>%{percent}<extra></extra>"
            )])
            
            fig.update_layout(
                height=400,
                showlegend=True,
                font=dict(size=12)
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        else:
            st.info("No positions in portfolio")
        
        st.divider()
        
        # Stock Quotes Section
        st.subheader("📊 Stock Quotes")
        
        # Get quotes for symbols in portfolio
        if positions:
            quote_symbols = [pos['symbol'] for pos in positions]
            quotes = etrade_service.get_quotes_batch(quote_symbols)
            
            if quotes:
                quote_data = []
                for symbol, quote in quotes.items():
                    if quote:
                        quote_data.append({
                            'Symbol': symbol,
                            'Price': f"${quote['price']:.2f}",
                            'Bid': f"${quote['bid']:.2f}",
                            'Ask': f"${quote['ask']:.2f}",
                            'Change': f"${quote['change']:.2f}",
                            'Change %': f"{quote['change_percent']:.2f}%",
                            'Volume': f"{quote['volume']:,}"
                        })
                
                quotes_df = pd.DataFrame(quote_data)
                st.dataframe(
                    quotes_df,
                    use_container_width=True,
                    hide_index=True
                )
        
        st.divider()
        
        # Orders Section
        st.subheader("📋 Open Orders")
        
        orders = etrade_service.get_orders(account_id)
        
        if orders:
            orders_data = []
            for order in orders:
                orders_data.append({
                    'Order ID': order['order_id'],
                    'Symbol': order['symbol'],
                    'Side': order['side'],
                    'Quantity': order['quantity'],
                    'Type': order['order_type'],
                    'Price': f"${order['price']:.2f}" if order['price'] else "Market",
                    'Status': order['status'],
                    'Placed': order['placed_time'][:10] if order['placed_time'] else 'N/A'
                })
            
            orders_df = pd.DataFrame(orders_data)
            st.dataframe(
                orders_df,
                use_container_width=True,
                hide_index=True
            )
            
            # Cancel order section
            st.markdown("### Manage Orders")
            col1, col2 = st.columns([3, 1])
            
            with col1:
                order_to_cancel = st.selectbox(
                    "Select order to cancel:",
                    options=[o['order_id'] for o in orders],
                    format_func=lambda oid: f"{oid} - {[o['symbol'] for o in orders if o['order_id'] == oid][0]}",
                    key="cancel_order_select"
                )
            
            with col2:
                if st.button("🗑️ Cancel Order", use_container_width=True):
                    with st.spinner("Canceling order..."):
                        result = etrade_service.cancel_order(account_id, order_to_cancel)
                        if result:
                            st.success("✅ Order cancelled successfully")
                            st.rerun()
                        else:
                            st.error("❌ Failed to cancel order")
        
        else:
            st.info("No open orders")
        
        st.divider()
        
        # Place Order Section
        st.subheader("📝 Place New Order")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            order_symbol = st.text_input(
                "Symbol:",
                placeholder="e.g., TSLA",
                value="TSLA"
            ).upper()
        
        with col2:
            order_quantity = st.number_input(
                "Quantity:",
                min_value=1,
                value=1,
                step=1
            )
        
        with col3:
            order_side = st.selectbox(
                "Side:",
                options=["Buy", "Sell"]
            )
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            order_type = st.selectbox(
                "Order Type:",
                options=["Limit"],
                help="Desk is LIMIT-only. Premarket/after-hours use EXTENDED + GOOD_FOR_DAY.",
            )
        
        with col2:
            order_price = st.number_input(
                "Limit Price:",
                value=100.00,
                step=0.01,
            )
        
        is_sandbox = service_status.get("sandbox", True)
        if "pending_preview" not in st.session_state:
            st.session_state.pending_preview = None

        confirm_live = True
        if not is_sandbox:
            st.warning("LIVE E*TRADE — preview then place; one-shot place is disabled.")
            confirm_live = st.checkbox(
                "I confirm this LIVE E*TRADE order",
                value=False,
                key="confirm_live_order",
            )

        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            if st.button("Preview", use_container_width=True, key="preview_order"):
                with st.spinner("Previewing order..."):
                    result = etrade_service.place_order(
                        account_id=account_id,
                        symbol=order_symbol,
                        quantity=order_quantity,
                        side=order_side,
                        order_type=order_type,
                        price=order_price,
                        preview=True,
                    )
                    if result and result.get("status") not in ("ERROR", "error"):
                        st.session_state.pending_preview = result
                        st.success("Order preview successful")
                        st.json(result.get("order_data", result))
                    else:
                        st.session_state.pending_preview = None
                        st.error((result or {}).get("message") or "Failed to preview order")

        with col2:
            if st.button("Place Order", use_container_width=True, key="place_order"):
                pending = st.session_state.get("pending_preview") or {}
                preview_id = pending.get("preview_id")
                if not preview_id:
                    st.error("Preview first. Place is separate from preview; live will not one-shot.")
                elif not is_sandbox and not confirm_live:
                    st.error("LIVE place requires the per-order confirm checkbox.")
                else:
                    with st.spinner("Placing order..."):
                        result = etrade_service.place_order(
                            account_id=account_id,
                            symbol=order_symbol,
                            quantity=order_quantity,
                            side=order_side,
                            order_type=order_type,
                            price=order_price,
                            preview=False,
                            preview_id=preview_id,
                            client_order_id=pending.get("client_order_id"),
                            confirm_live=confirm_live,
                        )
                        if result and result.get("status") not in ("ERROR", "error"):
                            st.session_state.pending_preview = None
                            st.success("Order placed")
                            st.json(result)
                            st.rerun()
                        else:
                            st.error((result or {}).get("message") or "Failed to place order")
        
        st.divider()
        
        # Debug Information
        with st.expander("🔍 Debug Information"):
            st.json({
                'Account ID': account_id,
                'Account Type': selected_account.get('account_type'),
                'Option Level': selected_account.get('option_level'),
                'E*TRADE Status': service_status,
                'Timestamp': datetime.now().isoformat()
            })

else:
    # Stonks fallback mode
    st.info("""
    ### Using Stonks Fallback Data
    
    E*TRADE is not connected. Displaying data from Stonks backup service:
    - Real market data from public sources
    - Delayed quotes
    - Historical chart data
    
    **To enable live E*TRADE integration:**
    1. Go to the OAuth Manager page
    2. Complete the authentication flow
    3. Return here to access your real account and live data
    """)
    
    # Show stonks portfolio data
    st.subheader("📈 Portfolio (Stonks Data)")
    
    stonks_service = get_stonks_backup_service()
    
    # Test with TSLA and F
    test_symbols = ['TSLA', 'F']
    portfolio_data = []
    
    for symbol in test_symbols:
        stock_info = stonks_service.get_stock_info(symbol)
        if stock_info:
            # Extract from OHLCV data
            if isinstance(stock_info, list) and len(stock_info) > 0:
                latest = stock_info[0]
                price = latest.get('c', 0)  # close price
                portfolio_data.append({
                    'Symbol': symbol,
                    'Price': f"${price:.2f}",
                    'Open': f"${latest.get('o', 0):.2f}",
                    'High': f"${latest.get('h', 0):.2f}",
                    'Low': f"${latest.get('l', 0):.2f}",
                    'Volume': f"{latest.get('v', 0):,}",
                    'Source': 'Stonks'
                })
            elif isinstance(stock_info, dict):
                price = stock_info.get('price', stock_info.get('c', 0))
                portfolio_data.append({
                    'Symbol': symbol,
                    'Price': f"${price:.2f}",
                    'Data': 'Available',
                    'Source': 'Stonks'
                })
    
    if portfolio_data:
        portfolio_df = pd.DataFrame(portfolio_data)
        st.dataframe(portfolio_df, use_container_width=True, hide_index=True)
        
        # Show chart for available symbols
        st.markdown("### Price History")
        
        chart_symbol = st.selectbox(
            "Select symbol to view chart:",
            options=test_symbols,
            key="stonks_chart_select"
        )
        
        chart_data = stonks_service.get_chart_data(chart_symbol)
        if chart_data:
            # Convert to DataFrame for plotting
            chart_df = pd.DataFrame(chart_data)
            if not chart_df.empty:
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=chart_df['date'],
                    y=chart_df['close'],
                    mode='lines',
                    name='Close Price',
                    fill='tozeroy'
                ))
                
                fig.update_layout(
                    title=f"{chart_symbol} Price History (Stonks)",
                    xaxis_title="Date",
                    yaxis_title="Price ($)",
                    height=400,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"No chart data available for {chart_symbol} from Stonks")
    
    else:
        st.warning("Unable to fetch data from Stonks. Please check your connection and try again.")

st.divider()

# Footer
st.markdown("""
---
**E*TRADE Dashboard** | Neon Trader v1.0
- Environment: Sandbox (Paper Trading)
- Last Updated: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """
- 📖 [E*TRADE API Docs](https://apisb.etrade.com/docs/api/account/api-account-v1.html)
""")
