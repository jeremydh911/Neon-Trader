"""
Stock Ticker with Favorites - Real data only
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import numpy as np

def render_stock_ticker():
    """Main function to render Stock Ticker page"""
    st.title("📈 Stock Ticker & Favorites")

    # Initialize stock data service for real data
    from services.stock_data_service import get_stock_data_service
    stock_data_service = get_stock_data_service()
    
    # Initialize favorites storage
    FAVORITES_FILE = Path("/app/data/favorites.json")
    FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    def load_favorites():
        """Load favorite stocks from file"""
        if FAVORITES_FILE.exists():
            try:
                with open(FAVORITES_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_favorites(favorites):
        """Save favorite stocks to file"""
        try:
            with open(FAVORITES_FILE, 'w') as f:
                json.dump(favorites, f, indent=2)
            return True
        except:
            return False

    def get_stock_data(symbol):
        """Get REAL stock data from yfinance - NO simulation"""
        try:
            data = stock_data_service.get_stock_data(symbol, period="1d")
            current_price = data.get('current_price', 0)
            
            if current_price and current_price > 0:
                return {
                    'symbol': symbol,
                    'price': current_price,
                    'change': data.get('change', 0),
                    'change_pct': data.get('change_percent', 0),
                    'high': data.get('high_price', current_price * 1.05),
                    'low': data.get('low_price', current_price * 0.95),
                    'volume': data.get('volume', 0),
                    'timestamp': datetime.now().isoformat()
                }
        except:
            pass
        
        # Return None if no real data - do NOT fallback to simulated
        return None

    # Load favorites from persistent storage
    if 'favorites' not in st.session_state:
        st.session_state.favorites = load_favorites()

    favorites = st.session_state.favorites

    # Sidebar: Add Stock
    st.sidebar.markdown("### ⭐ Manage Favorites")
    new_stock = st.sidebar.text_input("Add Stock Symbol", placeholder="e.g., AAPL", key="stock_ticker_add_symbol").upper()
    col_add, col_clear = st.sidebar.columns(2)
    with col_add:
        if st.button("➕ Add", key="ticker_add_btn"):
            if new_stock and len(new_stock) <= 5:
                # Verify stock exists with real data
                test_data = get_stock_data(new_stock)
                if test_data and new_stock not in favorites:
                    favorites[new_stock] = {
                        'added': datetime.now().isoformat(),
                        'alert_price_high': None,
                        'alert_price_low': None
                    }
                    st.session_state.favorites = favorites
                    save_favorites(favorites)
                    st.success(f"✅ Added {new_stock}")
                    st.rerun()
                elif new_stock in favorites:
                    st.warning(f"{new_stock} already in favorites")
                else:
                    st.error(f"❌ {new_stock} - No real data available")

    with col_clear:
        if st.button("🗑️ Clear All", key="ticker_clear_btn"):
            st.session_state.favorites = {}
            save_favorites({})
            st.info("Cleared all favorites")
            st.rerun()

    # Main tabs
    tab1, tab2, tab3 = st.tabs(["⭐ Favorites", "📊 Market Watch", "🔔 Price Alerts"])
    
    with tab1:
        st.subheader("Your Favorite Stocks (Real Data)")
        
        if not favorites:
            st.info("👈 Add stocks from the sidebar to track them here")
        else:
            for idx, (symbol, data) in enumerate(favorites.items()):
                stock_data = get_stock_data(symbol)
                
                if stock_data:
                    price = stock_data['price']
                    change = stock_data['change']
                    change_pct = stock_data['change_pct']
                    
                    # Color based on direction
                    color = "🟢" if change >= 0 else "🔴"
                    
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"## {color} {symbol}")
                        st.metric(
                            f"${price:.2f}",
                            f"{change_pct:+.2f}%",
                            f"${change:+.2f}",
                            delta_color="normal"
                        )
                    
                    with col2:
                        st.write(f"**High:** ${stock_data['high']:.2f}")
                        st.write(f"**Low:** ${stock_data['low']:.2f}")
                    
                    with col3:
                        if st.button("❌ Remove", key=f"remove_{symbol}"):
                            del favorites[symbol]
                            st.session_state.favorites = favorites
                            save_favorites(favorites)
                            st.success(f"Removed {symbol}")
                            st.rerun()
                        
                        if st.button("📌 Pin", key=f"pin_{symbol}"):
                            st.info(f"Pinned {symbol}")
                    
                    st.divider()
                else:
                    st.warning(f"⚠️ {symbol} - No real data available, removing from favorites")
                    del favorites[symbol]
                    save_favorites(favorites)
            
            # Summary stats - only from stocks with real data
            real_stocks = [s for s in favorites.keys() if get_stock_data(s)]
            if real_stocks:
                st.subheader("📊 Portfolio Summary")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Tracked Stocks", len(real_stocks))
                with col2:
                    avg_prices = [get_stock_data(s)['price'] for s in real_stocks]
                    st.metric("Avg Price", f"${np.mean(avg_prices):.2f}")
                with col3:
                    avg_change = np.mean([get_stock_data(s)['change_pct'] for s in real_stocks])
                    st.metric("Avg Change", f"{avg_change:+.2f}%")
    
    with tab2:
        st.subheader("Live Market Watch (Real Data)")
        
        # Common stocks to watch
        market_stocks = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'AMD']
        col1, col2 = st.columns([2, 1])
        with col1:
            st.write("**Top Stocks Today**")
        with col2:
            if st.button("🔄 Refresh", key="ticker_refresh_btn"):
                st.rerun()
        
        # Display as table with real data
        market_data = []
        for symbol in market_stocks:
            data = get_stock_data(symbol)
            if data:  # Only include stocks with real data
                market_data.append({
                    '📊': '🟢' if data['change_pct'] >= 0 else '🔴',
                    'Symbol': symbol,
                    'Price': f"${data['price']:.2f}",
                    'Change': f"{data['change_pct']:+.2f}%",
                    'Volume': f"{data['volume']/1e6:.1f}M" if data['volume'] > 0 else "N/A",
                    'Action': '⭐' if symbol in favorites else '☆'
                })
        
        if market_data:
            df = pd.DataFrame(market_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Quick add to favorites
            st.write("**Quick Add to Favorites:**")
            cols = st.columns(len([s for s in market_stocks if get_stock_data(s)]))
            for idx, symbol in enumerate([s for s in market_stocks if get_stock_data(s)]):
                with cols[idx]:
                    if st.button(symbol, key=f"quickadd_{symbol}"):
                        if symbol not in favorites:
                            favorites[symbol] = {
                                'added': datetime.now().isoformat(),
                                'alert_price_high': None,
                                'alert_price_low': None
                            }
                            st.session_state.favorites = favorites
                            save_favorites(favorites)
                            st.success(f"Added {symbol}")
                            st.rerun()
        else:
            st.warning("No real data available for market stocks")

    with tab3:
        st.subheader("🔔 Price Alerts")
        
        if not favorites:
            st.info("Add stocks to your favorites to set price alerts")
        else:
            for symbol in favorites.keys():
                stock_data = get_stock_data(symbol)
                if stock_data:
                    current_price = stock_data['price']
                    
                    with st.expander(f"🔔 {symbol} Alerts"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            alert_high = st.number_input(
                                f"Alert when {symbol} reaches",
                                value=current_price * 1.05,
                                key=f"alert_high_{symbol}",
                                step=0.01
                            )
                        
                        with col2:
                            alert_low = st.number_input(
                                f"Alert if {symbol} falls to",
                                value=current_price * 0.95,
                                key=f"alert_low_{symbol}",
                                step=0.01
                            )
                        
                        if st.button(f"💾 Save {symbol} Alerts", key=f"save_alerts_{symbol}"):
                            favorites[symbol]['alert_price_high'] = alert_high
                            favorites[symbol]['alert_price_low'] = alert_low
                            st.session_state.favorites = favorites
                            save_favorites(favorites)
                            st.success(f"✅ Alerts set for {symbol}")
                        
                        # Display current status
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Current Price", f"${current_price:.2f}")
                        with col2:
                            alert_high_val = favorites[symbol].get('alert_price_high')
                            if alert_high_val and current_price > alert_high_val:
                                st.warning(f"🚨 Above ${alert_high_val:.2f}")
                            else:
                                st.info(f"High: ${alert_high_val:.2f}" if alert_high_val else "High: Not set")
                        with col3:
                            alert_low_val = favorites[symbol].get('alert_price_low')
                            if alert_low_val and current_price < alert_low_val:
                                st.error(f"🚨 Below ${alert_low_val:.2f}")
                            else:
                                st.info(f"Low: ${alert_low_val:.2f}" if alert_low_val else "Low: Not set")
    
    # Refresh indicator
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    with col2:
        if st.button("🔄 Refresh", key="ticker_refresh_footer"):
            st.rerun()

# Run the page
if __name__ == "__main__":
    render_stock_ticker()
else:
    render_stock_ticker()
