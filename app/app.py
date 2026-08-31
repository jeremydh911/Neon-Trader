"""AhanaTrade Streamlit entry: splash then the AI desk."""

import os
import sys
import logging

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

try:
    from services.tracing_config import setup_tracing
    setup_tracing()
except Exception:
    pass

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="AhanaTrade",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.splash import render_splash  # noqa: E402
from components.desk import render_desk  # noqa: E402

st.sidebar.title("AhanaTrade")
st.sidebar.caption("GitHub repo remains Neon-Trader")

if st.session_state.get("ahanatrade_enter_desk"):
    st.session_state["nav_page"] = st.session_state.get("ahanatrade_desk_target") or "Desk"
    st.session_state["ahanatrade_enter_desk"] = False
if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "Home"

page = st.sidebar.radio("Navigation", ["Home", "Desk"], key="nav_page")

if page == "Home":
    render_splash(cta_page="Desk", cta_label="Enter the desk")
    st.stop()

render_desk()
