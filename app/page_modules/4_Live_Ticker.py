"""
Live Trade Ticker - Real trades only
Displays autonomous trader activity with real executed trades
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from pathlib import Path
import json

# Add parent directory to path
from services.memory_service import MemoryService

st.set_page_config(page_title="Live Ticker", page_icon="📊", layout="wide")
st.title("📊 Live Trade Ticker")
st.markdown("Real-time autonomous trader activity - Real trades only")

# Initialize services
@st.cache_resource
def init_services():
    memory_service = MemoryService()
    return memory_service

memory_service = init_services()

def load_real_trades():
    """Load REAL trades from JSON files - NOT simulated"""
    all_trades = []
    
    # Load Alpaca trades
    try:
        alpaca_file = Path('/app/data/orders.json')
        if alpaca_file.exists():
            with open(alpaca_file) as f:
                alpaca_trades = json.load(f)
                if alpaca_trades:
                    for trade in alpaca_trades:
                        trade['broker'] = 'Alpaca'
                        all_trades.append(trade)
    except Exception as e:
        st.warning(f"Could not load Alpaca trades: {e}")
    
    # Load E*TRADE trades
    try:
        etrade_file = Path('/app/data/etrade_orders.json')
        if etrade_file.exists():
            with open(etrade_file) as f:
                etrade_trades = json.load(f)
                if etrade_trades:
                    for trade in etrade_trades:
                        trade['broker'] = 'E*TRADE'
                        all_trades.append(trade)
    except Exception as e:
        st.warning(f"Could not load E*TRADE trades: {e}")
    
    # Sort by timestamp descending
    all_trades.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return all_trades

# Sidebar controls
st.sidebar.markdown("### ⚙️ Ticker Settings")

show_all = st.sidebar.checkbox("Show all time", value=False)
broker_filter = st.sidebar.multiselect(
    "Filter by Broker",
    ["Alpaca", "E*TRADE"],
    default=["Alpaca", "E*TRADE"],
    key="ticker_broker_filter"
)

# Display real trades
st.markdown("### 📈 Executed Trades")

real_trades = load_real_trades()

if real_trades:
    # Filter by broker
    filtered_trades = [t for t in real_trades if t.get('broker') in broker_filter]
    
    if filtered_trades:
        # Create ticker display
        ticker_data = []
        for trade in filtered_trades[:50]:  # Show last 50 trades
            ticker_data.append({
                "⏰ Time": trade.get('timestamp', 'N/A')[:19] if trade.get('timestamp') else 'N/A',
                "💼 Broker": trade.get('broker', 'N/A'),
                "📍 Symbol": trade.get('symbol', 'N/A'),
                "💹 Action": trade.get('side', 'N/A'),
                "💵 Price": f"${trade.get('entry_price', 0):.2f}" if trade.get('entry_price') else "N/A",
                "�� Quantity": int(trade.get('qty', trade.get('quantity', 0))),
                "💰 Status": trade.get('status', 'EXECUTED')
            })
        
        df_ticker = pd.DataFrame(ticker_data)
        st.dataframe(df_ticker, use_container_width=True, hide_index=True)
        
        st.success(f"✅ Showing {len(filtered_trades)} executed trades")
    else:
        st.info("No trades match the selected brokers")
else:
    st.info("📊 No trades executed yet. Executed trades will appear here.")

# Trading Statistics from real trades
st.markdown("### 📊 Trading Statistics")

if real_trades:
    total_trades = len(real_trades)
    buy_trades = len([t for t in real_trades if t.get('side') == 'BUY'])
    sell_trades = len([t for t in real_trades if t.get('side') == 'SELL'])
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades", total_trades)
    with col2:
        st.metric("Buy Orders", buy_trades)
    with col3:
        st.metric("Sell Orders", sell_trades)
    with col4:
        if total_trades > 0:
            buy_pct = (buy_trades / total_trades) * 100
            st.metric("Buy %", f"{buy_pct:.1f}%")
        else:
            st.metric("Buy %", "0%")
else:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Trades", 0)
    with col2:
        st.metric("Buy Orders", 0)
    with col3:
        st.metric("Sell Orders", 0)
    with col4:
        st.metric("Buy %", "0%")

# Trades by Symbol
st.markdown("### 🎯 Trades by Symbol")

if real_trades:
    symbols = {}
    for trade in real_trades:
        symbol = trade.get('symbol', 'UNKNOWN')
        if symbol not in symbols:
            symbols[symbol] = []
        symbols[symbol].append(trade)
    
    for symbol in list(symbols.keys())[:10]:  # Top 10 symbols
        with st.expander(f"📌 {symbol} ({len(symbols[symbol])} trades)", expanded=False):
            symbol_trades = symbols[symbol][:20]
            symbol_data = []
            
            for trade in symbol_trades:
                symbol_data.append({
                    "Time": trade.get('timestamp', '')[:19],
                    "Broker": trade.get('broker', 'N/A'),
                    "Action": trade.get('side', 'N/A'),
                    "Price": f"${trade.get('entry_price', 0):.2f}",
                    "Qty": int(trade.get('qty', trade.get('quantity', 0))),
                    "Status": trade.get('status', 'EXECUTED')
                })
            
            st.dataframe(pd.DataFrame(symbol_data), use_container_width=True, hide_index=True)

# Auto-refresh
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    auto_refresh = st.checkbox("Auto-refresh every 5 seconds", value=False, key="ticker_auto_refresh")
with col2:
    st.caption("Loading real executed trades only - no simulation")

if auto_refresh:
    time.sleep(5)
    st.rerun()

# Instructions
st.markdown("""
### 📖 How It Works
1. **Real Trades Only** - Shows only trades executed by brokers (Alpaca, E*TRADE)
2. **Broker Filter** - Toggle each broker to filter displayed trades
3. **Statistics** - View buy/sell ratio and symbol distribution
4. **Trade Details** - Expand each symbol to see detailed trade history
5. **Auto-Refresh** - Enable auto-refresh to monitor live trading activity

### ✅ Data Source
- All trades loaded from real execution files
- No simulated or demo trades displayed
- Reflects actual broker order status
""")
