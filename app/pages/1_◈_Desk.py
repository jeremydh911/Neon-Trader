"""AhanaTrade desk (Streamlit multipage)."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(
    page_title="AhanaTrade desk",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.desk import render_desk  # noqa: E402

st.sidebar.title("AhanaTrade")
st.sidebar.caption("GitHub repo remains Neon-Trader")
render_desk()
