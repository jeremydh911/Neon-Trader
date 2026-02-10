"""
Agent Mode Components

Modular components for the Agent Mode page:
- status_display: Agent status cards and health monitoring
- control_panel: Start/stop/pause controls
- position_monitor: Trading positions and P&L tracking
- performance_metrics: Performance analytics and charts
- history_viewer: Audit trail and SEC compliance features
"""

from .status_display import render_agent_status, render_performance_summary, render_system_status
from .control_panel import (
    render_control_panel, 
    render_automation_status,
    render_system_controls,
    render_agent_guidance
)
from .position_monitor import (
    render_live_decisions,
    render_pending_approvals,
    render_market_overview
)
from .performance_metrics import (
    render_performance_metrics,
    render_equity_curve,
    render_win_rate_chart,
    render_agent_comparison
)
from .history_viewer import (
    render_decision_history,
    render_audit_trail,
    render_electronic_signatures,
    render_trade_log,
    render_compliance_summary
)

__all__ = [
    # Status Display
    'render_agent_status',
    'render_performance_summary',
    'render_system_status',
    # Control Panel
    'render_control_panel',
    'render_automation_status',
    'render_system_controls',
    'render_agent_guidance',
    # Position Monitor
    'render_live_decisions',
    'render_pending_approvals',
    'render_market_overview',
    # Performance Metrics
    'render_performance_metrics',
    'render_equity_curve',
    'render_win_rate_chart',
    'render_agent_comparison',
    # History Viewer
    'render_decision_history',
    'render_audit_trail',
    'render_electronic_signatures',
    'render_trade_log',
    'render_compliance_summary'
]
