"""
Stop Loss Management Module
Enforces tight stop losses for autonomous trader protection
Prevents catastrophic losses when trader is offline
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class StopLossStrategy(Enum):
    """Stop loss strategies"""
    FIXED_PERCENT = "fixed_percent"           # Fixed % below entry
    ATR_BASED = "atr_based"                   # Based on ATR volatility
    TRAILING = "trailing"                     # Trailing stop
    SUPPORT_LEVEL = "support_level"           # Based on technical support
    VOLATILITY_ADJUSTED = "volatility_adjusted"  # Based on market volatility


@dataclass
class StopLossConfig:
    """Configuration for stop loss management"""
    strategy: StopLossStrategy = StopLossStrategy.FIXED_PERCENT
    default_percent: float = 2.0               # Default 2% stop loss
    max_percent: float = 5.0                   # Maximum allowed stop loss
    min_percent: float = 0.5                   # Minimum allowed stop loss
    use_trailing: bool = True                  # Use trailing stops
    trailing_percent: float = 1.5              # How much to trail
    enforce_hard_stops: bool = True            # Forcefully exit at stop
    alert_on_breach: bool = True               # Alert before exiting
    emergency_stop_loss: float = 3.0           # Emergency stop if offline
    default_take_profit_percent: float = 3.0   # Bank winners
    atr_multiplier: float = 1.5                # For ATR_BASED strategy


@dataclass
class Position:
    """Open position tracking"""
    symbol: str
    entry_price: float
    entry_time: datetime
    quantity: int
    stop_loss_price: float
    stop_loss_percent: float
    initial_stop_loss: float
    trailing_high: Optional[float] = None
    trailing_stop: Optional[float] = None
    take_profit_price: Optional[float] = None
    take_profit_percent: Optional[float] = None
    broker_stop_order_id: Optional[str] = None
    status: str = "open"  # open, stopped_out, take_profit, closed
    
    def get_current_loss_percent(self, current_price: float) -> float:
        """Calculate current loss percentage"""
        if self.entry_price == 0:
            return 0.0
        return ((current_price - self.entry_price) / self.entry_price) * 100

    def effective_stop(self) -> float:
        """Tightest long stop: never looser than the initial hard stop."""
        stops = [self.stop_loss_price, self.initial_stop_loss]
        if self.trailing_stop is not None:
            stops.append(self.trailing_stop)
        return max(s for s in stops if s is not None)
    
    def is_stop_triggered(self, current_price: float) -> bool:
        """Check if stop loss is triggered"""
        return current_price <= self.effective_stop()

    def is_take_profit_triggered(self, current_price: float) -> bool:
        """Check if take profit is hit"""
        if self.take_profit_price is None:
            return False
        return current_price >= self.take_profit_price
    
    def update_trailing_stop(self, current_price: float, trailing_percent: float):
        """Ratchet trailing stop up only; never below initial hard stop."""
        if self.trailing_high is None or current_price > self.trailing_high:
            self.trailing_high = current_price
            candidate = current_price * (1 - trailing_percent / 100)
            # Never loosen protection below the original stop
            floor = max(self.initial_stop_loss, self.stop_loss_price)
            self.trailing_stop = max(candidate, floor)


class StopLossManager:
    """
    Manages stop loss enforcement for autonomous trader
    Ensures protection even when trader is offline
    """
    
    def __init__(self, config: Optional[StopLossConfig] = None):
        """
        Initialize stop loss manager
        
        Args:
            config: StopLossConfig with settings
        """
        self.config = config or StopLossConfig()
        self.positions: Dict[str, Position] = {}
        self.stopped_out_positions: List[Position] = []
        self.alerts: List[Dict[str, Any]] = []
    
    def open_position(
        self,
        symbol: str,
        entry_price: float,
        quantity: int,
        stop_loss_percent: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_percent: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> Position:
        """
        Open a new position with stop loss + take profit protection
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price
            quantity: Number of shares
            stop_loss_percent: Stop loss as percentage (override default)
            stop_loss_price: Explicit stop loss price (overrides percent)
            take_profit_percent: Take profit as percentage
            take_profit_price: Explicit take profit price
            atr: Optional ATR for ATR_BASED strategy
            
        Returns:
            Position object
        """
        
        # Determine stop loss level
        if stop_loss_price:
            sl_price = stop_loss_price
            sl_percent = abs((sl_price - entry_price) / entry_price) * 100 if entry_price else 0
        elif self.config.strategy == StopLossStrategy.ATR_BASED and atr and atr > 0 and entry_price > 0:
            sl_price = entry_price - (atr * self.config.atr_multiplier)
            sl_percent = abs((sl_price - entry_price) / entry_price) * 100
            sl_percent = max(self.config.min_percent, min(sl_percent, self.config.max_percent))
            sl_price = entry_price * (1 - sl_percent / 100)
        else:
            sl_percent = stop_loss_percent or self.config.default_percent
            # Enforce min/max constraints
            sl_percent = max(self.config.min_percent, min(sl_percent, self.config.max_percent))
            sl_price = entry_price * (1 - sl_percent / 100)

        if take_profit_price is not None:
            tp_price = take_profit_price
            tp_percent = abs((tp_price - entry_price) / entry_price) * 100 if entry_price else None
        else:
            tp_percent = take_profit_percent if take_profit_percent is not None else self.config.default_take_profit_percent
            tp_price = entry_price * (1 + tp_percent / 100) if tp_percent else None
        
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            entry_time=datetime.utcnow(),
            quantity=quantity,
            stop_loss_price=sl_price,
            stop_loss_percent=sl_percent,
            initial_stop_loss=sl_price,
            take_profit_price=tp_price,
            take_profit_percent=tp_percent,
        )
        
        self.positions[symbol] = position
        
        tp_str = f", TP={tp_price:.2f}" if tp_price else ""
        logger.info(
            f"Opened {symbol} position: Entry={entry_price:.2f}, "
            f"Stop Loss={sl_price:.2f} ({sl_percent:.2f}%){tp_str}"
        )
        
        return position
    
    def update_position(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Update position with current price and check for stop loss / take profit
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            
        Returns:
            Tuple of (should_exit, message)
        """
        
        if symbol not in self.positions:
            return False, None
        
        position = self.positions[symbol]
        
        # Emergency hard stop (offline / gap protection)
        if self.config.enforce_hard_stops and position.entry_price > 0:
            emergency_price = position.entry_price * (1 - self.config.emergency_stop_loss / 100)
            if current_price <= emergency_price:
                return self._trigger_stop_loss(position, current_price, reason="EMERGENCY_STOP")

        # Update trailing stop if enabled — only ratchet after price is at/above entry
        if self.config.use_trailing:
            if current_price >= position.entry_price:
                if position.trailing_high is None:
                    position.trailing_high = current_price
                    candidate = current_price * (1 - self.config.trailing_percent / 100)
                    position.trailing_stop = max(candidate, position.initial_stop_loss)
                else:
                    position.update_trailing_stop(current_price, self.config.trailing_percent)
        
        # Take profit first (bank the gain)
        if position.is_take_profit_triggered(current_price):
            return self._trigger_take_profit(position, current_price)

        # Check if stop loss triggered
        if position.is_stop_triggered(current_price):
            return self._trigger_stop_loss(position, current_price)
        
        # Check for alert threshold (80% of stop loss)
        loss_percent = position.get_current_loss_percent(current_price)
        alert_threshold = position.stop_loss_percent * 0.8
        
        if loss_percent < -alert_threshold and self.config.alert_on_breach:
            self._create_alert(position, current_price, loss_percent)
        
        return False, None
    
    def _trigger_stop_loss(
        self,
        position: Position,
        exit_price: float,
        reason: str = "STOP_LOSS",
    ) -> Tuple[bool, str]:
        """Trigger stop loss exit — caller must place the broker sell."""
        
        position.status = "stopped_out"
        pnl = (exit_price - position.entry_price) * position.quantity
        loss_percent = position.get_current_loss_percent(exit_price)
        
        message = (
            f"🛑 {reason} TRIGGERED for {position.symbol}\n"
            f"Entry: ${position.entry_price:.2f}\n"
            f"Exit: ${exit_price:.2f}\n"
            f"Loss: {loss_percent:.2f}% (${pnl:.2f})"
        )
        
        self.stopped_out_positions.append(position)
        del self.positions[position.symbol]
        
        logger.warning(message)
        
        return True, message

    def _trigger_take_profit(
        self,
        position: Position,
        exit_price: float,
    ) -> Tuple[bool, str]:
        """Trigger take profit exit — caller must place the broker sell."""
        position.status = "take_profit"
        pnl = (exit_price - position.entry_price) * position.quantity
        pnl_percent = position.get_current_loss_percent(exit_price)
        message = (
            f"🎯 TAKE PROFIT for {position.symbol}\n"
            f"Entry: ${position.entry_price:.2f}\n"
            f"Exit: ${exit_price:.2f}\n"
            f"Gain: {pnl_percent:.2f}% (${pnl:.2f})"
        )
        self.stopped_out_positions.append(position)
        del self.positions[position.symbol]
        logger.info(message)
        return True, message
    
    def _create_alert(
        self,
        position: Position,
        current_price: float,
        loss_percent: float
    ):
        """Create stop loss warning alert"""
        
        alert = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": position.symbol,
            "type": "stop_loss_warning",
            "current_price": current_price,
            "loss_percent": loss_percent,
            "distance_to_stop": position.stop_loss_price - current_price,
            "message": f"⚠️ {position.symbol} within 20% of stop loss! "
                      f"Loss: {loss_percent:.2f}%, Price: ${current_price:.2f}"
        }
        
        self.alerts.append(alert)
        logger.warning(alert["message"])
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "manual"
    ) -> Optional[Dict[str, Any]]:
        """
        Close a position
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            reason: Reason for closing
            
        Returns:
            Close details dict
        """
        
        if symbol not in self.positions:
            logger.warning(f"Position {symbol} not found")
            return None
        
        position = self.positions[symbol]
        pnl = (exit_price - position.entry_price) * position.quantity
        pnl_percent = position.get_current_loss_percent(exit_price)
        
        close_detail = {
            "symbol": symbol,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "quantity": position.quantity,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "reason": reason,
            "hold_time_minutes": (
                (datetime.utcnow() - position.entry_time).total_seconds() / 60
            )
        }
        
        position.status = "closed"
        del self.positions[symbol]
        
        logger.info(f"Closed {symbol}: P&L ${pnl:.2f} ({pnl_percent:.2f}%)")
        
        return close_detail
    
    def adjust_stop_loss(
        self,
        symbol: str,
        new_stop_loss_percent: Optional[float] = None,
        new_stop_loss_price: Optional[float] = None
    ) -> bool:
        """
        Adjust stop loss for open position
        
        Args:
            symbol: Stock symbol
            new_stop_loss_percent: New stop loss percent
            new_stop_loss_price: New stop loss price
            
        Returns:
            Success boolean
        """
        
        if symbol not in self.positions:
            logger.warning(f"Position {symbol} not found")
            return False
        
        position = self.positions[symbol]
        
        if new_stop_loss_price:
            new_sl_pct = abs((new_stop_loss_price - position.entry_price) / position.entry_price) * 100
            if new_sl_pct > self.config.max_percent:
                logger.warning(f"Stop loss {new_sl_pct:.2f}% exceeds max of {self.config.max_percent}%")
                return False
            
            position.stop_loss_price = new_stop_loss_price
            position.stop_loss_percent = new_sl_pct
        
        elif new_stop_loss_percent:
            if new_stop_loss_percent > self.config.max_percent:
                logger.warning(f"Stop loss {new_stop_loss_percent:.2f}% exceeds max of {self.config.max_percent}%")
                return False
            
            position.stop_loss_percent = new_stop_loss_percent
            position.stop_loss_price = position.entry_price * (1 - new_stop_loss_percent / 100)
        
        logger.info(f"Adjusted {symbol} stop loss to {position.stop_loss_percent:.2f}%")
        return True
    
    def get_position_status(self, symbol: str) -> Optional[Dict]:
        """Get current position status"""
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        
        return {
            "symbol": symbol,
            "entry_price": position.entry_price,
            "stop_loss_price": position.stop_loss_price,
            "stop_loss_percent": position.stop_loss_percent,
            "take_profit_price": position.take_profit_price,
            "take_profit_percent": position.take_profit_percent,
            "quantity": position.quantity,
            "entry_time": position.entry_time.isoformat(),
            "trailing_stop": position.trailing_stop,
            "effective_stop": position.effective_stop(),
            "broker_stop_order_id": position.broker_stop_order_id,
            "status": position.status
        }
    
    def get_all_positions(self) -> Dict[str, Dict]:
        """Get all open positions"""
        return {
            symbol: self.get_position_status(symbol)
            for symbol in self.positions.keys()
        }
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """Get overall risk summary"""
        
        positions = list(self.positions.values())
        
        if not positions:
            return {
                "open_positions": 0,
                "total_risk": 0.0,
                "max_position_risk": 0.0,
                "average_stop_loss": 0.0
            }
        
        total_risk = sum(p.stop_loss_percent * p.quantity for p in positions)
        position_risks = [p.stop_loss_percent for p in positions]
        
        return {
            "open_positions": len(positions),
            "total_risk": float(total_risk),
            "max_position_risk": float(max(position_risks)),
            "average_stop_loss": float(sum(position_risks) / len(position_risks)),
            "positions": [self.get_position_status(p.symbol) for p in positions]
        }
    
    def get_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent alerts"""
        return self.alerts[-limit:]


# Singleton instance
_stop_loss_manager = None


def get_stop_loss_manager() -> StopLossManager:
    """Get or create singleton stop loss manager"""
    global _stop_loss_manager
    if _stop_loss_manager is None:
        _stop_loss_manager = StopLossManager()
    return _stop_loss_manager


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Stop Loss Manager...\n")
    
    # Initialize manager
    config = StopLossConfig(
        default_percent=2.0,
        use_trailing=True,
        emergency_stop_loss=3.0
    )
    
    manager = StopLossManager(config)
    
    # Open position
    pos = manager.open_position("AAPL", entry_price=150.0, quantity=100)
    print(f"Opened position: {pos.symbol}")
    
    # Simulate price updates
    print("\nSimulating price updates...")
    
    is_stopped, msg = manager.update_position("AAPL", 149.0)
    print(f"Price $149: Stopped={is_stopped}")
    
    is_stopped, msg = manager.update_position("AAPL", 148.5)
    print(f"Price $148.5: Stopped={is_stopped}")
    
    is_stopped, msg = manager.update_position("AAPL", 147.0)
    if is_stopped:
        print(f"Price $147.0: {msg}")
    
    # Get risk summary
    print("\nRisk Summary:")
    import json
    print(json.dumps(manager.get_risk_summary(), indent=2))
