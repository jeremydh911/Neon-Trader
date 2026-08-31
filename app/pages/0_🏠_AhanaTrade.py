"""AhanaTrade landing page (Streamlit multipage entry)."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(
    page_title="AhanaTrade",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.splash import render_splash  # noqa: E402

st.sidebar.title("AhanaTrade")
st.sidebar.caption("GitHub repo remains Neon-Trader")

desk = Path(__file__).resolve().parent / "3_📊_E_TRADE_Dashboard.py"
if st.session_state.get("ahanatrade_enter_desk"):
    st.session_state["ahanatrade_enter_desk"] = False
    try:
        st.switch_page(str(desk))
    except Exception:
        st.info("Open **E*TRADE Dashboard** in the sidebar to enter the desk.")

render_splash(cta_page="E*TRADE Dashboard", cta_label="Enter the desk")
