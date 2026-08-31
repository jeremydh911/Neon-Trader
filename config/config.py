"""Neon Trader configuration.

Credentials never live here. Load E*TRADE keys from the environment or a
gitignored file (see README). Desk is sized to a $10k aggregate capital-out
cap — not investment advice and not a guarantee of results.
"""

from __future__ import annotations

# E*TRADE hosts (current developer platform). Do not use the retired
# etwssandbox.etrade.com hostname.
ETRADE_SANDBOX_HOST = "https://apisb.etrade.com"
ETRADE_PRODUCTION_HOST = "https://api.etrade.com"
ETRADE_SANDBOX_API_V1 = "https://apisb.etrade.com/v1"
ETRADE_PRODUCTION_API_V1 = "https://api.etrade.com/v1"
ETRADE_AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"

DEFAULT_ETRADE_ENV = "sandbox"

# Day-trading desk risk caps.
RISK = {
    "max_deployed_out_usd": 10000.0,
    "max_open_orders": 3,
    "daily_loss_halt_usd": 250.0,
    "daily_loss_halt_pct_equity": 0.025,
    "session_timezone": "America/New_York",
    # 7:00am pre-market through 8:00pm after-hours. Overnight out.
    "session_open": "07:00",
    "session_close": "20:00",
    "blackout_start": "04:00",
    "blackout_end": "07:00",
    "regular_open": "09:30",
    "regular_close": "16:00",
    "afterhours_open": "16:00",
    "afterhours_close": "20:00",
    "cancel_before_roll": "09:28",
    "include_premarket": True,
    "include_afterhours": True,
    "limit_only": True,
    "long_only": True,
    "allow_crypto": False,
    "restrict_us_listed_only": False,
    "ui_timezone": "Pacific/Honolulu",
    "ui_et_offset_hours_august": 6,
    "enforce_pdt": False,
    "min_equity_pdt_usd": None,
    "overnight_out": True,
    "follow_afterhours_working": True,
    "follow_min_tick": 0.01,
}
