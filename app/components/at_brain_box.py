"""
Autonomous Trader Brain Box UI Component
Displays current AT activity and running task list
"""

import streamlit as st
from services.at_brain_activity import get_at_brain
from datetime import datetime

def render_at_brain_box():
    """Render the AT brain box with current activity and history"""
    
    at_brain = get_at_brain()
    status = at_brain.get_current_status()
    
    # Brain box container with custom styling
    with st.container():
        st.markdown("""
        <style>
        .brain-box {
            border: 2px solid #00d4ff;
            border-radius: 10px;
            padding: 15px;
            background-color: rgba(0, 212, 255, 0.05);
            margin: 10px 0;
        }
        .brain-box-header {
            color: #00d4ff;
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 10px;
        }
        .brain-current-task {
            background-color: rgba(0, 212, 255, 0.1);
            border-left: 4px solid #00ff00;
            padding: 10px;
            border-radius: 5px;
            margin: 8px 0;
        }
        .brain-activity-item {
            background-color: rgba(100, 200, 255, 0.05);
            padding: 8px;
            border-left: 3px solid #1f77b4;
            margin: 5px 0;
            font-size: 12px;
            border-radius: 3px;
        }
        .brain-activity-decision {
            border-left-color: #ff7f0e;
        }
        .brain-activity-thought {
            border-left-color: #2ca02c;
        }
        .brain-activity-trade {
            border-left-color: #d62728;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Main brain box
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            <div class="brain-box">
                <div class="brain-box-header">🧠 AUTONOMOUS TRADER BRAIN</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Current Task Display
            if status['current_task']:
                task = status['current_task']
                task_time = task.get('timestamp', '')[:19]
                status_emoji = "🔄" if task['status'] == 'in_progress' else "✅"
                
                st.markdown(f"""
                <div class="brain-current-task">
                    <strong>{status_emoji} CURRENT TASK:</strong><br>
                    {task['task']}<br>
                    <small>🕐 {task_time} | {task['details']}</small>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="brain-current-task">
                    <strong>⚙️ IDLE</strong><br>
                    <small>Waiting for next task...</small>
                </div>
                """, unsafe_allow_html=True)
            
            # Recent Activities List
            st.markdown("<div class='brain-box-header' style='margin-top: 15px;'>📋 ACTIVITY LOG</div>", unsafe_allow_html=True)
            
            recent = at_brain.get_recent_activities(limit=10)
            
            if recent:
                for activity in reversed(recent):
                    activity_time = activity.get('timestamp', '')[-8:]
                    activity_type = activity.get('type', 'unknown')
                    
                    if activity_type == 'decision':
                        decision = activity.get('decision', '')
                        st.markdown(f"""
                        <div class="brain-activity-item brain-activity-decision">
                            <strong>🎯 DECISION:</strong> {decision}<br>
                            <small>⏱️ {activity_time}</small>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    elif activity_type == 'thought':
                        content = activity.get('content', '')
                        category = activity.get('category', 'analysis')
                        st.markdown(f"""
                        <div class="brain-activity-item brain-activity-thought">
                            <strong>💭 {category.upper()}:</strong> {content}<br>
                            <small>⏱️ {activity_time}</small>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    elif activity_type == 'trade_event':
                        event = activity.get('event_type', '')
                        symbol = activity.get('symbol', '')
                        st.markdown(f"""
                        <div class="brain-activity-item brain-activity-trade">
                            <strong>📊 {event.upper()}</strong> {symbol}<br>
                            <small>⏱️ {activity_time}</small>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No activities yet")
        
        with col2:
            st.markdown("<div class='brain-box-header'>📊 STATS</div>", unsafe_allow_html=True)
            
            # Statistics
            st.metric("Total Activities", status['total_activities'], delta=None)
            
            if status['last_activity']:
                last_time = status['last_activity'].get('timestamp', '')[-8:]
                st.metric("Last Activity", last_time)
            
            # Control buttons
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            
            if st.button("🔄 Refresh", use_container_width=True, key="brain_refresh"):
                st.rerun()
            
            if st.button("🗑️ Clear History", use_container_width=True, key="brain_clear"):
                at_brain.clear_history()
                st.success("History cleared!")
                st.rerun()


def simulate_at_activity():
    """Simulate some AT activity for demonstration"""
    at_brain = get_at_brain()
    
    import random
    
    activities = [
        {
            'type': 'thought',
            'category': 'analysis',
            'content': f'Analyzing AAPL price action... Current trend: {random.choice(["bullish", "bearish", "neutral"])}'
        },
        {
            'type': 'decision',
            'decision': f'Enter {random.choice(["long", "short"])} position on {random.choice(["AAPL", "MSFT", "GOOGL"])}',
            'reasoning': 'Technical indicators align with entry signals',
            'parameters': {'size': random.randint(1, 10), 'stop_loss': random.choice([1.5, 2.0, 2.5])}
        }
    ]
    
    activity = random.choice(activities)
    
    if activity['type'] == 'thought':
        at_brain.add_thought(activity['content'], activity['category'])
    elif activity['type'] == 'decision':
        at_brain.add_decision(activity['decision'], activity['reasoning'], activity.get('parameters'))
