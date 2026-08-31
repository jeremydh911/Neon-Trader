"""AhanaTrade retail splash / landing page.

Dark premium trading aesthetic. No live balances or quotes.
"""

from __future__ import annotations

from typing import Optional


SPLASH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

.ahana-splash {
    position: relative;
    overflow: hidden;
    padding: 2.6rem 2.2rem 2.2rem;
    border-radius: 18px;
    background:
        radial-gradient(1200px 480px at 12% -10%, rgba(201, 162, 39, 0.16), transparent 55%),
        radial-gradient(900px 420px at 100% 0%, rgba(45, 212, 191, 0.10), transparent 50%),
        linear-gradient(165deg, #07090f 0%, #0c1220 55%, #080a10 100%);
    border: 1px solid rgba(201, 162, 39, 0.22);
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255,255,255,0.04);
    color: #e8eaed;
    font-family: "IBM Plex Sans", sans-serif;
}
.ahana-splash::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 48px 48px;
    mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
    pointer-events: none;
}
.ahana-kicker {
    letter-spacing: 0.38em;
    text-transform: uppercase;
    font-size: 0.72rem;
    color: #c9a227;
    font-weight: 600;
    margin-bottom: 0.85rem;
}
.ahana-hero-name {
    font-family: "Cormorant Garamond", Georgia, serif;
    font-size: 4.1rem;
    line-height: 0.92;
    font-weight: 600;
    color: #f4efe4;
    text-shadow: 0 0 40px rgba(201, 162, 39, 0.18);
    margin: 0 0 0.55rem 0;
}
.ahana-hero-name span {
    color: #c9a227;
}
.ahana-tag {
    font-size: 1.15rem;
    color: #b7c0d1;
    max-width: 38rem;
    margin: 0 0 1.4rem 0;
}
.ahana-rule {
    height: 1px;
    width: 7rem;
    background: linear-gradient(90deg, #c9a227, transparent);
    margin: 0 0 1.4rem 0;
}
.ahana-chips {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.75rem;
    margin: 0 0 1.5rem 0;
}
.ahana-chip {
    background: rgba(10, 16, 28, 0.72);
    border: 1px solid rgba(61, 204, 199, 0.18);
    border-radius: 12px;
    padding: 0.9rem 1rem;
}
.ahana-chip h4 {
    margin: 0 0 0.25rem 0;
    color: #3dccc7;
    font-size: 0.78rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-weight: 600;
}
.ahana-chip p {
    margin: 0;
    color: #e8eaed;
    font-size: 0.98rem;
    font-weight: 500;
}
.ahana-note {
    color: #8b93a7;
    font-size: 0.85rem;
    margin-top: 1.4rem;
}
.ahana-disclaimer {
    color: #6d7588;
    font-size: 0.78rem;
    margin-top: 0.35rem;
}
</style>
"""

HERO_HTML = """
<div class="ahana-splash">
  <div class="ahana-kicker">Retail day-trading desk</div>
  <h1 class="ahana-hero-name">Ahana<span>Trade</span></h1>
  <p class="ahana-tag">Charts, strategy catch, and plan alerts under a $10k sleeve. Plug in a Grok Bot — or any OpenAI-compatible agent — as the brain. Sandbox first. Live is gated.</p>
  <div class="ahana-rule"></div>
  <div class="ahana-chips">
    <div class="ahana-chip">
      <h4>Session</h4>
      <p>7:00am–8:00pm ET</p>
    </div>
    <div class="ahana-chip">
      <h4>Orders</h4>
      <p>Limit-only · GFD</p>
    </div>
    <div class="ahana-chip">
      <h4>Risk</h4>
      <p>$10k deployed-out</p>
    </div>
    <div class="ahana-chip">
      <h4>Brain</h4>
      <p>Catch · plan · brain</p>
    </div>
  </div>
  <p class="ahana-note">No live balances or quotes on this page. Connect the desk to see your account.</p>
  <p class="ahana-disclaimer">Not investment advice. Overnight is flat after 8:00pm ET. The GitHub repository is still named Neon-Trader.</p>
</div>
"""


def render_splash(cta_page: Optional[str] = "Trading", cta_label: str = "Enter the desk") -> bool:
    """Render the landing hero. Returns True if the CTA was clicked.

    Sets st.session_state['ahanatrade_enter_desk'] and reruns so the host
    can switch into the existing desk before its nav widget is created.
    """
    import streamlit as st

    st.markdown(SPLASH_CSS, unsafe_allow_html=True)
    st.markdown(HERO_HTML, unsafe_allow_html=True)

    clicked = st.button(cta_label, type="primary", key="ahanatrade_enter_desk_btn")
    if clicked:
        st.session_state["ahanatrade_enter_desk"] = True
        if cta_page:
            st.session_state["ahanatrade_desk_target"] = cta_page
        st.rerun()
    return clicked
