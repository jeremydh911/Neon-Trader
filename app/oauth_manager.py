"""
E*TRADE OAuth Manager - Streamlit UI
Browser-based interface for OAuth authentication flow
"""

import streamlit as st
import logging
from datetime import datetime
from pathlib import Path
import sys

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.etrade_oauth_service import ETradeOAuthService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="E*TRADE OAuth Manager",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stAlert {
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🔐 E*TRADE OAuth Authentication Manager")
st.markdown("Complete E*TRADE OAuth authentication for Neon Trader")

# Initialize session state
if 'oauth_service' not in st.session_state:
    st.session_state.oauth_service = ETradeOAuthService()
    logger.info("OAuth service initialized")

oauth_service = st.session_state.oauth_service

# Sidebar - Status
with st.sidebar:
    st.header("📊 Status")
    
    status = oauth_service.get_status()
    
    if status['is_authenticated']:
        st.success("✅ Authenticated")
    else:
        st.warning("⚠️ Not Authenticated")
    
    if status['last_auth_time']:
        st.caption(f"Last Auth: {status['last_auth_time']}")
    
    if status['token_expiry']:
        st.caption(f"Expires: {status['token_expiry']}")
    
    st.divider()
    
    st.subheader("📌 Quick Links")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("❌ Clear Session", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    st.divider()
    
    with st.expander("❓ Help"):
        st.markdown("""
        **OAuth Flow Steps:**
        1. Click "Initiate OAuth Flow"
        2. Visit the authorization URL
        3. Login to E*TRADE
        4. Approve "Neon Trader"
        5. Copy verification code
        6. Paste code below
        7. Click "Complete Authentication"
        
        **Tokens expire after 24 hours**
        Reauthenticate when needed.
        """)

# Main content
st.divider()

# Display current status in columns
col1, col2, col3 = st.columns(3)

with col1:
    if status['is_authenticated']:
        st.success("✅ **Authenticated**")
    else:
        st.warning("⚠️ **Not Authenticated**")

with col2:
    if status['last_auth_time']:
        st.info(f"**Last Auth:** {status['last_auth_time']}")
    else:
        st.info("**No previous auth**")

with col3:
    if status['token_expiry']:
        st.info(f"**Expires:** {status['token_expiry']}")

st.divider()

# Try to load cached tokens
st.subheader("🔄 Option 1: Load Cached Tokens")
st.caption("If you have previously authenticated, load saved tokens")

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("Load Cached Tokens", use_container_width=True, key="load_cached"):
        with st.spinner("Loading cached tokens..."):
            if oauth_service.load_cached_tokens():
                st.success("✅ Tokens loaded successfully!")
                st.balloons()
                st.session_state.tokens_loaded = True
                st.rerun()
            else:
                st.info("No cached tokens available. Start fresh OAuth flow below.")

st.divider()

# Fresh OAuth Flow
st.subheader("🚀 Option 2: Start Fresh OAuth Flow")
st.caption("Complete new authentication with E*TRADE")

if st.button("Initiate OAuth Flow", use_container_width=True, type="primary", key="initiate_oauth"):
    with st.spinner("Initiating OAuth flow..."):
        result = oauth_service.initiate_oauth_flow()

        # Support both str return (auth_url) and dict {success, auth_url}
        auth_url = None
        if isinstance(result, dict):
            auth_url = result.get('auth_url')
            success = result.get('success', bool(auth_url))
        else:
            auth_url = result
            success = bool(auth_url)

        if success:
            st.success("✅ OAuth flow initiated!")

            # Store auth URL in session
            st.session_state.auth_url = auth_url
            st.session_state.oauth_initiated = True
            
            # Display authorization URL
            st.markdown("### 📋 Authorization URL")
            st.markdown("**Please visit this URL to authorize Neon Trader:**")
            st.code(result['auth_url'], language="text")
            
            st.markdown("### 📌 Instructions:")
            st.markdown("""
            1. **Visit the URL above** (or copy and paste into your browser)
            2. **Login to E*TRADE** with your sandbox account
            3. **Review permissions** and approve the "Neon Trader" application
            4. **Copy the verification code** from E*TRADE (usually 6-8 characters)
            5. **Paste the code below** and click "Complete Authentication"
            """)
            
        else:
            st.error(f"❌ {result['message']}")
            if result.get('error'):
                st.code(result['error'], language="text")
            
            with st.expander("💡 Troubleshooting"):
                st.markdown("""
                **Common issues:**
                - E*TRADE API temporarily unavailable → Wait 10 minutes and retry
                - Network connectivity → Check internet connection
                - pyetrade not installed → Run: `pip install pyetrade`
                
                **Check status:**
                - E*TRADE Status: https://www.etrade.com/status
                - API Docs: https://developer.etrade.com/
                """)

st.divider()

# Verification code entry
st.subheader("✅ Complete Authentication")
st.caption("Enter the verification code from E*TRADE")

verification_code = st.text_input(
    "Verification Code:",
    placeholder="Enter 6-8 character code from E*TRADE",
    type="password",
    key="verification_code"
)

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("Complete Authentication", use_container_width=True, type="primary", key="complete_auth"):
        if not verification_code:
            st.error("❌ Please enter the verification code")
        else:
            with st.spinner("Verifying code and obtaining access tokens..."):
                result = oauth_service.complete_oauth_flow(verification_code)
                
                if result['success']:
                    st.success("🎉 **Authentication successful!**")
                    st.balloons()
                    st.session_state.auth_complete = True
                    
                    st.markdown(f"✅ Tokens saved and will be active until **{result['expiry']}**")
                    
                    with st.expander("📋 Next Steps", expanded=True):
                        st.markdown("""
                        1. ✅ Restart the Neon Trader app
                        2. ✅ E*TRADE integration will now be active
                        3. ✅ Real-time quotes from E*TRADE will be used
                        4. ✅ You can now place live orders in sandbox
                        
                        **Start trading:**
                        ```bash
                        ~/Desktop/Neon Trader Start
                        ```
                        
                        **Access the app:**
                        http://localhost:8502
                        """)
                else:
                    st.error(f"❌ {result['message']}")
                    if result.get('error'):
                        st.code(result['error'], language="text")
                    
                    with st.expander("💡 Troubleshooting"):
                        st.markdown("""
                        **Possible issues:**
                        - Verification code is incorrect or expired
                        - Code used wrong format (remove spaces)
                        - E*TRADE API temporarily unavailable
                        - Network connectivity issue
                        
                        **Solutions:**
                        1. Copy verification code directly from E*TRADE
                        2. Use code within 5 minutes of generation
                        3. Wait 10 minutes and try again
                        4. Check internet connection
                        5. Restart OAuth flow if needed
                        """)

st.divider()

# Debug info
with st.expander("🔍 Debug Information"):
    debug_info = {
        'Credentials File': oauth_service.credentials_file,
        'Tokens File': oauth_service.tokens_file,
        'Has Credentials': bool(oauth_service.credentials),
        'Credentials Keys': list(oauth_service.credentials.keys()) if oauth_service.credentials else [],
        'OAuth Status': oauth_service.get_status()
    }
    st.json(debug_info)

st.divider()

# Footer
st.markdown("""
---
**E*TRADE OAuth Manager** | Neon Trader v1.0
- 📖 [E*TRADE Developer](https://developer.etrade.com/)
- 🔗 [API Docs](https://apisb.etrade.com/docs/api/account/api-account-v1.html)
- 🐛 [Report Issues](https://github.com/your-repo/issues)
""")
