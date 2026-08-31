"""
E*TRADE OAuth Callback Manager - Streamlit Page
Implements automatic OAuth callback handling with browser redirect
"""

import streamlit as st
import sys
from pathlib import Path
import logging
from typing import Optional

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.etrade_oauth_service import ETradeOAuthService
from services.etrade_oauth_callback import get_etrade_oauth_callback_flow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="E*TRADE OAuth Callback",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .oauth-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
    }
    .step-card {
        background: #f0f2f6;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #667eea;
    }
    .success-badge {
        background: #28a745;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        display: inline-block;
        font-weight: bold;
    }
    .warning-badge {
        background: #ffc107;
        color: black;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        display: inline-block;
        font-weight: bold;
    }
    .button-link {
        display: inline-block;
        background: #667eea;
        color: white;
        padding: 0.75rem 2rem;
        border-radius: 5px;
        text-decoration: none;
        font-weight: bold;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'oauth_service' not in st.session_state:
    st.session_state.oauth_service = ETradeOAuthService()
    logger.info("OAuth service initialized")

if 'oauth_callback_flow' not in st.session_state:
    st.session_state.oauth_callback_flow = None

if 'authorization_url' not in st.session_state:
    st.session_state.authorization_url = None

if 'callback_info' not in st.session_state:
    st.session_state.callback_info = None

oauth_service = st.session_state.oauth_service

# Title and header
st.markdown("""
<div class="oauth-container">
    <h1>🔐 E*TRADE OAuth Callback Authentication</h1>
    <p>Automatic verification code capture via browser redirect</p>
</div>
""", unsafe_allow_html=True)

# Tabs for different flows
tab1, tab2, tab3 = st.tabs(["🚀 Start OAuth", "📋 Status", "ℹ️ Help"])

with tab1:
    st.header("OAuth Flow - Step by Step")
    
    # Check current authentication status
    oauth_status = oauth_service.get_status()
    
    if oauth_status['is_authenticated']:
        st.success("✅ Already Authenticated!")
        st.info(f"""
        **Authentication Details:**
        - Authenticated at: {oauth_status['auth_time']}
        - Expires at: {oauth_status['expiry_time']}
        - Status: {oauth_status['status']}
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Re-authenticate", use_container_width=True):
                st.session_state.oauth_callback_flow = None
                st.rerun()
        
        with col2:
            if st.button("🚪 Logout", use_container_width=True):
                oauth_service.etrade_oauth = None
                st.success("✅ Logged out successfully")
                st.rerun()
    
    else:
        st.info("""
        This page uses the **callback-based OAuth flow**:
        1. Click "Start OAuth Flow" to begin
        2. You'll be redirected to E*TRADE authorization
        3. Login and grant permission
        4. E*TRADE redirects back automatically
        5. Verification code is automatically captured
        6. Authentication completes instantly
        """)
        
        # Start OAuth Flow button
        if st.button("🔗 Start OAuth Flow", use_container_width=True, key="start_oauth"):
            with st.spinner("Initializing OAuth callback server..."):
                try:
                    # Create callback flow
                    callback_flow = get_etrade_oauth_callback_flow(
                        oauth_service=oauth_service,
                        host='localhost',
                        port=8080
                    )
                    
                    st.session_state.oauth_callback_flow = callback_flow
                    
                    # Get authorization info
                    flow_info = callback_flow.get_authorization_flow_info()
                    
                    if flow_info['success']:
                        st.session_state.callback_info = flow_info
                        st.session_state.authorization_url = flow_info['authorization_url']
                        st.success("✅ OAuth server initialized!")
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to initialize OAuth: {flow_info.get('error')}")
                
                except Exception as e:
                    logger.error(f"Error initializing OAuth: {e}")
                    st.error(f"❌ Error: {str(e)}")
        
        # Show authorization steps if flow is initialized
        if st.session_state.callback_info:
            callback_info = st.session_state.callback_info
            
            st.markdown("---")
            st.subheader("📋 Authorization Steps")
            
            # Step 1: Authorization URL
            st.markdown("""
            <div class="step-card">
                <h3>Step 1: Open Authorization URL</h3>
                <p>Click the link below to authorize AhanaTrade with E*TRADE:</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Create clickable link
            auth_url = callback_info['authorization_url']
            st.markdown(f"""
            #### [🌐 Click Here to Authorize →]({auth_url})
            
            Or copy this URL if link doesn't work:
            ```
            {auth_url}
            ```
            """)
            
            # Step 2: What happens
            st.markdown("""
            <div class="step-card">
                <h3>Step 2: E*TRADE Authorization</h3>
                <ul>
                    <li>Login with your E*TRADE credentials</li>
                    <li>Review the permissions</li>
                    <li>Click "Authorize" or "Allow"</li>
                    <li>E*TRADE will redirect back automatically</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 3: Callback info
            st.markdown("""
            <div class="step-card">
                <h3>Step 3: Automatic Callback</h3>
                <p>The verification code will be automatically captured when E*TRADE redirects back.</p>
                <p><strong>Callback URL:</strong></p>
            </div>
            """, unsafe_allow_html=True)
            
            st.code(callback_info['callback_url'], language="text")
            
            # Waiting for callback
            st.markdown("---")
            st.subheader("⏳ Waiting for Authorization...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Wait for callback (non-blocking with timeout)
            if st.button("⏱️ Wait for Callback (10 minutes)", use_container_width=True, key="wait_callback"):
                with st.spinner("Waiting for E*TRADE callback..."):
                    status_text.info("🔄 Waiting for authorization callback...")
                    
                    # Complete OAuth flow (blocks until callback or timeout)
                    success = st.session_state.oauth_callback_flow.complete_oauth_flow(timeout=600)
                    
                    if success:
                        st.success("✅ Authorization Successful!")
                        st.balloons()
                        st.info("Your E*TRADE account is now connected. Return to the main app to start trading.")
                        
                        # Reload status
                        oauth_status = oauth_service.get_status()
                        st.json(oauth_status)
                        
                        # Redirect link
                        st.markdown("""
                        ### Next Steps:
                        - [Go to Main App](http://localhost:8501) to access your trading dashboard
                        - [Go to E*TRADE Dashboard](http://localhost:8501/E*TRADE_Dashboard) to see your portfolio
                        """)
                    else:
                        st.error("❌ Authorization failed or timeout. Please try again.")

with tab2:
    st.header("📋 OAuth Status")
    
    # Get current status
    oauth_status = oauth_service.get_status()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if oauth_status['is_authenticated']:
            st.markdown('<span class="success-badge">✅ AUTHENTICATED</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="warning-badge">⏳ NOT AUTHENTICATED</span>', unsafe_allow_html=True)
    
    with col2:
        if st.session_state.oauth_callback_flow:
            st.markdown('<span class="success-badge">✅ CALLBACK SERVER</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="warning-badge">⏳ NO SERVER</span>', unsafe_allow_html=True)
    
    with col3:
        st.metric("Status", oauth_status['status'])
    
    st.markdown("---")
    
    st.subheader("📊 Detailed Status")
    st.json(oauth_status)
    
    if st.session_state.callback_info:
        st.subheader("🔗 Callback Information")
        st.json({
            'authorization_url': st.session_state.callback_info['authorization_url'],
            'callback_url': st.session_state.callback_info['callback_url'],
            'instructions': st.session_state.callback_info['instructions']
        })

with tab3:
    st.header("ℹ️ Help & Information")
    
    st.subheader("🔄 How Callback OAuth Works")
    st.markdown("""
    **Traditional Flow (Copy-Paste):**
    1. User clicks authorization URL
    2. Browser opens separate window
    3. User authorizes and receives code
    4. User manually enters code in app
    5. App completes authentication
    
    **Callback Flow (Automatic):**
    1. App starts local callback server
    2. User clicks authorization URL
    3. E*TRADE redirects to local server
    4. Code captured automatically
    5. App instantly completes authentication
    6. Callback window auto-closes
    
    **Advantages:**
    ✅ No manual code copying
    ✅ Faster authorization
    ✅ Better user experience
    ✅ More secure (no copy-paste errors)
    """)
    
    st.subheader("🆘 Troubleshooting")
    
    with st.expander("❓ What if the callback doesn't work?"):
        st.markdown("""
        **Common Issues:**
        
        1. **Port 8080 Already in Use**
           - Change port in callback initialization
           - Or kill process: `lsof -ti:8080 | xargs kill -9`
        
        2. **Firewall Blocking**
           - Allow localhost:8080
           - Or use different port (8000, 8888, etc.)
        
        3. **E*TRADE Not Redirecting**
           - Check callback URL configuration
           - Ensure callback URL matches E*TRADE settings
        
        4. **Timeout**
           - Default is 10 minutes
           - Make sure you're connected to internet
        """)
    
    with st.expander("🔐 Is this secure?"):
        st.markdown("""
        **Security Features:**
        
        ✅ Local server on localhost only
        ✅ OAuth 1.0a protocol (industry standard)
        ✅ Tokens stored securely (pickle, 0o600)
        ✅ No tokens in URLs (safer than copy-paste)
        ✅ Auto-closes after callback
        ✅ Timeout prevents hanging connections
        """)
    
    with st.expander("📱 Can I use this on mobile?"):
        st.markdown("""
        **Mobile Compatibility:**
        
        ⚠️ Callback approach works best on **desktop**
        
        For mobile:
        - Use the manual copy-paste flow in `oauth_manager.py`
        - Or access Streamlit app from desktop
        
        The callback requires a local server, which isn't practical 
        for mobile browsers.
        """)
    
    st.subheader("📞 Need Help?")
    st.markdown("""
    - Check: `ETRADE_OAUTH_TROUBLESHOOTING.md`
    - Docs: `ETRADE_QUICKSTART.md`
    - Issues: Enable debug mode with logs
    """)

# Footer
st.divider()
st.markdown("""
---
**E*TRADE OAuth Callback Manager** | AhanaTrade
- Flow: Callback-based (automatic verification code capture)
- Protocol: OAuth 1.0a
- Environment: Sandbox (Paper Trading)
""")
