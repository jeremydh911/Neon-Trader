"""
Autonomous Trader with ML Integration
Enhanced decision making using LSTM predictions, sentiment analysis, and RAG memory
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import random

logger = logging.getLogger(__name__)

class AutonomousTraderML:
    """Autonomous trader with ML-powered predictions and sentiment analysis"""
    
    def __init__(self, memory_service, ml_predictor, sentiment_analyzer, llm_service=None):
        self.memory = memory_service
        self.ml_predictor = ml_predictor
        self.sentiment_analyzer = sentiment_analyzer
        self.llm = llm_service
        self.trading_enabled = False
        self.risk_config = {
            "max_position_size": 0.05,
            "max_daily_loss": 0.02,
            "min_win_rate": 0.50,
            "take_profit_pct": 2.0,
            "stop_loss_pct": 1.0,
            "min_ml_confidence": 0.55
        }
    
    def enable_autonomous_trading(self, enable: bool = True) -> None:
        """Enable/disable autonomous trading"""
        self.trading_enabled = enable
        logger.info(f"Autonomous trading {'enabled' if enable else 'disabled'}")
    
    def set_risk_parameters(self, params: Dict[str, float]) -> None:
        """Update risk management parameters"""
        self.risk_config.update(params)
        logger.info(f"Risk parameters updated: {params}")
    
    def make_trading_decision(
        self, 
        symbol: str,
        current_price: float,
        indicators: Dict[str, Any],
        market_sentiment: str = "neutral",
        available_capital: float = 10000.0,
        price_history: Optional[List[float]] = None,
        volume_history: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Make an ML-informed trading decision"""
        
        try:
            # Get ML price prediction
            ml_prediction = self.ml_predictor.predict_price_movement(
                symbol=symbol,
                current_price=current_price,
                indicators=indicators,
                historical_data=price_history
            )
            
            # Get sentiment analysis
            sentiment_analysis = self.sentiment_analyzer.analyze_market_sentiment(
                symbol=symbol,
                indicators=indicators,
                recent_price_action=price_history,
                volume_data=volume_history
            )
            
            # Get chart pattern recognition
            pattern_analysis = {}
            if price_history and len(price_history) > 5:
                pattern_analysis = self.ml_predictor.recognize_chart_pattern(price_history)
            
            # Recall similar trades from memory
            similar_trades = self.memory.recall_similar_trades(query=symbol, symbol=symbol, k=5)
            profitable_patterns = self.memory.get_profitable_patterns(symbol=symbol, min_trades=2)
            
            # Determine action based on multiple factors
            action, confidence = self._determine_ml_action(
                ml_prediction=ml_prediction,
                sentiment_analysis=sentiment_analysis,
                pattern_analysis=pattern_analysis,
                similar_trades=similar_trades,
                indicators=indicators
            )
            
            # Build comprehensive reasoning
            reasoning = self._build_ml_reasoning(
                ml_prediction=ml_prediction,
                sentiment_analysis=sentiment_analysis,
                pattern_analysis=pattern_analysis,
                action=action,
                confidence=confidence
            )
            
            # Check risk limits
            if not self._passes_risk_check(symbol, action, available_capital):
                action = "HOLD"
                confidence = 0.1
                reasoning += " [Risk limits exceeded]"
            
            # Check ML confidence minimum
            if confidence < self.risk_config["min_ml_confidence"] and action != "HOLD":
                action = "HOLD"
                reasoning += f" [ML confidence {confidence:.2%} below minimum {self.risk_config['min_ml_confidence']:.2%}]"
            
            decision = {
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "price": current_price,
                "reasoning": reasoning,
                "indicators": indicators,
                "market_sentiment": sentiment_analysis.get("overall_sentiment", market_sentiment),
                "sentiment_score": sentiment_analysis.get("sentiment_score", 0),
                "ml_prediction": ml_prediction.get("direction"),
                "predicted_price": ml_prediction.get("predicted_price"),
                "predicted_change_pct": ml_prediction.get("predicted_change_pct"),
                "pattern_detected": pattern_analysis.get("pattern", "UNKNOWN"),
                "pattern_confidence": pattern_analysis.get("confidence", 0),
                "recalled_similar": len(similar_trades),
                "profitable_patterns": len(profitable_patterns),
                "timestamp": datetime.utcnow().isoformat(),
                "position_size": self._calculate_position_size(current_price, available_capital, confidence) if action != "HOLD" else 0,
                "take_profit": current_price * (1 + self.risk_config["take_profit_pct"] / 100) if action == "BUY" else current_price * (1 - self.risk_config["take_profit_pct"] / 100),
                "stop_loss": current_price * (1 - self.risk_config["stop_loss_pct"] / 100) if action == "BUY" else current_price * (1 + self.risk_config["stop_loss_pct"] / 100)
            }
            
            # Store decision in memory
            self.memory.store_decision_memory(decision)
            
            logger.info(f"ML Decision {symbol}: {action} (ML: {ml_prediction.get('direction')}, Sentiment: {sentiment_analysis.get('overall_sentiment')}, Confidence: {confidence:.2f})")
            return decision
        except Exception as e:
            logger.error(f"Error making ML trading decision: {e}")
            return {
                "symbol": symbol,
                "action": "HOLD",
                "confidence": 0.0,
                "reasoning": f"Error in ML decision making: {str(e)}"
            }
    
    def _determine_ml_action(
        self,
        ml_prediction: Dict,
        sentiment_analysis: Dict,
        pattern_analysis: Dict,
        similar_trades: List[Dict],
        indicators: Dict
    ) -> Tuple[str, float]:
        """Determine action using multiple ML signals"""
        
        action_score = 0
        confidence_components = []
        
        # ML prediction signal (weight: 0.35)
        ml_direction = ml_prediction.get("direction", "NEUTRAL")
        ml_conf = ml_prediction.get("confidence", 0.5)
        if ml_direction == "UP":
            action_score += 0.35 * ml_conf
            confidence_components.append(("ML_BUY", ml_conf))
        elif ml_direction == "DOWN":
            action_score -= 0.35 * ml_conf
            confidence_components.append(("ML_SELL", ml_conf))
        
        # Sentiment signal (weight: 0.25)
        sentiment_score = sentiment_analysis.get("sentiment_score", 0)
        sentiment_conf = sentiment_analysis.get("confidence", 0)
        action_score += 0.25 * sentiment_score * sentiment_conf
        confidence_components.append(("Sentiment", abs(sentiment_score)))
        
        # Pattern signal (weight: 0.20)
        pattern = pattern_analysis.get("pattern", "UNKNOWN")
        pattern_conf = pattern_analysis.get("confidence", 0)
        if pattern == "HEAD_AND_SHOULDERS":
            action_score -= 0.20 * pattern_conf  # Reversal pattern
        elif pattern in ["TRIANGLE", "DOUBLE_BOTTOM"]:
            action_score += 0.15 * pattern_conf
        confidence_components.append(("Pattern", pattern_conf if pattern != "UNKNOWN" else 0))
        
        # Memory signal (weight: 0.15)
        if similar_trades:
            successful = sum(1 for t in similar_trades if t.get("success", False))
            memory_confidence = successful / len(similar_trades)
            if memory_confidence > 0.6:
                action_score += 0.1 * memory_confidence
            confidence_components.append(("Memory", memory_confidence))
        
        # Technical indicators confirmation (weight: 0.05)
        rsi = indicators.get("rsi", 50)
        if rsi < 30 and action_score > 0:
            action_score += 0.05  # Oversold confirms buy
        elif rsi > 70 and action_score < 0:
            action_score += 0.05  # Overbought confirms sell
        
        # Determine final action
        if action_score > 0.2:
            action = "BUY"
        elif action_score < -0.2:
            action = "SELL"
        else:
            action = "HOLD"
        
        # Calculate confidence
        avg_confidence = sum(c[1] for c in confidence_components) / len(confidence_components) if confidence_components else 0.5
        confidence = min(0.99, max(0.01, abs(action_score) * 1.5 * avg_confidence))
        
        return action, confidence
    
    def _build_ml_reasoning(
        self,
        ml_prediction: Dict,
        sentiment_analysis: Dict,
        pattern_analysis: Dict,
        action: str,
        confidence: float
    ) -> str:
        """Build comprehensive reasoning for ML decision"""
        
        reasoning = f"Trading {action} with {confidence:.1%} ML confidence. "
        
        # ML prediction reasoning
        reasoning += f"ML predicts {ml_prediction.get('direction')} "
        reasoning += f"({ml_prediction.get('confidence'):.1%}). "
        
        # Sentiment reasoning
        sentiment = sentiment_analysis.get("overall_sentiment", "neutral")
        reasoning += f"Market sentiment: {sentiment}. "
        
        # Pattern reasoning
        pattern = pattern_analysis.get("pattern", "UNKNOWN")
        if pattern != "UNKNOWN":
            reasoning += f"Pattern detected: {pattern}. "
        
        # Add ML prediction details
        if ml_prediction.get("predicted_price"):
            change_pct = ml_prediction.get("predicted_change_pct", 0)
            reasoning += f"Target: {ml_prediction.get('predicted_price'):.2f} ({change_pct:+.2f}%). "
        
        return reasoning
    
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
        
        # Check daily loss limit
        daily_loss = sum(t.get("profit_loss", 0) for t in self.memory.get_recent_trades(limit=50, symbol=symbol))
        if daily_loss < -available_capital * self.risk_config["max_daily_loss"]:
            logger.warning("Trade blocked: daily loss limit exceeded")
            return False
        
        return True
    
    def _calculate_position_size(self, price: float, capital: float, confidence: float) -> float:
        """Calculate position size based on confidence and capital"""
        max_position = capital * self.risk_config["max_position_size"]
        # Size increases with confidence
        position_size = max_position * confidence
        return int(position_size / price) if price > 0 else 0
    
    def record_completed_trade(
        self, 
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: int,
        ml_prediction: Optional[Dict] = None,
        reason: str = "",
        indicators: Dict[str, Any] = None
    ) -> bool:
        """Record completed trade and extract ML lessons"""
        
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
                "market_condition": self._assess_market_condition(indicators or {}),
                "ml_predicted_direction": ml_prediction.get("direction") if ml_prediction else None,
                "ml_prediction_accuracy": self._check_ml_prediction_accuracy(
                    exit_price, entry_price, ml_prediction
                ) if ml_prediction else None
            }
            
            success = self.memory.store_trade_memory(trade_data)
            
            if success and profit_loss_pct != 0:
                self._extract_ml_lessons(symbol, trade_data, ml_prediction)
            
            return success
        except Exception as e:
            logger.error(f"Error recording ML trade: {e}")
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
    
    def _check_ml_prediction_accuracy(self, exit_price: float, entry_price: float, ml_prediction: Dict) -> float:
        """Check how accurate the ML prediction was"""
        actual_direction = "UP" if exit_price > entry_price else "DOWN"
        predicted_direction = ml_prediction.get("direction", "NEUTRAL")
        
        if actual_direction == predicted_direction:
            actual_change = abs((exit_price - entry_price) / entry_price)
            predicted_change = abs(ml_prediction.get("predicted_change_pct", 0) / 100)
            accuracy = 1.0 - abs(actual_change - predicted_change)
            return max(0, min(1, accuracy))
        return 0.0
    
    def _extract_ml_lessons(self, symbol: str, trade_data: Dict[str, Any], ml_prediction: Optional[Dict]) -> None:
        """Extract learned lessons from ML-predicted trades"""
        
        try:
            profit_loss_pct = trade_data.get("profit_loss_pct", 0)
            ml_direction = ml_prediction.get("direction") if ml_prediction else None
            actual_direction = "UP" if trade_data.get("profit_loss", 0) > 0 else "DOWN"
            
            # ML prediction accuracy lesson
            if ml_direction and ml_direction == actual_direction and abs(profit_loss_pct) > 1.0:
                lesson = {
                    "category": "ml_pattern",
                    "lesson": f"ML {ml_direction} prediction on {symbol} with {trade_data.get('market_condition')} condition yielded {profit_loss_pct:.2f}%",
                    "impact": "positive" if profit_loss_pct > 0 else "negative",
                    "confidence": 0.85,
                    "examples": [symbol]
                }
                self.memory.store_lesson(lesson)
            
            # Risk management lesson
            if profit_loss_pct < -1.5:
                lesson = {
                    "category": "risk",
                    "lesson": f"ML stop loss on {symbol} prevented larger loss: {profit_loss_pct:.2f}%",
                    "impact": "protective",
                    "confidence": 0.75,
                    "examples": [symbol]
                }
                self.memory.store_lesson(lesson)
        except Exception as e:
            logger.debug(f"Error extracting ML lessons: {e}")
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get trader's memory summary with ML metrics"""
        stats = self.memory.get_memory_stats()
        ml_metrics = self.ml_predictor.get_ml_confidence_metrics("*")
        
        return {
            "trading_enabled": self.trading_enabled,
            "memory": stats,
            "risk_config": self.risk_config,
            "ml_metrics": ml_metrics,
            "status": "active" if self.trading_enabled else "inactive"
        }
    
    def get_trading_recommendations(self, symbol: str, top_n: int = 3) -> List[Dict]:
        """Get top ML recommendations based on historical performance"""
        
        try:
            profitable_patterns = self.memory.get_profitable_patterns(symbol=symbol, min_trades=2)
            return profitable_patterns[:top_n]
        except Exception as e:
            logger.debug(f"Error getting recommendations: {e}")
            return []
