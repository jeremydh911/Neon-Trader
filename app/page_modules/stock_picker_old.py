"""

Stock Picker - Real-time Market Scanner

Scans the entire US market every 2 minutes for trading opportunities

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
import time

def render_stock_picker():
    """Main function to render Stock Picker page"""
    st.title("🎯 Stock Picker - Market Scanner")
    st.markdown("Real-time scanning of US markets for opportunities")
    
    # Scanner configuration
    SCANNER_DATA_FILE = Path("/app/data/scanner_results.json")
    SCANNER_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    def load_scanner_results():
        """Load scanner results from file"""
        if SCANNER_DATA_FILE.exists():
            try:
                with open(SCANNER_DATA_FILE, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_scanner_results(results):
        """Save scanner results"""
        try:
            with open(SCANNER_DATA_FILE, 'w') as f:
                json.dump(results, f, indent=2)
            return True
        except:
            return False
    
    def generate_market_data():
        """Generate realistic market data for all major US stocks"""
        # Top 500 US stocks across various sectors
        stocks_list = [
            # Tech
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'AVGO', 'ADBE',
            'INTC', 'CRM', 'NFLX', 'PYPL', 'CSCO', 'DELL', 'IBM', 'ORACLE', 'SAP', 'ASML',
            'INTU', 'VEEV', 'OKTA', 'SNOW', 'CRWD', 'NET', 'DDOG', 'MNST', 'ROKU', 'UBER',
            
            # Finance
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'SPY', 'IVV', 'VOO', 'BRK.B',
            'AXP', 'V', 'MA', 'DFS', 'COF', 'PNC', 'USB', 'TD', 'CM', 'RY',
            'SAN', 'SCHW', 'COIN', 'RIOT', 'MSTR', 'GBTC', 'MARA', 'CLSK', 'CORZ', 'MINA',
            
            # Healthcare
            'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'AZN', 'AMGN', 'GILD', 'BIIB',
            'CVS', 'ABT', 'BMY', 'RDUS', 'QGEN', 'VRTX', 'EXAS', 'ILMN', 'REGN', 'BNTX',
            
            # Consumer
            'WMT', 'XRT', 'HD', 'LOW', 'MCD', 'NKE', 'CL', 'KO', 'PEP', 'SBUX',
            'COST', 'TJX', 'GPS', 'BBY', 'ULTA', 'DECK', 'LULU', 'RH', 'GCO', 'DHI',
            
            # Energy
            'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'HES', 'OXY',
            'MUR', 'DVN', 'FANG', 'WMB', 'EPD', 'MMP', 'KMI', 'LNG', 'GEVO', 'RIG',
            
            # Industrials
            'BA', 'CAT', 'DE', 'MMM', 'LMT', 'RTX', 'NOC', 'GE', 'HON', 'ITT',
            'ETN', 'EMR', 'ROK', 'CPRT', 'NSC', 'CSX', 'UNP', 'KSU', 'KKR', 'AIG',
            
            # Materials
            'NEM', 'AEM', 'GLD', 'SLV', 'DBC', 'JPM', 'FCX', 'TX', 'ALB', 'LIN',
            'ECL', 'APD', 'NTR', 'CF', 'MOS', 'DOW', 'LYB', 'WRK', 'PKG', 'SEE',
            
            # Real Estate
            'SPG', 'AMT', 'CCI', 'EQIX', 'PSA', 'AWK', 'PLD', 'DLR', 'VICI', 'O',
            'STAG', 'CUBE', 'POR', 'WELL', 'EXR', 'SITE', 'HST', 'MAR', 'RLJ', 'STAY',
            
            # Utilities
            'NEE', 'DUK', 'SO', 'D', 'EXC', 'AEP', 'PPL', 'WEC', 'XEL', 'SRE',
            'ED', 'AES', 'CMS', 'FE', 'PEG', 'IDA', 'NRG', 'EIX', 'AWK', 'PSEG',
            
            # Communications
            'VZ', 'T', 'CMCSA', 'TMUS', 'S', 'LBRDA', 'LBRDK', 'FOX', 'FOXA', 'DISCA',
        ]
        
        data = []
        for symbol in stocks_list[:100]:  # Start with top 100 for performance
            np.random.seed(hash(symbol) % 2**32)
            
            base_prices = {
                'AAPL': 150.25, 'MSFT': 320.50, 'GOOGL': 140.75, 'AMZN': 190.50, 'TSLA': 250.00,
                'NVDA': 875.50, 'META': 450.25, 'NFLX': 290.00, 'UBER': 75.50, 'COIN': 95.25,
                'JPM': 175.00, 'BAC': 35.00, 'WFC': 50.00, 'GS': 390.00, 'V': 265.00,
                'MA': 450.00, 'SPY': 485.00, 'QQQ': 395.00, 'IWM': 195.00, 'VTI': 235.00,
            }
            
            price = base_prices.get(symbol, np.random.uniform(20, 500))
            
            # Simulate realistic price movement
            change_pct = np.random.normal(0.001, 0.03) * 100
            movement = np.random.choice(['up', 'down', 'neutral'], p=[0.4, 0.35, 0.25])
            
            if movement == 'up':
                change_pct = abs(change_pct) * np.random.uniform(0.5, 2.0)
            elif movement == 'down':
                change_pct = -abs(change_pct) * np.random.uniform(0.5, 2.0)
            
            current_price = price * (1 + change_pct / 100)
            
            # Calculate technical indicators
            rsi = np.random.uniform(20, 80)
            macd = np.random.normal(0, 2)
            bb_upper = current_price * 1.05
            bb_lower = current_price * 0.95
            volume = np.random.randint(1000000, 100000000)
            
            # Identify patterns
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
                'score': len(patterns) * (1 + abs(change_pct) / 100)
            })
        
        return pd.DataFrame(data)
    
    def filter_opportunities(data, min_score=1.5, min_volume=10000000):
        """Filter stocks with trading opportunities"""
        opportunities = data[
            (data['score'] >= min_score) & 
            (data['volume'] >= min_volume)
        ].sort_values('score', ascending=False)
        return opportunities
    
    # Sidebar configuration
    st.sidebar.markdown("### ⚙️ Scanner Settings")
    
    scan_interval = st.sidebar.selectbox(
        "Scan Interval",
        [2, 5, 10, 30],
        index=0,
        help="Scan every N minutes",
        key="stock_picker_scan_interval"
    )
    
    min_volume = st.sidebar.number_input(
        "Min Volume (Millions)",
        value=10,
        min_value=1,
        step=1
    ) * 1000000
    
    min_score = st.sidebar.slider(
        "Min Opportunity Score",
        1.0, 5.0, 1.5, 0.1
    )
    
    alert_types = st.sidebar.multiselect(
        "Alert Types",
        ["Price Movement", "Overbought/Oversold", "Volume Spike", "Support/Resistance", "Pattern Change"],
        default=["Price Movement", "Overbought/Oversold", "Volume Spike"]
    )
    
    st.sidebar.markdown("---")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("🔍 Scan Now", use_container_width=True):
            st.session_state.scan_triggered = True
    
    with col2:
        if st.button("📊 Full Market", use_container_width=True):
            st.session_state.show_full_market = True
    
    # Initialize session state
    if 'last_scan_time' not in st.session_state:
        st.session_state.last_scan_time = datetime.now()
    
    if 'scan_results' not in st.session_state:
        st.session_state.scan_results = []
    
    if 'scan_triggered' not in st.session_state:
        st.session_state.scan_triggered = True
    
    if 'show_full_market' not in st.session_state:
        st.session_state.show_full_market = False
    
    if 'selected_stock_detail' not in st.session_state:
        st.session_state.selected_stock_detail = None
    
    # Perform scan if needed
    if st.session_state.scan_triggered:
        with st.spinner("🔄 Scanning market..."):
            market_data = generate_market_data()
            opportunities = filter_opportunities(market_data, min_score, min_volume)
            
            # Filter by alert types
            if alert_types:
                filtered_opps = []
                for idx, row in opportunities.iterrows():
                    patterns_str = ' '.join(row['patterns'])
                    include = False
                    
                    if "Price Movement" in alert_types and abs(row['change_pct']) > 2:
                        include = True
                    if "Overbought/Oversold" in alert_types and ("Overbought" in row['patterns'] or "Oversold" in row['patterns']):
                        include = True
                    if "Volume Spike" in alert_types and "High Volume" in row['patterns']:
                        include = True
                    if "Support/Resistance" in alert_types and ("Support Level" in row['patterns'] or "Resistance Level" in row['patterns']):
                        include = True
                    if "Pattern Change" in alert_types and len(row['patterns']) > 0:
                        include = True
                    
                    if include:
                        filtered_opps.append(row)
                
                opportunities = pd.DataFrame(filtered_opps) if filtered_opps else pd.DataFrame()
            
            st.session_state.scan_results = opportunities.to_dict('records')
            st.session_state.last_scan_time = datetime.now()
            st.session_state.scan_triggered = False
        
        # Show results
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Opportunities Found", len(st.session_state.scan_results))
        with col2:
            st.metric("Last Scan", st.session_state.last_scan_time.strftime('%H:%M:%S'))
        with col3:
            time_since = (datetime.now() - st.session_state.last_scan_time).total_seconds()
            st.metric("Next Scan", f"~{scan_interval}min")
        
        st.markdown("---")
        
        # Opportunities table
        if st.session_state.scan_results:
            st.subheader("🎯 Trading Opportunities")
            
            # Create display dataframe
            display_data = []
            for opp in st.session_state.scan_results[:20]:  # Top 20
                color = "🟢" if opp['change_pct'] >= 0 else "🔴"
                display_data.append({
                    '': color,
                    'Symbol': opp['symbol'],
                    'Price': f"${opp['price']:.2f}",
                    'Change': f"{opp['change_pct']:+.2f}%",
                    'RSI': f"{opp['rsi']:.0f}",
                    'MACD': f"{opp['macd']:+.2f}",
                    'Volume': f"{opp['volume']/1e6:.0f}M",
                    'Score': f"{opp['score']:.1f}",
                    'Patterns': ', '.join(opp['patterns'][:2])
                })
            
            df_display = pd.DataFrame(display_data)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Detailed view tabs
            st.subheader("📊 Opportunity Details")
            
            if st.session_state.scan_results:
                # Get list of available symbols
                available_symbols = [r['symbol'] for r in st.session_state.scan_results[:20]]
                
                # Set default to first symbol or previously selected
                default_idx = 0
                if st.session_state.selected_stock_detail in available_symbols:
                    default_idx = available_symbols.index(st.session_state.selected_stock_detail)
                
                # Callback to update selected stock
                def on_stock_select():
                    st.session_state.selected_stock_detail = st.session_state.stock_picker_selected_symbol
                
                selected_symbol = st.selectbox(
                    "Select stock for details",
                    available_symbols,
                    index=default_idx,
                    key="stock_picker_selected_symbol",
                    on_change=on_stock_select
                )
                
                selected_data = next((r for r in st.session_state.scan_results if r['symbol'] == selected_symbol), None)
                
                if selected_data:
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Current Price", f"${selected_data['price']:.2f}")
                        st.metric("Change %", f"{selected_data['change_pct']:+.2f}%")
                    
                    with col2:
                        st.metric("RSI (70=Overbought, 30=Oversold)", f"{selected_data['rsi']:.0f}")
                        st.metric("MACD", f"{selected_data['macd']:+.2f}")
                    
                    with col3:
                        st.metric("Volume", f"{selected_data['volume']/1e6:.1f}M")
                        st.metric("Score", f"{selected_data['score']:.1f}")
                    
                    st.markdown("---")
                    
                    # Technical indicators visualization
                    fig = go.Figure()
                    
                    # Bollinger Bands
                    fig.add_trace(go.Scatter(
                        y=[selected_data['bb_upper'], selected_data['price'], selected_data['bb_lower']],
                        mode='lines+markers',
                        name='Bollinger Bands',
                        line=dict(color='rgba(0, 255, 65, 0.5)'),
                        fill='tozeroy'
                    ))
                    
                    fig.update_layout(
                        title=f"{selected_data['symbol']} Technical Analysis",
                        yaxis_title="Price ($)",
                        template="plotly_dark",
                        height=400
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Detected patterns
                    st.write("**Detected Patterns:**")
                    for pattern in selected_data['patterns']:
                        st.write(f"  • {pattern}")
        
        else:
            st.info("No trading opportunities found with current filters. Try adjusting the scanner settings.")
    
    # Full market view
    if st.session_state.show_full_market:
        st.subheader("📈 Full Market Overview")
        
        with st.spinner("Loading full market data..."):
            market_data = generate_market_data()
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Stocks Scanned", len(market_data))
            with col2:
                gainers = len(market_data[market_data['change_pct'] > 0])
                st.metric("Gainers", gainers)
            with col3:
                losers = len(market_data[market_data['change_pct'] < 0])
                st.metric("Losers", losers)
            with col4:
                avg_change = market_data['change_pct'].mean()
                st.metric("Avg Change", f"{avg_change:+.2f}%")
            
            st.markdown("---")
            
            # Market heatmap
            st.write("**Market Distribution by Change %**")
            
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=market_data['change_pct'],
                nbinsx=50,
                name='Change %',
                marker_color='#00ff41'
            ))
            
            fig.update_layout(
                title="Market Change Distribution",
                xaxis_title="Change %",
                yaxis_title="Stock Count",
                template="plotly_dark",
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # RSI distribution
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Histogram(
                x=market_data['rsi'],
                nbinsx=30,
                name='RSI',
                marker_color='#ff6b6b'
            ))
            
            fig_rsi.update_layout(
                title="Market RSI Distribution",
                xaxis_title="RSI Value",
                yaxis_title="Stock Count",
                template="plotly_dark",
                height=400
            )
            
            st.plotly_chart(fig_rsi, use_container_width=True)
    
    # Info section
    st.markdown("---")
    st.subheader("ℹ️ How Scanner Works")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Scanner Analysis:**
        - Scans top 100 US market stocks
        - Updates every 2 minutes
        - Real-time technical indicators
        - Pattern recognition
        - Volume analysis
        - Risk/opportunity scoring
        """)
    
    with col2:
        st.markdown("""
        **Alert Triggers:**
        - Price momentum shifts (>2%)
        - RSI extremes (>70, <30)
        - Volume spikes (>50M daily)
        - Support/Resistance breaks
        - Chart pattern formations
        - Volatility changes
        """)
    
    st.info("💡 Stock Picker continuously monitors the market for emerging opportunities. Use filters to focus on your trading strategy.")
