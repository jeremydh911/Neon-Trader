"""
Chat Interface for Neon Trader
Allows users to chat with:
1. Autonomous Trader
2. Trading Council (4 members)
3. All-in-one (Trader + Council)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


import streamlit as st
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# Add parent directory to path for imports

logger = logging.getLogger(__name__)

# Configure page
st.set_page_config(
    page_title="Chat Interface - AhanaTrade",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better chat appearance
st.markdown("""
<style>
    .chat-message {
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: column;
    }
    
    .chat-message.user {
        background-color: #2a3f5f;
        color: #ffffff;
        border-left: 4px solid #4da6ff;
    }
    
    .chat-message.assistant {
        background-color: #3a3a3a;
        color: #ffffff;
        border-left: 4px solid #66bb6a;
    }
    
    .chat-message.council {
        background-color: #3a2a1a;
        color: #ffffff;
        border-left: 4px solid #ffa726;
    }
    
    .chat-message.trader {
        background-color: #3a2a3f;
        color: #ffffff;
        border-left: 4px solid #ce93d8;
    }
    
    .chat-member-tag {
        font-size: 0.75rem;
        font-weight: bold;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        margin-right: 0.5rem;
        display: inline-block;
    }
    
    .technical-tag {
        background-color: #1565c0;
        color: #ffffff;
    }
    
    .sentiment-tag {
        background-color: #2e7d32;
        color: #ffffff;
    }
    
    .risk-tag {
        background-color: #d84315;
        color: #ffffff;
    }
    
    .memory-tag {
        background-color: #6a1b9a;
        color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "chat_mode" not in st.session_state:
    st.session_state.chat_mode = "trader"

if "council_responses" not in st.session_state:
    st.session_state.council_responses = {}


class ChatManager:
    """Manages chat interactions with different entities"""
    
    def __init__(self):
        self.trader_history = []
        self.council_history = []
    
    def format_timestamp(self) -> str:
        """Get formatted timestamp"""
        return datetime.now().strftime("%H:%M:%S")
    
    def add_trader_message(self, user_message: str, response: str) -> Dict:
        """Add message to trader chat history"""
        message = {
            "type": "trader",
            "timestamp": self.format_timestamp(),
            "user": user_message,
            "response": response
        }
        self.trader_history.append(message)
        return message
    
    def add_council_message(self, user_message: str, responses: Dict[str, str]) -> Dict:
        """Add message to council chat history"""
        message = {
            "type": "council",
            "timestamp": self.format_timestamp(),
            "user": user_message,
            "responses": responses
        }
        self.council_history.append(message)
        return message
    
    def get_trader_response(self, query: str) -> str:
        """Get response from autonomous trader"""
        try:
            # Use the chat adapter to handle trader initialization properly
            from services.chat_adapter import TraderChatAdapter
            
            adapter = TraderChatAdapter()
            result = adapter.process_query(query)
            
            if result.get("status") == "success":
                return result.get("response", "I'm analyzing your query... Please try again.")
            else:
                return result.get("message", "Unable to process your request.")
        except Exception as e:
            logger.error(f"Trader error: {e}")
            return f"Unable to process your request: {str(e)}"
    
    def get_council_responses(self, query: str) -> Dict[str, str]:
        """Get responses from all council members"""
        try:
            # Use the chat adapter to handle council initialization properly
            from services.chat_adapter import CouncilChatAdapter
            
            adapter = CouncilChatAdapter()
            result = adapter.process_query(query)
            
            if result.get("status") == "success":
                return result.get("responses", {})
            else:
                return {"error": result.get("message", "Unable to process council request.")}
        except Exception as e:
            logger.error(f"Council error: {e}")
            return {"error": f"Unable to process council request: {str(e)}"}
    
    def _get_technical_response(self, query: str) -> str:
        """Get technical analyst response"""
        return f"📊 Technical Analysis: Analyzing technical indicators for your query..."
    
    def _get_sentiment_response(self, query: str) -> str:
        """Get sentiment analyst response"""
        return f"📰 Sentiment Analysis: Evaluating market sentiment..."
    
    def _get_risk_response(self, query: str) -> str:
        """Get risk manager response"""
        return f"⚠️ Risk Assessment: Evaluating risk parameters..."
    
    def _get_memory_response(self, query: str) -> str:
        """Get memory curator response"""
        return f"🧠 Pattern Recognition: Analyzing historical patterns..."


def display_chat_message(role: str, content: str, timestamp: str = None, member: str = None):
    """Display a formatted chat message"""
    css_class = role.lower()
    
    if member:
        if member == "technical":
            tag = f'<span class="chat-member-tag technical-tag">📊 {member.title()}</span>'
        elif member == "sentiment":
            tag = f'<span class="chat-member-tag sentiment-tag">📰 {member.title()}</span>'
        elif member == "risk":
            tag = f'<span class="chat-member-tag risk-tag">⚠️ {member.title()}</span>'
        elif member == "memory":
            tag = f'<span class="chat-member-tag memory-tag">🧠 {member.title()}</span>'
        else:
            tag = ""
        
        html = f"""
        <div class="chat-message {css_class}">
            <div style="font-weight: bold; margin-bottom: 0.5rem;">
                {tag} {member.title()}
                {f'<span style="float: right; font-size: 0.8rem; color: #666;">{timestamp}</span>' if timestamp else ''}
            </div>
            <div>{content}</div>
        </div>
        """
    else:
        html = f"""
        <div class="chat-message {css_class}">
            <div style="font-weight: bold; margin-bottom: 0.5rem;">
                {role}
                {f'<span style="float: right; font-size: 0.8rem; color: #666;">{timestamp}</span>' if timestamp else ''}
            </div>
            <div>{content}</div>
        </div>
        """
    
    st.markdown(html, unsafe_allow_html=True)


def chat_trader_tab():
    """Chat with autonomous trader"""
    st.header("💬 Chat with Autonomous Trader")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("**Communicate directly with the autonomous trader for real-time analysis and trading insights.**")
    
    with col2:
        if st.button("🗑️ Clear History", key="clear_trader"):
            st.session_state.chat_history = [m for m in st.session_state.chat_history if m.get("type") != "trader"]
            st.rerun()
    
    # Chat display area
    chat_container = st.container(height=400, border=True)
    
    with chat_container:
        trader_messages = [m for m in st.session_state.chat_history if m.get("type") == "trader"]
        
        if not trader_messages:
            st.info("👋 Start a conversation with the autonomous trader. Ask questions about market analysis, trading strategies, or current positions.")
        else:
            for msg in trader_messages:
                display_chat_message("You", msg["user"], msg["timestamp"])
                display_chat_message("🤖 Trader", msg["response"], msg["timestamp"])
    
    # Input area
    st.divider()
    
    user_input = st.text_input(
        "Ask the trader a question:",
        placeholder="What's your analysis on AAPL? Should I buy or sell?",
        key="trader_input"
    )
    
    col1, col2 = st.columns([1, 5])
    
    with col1:
        send_btn = st.button("📤 Send", key="send_trader", use_container_width=True)
    
    if send_btn and user_input:
        with st.spinner("🤖 Trader is analyzing..."):
            chat_mgr = ChatManager()
            response = chat_mgr.get_trader_response(user_input)
            
            message = {
                "type": "trader",
                "timestamp": chat_mgr.format_timestamp(),
                "user": user_input,
                "response": response
            }
            st.session_state.chat_history.append(message)
        
        st.rerun()


def chat_council_tab():
    """Chat with trading council"""
    st.header("🏛️ Chat with Trading Council")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("**Get perspectives from all 4 council members: Technical Analyst, Sentiment Analyst, Risk Manager, and Memory Curator.**")
    
    with col2:
        if st.button("🗑️ Clear History", key="clear_council"):
            st.session_state.chat_history = [m for m in st.session_state.chat_history if m.get("type") != "council"]
            st.rerun()
    
    # Chat display area
    chat_container = st.container(height=400, border=True)
    
    with chat_container:
        council_messages = [m for m in st.session_state.chat_history if m.get("type") == "council"]
        
        if not council_messages:
            st.info("🏛️ Start a discussion with the trading council. Ask about technical analysis, sentiment, risk assessment, or historical patterns.")
        else:
            for msg in council_messages:
                display_chat_message("You", msg["user"], msg["timestamp"])
                
                responses = msg.get("responses", {})
                col1, col2 = st.columns(2)
                
                with col1:
                    if "technical" in responses:
                        display_chat_message("Technical", responses["technical"], msg["timestamp"], "technical")
                    if "risk" in responses:
                        display_chat_message("Risk", responses["risk"], msg["timestamp"], "risk")
                
                with col2:
                    if "sentiment" in responses:
                        display_chat_message("Sentiment", responses["sentiment"], msg["timestamp"], "sentiment")
                    if "memory" in responses:
                        display_chat_message("Memory", responses["memory"], msg["timestamp"], "memory")
    
    # Input area
    st.divider()
    
    user_input = st.text_input(
        "Ask the council a question:",
        placeholder="What do you think about the current market conditions?",
        key="council_input"
    )
    
    col1, col2 = st.columns([1, 5])
    
    with col1:
        send_btn = st.button("📤 Send", key="send_council", use_container_width=True)
    
    if send_btn and user_input:
        with st.spinner("🏛️ Council is deliberating..."):
            chat_mgr = ChatManager()
            responses = chat_mgr.get_council_responses(user_input)
            
            message = {
                "type": "council",
                "timestamp": chat_mgr.format_timestamp(),
                "user": user_input,
                "responses": responses
            }
            st.session_state.chat_history.append(message)
        
        st.rerun()


def chat_all_in_one_tab():
    """Chat with both trader and council"""
    st.header("🎯 All-in-One Discussion")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("**Get comprehensive analysis from both the autonomous trader and all 4 council members in one conversation.**")
    
    with col2:
        if st.button("🗑️ Clear History", key="clear_all"):
            st.session_state.chat_history = []
            st.rerun()
    
    # Chat display area
    chat_container = st.container(height=450, border=True)
    
    with chat_container:
        if not st.session_state.chat_history:
            st.info("🎯 Start a comprehensive discussion. Get analysis from both the autonomous trader and the entire council.")
        else:
            for msg in st.session_state.chat_history:
                display_chat_message("You", msg["user"], msg["timestamp"])
                
                if msg.get("type") == "trader":
                    display_chat_message("🤖 Trader", msg["response"], msg["timestamp"])
                
                elif msg.get("type") == "council":
                    responses = msg.get("responses", {})
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if "technical" in responses:
                            display_chat_message("Technical", responses["technical"], msg["timestamp"], "technical")
                        if "risk" in responses:
                            display_chat_message("Risk", responses["risk"], msg["timestamp"], "risk")
                    
                    with col2:
                        if "sentiment" in responses:
                            display_chat_message("Sentiment", responses["sentiment"], msg["timestamp"], "sentiment")
                        if "memory" in responses:
                            display_chat_message("Memory", responses["memory"], msg["timestamp"], "memory")
    
    # Input area
    st.divider()
    
    user_input = st.text_input(
        "Ask trader and council anything:",
        placeholder="What's your comprehensive view on the market right now?",
        key="all_input"
    )
    
    col1, col2 = st.columns([1, 5])
    
    with col1:
        send_btn = st.button("📤 Send All", key="send_all", use_container_width=True)
    
    if send_btn and user_input:
        with st.spinner("🎯 Getting comprehensive analysis..."):
            chat_mgr = ChatManager()
            
            # Get trader response
            trader_response = chat_mgr.get_trader_response(user_input)
            trader_msg = {
                "type": "trader",
                "timestamp": chat_mgr.format_timestamp(),
                "user": user_input,
                "response": trader_response
            }
            st.session_state.chat_history.append(trader_msg)
            
            # Get council responses
            council_responses = chat_mgr.get_council_responses(user_input)
            council_msg = {
                "type": "council",
                "timestamp": chat_mgr.format_timestamp(),
                "user": user_input,
                "responses": council_responses
            }
            st.session_state.chat_history.append(council_msg)
        
        st.rerun()


# Main app
def main():
    st.sidebar.title("AhanaTrade Chat")
    
    # Mode selection
    chat_mode = st.sidebar.radio(
        "Select Chat Mode:",
        options=["Autonomous Trader", "Trading Council", "All-in-One"],
        captions=[
            "1-on-1 with the trader",
            "Discussion with 4 council members",
            "Full discussion with trader + council"
        ]
    )
    
    st.sidebar.divider()
    
    # Chat statistics
    st.sidebar.subheader("📊 Chat Statistics")
    
    trader_count = len([m for m in st.session_state.chat_history if m.get("type") == "trader"])
    council_count = len([m for m in st.session_state.chat_history if m.get("type") == "council"])
    
    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        st.metric("Trader", trader_count)
    with col2:
        st.metric("Council", council_count)
    with col3:
        st.metric("Total", trader_count + council_count)
    
    st.sidebar.divider()
    
    # Help section
    st.sidebar.subheader("❓ Help")
    with st.sidebar.expander("How to use"):
        st.markdown("""
        **Autonomous Trader Mode:**
        - Direct 1-on-1 conversation with the AI trader
        - Get real-time market analysis
        - Ask about trading strategies
        
        **Trading Council Mode:**
        - Discuss with 4 specialist AI members
        - Technical Analyst (📊)
        - Sentiment Analyst (📰)
        - Risk Manager (⚠️)
        - Memory Curator (🧠)
        
        **All-in-One Mode:**
        - Get comprehensive analysis
        - Trader + Council perspectives
        - Balanced decision making
        """)
    
    st.sidebar.divider()
    
    # Display appropriate chat interface
    if chat_mode == "Autonomous Trader":
        chat_trader_tab()
    elif chat_mode == "Trading Council":
        chat_council_tab()
    else:
        chat_all_in_one_tab()


if __name__ == "__main__":
    main()
