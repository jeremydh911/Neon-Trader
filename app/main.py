"""AhanaTrade — Streamlit desk with E*TRADE OAuth."""

import logging
import sys
from pathlib import Path

import streamlit as st

if "pyetrade" in sys.modules:
    del sys.modules["pyetrade"]
if "pyetrade.authorization" in sys.modules:
    del sys.modules["pyetrade.authorization"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from services.etrade_oauth_service import ETradeOAuthService
from services.funding_service import FundingService
from components.splash import render_splash
from components.desk import render_desk

st.set_page_config(
    page_title="AhanaTrade",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "oauth_service" not in st.session_state:
    try:
        st.session_state.oauth_service = ETradeOAuthService()
    except Exception as e:
        logger.error("OAuth init failed: %s", e)
        st.error(f"OAuth initialization failed: {e}")
        st.stop()

oauth_service = st.session_state.oauth_service

if "funding_service" not in st.session_state:
    try:
        st.session_state.funding_service = FundingService()
        try:
            st.session_state.funding_service.reload()
        except Exception:
            pass
    except Exception as e:
        logger.warning("FundingService: %s", e)

with st.sidebar:
    st.markdown("## AhanaTrade")
    st.caption("GitHub repo remains Neon-Trader")
    st.markdown("### E*TRADE OAuth")
    oauth_status = oauth_service.get_status()
    if oauth_status.get("is_authenticated"):
        st.success("Connected")
        st.caption(f"Authenticated at: {oauth_status.get('auth_time')}")
    else:
        st.error("Disconnected")
        if st.button("Start OAuth Flow", use_container_width=True, key="start_oauth"):
            try:
                auth_url = oauth_service.initiate_oauth_flow()
                if auth_url:
                    st.session_state.oauth_url = auth_url
                    st.markdown(f"[Authorize at E*TRADE]({auth_url})")
                    st.code(auth_url, language="text")
                else:
                    st.error("Failed to initiate OAuth")
            except Exception as e:
                st.error(str(e))
        if st.session_state.get("oauth_url"):
            verification_code = st.text_input("Verification code", type="password", key="verify_code_input")
            if st.button("Complete authentication", use_container_width=True, key="complete_oauth"):
                try:
                    if oauth_service.complete_oauth_flow(verification_code):
                        st.success("Authenticated")
                        del st.session_state.oauth_url
                        st.rerun()
                    else:
                        st.error("Failed to complete authentication")
                except Exception as e:
                    st.error(str(e))
    st.divider()
    if st.session_state.get("ahanatrade_enter_desk"):
        st.session_state["page_selector"] = "Desk"
        st.session_state["ahanatrade_enter_desk"] = False
    page = st.radio("Select page:", ["Home", "Desk"], key="page_selector")
    st.divider()
    fs = st.session_state.get("funding_service")
    if fs:
        try:
            summary = fs.get_balance_summary()
            st.caption(f"Funding allocated: ${summary.get('allocated_to_portfolio', 0.0):,.2f}")
        except Exception:
            pass

if page == "Home":
    render_splash(cta_page="Desk", cta_label="Enter the desk")
    st.stop()

render_desk(oauth_service=oauth_service)
