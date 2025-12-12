"""
Settings Manager - Persistent configuration storage
Saves and loads user preferences to/from disk
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SettingsManager:
    """Manage persistent user settings"""
    
    def __init__(self, settings_path: str = "/app/data/settings.json"):
        self.settings_path = Path(settings_path)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Default settings
        self.defaults = {
            "trading_mode": "Autonomous Trade",
            "day_trade_enabled": True,
            "day_trade_close_time": "16:00",
            "day_trade_max_loss": 5.0,
            "day_trade_max_gain": 10.0,
            "autonomous_enabled": True,
            "autonomous_confirmed": True,
            "autonomous_max_positions": 10,
            "autonomous_max_loss_per_trade": 2.0,
            "autonomous_take_profit": 3.0,
            "autonomous_portfolio_loss_limit": 5.0,
            "risk_level": 7,
            "position_size": 1000,
            "max_position_single": 10,
            "notify_trades": True,
            "notify_signals": True,
            "notify_losses": True,
            "require_confirmation": False,
            "last_updated": datetime.utcnow().isoformat()
        }
        
        self.settings = self._load_settings()
        logger.info(f"SettingsManager initialized with path: {self.settings_path}")
        logger.info(f"Loaded settings: {json.dumps(self.settings, indent=2, default=str)}")
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from disk or return defaults"""
        try:
            if self.settings_path.exists():
                with open(self.settings_path, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults to handle new settings
                    settings = {**self.defaults, **loaded}
                    logger.info(f"✅ Loaded settings from {self.settings_path}")
                    logger.info(f"Loaded settings keys: {list(loaded.keys())}")
                    return settings
            else:
                logger.info(f"Settings file not found at {self.settings_path}, using defaults")
        except Exception as e:
            logger.warning(f"❌ Failed to load settings: {e}")
        
        logger.info("Using default settings")
        return self.defaults.copy()
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to disk"""
        try:
            settings["last_updated"] = datetime.utcnow().isoformat()
            
            # Ensure directory exists
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=2, default=str)
            
            self.settings = settings
            logger.info(f"✅ Settings saved to {self.settings_path}")
            logger.info(f"Saved settings: {json.dumps(settings, indent=2, default=str)}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save settings: {e}")
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a single setting"""
        value = self.settings.get(key, default)
        logger.debug(f"Getting setting '{key}': {value}")
        return value
    
    def set_setting(self, key: str, value: Any) -> bool:
        """Set a single setting and save"""
        self.settings[key] = value
        return self.save_settings(self.settings)
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings"""
        logger.debug(f"Getting all settings: {list(self.settings.keys())}")
        return self.settings.copy()
    
    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults"""
        self.settings = self.defaults.copy()
        return self.save_settings(self.settings)
    
    def export_settings(self, export_path: Optional[str] = None) -> Optional[str]:
        """Export settings to file"""
        try:
            path = Path(export_path) if export_path else Path("/app/data/settings_export.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w') as f:
                json.dump(self.settings, f, indent=2, default=str)
            
            logger.info(f"✅ Settings exported to {path}")
            return str(path)
        except Exception as e:
            logger.error(f"❌ Failed to export settings: {e}")
            return None
    
    def import_settings(self, import_path: str) -> bool:
        """Import settings from file"""
        try:
            path = Path(import_path)
            if not path.exists():
                logger.error(f"❌ Import file not found: {path}")
                return False
            
            with open(path, 'r') as f:
                imported = json.load(f)
            
            # Merge with defaults to ensure all keys exist
            self.settings = {**self.defaults, **imported}
            return self.save_settings(self.settings)
        except Exception as e:
            logger.error(f"❌ Failed to import settings: {e}")
            return False
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading-specific configuration"""
        return {
            "mode": self.get_setting("trading_mode", "Manual"),
            "day_trade": {
                "enabled": self.get_setting("day_trade_enabled", False),
                "close_time": self.get_setting("day_trade_close_time", "16:00"),
                "max_loss_pct": self.get_setting("day_trade_max_loss", 5.0),
                "take_profit_pct": self.get_setting("day_trade_max_gain", 10.0)
            },
            "autonomous": {
                "enabled": self.get_setting("autonomous_enabled", False),
                "confirmed": self.get_setting("autonomous_confirmed", False),
                "max_positions": self.get_setting("autonomous_max_positions", 10),
                "max_loss_pct": self.get_setting("autonomous_max_loss_per_trade", 2.0),
                "take_profit_pct": self.get_setting("autonomous_take_profit", 3.0),
                "portfolio_loss_limit": self.get_setting("autonomous_portfolio_loss_limit", 5.0)
            },
            "risk_level": self.get_setting("risk_level", 5),
            "position_size": self.get_setting("position_size", 1000),
            "max_position_single_pct": self.get_setting("max_position_single", 10)
        }
    
    def get_notification_config(self) -> Dict[str, bool]:
        """Get notification preferences"""
        return {
            "trades": self.get_setting("notify_trades", True),
            "signals": self.get_setting("notify_signals", True),
            "losses": self.get_setting("notify_losses", True)
        }
