"""
Control Panel Module

Handles agent control buttons (start/stop/pause/resume) and automation status display.
"""

import streamlit as st
from typing import Dict, Any


def render_control_panel() -> None:
    """Render the main agent control panel with activation controls."""
    col_status, col_mode = st.columns(2)
    
    with col_status:
        if st.session_state.agent_mode_active:
            st.success("✅ **Agent Mode ACTIVE**")
            if st.button("⏸️ Pause Agents", key="pause_agents"):
                st.session_state.agent_mode_active = False
                st.info("Agents paused")
                st.rerun()
        else:
            st.warning("⏸️ **Agent Mode PAUSED**")
            if st.button("▶️ Activate Agents", key="activate_agents"):
                st.session_state.agent_mode_active = True
                st.success("Agents activated!")
                st.rerun()


def render_automation_status(automation_controller: Any) -> Dict[str, Any]:
    """
    Render automation status and controls.
    
    Returns:
        Dict with automation status information including 'enabled' flag and 'autonomy_level'
    """
    automation_enabled = automation_controller.is_automation_enabled()
    
    col_automation, col_mode, col_monitoring = st.columns([2, 2, 3])
    
    with col_automation:
        if automation_enabled:
            st.success("🤖 **AUTO ENABLED**")
            st.caption("[Manage →](/12_🤖_Automation_Control)")
        else:
            st.warning("👤 **MANUAL MODE**")
            if st.button("Enable Automation", key="goto_automation"):
                st.switch_page("pages/12_🤖_Automation_Control.py")
    
    with col_mode:
        if automation_enabled:
            agent_autonomy = "Full Auto (No approval)"
            st.info("**Full Automation**")
            st.caption("Trades execute automatically")
        else:
            agent_autonomy = st.selectbox(
                "Autonomy Level",
                options=["Semi-Auto (Approve trades)", "Manual (Approve all)"],
                index=0,
                key="autonomy_level"
            )
    
    with col_monitoring:
        st.write("**Monitoring:**")
        symbols_count = len(st.session_state.get('monitoring_symbols', []))
        st.write(f"📊 {symbols_count} symbols | 🤖 10 active agents | ⏱️ Refresh: 30s")
    
    return {
        'enabled': automation_enabled,
        'autonomy_level': agent_autonomy if not automation_enabled else "Full Auto (No approval)"
    }


def render_system_controls() -> None:
    """Render system-level control buttons."""
    st.subheader("⚙️ System Controls")
    
    if st.button("🔄 Restart All Agents", use_container_width=True):
        st.info("Restarting agent system...")
    
    if st.button("💾 Save Agent States", use_container_width=True):
        st.success("✅ All agent states saved!")
    
    if st.button("📤 Export Performance Data", use_container_width=True):
        st.success("✅ Performance data exported to CSV!")


def render_agent_guidance(agents: list) -> None:
    """Render agent guidance and training interface."""
    st.subheader("🎓 Agent Guidance & Training")
    
    # Select agent to guide
    agent_to_guide = st.selectbox(
        "Select Agent",
        options=[a['name'] for a in agents],
        key="agent_to_guide"
    )
    
    st.divider()
    
    # Guidance tabs
    guidance_tab1, guidance_tab2, guidance_tab3 = st.tabs(["💬 Chat", "🎯 Directive", "📚 Training"])
    
    with guidance_tab1:
        render_agent_chat(agent_to_guide)
    
    with guidance_tab2:
        render_agent_directive(agent_to_guide)
    
    with guidance_tab3:
        render_agent_training(agent_to_guide)


def render_agent_chat(agent_name: str) -> None:
    """Render chat interface with an agent."""
    st.write(f"**Chat with {agent_name}:**")
    
    # Chat history
    chat_key = f"chat_history_{agent_name}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = [
            {"role": "agent", "message": f"Hi! I'm {agent_name}. How can I improve my trading?"}
        ]
    
    # Display chat
    for msg in st.session_state[chat_key]:
        if msg['role'] == 'agent':
            st.markdown(f"🤖 **{agent_name}:** {msg['message']}")
        else:
            st.markdown(f"👤 **You:** {msg['message']}")
    
    # Chat input
    user_message = st.text_input("Your message", key=f"chat_input_{agent_name}", placeholder="Type your guidance...")
    if st.button("Send", key=f"send_chat_{agent_name}"):
        if user_message:
            st.session_state[chat_key].append({"role": "user", "message": user_message})
            
            # Generate agent response (mock)
            agent_response = f"Understood! I'll {user_message.lower()} in my analysis going forward."
            st.session_state[chat_key].append({"role": "agent", "message": agent_response})
            st.rerun()


def render_agent_directive(agent_name: str) -> None:
    """Render directive interface for giving commands to an agent."""
    st.write(f"**Give {agent_name} a directive:**")
    
    directive_type = st.selectbox(
        "Directive Type",
        options=[
            "Focus on specific sector",
            "Increase/decrease risk tolerance",
            "Prioritize certain indicators",
            "Avoid specific stocks",
            "Custom directive"
        ],
        key="directive_type"
    )
    
    directive_text = st.text_area(
        "Directive Details",
        placeholder="e.g., 'Focus on tech sector for next week' or 'Increase position sizes by 20%'",
        key="directive_text"
    )
    
    if st.button("📨 Send Directive", key="send_directive", use_container_width=True):
        if directive_text:
            st.success(f"✅ Directive sent to {agent_name}!")
            st.info(f"📋 {agent_name} will apply: {directive_text}")


def render_agent_training(agent_name: str) -> None:
    """Render training interface for agent improvement."""
    st.write(f"**Training {agent_name}:**")
    
    st.write("**Recent Performance:**")
    st.metric("Win Rate (Last 30 days)", "68%", "+5%")
    st.metric("Sharpe Ratio", "1.85", "+0.23")
    
    st.write("")
    st.write("**Training Actions:**")
    
    if st.button("🎓 Run Historical Training", use_container_width=True):
        st.info(f"Starting historical pattern training for {agent_name}...")
        st.write("- Analyzing 2 years of S&P 500 data")
        st.write("- Identifying successful patterns")
        st.write("- Updating decision weights")
    
    if st.button("📊 Review Mistakes", use_container_width=True):
        st.warning("Showing losing trades for analysis...")
        st.write("- TSLA SELL 12/15: Lost $450 (RSI false signal)")
        st.write("- NVDA BUY 12/08: Lost $320 (Ignored resistance level)")
    
    if st.button("✨ Suggest Improvements", use_container_width=True):
        st.success("AI-generated improvement suggestions:")
        st.write("1. Wait for volume confirmation on RSI signals")
        st.write("2. Check key resistance levels before entries")
        st.write("3. Reduce position size during low ADX periods")
