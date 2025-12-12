"""
Autonomous Trader Brain Activity Tracker
Tracks and displays current AT activity and running task list
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

class ATBrainActivity:
    """Tracks autonomous trader brain activity"""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.activity_file = self.data_dir / "at_brain_activity.json"
        self.load_activities()
    
    def load_activities(self) -> None:
        """Load activity log from disk"""
        if self.activity_file.exists():
            try:
                with open(self.activity_file, 'r') as f:
                    data = json.load(f)
                    self.activities = data.get('activities', [])
                    self.current_task = data.get('current_task', None)
            except:
                self.activities = []
                self.current_task = None
        else:
            self.activities = []
            self.current_task = None
    
    def save_activities(self) -> None:
        """Save activity log to disk"""
        try:
            data = {
                'activities': self.activities[-100:],
                'current_task': self.current_task,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.activity_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving activities: {e}")
    
    def set_current_task(self, task: str, details: str = "") -> None:
        """Set what the AT is currently doing"""
        self.current_task = {
            'task': task,
            'details': details,
            'timestamp': datetime.now().isoformat(),
            'status': 'in_progress'
        }
        self.save_activities()
    
    def complete_task(self) -> None:
        """Mark current task as complete and move to history"""
        if self.current_task:
            self.current_task['status'] = 'completed'
            self.activities.append(self.current_task)
            self.current_task = None
            self.save_activities()
    
    def add_thought(self, thought: str, category: str = "analysis") -> None:
        """Add a thought or conversation entry"""
        activity = {
            'type': 'thought',
            'category': category,
            'content': thought,
            'timestamp': datetime.now().isoformat()
        }
        self.activities.append(activity)
        self.save_activities()
    
    def add_decision(self, decision: str, reasoning: str = "", parameters: Dict = None) -> None:
        """Log a trading decision"""
        activity = {
            'type': 'decision',
            'decision': decision,
            'reasoning': reasoning,
            'parameters': parameters or {},
            'timestamp': datetime.now().isoformat()
        }
        self.activities.append(activity)
        self.save_activities()
    
    def add_trade_event(self, event_type: str, symbol: str, details: Dict) -> None:
        """Log trade-related events"""
        activity = {
            'type': 'trade_event',
            'event_type': event_type,
            'symbol': symbol,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.activities.append(activity)
        self.save_activities()
    
    def get_recent_activities(self, limit: int = 20) -> List[Dict]:
        """Get recent activities"""
        return self.activities[-limit:]
    
    def get_current_status(self) -> Dict:
        """Get current AT status"""
        return {
            'current_task': self.current_task,
            'total_activities': len(self.activities),
            'last_activity': self.activities[-1] if self.activities else None
        }
    
    def clear_history(self) -> None:
        """Clear activity history"""
        self.activities = []
        self.current_task = None
        self.save_activities()


def get_at_brain():
    """Get singleton instance of AT brain activity tracker"""
    if not hasattr(get_at_brain, '_instance'):
        get_at_brain._instance = ATBrainActivity()
    return get_at_brain._instance
