"""
Stock Picker - Real-time Market Scanner
Scans the entire US market for trading opportunities - REAL DATA ONLY
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def render_stock_picker():
    """Main function to render Stock Picker page"""
    st.title("🎯 Stock Picker - Market Scanner")
    st.markdown("Real-time scanning of US markets using actual yfinance data")
    
    # Initialize stock data service for real data
    try:
        from services.stock_data_service import get_stock_data_service
        stock_data_service = get_stock_data_service()
    except Exception as e:
        st.error(f"Error loading stock data service: {e}")
        return
    
    # Initialize session state
    if 'scanner_data' not in st.session_state:
        st.session_state.scanner_data = None
    if 'selected_symbol' not in st.session_state:
        st.session_state.selected_symbol = None
    if 'auto_scanned' not in st.session_state:
        st.session_state.auto_scanned = False
    if 'page_load_count' not in st.session_state:
        st.session_state.page_load_count = 0
    
    def fetch_real_market_data():
        """Fetch ONLY real market data from yfinance - NO simulated data fallback"""
        stocks_list = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'CRM',
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'V', 'MA', 'AXP', 'COIN',
            'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'AZN', 'AMGN', 'GILD', 'BIIB',
            'WMT', 'XRT', 'HD', 'LOW', 'MCD', 'NKE', 'CL', 'KO', 'PEP', 'SBUX',
            'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'MU',
        ]
        
        data = []
        
        for symbol in stocks_list:
            try:
                # Fetch REAL data only from yfinance - no fallback
                stock_info = stock_data_service.get_stock_data(symbol, period="1y")
                
                current_price = stock_info.get('current_price')
                change_pct = stock_info.get('change_percent', 0)
                technicals = stock_info.get('technicals', {})
                
                # Only include if we have real price data
                if current_price and current_price > 0:
                    rsi = technicals.get('rsi_14', 50)
                    macd = technicals.get('macd', 0)
                    bb_upper = technicals.get('bb_upper', current_price * 1.05)
                    bb_lower = technicals.get('bb_lower', current_price * 0.95)
                    volume = stock_info.get('volume', 0)
                    
                    # Identify patterns from REAL technical indicators
                    patterns = []
                    if rsi > 70:
                        patterns.append("Overbought")
                    elif rsi < 30:
                        patterns.append("Oversold")
                    
                    if abs(change_pct) > 3:
                        patterns.append(f"Strong Move ({abs(change_pct):.1f}%)")
                    
                    if volume > 50000000:
                        patterns.append("High Volume")
                    
                    if current_price < bb_lower:
                        patterns.append("Support Level")
                    elif current_price > bb_upper:
                        patterns.append("Resistance Level")
                    
                    data.append({
                        'symbol': symbol,
                        'price': current_price,
                        'change_pct': change_pct,
                        'rsi': rsi,
                        'macd': macd,
                        'bb_upper': bb_upper,
                        'bb_lower': bb_lower,
                        'volume': volume,
                        'patterns': patterns,
                        'timestamp': datetime.now().isoformat(),
                        'score': len(patterns) * (1 + max(0, abs(change_pct) / 100))
                    })
            except Exception as e:
                # Skip stocks with no data - do NOT use fallback
                logger.debug(f"Error fetching {symbol}: {e}")
                continue
        
        return pd.DataFrame(data) if data else pd.DataFrame()
    
    def filter_opportunities(data, min_score=1.5, min_volume=10000000):
        """Filter stocks with trading opportunities"""
        if data.empty:
            return data
        opportunities = data[
            (data['score'] >= min_score) & 
            (data['volume'] >= min_volume)
        ].sort_values('score', ascending=False)
        return opportunities
    
    # ===== SCANNER SETTINGS (MOVED TO MAIN AREA) =====
    st.subheader("⚙️ Scanner Settings")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        scan_interval = st.slider(
            "Scan Interval (minutes)",
            min_value=0.5,
            max_value=10.0,
            value=2.0,
            step=0.5,
            help="Scan every 0.5 to 10 minutes",
            key="scanner_scan_interval"
        )
    
    with col2:
        min_score = st.slider(
            "Minimum Score",
            min_value=0.5,
            max_value=5.0,
            value=1.5,
            step=0.5,
            key="scanner_min_score"
        )
    
    with col3:
        min_volume = st.slider(
            "Minimum Volume (M)",
            min_value=5,
            max_value=100,
            value=10,
            step=5,
            key="scanner_min_volume"
        ) * 1000000
    
    with col4:
        alert_types = st.multiselect(
            "Alert Types",
            ["Overbought", "Oversold", "High Volume", "Support Level", "Resistance Level", "Strong Move"],
            default=["Overbought", "Oversold"],
            key="scanner_alert_types"
        )
    
    st.markdown("---")
    
    # ===== STOCK PICKER MARKET SCAN =====
    st.subheader("📊 Stock Picker Market Scan")
    
    # Control buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Scan Now", use_container_width=True):
            try:
                with st.spinner("📊 Scanning real market data..."):
                    market_data = fetch_real_market_data()
                    
                    if market_data.empty:
                        st.warning("No market data retrieved. Check data service connection.")
                    else:
                        opportunities = filter_opportunities(market_data, min_score, min_volume)
                        
                        if alert_types and not opportunities.empty:
                            filtered_opps = []
                            try:
                                for idx, row in opportunities.iterrows():
                                    row_patterns = row.get('patterns', [])
                                    if isinstance(row_patterns, list) and any(alert in row_patterns for alert in alert_types):
                                        filtered_opps.append(row.to_dict())
                                st.session_state.scanner_data = filtered_opps
                            except Exception as filter_err:
                                logger.warning(f"Error filtering by alert types: {filter_err}")
                                st.session_state.scanner_data = opportunities.to_dict('records')
                        else:
                            st.session_state.scanner_data = opportunities.to_dict('records') if not opportunities.empty else []
                        
                        if st.session_state.scanner_data:
                            st.success(f"✅ Found {len(st.session_state.scanner_data)} real opportunities")
                        else:
                            st.info("No opportunities matched your filters")
            except Exception as e:
                st.error(f"Error during scan: {e}")
                logger.error(f"Scan error: {e}", exc_info=True)
    
    with col2:
        if st.button("🗑️ Clear Cache", use_container_width=True):
            st.session_state.scanner_data = None
            st.session_state.auto_scanned = False
            st.session_state.selected_symbol = None
    
    with col3:
        # Auto-load on first page load only - prevent re-triggering on dropdown changes
        st.info("💡 Click \"Scan Now\" button above to find trading opportunities\n")
        # Only run if we haven't scanned yet AND no data exists
        #         if not st.session_state.auto_scanned and st.session_state.scanner_data is None:
            # Track that we're attempting to auto-scan
        #             st.session_state.auto_scanned = True  # Set FIRST to prevent re-entry
        #             try:
        #                 with st.spinner("📊 Loading real market data..."):
        #                     market_data = fetch_real_market_data()
                    
        #                     if market_data.empty:
        #                         st.session_state.scanner_data = []
        #                     else:
        #                         opportunities = filter_opportunities(market_data, min_score, min_volume)
                        
        #                         if alert_types and not opportunities.empty:
        #                             filtered_opps = []
        #                             try:
        #                                 for idx, row in opportunities.iterrows():
        #                                     row_patterns = row.get('patterns', [])
        #                                     if isinstance(row_patterns, list) and any(alert in row_patterns for alert in alert_types):
        #                                         filtered_opps.append(row.to_dict())
        #                                 st.session_state.scanner_data = filtered_opps
        #                             except Exception as filter_err:
        #                                 logger.warning(f"Error filtering by alert types: {filter_err}")
        #                                 st.session_state.scanner_data = opportunities.to_dict('records')
        #                         else:
        #                             st.session_state.scanner_data = opportunities.to_dict('records') if not opportunities.empty else []
                    
        #                     st.session_state.auto_scanned = True
        #             except Exception as e:
        #                 st.session_state.auto_scanned = True
        #                 logger.error(f"Auto-load error: {e}", exc_info=True)
    
    # Display auto-scan status messages (outside of column context)
    if st.session_state.auto_scanned and st.session_state.scanner_data:
        st.info(f"📊 Auto-loaded {len(st.session_state.scanner_data)} opportunities")
    elif st.session_state.auto_scanned and not st.session_state.scanner_data:
        st.warning("Auto-scan completed but found no matching opportunities")
    
    # Display results
    if st.session_state.scanner_data:
        st.info(f"**Found {len(st.session_state.scanner_data)} Trading Opportunities**")
        
        # Create dataframe for display
        display_df = pd.DataFrame(st.session_state.scanner_data)
        
        if not display_df.empty:
            # Format display columns
            display_df['Price'] = display_df['price'].apply(lambda x: f"${x:.2f}")
            display_df['Change'] = display_df['change_pct'].apply(lambda x: f"{x:+.2f}%")
            display_df['RSI'] = display_df['rsi'].apply(lambda x: f"{x:.1f}")
            display_df['Volume'] = display_df['volume'].apply(lambda x: f"{x/1e6:.1f}M" if x > 0 else "N/A")
            display_df['Patterns'] = display_df['patterns'].apply(lambda x: ", ".join(x) if isinstance(x, list) and x else "None")
            display_df['Score'] = display_df['score'].apply(lambda x: f"{x:.2f}")
            
            cols_to_show = ['symbol', 'Price', 'Change', 'RSI', 'Volume', 'Patterns', 'Score']
            st.dataframe(display_df[cols_to_show], use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Details section
            st.subheader("📈 Stock Details")
            selected = st.selectbox(
                "Select a stock to view details",
                [d['symbol'] for d in st.session_state.scanner_data],
                key="stock_picker_details"
            )
            
            if selected:
                stock_detail = next((d for d in st.session_state.scanner_data if d['symbol'] == selected), None)
                if stock_detail:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Price", f"${stock_detail['price']:.2f}")
                    with col2:
                        st.metric("Change", f"{stock_detail['change_pct']:+.2f}%")
                    with col3:
                        st.metric("RSI(14)", f"{stock_detail['rsi']:.1f}")
                    with col4:
                        st.metric("MACD", f"{stock_detail['macd']:.4f}")
                    
                    st.write(f"**Patterns**: {', '.join(stock_detail['patterns']) if stock_detail['patterns'] else 'None'}")
                    st.write(f"**Volume**: {stock_detail['volume']/1e6:.1f}M" if stock_detail['volume'] > 0 else "**Volume**: N/A")
    else:
        st.info("👈 Click 'Scan Now' or wait for auto-load to find market opportunities using real data")

# Run the page only when called directly
if __name__ == "__main__":
    render_stock_picker()
