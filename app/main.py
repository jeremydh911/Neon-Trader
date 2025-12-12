"""
Neon Trader - Main Streamlit Application
Trading council with E*TRADE integration, RAG learning, and autonomous trading
"""

import streamlit as st
import sys
from pathlib import Path
import logging
import importlib

# CRITICAL: Force reimport of pyetrade to avoid Streamlit caching issues
if 'pyetrade' in sys.modules:
    del sys.modules['pyetrade']
if 'pyetrade.authorization' in sys.modules:
    del sys.modules['pyetrade.authorization']

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.etrade_oauth_service import ETradeOAuthService

# Page configuration
st.set_page_config(
    page_title="Neon Trader",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 0.5rem;
        margin-bottom: 2rem;
    }
    .status-badge {
        padding: 0.5rem 1rem;
        border-radius: 0.25rem;
        font-weight: bold;
        display: inline-block;
    }
    .status-connected {
        background-color: #28a745;
        color: white;
    }
    .status-disconnected {
        background-color: #dc3545;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'oauth_service' not in st.session_state:
    try:
        st.session_state.oauth_service = ETradeOAuthService()
        logger.info("✅ OAuth service initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OAuth service: {e}")
        import traceback
        logger.error(traceback.format_exc())
        st.error(f"❌ OAuth initialization failed: {e}")
        st.stop()

oauth_service = st.session_state.oauth_service

# Sidebar - OAuth Status & Controls
with st.sidebar:
    st.markdown("## 🔐 E*TRADE OAuth")
    
    # Get OAuth status
    oauth_status = oauth_service.get_status()
    
    # Status indicator
    if oauth_status['is_authenticated']:
        st.markdown(
            '<span class="status-badge status-connected">✅ Connected</span>',
            unsafe_allow_html=True
        )
        st.caption(f"Authenticated at: {oauth_status['auth_time']}")
        if oauth_status['expiry_time']:
            st.caption(f"Expires: {oauth_status['expiry_time']}")
    else:
        st.markdown(
            '<span class="status-badge status-disconnected">❌ Disconnected</span>',
            unsafe_allow_html=True
        )
        st.caption("Not authenticated")
    
    st.divider()
    
    # OAuth Controls
    if not oauth_status['is_authenticated']:
        st.markdown("### Get Started")
        
        if st.button("🔗 Start OAuth Flow", use_container_width=True, key="start_oauth"):
            with st.spinner("Initiating OAuth flow..."):
                try:
                    auth_url = oauth_service.initiate_oauth_flow()
                    if auth_url:
                        st.success("✅ OAuth flow initiated!")
                        st.markdown("""
                        ### Step 1: Open Authorization URL

                        """)

                        # Defensive: avoid showing a request_token endpoint URL to the user
                        if '/oauth/request_token' in auth_url:
                            st.warning('⚠️ The authorization URL looks incorrect (points at the request_token endpoint).')
                            st.code(auth_url, language='text')
                            # Try to reconstruct a better URL for the user
                            try:
                                consumer_key = oauth_service.credentials['etrade']['oauth']['consumer_key']
                                web_authorize = 'https://us.etrade.com/e/t/etws/authorize'
                                corrected_url = f"{web_authorize}?key={consumer_key}&token={oauth_service.request_token}"
                                st.markdown(f"[Try this authorization link instead]({corrected_url})")
                            except Exception:
                                st.info('Please clear session and try again, or use the callback flow.')
                        else:
                            st.markdown(f"[Click here to authorize]({auth_url})")

                        st.markdown("Or copy and paste this URL in your browser:")
                        st.code(auth_url, language='text')
                        st.markdown("After authorizing, you'll get a verification code.")
                        st.session_state.oauth_url = auth_url
                    else:
                        st.error("❌ Failed to initiate OAuth flow")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        # Verification code input
        if hasattr(st.session_state, 'oauth_url') and st.session_state.oauth_url:
            st.markdown("### Step 2: Enter Verification Code")
            
            verification_code = st.text_input(
                "Verification Code:",
                placeholder="Enter the code from E*TRADE",
                type="password",
                key="verify_code_input"
            )
            
            if st.button("✅ Complete Authentication", use_container_width=True, key="complete_oauth"):
                with st.spinner("Completing authentication..."):
                    try:
                        if oauth_service.complete_oauth_flow(verification_code):
                            st.success("✅ Authentication successful!")
                            st.balloons()
                            # Clear the URL and rerun
                            del st.session_state.oauth_url
                            st.rerun()
                        else:
                            st.error("❌ Failed to complete authentication")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
    
    else:
        st.markdown("### OAuth Actions")
        
        if st.button("🔄 Refresh Status", use_container_width=True, key="refresh_status"):
            st.rerun()
        
        if st.button("🔑 Load Cached Tokens", use_container_width=True, key="load_cached"):
            try:
                if oauth_service.load_cached_tokens():
                    st.success("✅ Tokens loaded from cache")
                    st.rerun()
                else:
                    st.warning("⚠️ No cached tokens found")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
        
        if st.button("🚪 Logout", use_container_width=True, key="logout"):
            # Clear tokens
            oauth_service.etrade_oauth = None
            st.success("✅ Logged out successfully")
            st.rerun()
    
    st.divider()
    
    # Navigation
    st.markdown("### 📊 Pages")
    page = st.radio(
        "Select page:",
        options=["Dashboard", "E*TRADE Dashboard", "Trading Council", "Settings"],
        key="page_selector"
    )

# Main content
st.markdown("""
<div class="main-header">
    <h1>🚀 Neon Trader</h1>
    <p>Multi-Council Trading with E*TRADE Integration</p>
</div>
""", unsafe_allow_html=True)

# Page routing
if page == "Dashboard":
    st.header("📊 Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Portfolio", "$12,456.32", delta="+$234.56")
    with col2:
        st.metric("Daily Return", "+2.34%", delta="+0.12%")
    with col3:
        st.metric("Open Positions", "12", delta="+2")
    with col4:
        st.metric("Win Rate", "68.5%", delta="+2.1%")
    
    st.divider()
    
    st.subheader("📈 Performance Overview")
    
    # Placeholder for performance chart
    import plotly.graph_objects as go
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=[0, 100, 200, 250, 180, 220, 250, 290, 310],
        mode='lines+markers',
        name='Portfolio Value',
        fill='tozeroy'
    ))
    
    fig.update_layout(
        title="Portfolio Growth (Last 30 Days)",
        xaxis_title="Days",
        yaxis_title="Value ($)",
        height=400,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)

elif page == "E*TRADE Dashboard":
    st.markdown("Redirecting to E*TRADE Dashboard...")
    # The dashboard page will be auto-loaded by Streamlit
    # This is handled through the pages/ directory

elif page == "Trading Council":
    st.header("🤖 Trading Council")
    
    st.info("""
    ### Council Members
    
    - **Technical Analysis**: Pattern recognition and technical indicators
    - **Sentiment Analysis**: News and market sentiment analysis  
    - **ML Optimization**: Machine learning-driven trading optimization
    
    All council members have access to the RAG (Retrieval-Augmented Generation) 
    memory system for learning from historical trading decisions.
    """)
    
    tabs = st.tabs(["Technical", "Sentiment", "ML Optimization"])
    
    with tabs[0]:
        st.subheader("📈 Technical Analysis")
        st.write("Analyzing market patterns and technical indicators...")
    
    with tabs[1]:
        st.subheader("💭 Sentiment Analysis")
        st.write("Analyzing market sentiment and news...")
    
    with tabs[2]:
        st.subheader("🧠 ML Optimization")
        st.write("Optimizing trading strategy with ML models...")

elif page == "Settings":
    st.header("⚙️ Settings")
    
    st.subheader("E*TRADE Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        environment = st.selectbox(
            "Environment:",
            options=["Sandbox", "Production"],
            index=0
        )
    
    with col2:
        auto_trade = st.toggle("Enable Autonomous Trading", value=False)
    
    st.divider()
    
    st.subheader("Notifications")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.toggle("Email Alerts", value=True)
    with col2:
        st.toggle("Desktop Notifications", value=True)
    with col3:
        st.toggle("Audio Alerts", value=False)
    
    st.divider()
    
    if st.button("💾 Save Settings", use_container_width=True):
        st.success("✅ Settings saved!")

# Footer
st.divider()

st.markdown("""
---
**Neon Trader v1.0** | Multi-GPU Trading Council  
Environment: **Sandbox** | E*TRADE Connected: **""" + 
("✅ Yes" if oauth_status['is_authenticated'] else "❌ No") + """**

🔗 Resources:
- [E*TRADE API Docs](https://apisb.etrade.com/docs/api/account/api-account-v1.html)
- [Neon Trader Docs](https://github.com/your-repo)
""")
