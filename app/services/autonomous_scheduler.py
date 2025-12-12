"""
Autonomous Trading Scheduler
Keeps the autonomous trader active during trading hours (1:00 AM Hawaii time onwards)
Monitors and executes trades based on AI signals with actual broker integration
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pytz import timezone
import threading
import time

logger = logging.getLogger(__name__)

class AutonomousTraderScheduler:
    """Schedule and manage autonomous trading during market hours"""
    
    def __init__(self, broker=None):
        self.config_file = "/app/data/autonomous_config.json"
        self.activity_log = "/app/data/autonomous_activity.json"
        self.hawaii_tz = timezone('Pacific/Honolulu')
        self.broker = broker  # Alpaca broker instance
        
        # Trading configuration
        self.trading_start_hour = 1  # 1:00 AM Hawaii time
        self.max_daily_trades = 10
        self.min_trade_interval = 300  # 5 minutes between trades
        
        self.load_config()
        self.load_activity()
    
    def load_config(self):
        """Load autonomous trading configuration"""
        try:
            os.makedirs("/app/data", exist_ok=True)
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                logger.info("✅ Loaded autonomous trading config")
            else:
                self.config = self._get_default_config()
                self.save_config()
                logger.info("✅ Created default autonomous trading config")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default autonomous trading configuration"""
        return {
            'trading_start_hour': 1,  # 1:00 AM Hawaii time
            'max_positions': 10,
            'risk_per_trade': 2.0,  # 2% risk per trade
            'min_confidence': 60,  # 60% AI confidence required
            'take_profit_pct': 3.0,
            'stop_loss_pct': 2.0,
            'trading_enabled': True,
            'symbols': ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'JPM', 'V', 'JNJ'],
        }
    
    def save_config(self):
        """Save configuration to file"""
        try:
            os.makedirs("/app/data", exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info("✅ Saved autonomous trading config")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def load_activity(self):
        """Load today's activity log"""
        try:
            if os.path.exists(self.activity_log):
                with open(self.activity_log, 'r') as f:
                    self.activity = json.load(f)
                logger.info(f"✅ Loaded activity log with {len(self.activity.get('trades', []))} trades")
            else:
                self.activity = self._get_default_activity()
                self.save_activity()
        except Exception as e:
            logger.error(f"Error loading activity: {e}")
            self.activity = self._get_default_activity()
    
    def _get_default_activity(self) -> Dict:
        """Get default activity structure"""
        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'trading_started': False,
            'start_time': None,
            'trades': [],
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
        }
    
    def save_activity(self):
        """Save activity log to file"""
        try:
            os.makedirs("/app/data", exist_ok=True)
            with open(self.activity_log, 'w') as f:
                json.dump(self.activity, f, indent=2)
            logger.debug("✅ Saved activity log")
        except Exception as e:
            logger.error(f"Error saving activity: {e}")
    
    def is_trading_active(self) -> bool:
        """Check if autonomous trading should be active now"""
        try:
            hawaii_time = datetime.now(self.hawaii_tz)
            is_active = hawaii_time.hour >= self.trading_start_hour
            
            # Log state change
            if is_active != self.activity['trading_started']:
                if is_active:
                    self.activity['trading_started'] = True
                    self.activity['start_time'] = hawaii_time.isoformat()
                    self.log_event("TRADING_STARTED", f"Autonomous trading activated at {hawaii_time.strftime('%H:%M:%S')}")
                else:
                    self.activity['trading_started'] = False
                    self.log_event("TRADING_STOPPED", f"Autonomous trading deactivated")
                self.save_activity()
            
            return is_active
        except Exception as e:
            logger.error(f"Error checking trading status: {e}")
            return False
    
    def should_place_trade(self) -> bool:
        """Check if we should place a new trade"""
        try:
            # Check max trades per day
            if self.activity['total_trades'] >= self.config['max_positions']:
                logger.warning(f"⚠️ Max trades ({self.config['max_positions']}) reached today")
                return False
            
            # Check minimum interval between trades
            if self.activity['trades']:
                last_trade = self.activity['trades'][-1]
                last_trade_time = datetime.fromisoformat(last_trade['timestamp'])
                time_since_last = (datetime.now(self.hawaii_tz) - last_trade_time).total_seconds()
                
                if time_since_last < self.min_trade_interval:
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking trade placement: {e}")
            return False
    
    def log_trade(self, symbol: str, action: str, price: float, shares: int, 
                  confidence: int, signal_reason: str, order_id: Optional[str] = None):
        """Log a trade execution"""
        try:
            trade = {
                'timestamp': datetime.now(self.hawaii_tz).isoformat(),
                'symbol': symbol,
                'action': action,  # BUY or SELL
                'price': price,
                'shares': shares,
                'confidence': confidence,
                'reason': signal_reason,
                'order_id': order_id,
                'status': 'EXECUTED'
            }
            
            self.activity['trades'].append(trade)
            self.activity['total_trades'] += 1
            
            self.save_activity()
            self.log_event("TRADE_EXECUTED", 
                          f"{action} {shares} {symbol} @ ${price:.2f} ({confidence}% confidence)")
            
            logger.info(f"✅ Trade logged: {action} {shares} {symbol} @ ${price:.2f}")
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
    
    def log_event(self, event_type: str, message: str):
        """Log an autonomous trading event"""
        try:
            event = {
                'timestamp': datetime.now(self.hawaii_tz).isoformat(),
                'type': event_type,
                'message': message
            }
            
            if 'events' not in self.activity:
                self.activity['events'] = []
            
            self.activity['events'].append(event)
            
            # Keep only last 100 events
            if len(self.activity['events']) > 100:
                self.activity['events'] = self.activity['events'][-100:]
            
            self.save_activity()
            logger.info(f"📝 {event_type}: {message}")
        except Exception as e:
            logger.error(f"Error logging event: {e}")
    
    def execute_trade(self, symbol: str, signal_type: str, current_price: float, 
                     confidence: int, reason: str) -> Dict:
        """
        Execute a trade via the broker
        
        Args:
            symbol: Stock symbol
            signal_type: 'BUY' or 'SELL'
            current_price: Current stock price
            confidence: Signal confidence (0-100)
            reason: Why this trade was triggered
        
        Returns:
            Trade execution result dict
        """
        if not self.broker or not self.broker.connected:
            return {'status': 'ERROR', 'message': 'Broker not connected'}
        
        if not self.is_trading_active():
            return {'status': 'ERROR', 'message': 'Not during trading hours'}
        
        if not self.should_place_trade():
            return {'status': 'ERROR', 'message': 'Trade limit reached or too soon'}
        
        try:
            # Calculate position size (1% of account per trade)
            account = self.broker.get_account()
            portfolio_value = account.get('portfolio_value', 50000)
            position_value = portfolio_value * 0.01  # 1% risk per trade
            shares = int(position_value / current_price)
            
            if shares < 1:
                return {'status': 'ERROR', 'message': f'Position too small ({shares} shares)'}
            
            # Place order
            order_result = self.broker.place_order(
                symbol=symbol,
                qty=shares,
                side=signal_type.lower(),
                order_type='market'
            )
            
            if order_result.get('status') == 'ERROR':
                self.log_event('TRADE_FAILED', f"{signal_type} {shares} {symbol}: {order_result.get('message')}")
                return order_result
            
            # Log successful trade
            self.log_trade(
                symbol=symbol,
                action=signal_type,
                price=current_price,
                shares=shares,
                confidence=confidence,
                signal_reason=reason,
                order_id=order_result.get('order_id')
            )
            
            return {
                'status': 'SUCCESS',
                'order_id': order_result.get('order_id'),
                'symbol': symbol,
                'action': signal_type,
                'shares': shares,
                'price': current_price,
                'confidence': confidence
            }
        
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            self.log_event('TRADE_ERROR', f"{signal_type} {symbol}: {str(e)}")
            return {'status': 'ERROR', 'message': str(e)}
    
    def get_status(self) -> Dict:
        """Get current autonomous trading status"""
        hawaii_time = datetime.now(self.hawaii_tz)
        is_active = self.is_trading_active()
        
        return {
            'hawaii_time': hawaii_time.isoformat(),
            'trading_active': is_active,
            'trades_today': self.activity['total_trades'],
            'max_daily_trades': self.config['max_positions'],
            'recent_trades': self.activity['trades'][-5:] if self.activity['trades'] else [],
            'total_pnl': self.activity['total_pnl'],
            'config': self.config
        }


# Global instance
_scheduler = None

def get_autonomous_scheduler(broker=None) -> AutonomousTraderScheduler:
    """Get or create the autonomous trading scheduler"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutonomousTraderScheduler(broker=broker)
    return _scheduler
