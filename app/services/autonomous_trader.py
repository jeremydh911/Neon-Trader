"""
Autonomous Trader with Memory Integration and Council Approval
Makes trading decisions informed by past experience and council voting
Includes strict stop loss enforcement for capital protection
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import random

from .stop_loss_manager import (
    StopLossManager, 
    StopLossConfig, 
    StopLossStrategy
)

logger = logging.getLogger(__name__)

class AutonomousTrader:
    """Autonomous trader that learns and remembers past trades, with council approval and full broker access"""
    
    def __init__(self, memory_service, llm_service=None, council=None, broker_type: str = 'etrade', use_sandbox: bool = True):
        self.memory = memory_service
        self.llm = llm_service
        self.council = council
        self.trading_enabled = False
        self.require_council_approval = True
        self.broker_type = broker_type
        self.use_sandbox = use_sandbox
        self.broker = None
        
        # Initialize broker connection
        self._init_broker()
        
        # Initialize stop loss manager with tight defaults
        sl_config = StopLossConfig(
            strategy=StopLossStrategy.FIXED_PERCENT,
            default_percent=2.0,          # Default 2% stop loss
            max_percent=5.0,              # Never allow > 5% loss
            min_percent=0.5,              # Minimum 0.5% stop loss
            use_trailing=True,            # Enable trailing stops
            trailing_percent=1.5,         # Trailing distance
            enforce_hard_stops=True,      # Always enforce stops
            alert_on_breach=True,         # Alert at 80% threshold
            emergency_stop_loss=3.0       # 3% emergency stop if offline
        )
        self.stop_loss_manager = StopLossManager(sl_config)
        
        self.risk_config = {
            "max_position_size": 0.05,
            "max_daily_loss": 0.02,
            "min_win_rate": 0.50,
            "take_profit_pct": 2.0,
            "stop_loss_pct": 2.0,  # Updated to 2% minimum
            "use_stop_loss_manager": True  # Always use stop loss manager
        }
        
        logger.info(f"✅ Autonomous Trader initialized with tight stop loss protection (2% default)")
        logger.info(f"🔗 Broker: {broker_type.upper()} ({'SANDBOX' if use_sandbox else 'LIVE'})")
    
    def _init_broker(self):
        """Initialize broker connection"""
        try:
            from .broker import get_broker
            self.broker = get_broker(broker_type=self.broker_type, use_sandbox=self.use_sandbox)
            if self.broker.connect():
                logger.info(f"✅ {self.broker_type.upper()} broker connected successfully")
            else:
                logger.warning(f"⚠️ Failed to connect {self.broker_type.upper()} broker")
                self.broker = None
        except Exception as e:
            logger.error(f"❌ Error initializing broker: {e}")
            self.broker = None
    
    def enable_autonomous_trading(self, enable: bool = True) -> None:
        """Enable/disable autonomous trading"""
        self.trading_enabled = enable
        logger.info(f"Autonomous trading {'enabled' if enable else 'disabled'}")
    
    def open_position_with_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        quantity: int,
        stop_loss_percent: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Open a new position with automatic stop loss protection
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price
            quantity: Number of shares
            stop_loss_percent: Stop loss percent (uses default 2% if None)
            
        Returns:
            Position details with stop loss
        """
        
        sl_pct = stop_loss_percent or self.risk_config["stop_loss_pct"]
        
        # Open position with stop loss manager
        position = self.stop_loss_manager.open_position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss_percent=sl_pct
        )
        
        logger.info(
            f"🟢 Position opened with stop loss: {symbol} "
            f"Entry=${entry_price:.2f}, Stop=${position.stop_loss_price:.2f} "
            f"({sl_pct:.1f}%)"
        )
        
        return self.stop_loss_manager.get_position_status(symbol)
    
    def update_position_price(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Update position with current price, check for stop loss trigger
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            
        Returns:
            Tuple of (is_stopped_out, message)
        """
        
        is_stopped, message = self.stop_loss_manager.update_position(
            symbol=symbol,
            current_price=current_price
        )
        
        if is_stopped:
            logger.warning(f"🛑 Stop loss triggered for {symbol}")
            self.record_completed_trade(
                symbol=symbol,
                entry_price=0,  # Will get from position
                exit_price=current_price,
                quantity=0,  # Will get from position
                reason="STOP_LOSS_TRIGGERED"
            )
        
        return is_stopped, message
    
    def close_position_manually(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "manual"
    ) -> Optional[Dict[str, Any]]:
        """
        Close a position manually
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            reason: Reason for closing
            
        Returns:
            Close details
        """
        
        return self.stop_loss_manager.close_position(
            symbol=symbol,
            exit_price=exit_price,
            reason=reason
        )
    
    def get_positions_status(self) -> Dict[str, Any]:
        """Get all open positions with stop loss levels"""
        return self.stop_loss_manager.get_all_positions()
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """Get overall risk summary including stop losses"""
        return self.stop_loss_manager.get_risk_summary()
    
    def set_risk_parameters(self, params: Dict[str, float]) -> None:
        """Update risk management parameters"""
        self.risk_config.update(params)
        logger.info(f"Risk parameters updated: {params}")
    
    def set_council(self, council) -> None:
        """Set the trading council for trade approval"""
        self.council = council
        logger.info("Trading council assigned to autonomous trader")

    def consult_council(self, symbol: str, action: str, price: float, quantity: int) -> dict:
        """Convenience wrapper used by BackgroundTrader to get a council decision dict."""
        try:
            if self.council and hasattr(self.council, 'discuss_trade'):
                decision, approved = self.council.discuss_trade(
                    symbol=symbol,
                    action=action,
                    current_price=price,
                    indicators={},
                    available_capital=0.0,
                    market_sentiment="neutral"
                )
                if decision:
                    return {
                        "approval_percentage": getattr(decision, 'approval_percentage', 100.0),
                        "final_confidence": getattr(decision, 'final_confidence', 1.0),
                        "approved": approved
                    }
            # Default to auto-approve when no council is set (useful in sandbox/tests)
            return {"approval_percentage": 100.0, "final_confidence": 1.0, "approved": True}
        except Exception as e:
            logger.warning(f"⚠️ consult_council error: {e}")
            return {"approval_percentage": 0.0, "final_confidence": 0.0, "approved": False}

    def execute_order(self, symbol: str, action: str, qty: int, price: float = None, price_type: str = "MARKET", account_id: str | None = None) -> dict:
        """Execute an order via the configured broker. Returns an order result dict."""
        try:
            side = 'buy' if action.upper() in ('BUY', 'OPEN') else 'sell'
            if not self.broker:
                logger.warning("⚠️ No broker configured - cannot execute order")
                return {"status": "FAILED", "reason": "no_broker"}

            # Broker API: place_order(symbol, qty, side, order_type)
            result = self.broker.place_order(symbol=symbol, qty=qty, side=side, order_type=(price_type or "market"))
            if result and isinstance(result, dict):
                # Normalize success response
                if result.get('status') in ('filled', 'filled_partial', 'success', 'SUCCESS') or result.get('status') == 'FILLED':
                    return {"status": "SUCCESS", "order_id": result.get('order_id', result.get('id', None)), "raw": result}
                # For mock broker, interpret 'status' key or fallback
                if result.get('status') == 'filled':
                    return {"status": "SUCCESS", "order_id": result.get('order_id'), "raw": result}
                # Otherwise return as-is
                return {"status": result.get('status', 'UNKNOWN'), "raw": result}

            return {"status": "FAILED", "reason": "unexpected_broker_response", "raw": result}
        except Exception as e:
            logger.error(f"❌ execute_order error: {e}")
            return {"status": "FAILED", "reason": str(e)}
    
    def make_trading_decision(
        self, 
        symbol: str,
        current_price: float,
        indicators: Dict[str, Any],
        market_sentiment: str = "neutral",
        available_capital: float = 10000.0
    ) -> Dict[str, Any]:
        """Make an informed trading decision using memory and council approval"""
        
        try:
            # Recall similar past trades
            similar_trades = self.memory.recall_similar_trades(query=symbol, symbol=symbol, k=5)
            
            # Get profitable patterns for this symbol
            patterns = self.memory.get_profitable_patterns(symbol=symbol, min_trades=2)
            
            # Get relevant lessons
            lessons = self.memory.get_lessons_by_category("pattern") + \
                     self.memory.get_lessons_by_category("risk")
            
            # Build context from memory
            memory_context = self._build_memory_context(similar_trades, patterns, lessons)
            
            # Determine initial action and confidence
            action, confidence = self._determine_action(
                symbol=symbol,
                indicators=indicators,
                market_sentiment=market_sentiment,
                similar_trades=similar_trades,
                patterns=patterns,
                lessons=lessons
            )
            
            # Build reasoning
            reasoning = self._build_reasoning(
                symbol=symbol,
                action=action,
                indicators=indicators,
                memory_context=memory_context
            )
            
            # Check risk limits
            if not self._passes_risk_check(symbol, action, available_capital):
                action = "HOLD"
                confidence = 0.1
                reasoning += " [Risk limits exceeded]"
            
            # COUNCIL APPROVAL - Submit trade to council for vote
            council_approved = True
            council_decision = None
            
            if self.require_council_approval and self.council and action != "HOLD":
                logger.info(f"\n📋 Submitting {symbol} {action} to trading council for approval...")
                council_decision, council_approved = self.council.discuss_trade(
                    symbol=symbol,
                    action=action,
                    current_price=current_price,
                    indicators=indicators,
                    available_capital=available_capital,
                    market_sentiment=market_sentiment
                )
                
                # Update reasoning with council decision
                if council_decision:
                    reasoning += f"\n[Council Decision: {council_decision.approval_percentage:.0f}% approval, "
                    reasoning += f"Confidence: {council_decision.final_confidence:.1%}]"
                    
                    # If council rejected, downgrade to HOLD
                    if not council_approved:
                        action = "HOLD"
                        confidence = 0
                        logger.warning(f"⛔ Council rejected {symbol} {action} trade")
                    else:
                        logger.info(f"✅ Council approved {symbol} {action} trade")
            
            decision = {
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "price": current_price,
                "reasoning": reasoning,
                "indicators": indicators,
                "market_sentiment": market_sentiment,
                "recalled_similar": len(similar_trades),
                "timestamp": datetime.utcnow().isoformat(),
                "position_size": self._calculate_position_size(current_price, available_capital, confidence) if action != "HOLD" else 0,
                "council_approved": council_approved,
                "council_decision": council_decision.to_dict() if council_decision else None,
                # Stop loss information
                "stop_loss_percent": self.risk_config["stop_loss_pct"],
                "stop_loss_note": f"Automatic stop loss: {self.risk_config['stop_loss_pct']:.1f}% below entry (always active)"
            }
            
            # Store decision in memory
            self.memory.store_decision_memory(decision)
            
            logger.info(f"Decision made: {symbol} -> {action} (confidence: {confidence:.2f}, council: {council_approved})")
            return decision
        except Exception as e:
            logger.error(f"Error making trading decision: {e}")
            return {
                "symbol": symbol,
                "action": "HOLD",
                "confidence": 0.0,
                "reasoning": f"Error in decision making: {str(e)}",
                "council_approved": False
            }
    
    def _build_memory_context(
        self, 
        similar_trades: list, 
        patterns: list, 
        lessons: list
    ) -> str:
        """Build context from memory for decision making"""
        context = ""
        
        if similar_trades:
            successful = sum(1 for t in similar_trades if t.get("success", False))
            context += f"Similar trades: {len(similar_trades)} ({successful} profitable). "
        
        if patterns:
            avg_profit = sum(p.get("profit_loss_pct", 0) for p in patterns) / len(patterns)
            context += f"Profitable patterns show avg {avg_profit:.2f}% return. "
        
        if lessons:
            context += f"Based on {len(lessons)} learned lessons. "
        
        return context
    
    def _determine_action(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        market_sentiment: str,
        similar_trades: list,
        patterns: list,
        lessons: list
    ) -> Tuple[str, float]:
        """Determine trading action using indicators and memory"""
        
        confidence = 0.5
        action = "HOLD"
        
        # Check indicators
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        atr = indicators.get("atr", 0)
        
        # Simple logic: oversold = BUY, overbought = SELL
        if rsi < 30 and macd > 0:
            action = "BUY"
            confidence = 0.7
        elif rsi > 70 and macd < 0:
            action = "SELL"
            confidence = 0.6
        
        # Boost confidence if supported by memory
        if action == "BUY":
            successful_buys = sum(1 for t in similar_trades if t.get("action", "") == "BUY" and t.get("success", False))
            if successful_buys > 0:
                confidence = min(0.95, confidence + 0.15)
        
        # Consider market sentiment
        if market_sentiment == "bullish" and action == "BUY":
            confidence += 0.1
        elif market_sentiment == "bearish" and action == "SELL":
            confidence += 0.1
        
        confidence = min(0.99, max(0.01, confidence))
        return action, confidence
    
    def _build_reasoning(
        self,
        symbol: str,
        action: str,
        indicators: Dict[str, Any],
        memory_context: str
    ) -> str:
        """Build decision reasoning message"""
        
        reason = f"Trading {symbol}: {action}. "
        
        if indicators.get("rsi"):
            reason += f"RSI={indicators['rsi']:.1f}. "
        
        if memory_context:
            reason += memory_context
        
        return reason
    
    def _passes_risk_check(self, symbol: str, action: str, available_capital: float) -> bool:
        """Check if trade passes risk management criteria"""
        
        if action == "HOLD":
            return True
        
        # Get symbol stats
        stats = self.memory.get_trading_stats_by_symbol(symbol)
        
        # Check minimum win rate
        win_rate = stats.get("win_rate", 0)
        if win_rate > 0 and win_rate < self.risk_config["min_win_rate"] * 100:
            logger.warning(f"Trade blocked: {symbol} win rate {win_rate:.1f}% below minimum")
            return False
        
        # Check position size vs available capital
        if available_capital < self.risk_config["max_position_size"] * 1000:
            logger.warning("Trade blocked: insufficient capital")
            return False
        
        return True
    
    def _calculate_position_size(self, price: float, capital: float, confidence: float) -> float:
        """Calculate position size based on confidence and capital"""
        max_position = capital * self.risk_config["max_position_size"]
        position_size = max_position * confidence
        return int(position_size / price)
    
    def record_completed_trade(
        self, 
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: int,
        reason: str = "",
        indicators: Dict[str, Any] = None
    ) -> bool:
        """Record completed trade and extract lessons"""
        
        try:
            profit_loss = (exit_price - entry_price) * quantity
            profit_loss_pct = ((exit_price - entry_price) / entry_price) * 100
            
            trade_data = {
                "symbol": symbol,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": quantity,
                "profit_loss": profit_loss,
                "profit_loss_pct": profit_loss_pct,
                "reason": reason,
                "indicators": indicators or {},
                "market_condition": self._assess_market_condition(indicators or {})
            }
            
            success = self.memory.store_trade_memory(trade_data)
            
            if success and profit_loss_pct != 0:
                self._extract_lessons(symbol, trade_data)
            
            return success
        except Exception as e:
            logger.error(f"Error recording trade: {e}")
            return False
    
    def _assess_market_condition(self, indicators: Dict[str, Any]) -> str:
        """Assess market condition from indicators"""
        rsi = indicators.get("rsi", 50)
        
        if rsi < 30:
            return "oversold"
        elif rsi > 70:
            return "overbought"
        else:
            return "neutral"
    
    def _extract_lessons(self, symbol: str, trade_data: Dict[str, Any]) -> None:
        """Extract learned lessons from completed trade"""
        
        try:
            profit_loss_pct = trade_data.get("profit_loss_pct", 0)
            
            if profit_loss_pct > 2.0:
                lesson = {
                    "category": "pattern",
                    "lesson": f"Strong {trade_data['market_condition']} pattern on {symbol} yielded {profit_loss_pct:.2f}% profit",
                    "impact": "positive",
                    "confidence": 0.8,
                    "examples": [symbol]
                }
                self.memory.store_lesson(lesson)
            
            elif profit_loss_pct < -1.5:
                lesson = {
                    "category": "risk",
                    "lesson": f"Avoid {trade_data['market_condition']} trades on {symbol} - {profit_loss_pct:.2f}% loss",
                    "impact": "negative",
                    "confidence": 0.7,
                    "examples": [symbol]
                }
                self.memory.store_lesson(lesson)
        except Exception as e:
            logger.debug(f"Error extracting lessons: {e}")
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get trader's memory summary"""
        stats = self.memory.get_memory_stats()
        return {
            "trading_enabled": self.trading_enabled,
            "memory": stats,
            "risk_config": self.risk_config,
            "status": "active" if self.trading_enabled else "inactive"
        }
    
    # ============================================================================
    # BROKER TRADING TOOLS - Full Access to Execute Trades
    # ============================================================================
    
    def execute_trade(self, symbol: str, qty: int, side: str, order_type: str = "market", 
                     limit_price: float = None, stop_price: float = None) -> Dict[str, Any]:
        """
        Execute a trade directly on the broker
        
        Args:
            symbol: Stock symbol
            qty: Quantity of shares
            side: 'BUY' or 'SELL'
            order_type: 'market', 'limit', or 'stop'
            limit_price: Price for limit orders
            stop_price: Price for stop orders
            
        Returns:
            Trade execution result
        """
        if not self.broker:
            logger.error("❌ Broker not connected")
            return {
                "status": "error",
                "message": "Broker connection not available",
                "symbol": symbol
            }
        
        if not self.trading_enabled:
            logger.warning(f"⚠️ Autonomous trading disabled for {symbol} {side}")
            return {
                "status": "error",
                "message": "Autonomous trading is disabled",
                "symbol": symbol
            }
        
        try:
            logger.info(f"📤 Executing {side} order for {qty} {symbol} @ {order_type}")
            
            # Place order on broker
            result = self.broker.place_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price
            )
            
            if result.get('status') == 'ERROR' or result.get('status') == 'error':
                logger.error(f"❌ Order failed: {result.get('message', 'Unknown error')}")
                return result
            
            # Log successful execution
            logger.info(f"✅ Order executed: {result}")
            
            return {
                "status": "success",
                "order": result,
                "executed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}")
            return {
                "status": "error",
                "message": str(e),
                "symbol": symbol
            }
    
    def buy(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        """Buy shares - Direct broker access"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side="BUY",
            order_type="limit" if limit_price else "market",
            limit_price=limit_price
        )
    
    def sell(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        """Sell shares - Direct broker access"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side="SELL",
            order_type="limit" if limit_price else "market",
            limit_price=limit_price
        )
    
    def sell_short(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        """Short sell shares - Direct broker access"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side="SELL",
            order_type="limit" if limit_price else "market",
            limit_price=limit_price
        )
    
    def buy_to_cover(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        """Buy to cover short position - Direct broker access"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side="BUY",
            order_type="limit" if limit_price else "market",
            limit_price=limit_price
        )
    
    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Dict[str, Any]:
        """Place a limit order"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="limit",
            limit_price=limit_price
        )
    
    def place_stop_order(self, symbol: str, qty: int, side: str, stop_price: float) -> Dict[str, Any]:
        """Place a stop order"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="stop",
            stop_price=stop_price
        )
    
    def place_stop_limit_order(self, symbol: str, qty: int, side: str, 
                               stop_price: float, limit_price: float) -> Dict[str, Any]:
        """Place a stop-limit order"""
        return self.execute_trade(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="stop_limit",
            stop_price=stop_price,
            limit_price=limit_price
        )
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information from broker"""
        if not self.broker:
            return {"error": "Broker not connected"}
        
        try:
            account_info = self.broker.get_account()
            logger.info(f"📊 Account Info: {account_info}")
            return account_info
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {"error": str(e)}
    
    def get_positions(self) -> Dict[str, Any]:
        """Get all open positions from broker"""
        if not self.broker:
            return {"error": "Broker not connected"}
        
        try:
            positions = self.broker.get_positions()
            logger.info(f"📈 Positions: {positions}")
            return positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {"error": str(e)}
    
    def execute_advised_trade(self, symbol: str, current_price: float, 
                             indicators: Dict[str, Any], 
                             market_sentiment: str = "neutral",
                             available_capital: float = 10000.0) -> Dict[str, Any]:
        """
        Make a trading decision and execute it if approved by council
        Full autonomous trading with memory and council approval
        """
        try:
            # Make decision using memory and council
            decision = self.make_trading_decision(
                symbol=symbol,
                current_price=current_price,
                indicators=indicators,
                market_sentiment=market_sentiment,
                available_capital=available_capital
            )
            
            action = decision.get("action", "HOLD")
            
            if action == "HOLD":
                logger.info(f"🛑 HOLD decision for {symbol}")
                return decision
            
            if not self.trading_enabled:
                logger.warning(f"⚠️ Trading disabled - skipping {action} for {symbol}")
                return {**decision, "status": "skipped", "reason": "trading_disabled"}
            
            # Calculate position size
            position_size = self._calculate_position_size(
                price=current_price,
                capital=available_capital,
                confidence=decision.get("confidence", 0.5)
            )
            
            qty = int(position_size)
            
            if qty <= 0:
                logger.warning(f"Position size too small for {symbol}")
                return {**decision, "status": "skipped", "reason": "position_size_too_small"}
            
            # Execute trade
            if action == "BUY":
                result = self.buy(symbol=symbol, qty=qty)
            elif action == "SELL":
                result = self.sell(symbol=symbol, qty=qty)
            else:
                return decision
            
            # Record the trade
            if result.get("status") == "success":
                trade_record = {
                    "symbol": symbol,
                    "action": action,
                    "qty": qty,
                    "entry_price": current_price,
                    "order_id": result.get("order", {}).get("order_id"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "decision": decision
                }
                
                logger.info(f"✅ Trade executed and recorded: {trade_record}")
                return {**decision, "execution": result, "trade_record": trade_record}
            else:
                logger.error(f"❌ Trade execution failed: {result}")
                return {**decision, "execution": result, "status": "execution_failed"}
            
        except Exception as e:
            logger.error(f"Error in autonomous trade execution: {e}")
            return {"status": "error", "message": str(e), "symbol": symbol}
    
    def get_broker_status(self) -> Dict[str, Any]:
        """Get broker connection status"""
        return {
            "broker": self.broker_type,
            "connected": self.broker is not None and self.broker.connected if self.broker else False,
            "sandbox": self.use_sandbox,
            "trading_enabled": self.trading_enabled
        }
