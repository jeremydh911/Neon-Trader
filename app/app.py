"""
Neon Trader Application
Streamlit UI for trading platform
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import os
import logging
import sys
import json
import importlib.util
import inspect

# Add services to path
sys.path.insert(0, os.path.dirname(__file__))
from services.settings_manager import SettingsManager

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add pages path
pages_path = os.path.join(os.path.dirname(__file__), 'pages')
sys.path.insert(0, pages_path)

def load_page_module(page_name, file_path):
    """Dynamically load a page module"""
    spec = importlib.util.spec_from_file_location(page_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[page_name] = module
    spec.loader.exec_module(module)
    return module


# Initialize Settings Manager with persistent state
@st.cache_resource
def get_settings_manager():
    """Initialize settings manager (cached globally)"""
    mgr = SettingsManager()
    logger.info(f"✅ SettingsManager initialized globally")
    return mgr

settings_mgr = get_settings_manager()

# Initialize session state for tracking changes
if 'current_settings_cache' not in st.session_state:
    st.session_state.current_settings_cache = settings_mgr.get_all_settings()
    logger.info(f"✅ Session state initialized with cached settings")

# Page configuration
st.set_page_config(
    page_title="Neon Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for neon theme
st.markdown("""
    <style>
    .main {
        background-color: #0a0e27;
        color: #00ff41;
    }
    .stMetric {
        background-color: #1a1f3a;
        border: 1px solid #00ff41;
        border-radius: 8px;
        padding: 10px;
    }
    h1, h2, h3 {
        color: #00ff41;
        text-shadow: 0 0 10px #00ff41;
    }
    .stButton>button {
        background-color: #00ff41;
        color: #0a0e27;
        font-weight: bold;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ Neon Trader")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Stock Ticker", "Training", "Trading", "Portfolio", "Analytics", "Settings"],
    index=0
)

# Check LLM status
def check_llm_status():
    try:
        llm_url = os.getenv('OLLAMA_BASE_URL', 'http://ollama-gpu:11434')
        # Try direct connection first
        response = requests.get(f"{llm_url}/api/tags", timeout=2)
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            if models:
                return True, len(models)
            else:
                # Ollama is ready but no models loaded yet
                return False, 0
    except requests.exceptions.ConnectionError:
        logger.debug("Cannot connect to Ollama - trying localhost fallback")
        # Try localhost fallback
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return len(models) > 0, len(models)
        except:
            pass
    except Exception as e:
        logger.debug(f"LLM status check failed: {e}")
    
    return False, 0

# Main content
st.title("📊 Neon Trader - GPU Trading Platform")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Portfolio Value", "$50,000.00", "+12.5%")

with col2:
    llm_ready, model_count = check_llm_status()
    status = "🟢 Ready" if llm_ready else "🔴 Loading..."
    st.metric("LLM Status", status, f"{model_count} models")

with col3:
    st.metric("Win Rate", "68.2%", "+5.3%")

st.markdown("---")

if page == "Dashboard":
    st.header("📈 Dashboard")
    
    # Generate sample data
    dates = pd.date_range(end=datetime.now(), periods=100)
    prices = np.cumsum(np.random.randn(100)) + 100
    
    chart_data = pd.DataFrame({
        'Date': dates,
        'Price': prices,
        'MA20': pd.Series(prices).rolling(20).mean(),
        'MA50': pd.Series(prices).rolling(50).mean()
    })
    
    st.line_chart(chart_data.set_index('Date'))
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Recent Trades")
        trades = pd.DataFrame({
            'Symbol': ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'],
            'Entry': [150.25, 320.50, 140.75, 250.00, 875.50],
            'Exit': [152.50, 325.00, 142.00, 248.50, 870.00],
            'P&L': ['+$2.25', '+$4.50', '+$1.25', '-$1.50', '-$5.50']
        })
        st.dataframe(trades, use_container_width=True)
    
    with col2:
        st.subheader("Performance Metrics")
        metrics = {
            'Total Trades': 247,
            'Win Rate': '68.2%',
            'Profit Factor': 2.45,
            'Sharpe Ratio': 1.89,
            'Max Drawdown': '-8.5%'
        }
        for key, value in metrics.items():
            st.write(f"**{key}:** {value}")

elif page == "Stock Ticker":
    # Load and execute Stock Ticker page
    try:
        stock_ticker = load_page_module("stock_ticker", "/app/pages/1_Stock_Ticker.py")
    except Exception as e:
        st.error(f"Failed to load Stock Ticker page: {e}")

elif page == "Training":
    # Load and execute Training page
    try:
        training = load_page_module("training", "/app/pages/2_Training.py")
    except Exception as e:
        st.error(f"Failed to load Training page: {e}")

elif page == "Trading":
    st.header("🤖 Trading")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Quick Trade")
        symbol = st.text_input("Symbol", "AAPL")
        quantity = st.number_input("Quantity", 1, 1000, 10)
        order_type = st.selectbox("Order Type", ["Market", "Limit", "Stop"])
        
        if st.button("Execute Trade"):
            st.success(f"✓ Trade executed: Buy {quantity} {symbol}")
    
    with col2:
        st.subheader("AI Trading Signals")
        llm_ready, _ = check_llm_status()
        
        if llm_ready:
            st.write("🤖 Getting AI signals...")
            st.info("AI analysis: Strong buy signal detected for AAPL")
        else:
            st.warning("⏳ LLM loading... AI signals will be available soon")

elif page == "Portfolio":
    st.header("💼 Portfolio")
    
    # Matching values: Total = $50,000
    portfolio = pd.DataFrame({
        'Symbol': ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'],
        'Shares': [100, 50, 25, 10, 5],
        'Price': [150.25, 320.50, 140.75, 250.00, 875.50],
        'Value': [18125.56, 19331.92, 4245.18, 3015.90, 5281.44],
        'Change %': ['+2.5%', '+1.2%', '-0.8%', '+3.5%', '+5.2%']
    })
    
    st.dataframe(portfolio, use_container_width=True)
    st.metric("Total Portfolio Value", "$50,000.00", "+2.45%")
    
    # Portfolio P&L Graph
    st.subheader("📈 Portfolio Performance")
    
    # Generate 30-day P&L data
    days = pd.date_range(end=datetime.now(), periods=30)
    base_value = 50000
    pnl_values = base_value + np.cumsum(np.random.randn(30) * 200)
    pnl_pct = ((pnl_values - base_value) / base_value * 100)
    
    pnl_df = pd.DataFrame({
        'Date': days,
        'Portfolio Value': pnl_values,
        'P&L %': pnl_pct
    })
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.line_chart(pnl_df.set_index('Date')[['Portfolio Value']], height=300)
    
    with col2:
        current_pnl = pnl_values[-1] - base_value
        current_pnl_pct = pnl_pct[-1]
        
        col_metric1, col_metric2 = st.columns(2)
        with col_metric1:
            st.metric("Current P&L", f"${current_pnl:+.2f}", f"{current_pnl_pct:+.2f}%")
        with col_metric2:
            max_dd = np.min(pnl_values) - base_value
            st.metric("Max Drawdown", f"${max_dd:+.2f}", "lowest point")
    
    # Holdings breakdown
    st.subheader("Holdings Breakdown")
    holdings_pct = (portfolio['Value'] / portfolio['Value'].sum() * 100).round(1)
    
    fig_pie_data = pd.DataFrame({
        'Symbol': portfolio['Symbol'],
        'Percentage': holdings_pct
    })
    
    col1, col2 = st.columns([1, 2])
    with col1:
        for idx, row in fig_pie_data.iterrows():
            st.write(f"**{row['Symbol']}** - {row['Percentage']:.1f}%")
    
    with col2:
        st.bar_chart(fig_pie_data.set_index('Symbol')['Percentage'], height=250)

elif page == "Analytics":
    st.header("📊 Analytics")
    
    tabs = st.tabs(["Daily", "Weekly", "Monthly", "Yearly"])
    
    with tabs[0]:
        st.write("Daily performance analysis")
        daily_data = pd.DataFrame({
            'Hour': range(24),
            'Trades': np.random.randint(0, 20, 24),
            'Win%': np.random.randint(50, 80, 24)
        })
        st.bar_chart(daily_data.set_index('Hour'))

elif page == "Settings":
    st.header("⚙️ Settings")
    
    # Always reload current settings from disk
    current_settings = settings_mgr.get_all_settings()
    logger.info(f"✅ Loaded settings from disk: {list(current_settings.keys())}")
    
    # Use form to group inputs
    with st.form("settings_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Trading Mode")
            trading_mode = st.radio(
                "Select Trading Mode",
                ["Manual", "Day Trade", "Autonomous Trade"],
                index=["Manual", "Day Trade", "Autonomous Trade"].index(current_settings.get("trading_mode", "Manual")),
                help="Manual: You execute trades | Day Trade: Auto-close at EOD | Autonomous: Full AI control"
            )
            
            st.markdown("---")
            st.subheader("🔧 Day Trade Settings")
            
            day_trade_enabled = st.checkbox(
                "Enable Day Trading",
                value=current_settings.get("day_trade_enabled", False),
                help="Automatically close all positions at end of trading day"
            )
            
            day_trade_max_loss = 5.0
            day_trade_max_gain = 10.0
            
            if day_trade_enabled:
                day_trade_max_loss = st.number_input(
                    "Day Trade Max Loss %",
                    min_value=0.1,
                    max_value=100.0,
                    value=current_settings.get("day_trade_max_loss", 5.0),
                    step=0.1,
                    help="Stop all day trading if loss exceeds this %"
                )
                
                day_trade_max_gain = st.number_input(
                    "Day Trade Take Profit %",
                    min_value=0.1,
                    max_value=500.0,
                    value=current_settings.get("day_trade_max_gain", 10.0),
                    step=0.1,
                    help="Close winning trades at this gain %"
                )
            
            st.markdown("---")
            st.subheader("🤖 Autonomous Trade Settings")
            
            autonomous_enabled = st.checkbox(
                "Enable Autonomous Trading",
                value=current_settings.get("autonomous_enabled", False),
                help="Let AI make and manage trades automatically"
            )
            
            autonomous_confirm = False
            max_positions_auto = 10
            autonomous_max_loss = 2.0
            autonomous_take_profit = 3.0
            autonomous_portfolio_loss_limit = 5.0
            
            if autonomous_enabled:
                st.write("**⚠️ AUTONOMOUS TRADING ENABLED**")
                st.warning("Autonomous trading will execute trades without confirmation. Use with caution!")
                
                autonomous_confirm = st.checkbox(
                    "I understand the risks and want to enable autonomous trading",
                    value=current_settings.get("autonomous_confirmed", False)
                )
                
                if autonomous_confirm:
                    max_positions_auto = st.number_input(
                        "Max Open Positions",
                        min_value=1,
                        max_value=50,
                        value=current_settings.get("autonomous_max_positions", 10),
                        help="Maximum concurrent autonomous trades"
                    )
                    
                    autonomous_max_loss = st.number_input(
                        "Autonomous Max Loss % (per trade)",
                        min_value=0.1,
                        max_value=50.0,
                        value=current_settings.get("autonomous_max_loss_per_trade", 2.0),
                        step=0.1,
                        help="Stop loss for each autonomous trade"
                    )
                    
                    autonomous_take_profit = st.number_input(
                        "Autonomous Take Profit %",
                        min_value=0.1,
                        max_value=100.0,
                        value=current_settings.get("autonomous_take_profit", 3.0),
                        step=0.1,
                        help="Take profit target for autonomous trades"
                    )
                    
                    autonomous_portfolio_loss_limit = st.number_input(
                        "Portfolio Max Daily Loss %",
                        min_value=0.5,
                        max_value=50.0,
                        value=current_settings.get("autonomous_portfolio_loss_limit", 5.0),
                        step=0.5,
                        help="Stop all autonomous trading if portfolio loses this much"
                    )
        
        with col2:
            st.subheader("📈 General Parameters")
            risk_level = st.slider("Risk Level", 1, 10, current_settings.get("risk_level", 5), help="1=Conservative, 10=Aggressive")
            
            st.subheader("💰 Position Management")
            position_size = st.number_input(
                "Default Position Size ($)",
                min_value=100,
                max_value=100000,
                value=current_settings.get("position_size", 1000),
                step=100
            )
            
            max_position_single = st.number_input(
                "Max Single Position %",
                min_value=1,
                max_value=100,
                value=current_settings.get("max_position_single", 10),
                help="Max % of portfolio in single trade"
            )
            
            st.subheader("🔔 Notifications")
            notify_trades = st.checkbox("Notify on Trade Execution", value=current_settings.get("notify_trades", True))
            notify_signals = st.checkbox("Notify on AI Signals", value=current_settings.get("notify_signals", True))
            notify_losses = st.checkbox("Notify on Losses", value=current_settings.get("notify_losses", True))
            
            st.subheader("🔐 Security")
            require_confirmation = st.checkbox(
                "Require Confirmation for Manual Trades",
                value=current_settings.get("require_confirmation", True)
            )
            
            api_key = st.text_input("API Key (if needed)", type="password", placeholder="Leave blank to use environment")
        
        st.markdown("---")
        
        # Submit button for form
        submitted = st.form_submit_button("💾 Save Settings", use_container_width=True)
        
        if submitted:
            # Gather all settings
            settings_dict = {
                "trading_mode": trading_mode,
                "day_trade_enabled": day_trade_enabled,
                "day_trade_close_time": "16:00",
                "day_trade_max_loss": day_trade_max_loss,
                "day_trade_max_gain": day_trade_max_gain,
                "autonomous_enabled": autonomous_enabled,
                "autonomous_confirmed": autonomous_confirm,
                "autonomous_max_positions": max_positions_auto,
                "autonomous_max_loss_per_trade": autonomous_max_loss,
                "autonomous_take_profit": autonomous_take_profit,
                "autonomous_portfolio_loss_limit": autonomous_portfolio_loss_limit,
                "risk_level": risk_level,
                "position_size": position_size,
                "max_position_single": max_position_single,
                "notify_trades": notify_trades,
                "notify_signals": notify_signals,
                "notify_losses": notify_losses,
                "require_confirmation": require_confirmation
            }
            
            # Save to disk
            logger.info(f"💾 Saving settings: {json.dumps(settings_dict, indent=2, default=str)}")
            if settings_mgr.save_settings(settings_dict):
                st.session_state.current_settings_cache = settings_dict
                st.success("✅ Settings saved successfully and persisted!")
                st.info("Your settings will be restored when you return to this page.")
                logger.info("✅ Settings saved to disk successfully")
            else:
                st.error("❌ Failed to save settings")
                logger.error("❌ Failed to save settings to disk")
    
    # Additional buttons outside form
    st.markdown("---")
    col_reset, col_export, col_info = st.columns(3)
    
    with col_reset:
        if st.button("🔄 Reset to Defaults", use_container_width=True):
            if settings_mgr.reset_to_defaults():
                st.session_state.current_settings_cache = settings_mgr.get_all_settings()
                st.success("✅ Settings reset to defaults")
                st.rerun()
            else:
                st.error("❌ Failed to reset settings")
    
    with col_export:
        if st.button("📥 Export Settings", use_container_width=True):
            export_path = settings_mgr.export_settings()
            if export_path:
                st.success(f"✅ Settings exported to {export_path}")
            else:
                st.error("❌ Failed to export settings")
    
    # Display last updated time
    last_updated = current_settings.get("last_updated", "Never")
    with col_info:
        st.metric("Last Saved", last_updated)
    
    # Debug info
    with st.expander("🔧 Debug Info"):
        st.code(f"Settings file: {settings_mgr.settings_path}")
        st.code(f"Settings keys: {list(current_settings.keys())}")
        st.json(current_settings)

