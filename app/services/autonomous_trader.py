"""
Autonomous Trader with Memory Integration and Council Approval
Makes trading decisions informed by past experience and council voting
Includes strict stop loss enforcement for capital protection

Tim P0 rules:
- Momentum entries only (no RSI dip-buying)
- Broker-backed stops + take-profit exits
- Hard daily loss kill switch
- Risk-dollar position sizing
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple

from .stop_loss_manager import (
    StopLossManager,
    StopLossConfig,
    StopLossStrategy
)
from .momentum_engine import (
    MomentumConfig,
    evaluate_momentum_entry,
    compute_stop_and_target,
    risk_based_shares,
)

logger = logging.getLogger(__name__)

# Broker statuses that mean the order was accepted / filled enough to manage risk
_SUCCESS_STATUSES = {
    "filled", "filled_partial", "success", "SUCCESS", "FILLED",
    "PLACED", "placed", "accepted", "ACCEPTED", "new", "NEW", "pending", "PENDING",
}


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

        self._init_broker()

        sl_config = StopLossConfig(
            strategy=StopLossStrategy.ATR_BASED,
            default_percent=2.0,
            max_percent=5.0,
            min_percent=0.5,
            use_trailing=True,
            trailing_percent=1.5,
            enforce_hard_stops=True,
            alert_on_breach=True,
            emergency_stop_loss=3.0,
            default_take_profit_percent=3.0,
        )
        self.stop_loss_manager = StopLossManager(sl_config)
        self.momentum_config = MomentumConfig()

        self.risk_config = {
            "max_position_size": 0.05,
            "max_daily_loss": 0.02,
            "risk_per_trade": 0.01,
            "min_win_rate": 0.50,
            "take_profit_pct": 3.0,
            "stop_loss_pct": 2.0,
            "use_stop_loss_manager": True,
            "place_broker_stops": True,
        }
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: Optional[date] = None
        self._starting_capital_today: Optional[float] = None

        logger.info("✅ Autonomous Trader initialized with momentum + broker-backed stops")
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

    def _roll_daily_pnl(self, available_capital: Optional[float] = None) -> None:
        today = date.today()
        if self._daily_pnl_date != today:
            self._daily_pnl_date = today
            self._daily_pnl = 0.0
            self._starting_capital_today = available_capital

    def record_realized_pnl(self, pnl: float) -> None:
        self._roll_daily_pnl()
        self._daily_pnl += pnl

    def enable_autonomous_trading(self, enable: bool = True) -> None:
        """Enable/disable autonomous trading"""
        self.trading_enabled = enable
        logger.info(f"Autonomous trading {'enabled' if enable else 'disabled'}")

    def perform_research(self, symbol: str, mode: str = "EVALUATE") -> Dict[str, Any]:
        """Research a symbol; returns indicators + confidence for momentum engine."""
        indicators: Dict[str, Any] = {}
        confidence = 0.0
        price = 0.0
        try:
            try:
                from .stock_data_service import StockDataService
                sds = StockDataService()
                data = sds.get_stock_data(symbol, period="3mo")
                technicals = data.get("technicals") or {}
                price = float(data.get("current_price") or 0)
                indicators = {
                    "rsi": technicals.get("rsi_14", technicals.get("rsi", 50)),
                    "rsi_14": technicals.get("rsi_14"),
                    "macd": technicals.get("macd_histogram") or technicals.get("macd") or 0,
                    "macd_signal": technicals.get("macd_signal"),
                    "sma_20": technicals.get("sma_20"),
                    "sma_50": technicals.get("sma_50"),
                    "sma_200": technicals.get("sma_200"),
                    "atr": technicals.get("atr_14"),
                    "atr_14": technicals.get("atr_14"),
                    "volume_ratio": technicals.get("volume_ratio", 1.0),
                    "momentum_pct": technicals.get("momentum_pct", 50),
                    "vwap": technicals.get("vwap"),
                    "bb_upper": technicals.get("bb_upper"),
                    "bb_lower": technicals.get("bb_lower"),
                }
            except Exception as e:
                logger.debug(f"StockDataService research fallback for {symbol}: {e}")
                try:
                    from .stock_data import StockData
                    sd = StockData()
                    signals = sd.get_trading_signals(symbol)
                    indicators = signals.get("indicators") or signals.get("technicals") or {}
                    price = float(signals.get("price") or signals.get("current_price") or 0)
                    confidence = float(signals.get("confidence") or 50) / 100.0
                except Exception as e2:
                    logger.warning(f"⚠️ Research data unavailable for {symbol}: {e2}")
                    return {
                        "symbol": symbol,
                        "mode": mode,
                        "indicators": {},
                        "confidence": 0,
                        "price": 0,
                        "error": str(e2),
                    }

            action, conf, reason = evaluate_momentum_entry(price, indicators, self.momentum_config)
            confidence = max(confidence, conf)
            return {
                "symbol": symbol,
                "mode": mode,
                "indicators": indicators,
                "confidence": round(confidence * 100, 1),
                "price": price,
                "action_hint": action,
                "reason": reason,
            }
        except Exception as e:
            logger.error(f"❌ perform_research error for {symbol}: {e}")
            return {"symbol": symbol, "indicators": {}, "confidence": 0, "price": 0, "error": str(e)}

    def open_position_with_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        quantity: int,
        stop_loss_percent: Optional[float] = None,
        take_profit_percent: Optional[float] = None,
        indicators: Optional[Dict[str, Any]] = None,
        place_broker_stop: bool = True,
    ) -> Dict[str, Any]:
        """Open position with stop + TP; place broker stop when possible."""
        indicators = indicators or {}
        levels = compute_stop_and_target(entry_price, indicators, self.momentum_config)
        sl_pct = stop_loss_percent or levels["stop_loss_pct"] or self.risk_config["stop_loss_pct"]
        tp_pct = take_profit_percent or levels["take_profit_pct"] or self.risk_config["take_profit_pct"]
        atr = None
        try:
            atr = float(indicators.get("atr") or indicators.get("atr_14") or 0) or None
        except (TypeError, ValueError):
            atr = None

        position = self.stop_loss_manager.open_position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss_percent=sl_pct,
            stop_loss_price=levels.get("stop_loss_price"),
            take_profit_percent=tp_pct,
            take_profit_price=levels.get("take_profit_price"),
            atr=atr,
        )

        broker_stop = None
        if place_broker_stop and self.risk_config.get("place_broker_stops", True) and self.broker:
            broker_stop = self._place_protective_stop(
                symbol=symbol,
                qty=quantity,
                stop_price=position.stop_loss_price,
            )
            if broker_stop and broker_stop.get("order_id"):
                position.broker_stop_order_id = str(broker_stop.get("order_id"))

        logger.info(
            f"🟢 Position opened: {symbol} Entry=${entry_price:.2f}, "
            f"Stop=${position.stop_loss_price:.2f}, TP=${position.take_profit_price}, "
            f"broker_stop={position.broker_stop_order_id}"
        )

        status = self.stop_loss_manager.get_position_status(symbol) or {}
        status["broker_stop"] = broker_stop
        return status

    def _place_protective_stop(self, symbol: str, qty: int, stop_price: float) -> Dict[str, Any]:
        """Place protective stop without requiring trading_enabled."""
        if not self.broker:
            return {"status": "FAILED", "reason": "no_broker"}
        try:
            result = self.broker.place_order(
                symbol=symbol,
                qty=qty,
                side="sell",
                order_type="stop",
                stop_price=stop_price,
            )
            normalized = self._normalize_order_result(result)
            logger.info(f"🛡️ Broker stop placed for {symbol} @ {stop_price}: {normalized.get('status')}")
            return normalized
        except TypeError:
            try:
                result = self.broker.place_order(
                    symbol=symbol, qty=qty, side="sell", order_type="stop"
                )
                return self._normalize_order_result(result)
            except Exception as e:
                logger.error(f"❌ Protective stop failed for {symbol}: {e}")
                return {"status": "FAILED", "reason": str(e)}
        except Exception as e:
            logger.error(f"❌ Protective stop failed for {symbol}: {e}")
            return {"status": "FAILED", "reason": str(e)}

    def _normalize_order_result(self, result: Any) -> Dict[str, Any]:
        if not result or not isinstance(result, dict):
            return {"status": "FAILED", "reason": "unexpected_broker_response", "raw": result}
        status = str(result.get("status", "UNKNOWN"))
        if status in _SUCCESS_STATUSES:
            return {
                "status": "SUCCESS",
                "broker_status": status,
                "order_id": result.get("order_id", result.get("id")),
                "raw": result,
            }
        if status.upper() in ("ERROR", "FAILED", "REJECTED"):
            return {"status": "FAILED", "reason": result.get("message") or status, "raw": result}
        return {"status": status, "raw": result}

    def update_position_price(
        self,
        symbol: str,
        current_price: float,
        execute_exit: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """Update price; on stop/TP place market sell so we do not ride losers."""
        prior = self.stop_loss_manager.positions.get(symbol)
        prior_qty = prior.quantity if prior else 0
        prior_entry = prior.entry_price if prior else 0.0

        is_exit, message = self.stop_loss_manager.update_position(
            symbol=symbol,
            current_price=current_price
        )

        if is_exit:
            logger.warning(f"🛑 Exit rule triggered for {symbol}: {message}")
            exit_status = "STOP_LOSS_TRIGGERED"
            if message and "TAKE PROFIT" in message:
                exit_status = "TAKE_PROFIT"
            elif message and "EMERGENCY" in message:
                exit_status = "EMERGENCY_STOP"

            order_result = None
            if execute_exit and prior_qty > 0 and self.broker:
                order_result = self.execute_order(
                    symbol=symbol,
                    action="SELL",
                    qty=prior_qty,
                    price=current_price,
                    price_type="MARKET",
                )
                logger.info(f"💸 Exit order for {symbol}: {order_result.get('status')}")

            pnl = (current_price - prior_entry) * prior_qty if prior_entry else 0.0
            self.record_realized_pnl(pnl)

            if self.memory:
                try:
                    self.record_completed_trade(
                        symbol=symbol,
                        entry_price=prior_entry,
                        exit_price=current_price,
                        quantity=prior_qty,
                        reason=exit_status,
                    )
                except Exception as e:
                    logger.debug(f"Could not record completed trade: {e}")

            if message:
                message = f"{message} | exit_order={order_result}"

        return is_exit, message

    def manage_open_positions(self, quotes: Dict[str, float]) -> list:
        """Poll open positions against live quotes and enforce exits."""
        results = []
        for symbol in list(self.stop_loss_manager.positions.keys()):
            price = quotes.get(symbol)
            if price is None:
                continue
            exited, msg = self.update_position_price(symbol, float(price), execute_exit=True)
            results.append({"symbol": symbol, "exited": exited, "message": msg})
        return results

    def close_position_manually(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "manual"
    ) -> Optional[Dict[str, Any]]:
        prior = self.stop_loss_manager.positions.get(symbol)
        detail = self.stop_loss_manager.close_position(
            symbol=symbol,
            exit_price=exit_price,
            reason=reason
        )
        if detail and prior and self.broker:
            self.execute_order(symbol=symbol, action="SELL", qty=prior.quantity, price=exit_price)
        return detail

    def get_positions_status(self) -> Dict[str, Any]:
        return self.stop_loss_manager.get_all_positions()

    def get_risk_summary(self) -> Dict[str, Any]:
        summary = self.stop_loss_manager.get_risk_summary()
        summary["daily_pnl"] = self._daily_pnl
        summary["max_daily_loss"] = self.risk_config.get("max_daily_loss")
        return summary

    def set_risk_parameters(self, params: Dict[str, float]) -> None:
        self.risk_config.update(params)
        if "take_profit_pct" in params:
            self.stop_loss_manager.config.default_take_profit_percent = float(params["take_profit_pct"])
            self.momentum_config.take_profit_pct = float(params["take_profit_pct"])
        if "stop_loss_pct" in params:
            self.stop_loss_manager.config.default_percent = float(params["stop_loss_pct"])
            self.momentum_config.stop_loss_pct = float(params["stop_loss_pct"])
        logger.info(f"Risk parameters updated: {params}")

    def set_council(self, council) -> None:
        self.council = council
        logger.info("Trading council assigned to autonomous trader")

    def consult_council(self, symbol: str, action: str, price: float, quantity: int) -> dict:
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
            return {"approval_percentage": 100.0, "final_confidence": 1.0, "approved": True}
        except Exception as e:
            logger.warning(f"⚠️ consult_council error: {e}")
            return {"approval_percentage": 0.0, "final_confidence": 0.0, "approved": False}

    def execute_order(self, symbol: str, action: str, qty: int, price: float = None, price_type: str = "MARKET", account_id: str | None = None) -> dict:
        try:
            side = 'buy' if action.upper() in ('BUY', 'OPEN') else 'sell'
            if not self.broker:
                logger.warning("⚠️ No broker configured - cannot execute order")
                return {"status": "FAILED", "reason": "no_broker"}

            result = self.broker.place_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=(price_type or "market").lower(),
            )
            return self._normalize_order_result(result)
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
        try:
            similar_trades = []
            patterns = []
            lessons = []
            if self.memory:
                similar_trades = self.memory.recall_similar_trades(query=symbol, symbol=symbol, k=5)
                patterns = self.memory.get_profitable_patterns(symbol=symbol, min_trades=2)
                lessons = self.memory.get_lessons_by_category("pattern") + \
                         self.memory.get_lessons_by_category("risk")

            memory_context = self._build_memory_context(similar_trades, patterns, lessons)

            # Ensure price available to momentum engine via indicators
            ind = dict(indicators or {})
            ind.setdefault("price", current_price)
            ind.setdefault("current_price", current_price)

            action, confidence = self._determine_action(
                symbol=symbol,
                indicators=ind,
                market_sentiment=market_sentiment,
                similar_trades=similar_trades,
                patterns=patterns,
                lessons=lessons
            )

            reasoning = self._build_reasoning(
                symbol=symbol,
                action=action,
                indicators=ind,
                memory_context=memory_context
            )

            levels = compute_stop_and_target(current_price, ind, self.momentum_config)

            if not self._passes_risk_check(symbol, action, available_capital):
                action = "HOLD"
                confidence = 0.1
                reasoning += " [Risk limits exceeded]"

            council_approved = True
            council_decision = None

            if self.require_council_approval and self.council and action != "HOLD":
                logger.info(f"\n📋 Submitting {symbol} {action} to trading council for approval...")
                council_decision, council_approved = self.council.discuss_trade(
                    symbol=symbol,
                    action=action,
                    current_price=current_price,
                    indicators=ind,
                    available_capital=available_capital,
                    market_sentiment=market_sentiment
                )

                if council_decision:
                    reasoning += f"\n[Council Decision: {council_decision.approval_percentage:.0f}% approval, "
                    reasoning += f"Confidence: {council_decision.final_confidence:.1%}]"

                    if not council_approved:
                        action = "HOLD"
                        confidence = 0
                        logger.warning(f"⛔ Council rejected {symbol} trade")
                    else:
                        logger.info(f"✅ Council approved {symbol} {action} trade")

            position_size = 0
            if action != "HOLD":
                position_size = risk_based_shares(
                    capital=available_capital,
                    entry_price=current_price,
                    stop_price=levels["stop_loss_price"],
                    risk_fraction=self.risk_config.get("risk_per_trade", 0.01),
                    max_position_fraction=self.risk_config.get("max_position_size", 0.05),
                )
                if position_size <= 0:
                    position_size = self._calculate_position_size(current_price, available_capital, confidence)

            decision = {
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "price": current_price,
                "reasoning": reasoning,
                "indicators": ind,
                "market_sentiment": market_sentiment,
                "recalled_similar": len(similar_trades),
                "timestamp": datetime.utcnow().isoformat(),
                "position_size": position_size,
                "council_approved": council_approved,
                "council_decision": council_decision.to_dict() if council_decision else None,
                "stop_loss_percent": levels["stop_loss_pct"],
                "take_profit_percent": levels["take_profit_pct"],
                "stop_loss_price": levels["stop_loss_price"],
                "take_profit_price": levels["take_profit_price"],
                "stop_loss_note": f"Broker stop {levels['stop_loss_pct']:.1f}% / TP {levels['take_profit_pct']:.1f}%",
            }

            if self.memory and hasattr(self.memory, "store_decision_memory"):
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

    def _build_memory_context(self, similar_trades: list, patterns: list, lessons: list) -> str:
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
        """Momentum sniping — ride strength, never buy weakness hoping for a bounce."""
        price = float(
            indicators.get("price")
            or indicators.get("close")
            or indicators.get("current_price")
            or 0
        )
        if price <= 0:
            price = float(indicators.get("sma_20") or 0)

        action, confidence, reason = evaluate_momentum_entry(price, indicators, self.momentum_config)
        logger.debug(f"{symbol} momentum: {action} ({confidence:.2f}) — {reason}")

        if action == "BUY" and similar_trades:
            successful_buys = sum(
                1 for t in similar_trades
                if t.get("action", "") == "BUY" and t.get("success", False)
            )
            if successful_buys > 0:
                confidence = min(0.95, confidence + 0.1)

        if market_sentiment == "bullish" and action == "BUY":
            confidence = min(0.99, confidence + 0.05)
        elif market_sentiment == "bearish" and action == "BUY":
            confidence = max(0.01, confidence - 0.15)
            if confidence < self.momentum_config.min_confidence:
                action = "HOLD"

        return action, min(0.99, max(0.01, confidence))

    def _build_reasoning(self, symbol: str, action: str, indicators: Dict[str, Any], memory_context: str) -> str:
        reason = f"Trading {symbol}: {action}. "
        if indicators.get("rsi") or indicators.get("rsi_14"):
            rsi = indicators.get("rsi") or indicators.get("rsi_14")
            reason += f"RSI={float(rsi):.1f}. "
        if indicators.get("volume_ratio"):
            reason += f"RVOL={float(indicators['volume_ratio']):.2f}. "
        if indicators.get("momentum_pct") is not None:
            reason += f"Mom={float(indicators['momentum_pct']):.0f}. "
        if memory_context:
            reason += memory_context
        return reason

    def _passes_risk_check(self, symbol: str, action: str, available_capital: float) -> bool:
        if action == "HOLD":
            return True

        self._roll_daily_pnl(available_capital)
        max_daily_loss = self.risk_config.get("max_daily_loss", 0.02)
        baseline = self._starting_capital_today or available_capital or 0
        if baseline > 0 and self._daily_pnl < -(baseline * max_daily_loss):
            logger.warning(
                f"Trade blocked: daily loss ${self._daily_pnl:.2f} exceeds "
                f"{max_daily_loss*100:.1f}% of ${baseline:.2f}"
            )
            return False

        if self.memory and hasattr(self.memory, "get_trading_stats_by_symbol"):
            stats = self.memory.get_trading_stats_by_symbol(symbol)
            win_rate = stats.get("win_rate", 0)
            if win_rate > 0 and win_rate < self.risk_config["min_win_rate"] * 100:
                logger.warning(f"Trade blocked: {symbol} win rate {win_rate:.1f}% below minimum")
                return False

        if available_capital < 1:
            logger.warning("Trade blocked: insufficient capital")
            return False

        return True

    def _calculate_position_size(self, price: float, capital: float, confidence: float) -> float:
        if price <= 0 or capital <= 0:
            return 0
        max_position = capital * self.risk_config["max_position_size"]
        position_size = max_position * max(0.1, confidence)
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
        try:
            if not self.memory:
                return False
            profit_loss = (exit_price - entry_price) * quantity
            profit_loss_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price else 0

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
        rsi = indicators.get("rsi", indicators.get("rsi_14", 50)) or 50
        if rsi < 30:
            return "oversold"
        elif rsi > 70:
            return "overbought"
        return "neutral"

    def _extract_lessons(self, symbol: str, trade_data: Dict[str, Any]) -> None:
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
        stats = self.memory.get_memory_stats() if self.memory else {}
        return {
            "trading_enabled": self.trading_enabled,
            "memory": stats,
            "risk_config": self.risk_config,
            "daily_pnl": self._daily_pnl,
            "status": "active" if self.trading_enabled else "inactive"
        }

    def execute_trade(self, symbol: str, qty: int, side: str, order_type: str = "market",
                     limit_price: float = None, stop_price: float = None,
                     require_enabled: bool = True) -> Dict[str, Any]:
        if not self.broker:
            logger.error("❌ Broker not connected")
            return {"status": "error", "message": "Broker connection not available", "symbol": symbol}

        if require_enabled and not self.trading_enabled and order_type not in ("stop", "stop_limit"):
            logger.warning(f"⚠️ Autonomous trading disabled for {symbol} {side}")
            return {"status": "error", "message": "Autonomous trading is disabled", "symbol": symbol}

        try:
            logger.info(f"📤 Executing {side} order for {qty} {symbol} @ {order_type}")
            kwargs = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "order_type": order_type,
            }
            if limit_price is not None:
                kwargs["limit_price"] = limit_price
            if stop_price is not None:
                kwargs["stop_price"] = stop_price

            try:
                result = self.broker.place_order(**kwargs)
            except TypeError:
                result = self.broker.place_order(
                    symbol=symbol, qty=qty, side=side, order_type=order_type
                )

            normalized = self._normalize_order_result(result)
            if normalized.get("status") == "FAILED":
                logger.error(f"❌ Order failed: {normalized.get('reason', 'Unknown error')}")
                return {"status": "error", "message": normalized.get("reason"), "raw": result}

            logger.info(f"✅ Order executed: {result}")
            return {
                "status": "success",
                "order": result,
                "executed_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}")
            return {"status": "error", "message": str(e), "symbol": symbol}

    def buy(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side="BUY",
                                  order_type="limit" if limit_price else "market", limit_price=limit_price)

    def sell(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side="SELL",
                                  order_type="limit" if limit_price else "market", limit_price=limit_price)

    def short(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side="SELL",
                                  order_type="limit" if limit_price else "market", limit_price=limit_price)

    def cover(self, symbol: str, qty: int, limit_price: float = None) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side="BUY",
                                  order_type="limit" if limit_price else "market", limit_price=limit_price)

    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side=side, order_type="limit", limit_price=limit_price)

    def place_stop_order(self, symbol: str, qty: int, side: str, stop_price: float) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side=side, order_type="stop",
                                  stop_price=stop_price, require_enabled=False)

    def place_stop_limit_order(self, symbol: str, qty: int, side: str,
                               stop_price: float, limit_price: float) -> Dict[str, Any]:
        return self.execute_trade(symbol=symbol, qty=qty, side=side, order_type="stop_limit",
                                  stop_price=stop_price, limit_price=limit_price, require_enabled=False)

    def get_account_info(self) -> Dict[str, Any]:
        if not self.broker:
            return {"error": "Broker not connected"}
        try:
            return self.broker.get_account()
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {"error": str(e)}

    def get_positions(self) -> Dict[str, Any]:
        if not self.broker:
            return {"error": "Broker not connected"}
        try:
            return self.broker.get_positions()
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {"error": str(e)}

    def execute_advised_trade(self, symbol: str, current_price: float,
                             indicators: Dict[str, Any],
                             market_sentiment: str = "neutral",
                             available_capital: float = 10000.0) -> Dict[str, Any]:
        try:
            decision = self.make_trading_decision(
                symbol=symbol,
                current_price=current_price,
                indicators=indicators,
                market_sentiment=market_sentiment,
                available_capital=available_capital
            )

            if decision.get("action") == "HOLD" or not decision.get("council_approved"):
                return {"executed": False, "decision": decision, "reason": "Hold or council rejected"}

            qty = int(decision.get("position_size") or 0)
            if qty < 1:
                return {"executed": False, "decision": decision, "reason": "position size 0"}

            was_enabled = self.trading_enabled
            self.trading_enabled = True
            try:
                result = self.execute_order(
                    symbol=symbol,
                    action=decision["action"],
                    qty=qty,
                    price=current_price,
                )
            finally:
                self.trading_enabled = was_enabled

            if result.get("status") == "SUCCESS" and decision["action"].upper() == "BUY":
                self.open_position_with_stop_loss(
                    symbol=symbol,
                    entry_price=current_price,
                    quantity=qty,
                    stop_loss_percent=decision.get("stop_loss_percent"),
                    take_profit_percent=decision.get("take_profit_percent"),
                    indicators=indicators,
                )

            return {
                "executed": result.get("status") == "SUCCESS",
                "decision": decision,
                "order": result,
            }
        except Exception as e:
            logger.error(f"Error in execute_advised_trade: {e}")
            return {"executed": False, "error": str(e)}

    def get_broker_status(self) -> Dict[str, Any]:
        return {
            "broker": self.broker_type,
            "connected": self.broker is not None and getattr(self.broker, "connected", False),
            "sandbox": self.use_sandbox,
            "trading_enabled": self.trading_enabled
        }
