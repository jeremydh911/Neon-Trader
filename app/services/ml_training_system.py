"""
ML Training System for Autonomous Trader
Enables continuous learning with backtest simulation loops
Scores strategies and iteratively improves them
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
from collections import defaultdict
import pickle
import os

logger = logging.getLogger(__name__)


class MLTrainingSystem:
    """Manages ML training, learning, and strategy optimization"""
    
    def __init__(self, memory_service, data_service, config_path: str = "/app/data/ml_training.json"):
        self.memory = memory_service
        self.data = data_service
        self.config_path = config_path
        
        # Scoring system
        self.scores = defaultdict(float)
        self.strategy_history = []
        self.training_results = []
        
        # Learning configuration
        self.learning_config = {
            "max_iterations": 100,
            "min_improvement_threshold": 0.01,  # 1% improvement required
            "learning_rate": 0.05,
            "strategy_adjustment_magnitude": 0.1,
            "enable_pattern_learning": True,
            "enable_risk_adaptation": True,
            "enable_sentiment_learning": True
        }
        
        # Current strategy parameters (learnable)
        self.strategy_params = {
            "rsi_threshold_oversold": 30,
            "rsi_threshold_overbought": 70,
            "macd_signal_strength": 0.5,
            "bollinger_band_std_dev": 2.0,
            "moving_avg_period": 20,
            "take_profit_percent": 2.0,
            "stop_loss_percent": 1.0,
            "confidence_threshold": 0.65,
            "position_size_multiplier": 1.0,
            "sentiment_weight": 0.3,
            "pattern_weight": 0.4,
            "technical_weight": 0.3
        }
        
        # Scoring thresholds
        self.scoring_rules = {
            "winning_trade": 100,
            "trade_5_percent_gain": 200,
            "trade_5_5_percent_gain": 499,
            "loss_penalty": -50,
            "skipped_opportunity": -10,
            "pattern_recognition": 25,
            "successful_risk_management": 75
        }
        
        self.load_config()
    
    def load_config(self):
        """Load saved training configuration"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    self.strategy_params.update(data.get("strategy_params", {}))
                    self.learning_config.update(data.get("learning_config", {}))
                    self.scores = defaultdict(float, data.get("scores", {}))
                    self.strategy_history = data.get("strategy_history", [])
                    logger.info("ML training config loaded")
            except Exception as e:
                logger.error(f"Error loading config: {e}")
    
    def save_config(self):
        """Save training configuration"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            config_data = {
                "strategy_params": self.strategy_params,
                "learning_config": self.learning_config,
                "scores": dict(self.scores),
                "strategy_history": self.strategy_history,
                "timestamp": datetime.utcnow().isoformat()
            }
            with open(self.config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            logger.info("ML training config saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def score_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        action: str,
        entry_time: datetime,
        exit_time: datetime,
        indicators_at_entry: Dict[str, Any],
        was_pattern_recognized: bool = False,
        risk_managed_well: bool = False
    ) -> Dict[str, Any]:
        """
        Score a trade based on profitability and strategy effectiveness
        
        Scoring Rules:
        - Winning trade: +100
        - 5%+ gain: +200
        - 5.5%+ gain: +499
        - Loss: -50
        - Skipped opportunity: -10
        - Pattern recognition: +25
        - Good risk management: +75
        """
        
        score = 0
        profit_percent = ((exit_price - entry_price) / entry_price) * 100
        
        # Base profit scoring
        if action == "SELL":
            if exit_price > entry_price:
                score += self.scoring_rules["winning_trade"]
                
                if profit_percent >= 5.5:
                    score += self.scoring_rules["trade_5_5_percent_gain"]
                elif profit_percent >= 5.0:
                    score += self.scoring_rules["trade_5_percent_gain"]
            else:
                score += self.scoring_rules["loss_penalty"]
        
        # Pattern and risk bonus
        if was_pattern_recognized:
            score += self.scoring_rules["pattern_recognition"]
        
        if risk_managed_well:
            score += self.scoring_rules["successful_risk_management"]
        
        # Penalize missed opportunities
        if action == "HOLD" and profit_percent > 3.0:
            score += self.scoring_rules["skipped_opportunity"]
        
        trade_record = {
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "profit_percent": profit_percent,
            "score": score,
            "action": action,
            "entry_time": entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time,
            "exit_time": exit_time.isoformat() if isinstance(exit_time, datetime) else exit_time,
            "pattern_recognized": was_pattern_recognized,
            "risk_managed": risk_managed_well,
            "indicators_at_entry": indicators_at_entry,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.scores[symbol] += score
        self.strategy_history.append(trade_record)
        
        return trade_record
    
    def train_on_historical_data(
        self,
        symbol: str,
        historical_data: List[Dict[str, Any]],
        date_blind: bool = True
    ) -> Dict[str, Any]:
        """
        Train strategy on historical data without learning dates
        
        Args:
            symbol: Stock ticker
            historical_data: List of OHLCV candles
            date_blind: If True, don't use date info (only patterns/charts)
        
        Returns:
            Training results with score and strategy adjustments
        """
        
        if date_blind:
            # Remove date information from training data
            for candle in historical_data:
                candle.pop('date', None)
                candle.pop('timestamp', None)
                candle.pop('time', None)
        
        training_result = {
            "symbol": symbol,
            "iteration": 0,
            "initial_score": 0,
            "final_score": 0,
            "trades_executed": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "strategy_adjustments": {},
            "patterns_learned": [],
            "timestamp": datetime.utcnow().isoformat(),
            "data_points_processed": len(historical_data)
        }
        
        try:
            # Simulate trading on historical data
            trades = self._simulate_trading(symbol, historical_data)
            training_result["trades_executed"] = len(trades)
            
            # Score each trade
            total_score = 0
            for trade in trades:
                trade_score_result = self.score_trade(
                    symbol=symbol,
                    entry_price=trade.get("entry_price", 0),
                    exit_price=trade.get("exit_price", 0),
                    action=trade.get("action", "HOLD"),
                    entry_time=datetime.utcnow(),
                    exit_time=datetime.utcnow(),
                    indicators_at_entry=trade.get("indicators", {}),
                    was_pattern_recognized=trade.get("pattern_recognized", False),
                    risk_managed_well=trade.get("risk_managed", False)
                )
                total_score += trade_score_result["score"]
                
                if trade_score_result["profit_percent"] > 0:
                    training_result["winning_trades"] += 1
                else:
                    training_result["losing_trades"] += 1
            
            training_result["initial_score"] = total_score
            training_result["final_score"] = total_score
            
            # Learn patterns from data
            patterns = self._extract_patterns(symbol, historical_data)
            training_result["patterns_learned"] = patterns[:5]  # Top 5 patterns
            
            # Store in memory
            if self.memory:
                for pattern in patterns:
                    self.memory.store_pattern(symbol, pattern)
            
            logger.info(f"Training complete for {symbol}: Score={total_score}, Trades={len(trades)}")
            
        except Exception as e:
            logger.error(f"Error during training for {symbol}: {e}")
        
        self.training_results.append(training_result)
        return training_result
    
    def run_optimization_loop(
        self,
        symbol: str,
        historical_data: List[Dict[str, Any]],
        max_iterations: int = None
    ) -> Dict[str, Any]:
        """
        Run iterative optimization loop:
        1. Train on data
        2. Calculate score
        3. Adjust strategy
        4. Repeat until perfect or max iterations
        """
        
        if max_iterations is None:
            max_iterations = self.learning_config["max_iterations"]
        
        optimization_results = {
            "symbol": symbol,
            "iterations": [],
            "best_score": 0,
            "best_params": dict(self.strategy_params),
            "final_score": 0,
            "converged": False,
            "total_iterations": 0
        }
        
        previous_score = 0
        no_improvement_count = 0
        max_no_improvement = 5
        
        for iteration in range(max_iterations):
            logger.info(f"Optimization iteration {iteration + 1}/{max_iterations} for {symbol}")
            
            # Train on data
            training_result = self.train_on_historical_data(symbol, historical_data, date_blind=True)
            current_score = training_result["final_score"]
            
            iteration_result = {
                "iteration": iteration,
                "score": current_score,
                "params": dict(self.strategy_params),
                "winning_trades": training_result["winning_trades"],
                "trades_executed": training_result["trades_executed"]
            }
            optimization_results["iterations"].append(iteration_result)
            
            # Check improvement
            improvement = current_score - previous_score
            if improvement >= self.learning_config["min_improvement_threshold"]:
                no_improvement_count = 0
                logger.info(f"Score improved: {previous_score:.2f} → {current_score:.2f} (+{improvement:.2f})")
            else:
                no_improvement_count += 1
                logger.info(f"No improvement: {previous_score:.2f} → {current_score:.2f}")
            
            # Update best score
            if current_score > optimization_results["best_score"]:
                optimization_results["best_score"] = current_score
                optimization_results["best_params"] = dict(self.strategy_params)
            
            # Check for convergence (perfect score)
            if current_score >= 99999:  # Theoretical perfect score
                optimization_results["converged"] = True
                logger.info(f"Perfect score reached! Score: {current_score}")
                break
            
            # Early stopping if no improvement
            if no_improvement_count >= max_no_improvement:
                logger.info("Early stopping: No improvement for 5 iterations")
                break
            
            # Adjust strategy for next iteration
            if iteration < max_iterations - 1:
                self._adjust_strategy_parameters(symbol, training_result)
            
            previous_score = current_score
            optimization_results["total_iterations"] = iteration + 1
        
        optimization_results["final_score"] = optimization_results["best_score"]
        
        # Save best parameters
        self.strategy_params = optimization_results["best_params"]
        self.save_config()
        
        logger.info(f"Optimization complete: {optimization_results['total_iterations']} iterations, "
                   f"Best score: {optimization_results['best_score']}")
        
        return optimization_results
    
    def _simulate_trading(self, symbol: str, historical_data: List[Dict]) -> List[Dict[str, Any]]:
        """Simulate trading on historical data"""
        trades = []
        position = None
        
        for i, candle in enumerate(historical_data):
            # Extract price and indicators
            price = candle.get("close", candle.get("c", 0))
            high = candle.get("high", candle.get("h", price))
            low = candle.get("low", candle.get("l", price))
            
            # Calculate indicators (simplified)
            indicators = self._calculate_indicators(candle)
            
            # Generate trading signal
            action, confidence = self._generate_signal(indicators)
            
            # Execute trade
            if action == "BUY" and not position and confidence > self.strategy_params["confidence_threshold"]:
                position = {
                    "entry_price": price,
                    "entry_index": i,
                    "confidence": confidence
                }
            
            elif action == "SELL" and position:
                if price > position["entry_price"] or (i - position["entry_index"] > 10):
                    trade = {
                        "entry_price": position["entry_price"],
                        "exit_price": price,
                        "action": "SELL",
                        "profit_percent": ((price - position["entry_price"]) / position["entry_price"]) * 100,
                        "indicators": indicators,
                        "pattern_recognized": confidence > 0.8,
                        "risk_managed": price > (position["entry_price"] * (1 - 0.01 * self.strategy_params["stop_loss_percent"]))
                    }
                    trades.append(trade)
                    position = None
        
        return trades
    
    def _calculate_indicators(self, candle: Dict[str, Any]) -> Dict[str, float]:
        """Calculate technical indicators from candle"""
        return {
            "close": candle.get("close", candle.get("c", 0)),
            "high": candle.get("high", candle.get("h", 0)),
            "low": candle.get("low", candle.get("l", 0)),
            "volume": candle.get("volume", candle.get("v", 0)),
            "rsi": candle.get("rsi", 50),
            "macd": candle.get("macd", 0),
            "macd_signal": candle.get("macd_signal", 0),
            "bb_upper": candle.get("bb_upper", 0),
            "bb_lower": candle.get("bb_lower", 0),
        }
    
    def _generate_signal(self, indicators: Dict[str, float]) -> Tuple[str, float]:
        """Generate trading signal from indicators"""
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        
        confidence = 0.5
        action = "HOLD"
        
        # RSI-based signals
        if rsi < self.strategy_params["rsi_threshold_oversold"]:
            action = "BUY"
            confidence = min(0.9, (30 - rsi) / 30)
        elif rsi > self.strategy_params["rsi_threshold_overbought"]:
            action = "SELL"
            confidence = min(0.9, (rsi - 70) / 30)
        
        return action, confidence
    
    def _extract_patterns(self, symbol: str, historical_data: List[Dict]) -> List[Dict[str, Any]]:
        """Extract repeating patterns from historical data"""
        patterns = []
        
        # Simple pattern detection (can be enhanced with ML)
        for i in range(2, len(historical_data) - 5):
            window = historical_data[i:i+5]
            closes = [c.get("close", c.get("c", 0)) for c in window]
            
            # Detect uptrend
            if all(closes[j] < closes[j+1] for j in range(len(closes)-1)):
                patterns.append({
                    "type": "uptrend",
                    "strength": 0.9,
                    "length": 5
                })
            # Detect downtrend
            elif all(closes[j] > closes[j+1] for j in range(len(closes)-1)):
                patterns.append({
                    "type": "downtrend",
                    "strength": 0.9,
                    "length": 5
                })
        
        return patterns
    
    def _adjust_strategy_parameters(self, symbol: str, training_result: Dict):
        """Adjust strategy parameters based on training results"""
        learning_rate = self.learning_config["learning_rate"]
        adjustment_mag = self.learning_config["strategy_adjustment_magnitude"]
        
        # Adjust based on win rate
        win_rate = training_result["winning_trades"] / max(training_result["trades_executed"], 1)
        
        if win_rate > 0.6:
            # Increase confidence threshold if already winning
            self.strategy_params["confidence_threshold"] = min(
                0.9,
                self.strategy_params["confidence_threshold"] + (learning_rate * 0.05)
            )
        elif win_rate < 0.4:
            # Loosen confidence threshold if losing
            self.strategy_params["confidence_threshold"] = max(
                0.5,
                self.strategy_params["confidence_threshold"] - (learning_rate * 0.05)
            )
        
        # Adjust RSI thresholds
        if win_rate > 0.6:
            self.strategy_params["rsi_threshold_oversold"] = max(
                20,
                self.strategy_params["rsi_threshold_oversold"] - (learning_rate * 2)
            )
        
        # Adjust position size
        self.strategy_params["position_size_multiplier"] = min(
            2.0,
            max(0.5, self.strategy_params["position_size_multiplier"] * (1 + (win_rate - 0.5) * adjustment_mag))
        )
        
        logger.info(f"Strategy adjusted for {symbol}: win_rate={win_rate:.2%}")
    
    def get_current_strategy_score(self) -> float:
        """Get overall score for current strategy"""
        return sum(self.scores.values())
    
    def get_symbol_score(self, symbol: str) -> float:
        """Get score for specific symbol"""
        return self.scores.get(symbol, 0)
    
    def get_learning_metrics(self) -> Dict[str, Any]:
        """Get overall learning metrics"""
        if not self.strategy_history:
            return {}
        
        total_trades = len(self.strategy_history)
        winning_trades = sum(1 for t in self.strategy_history if t["profit_percent"] > 0)
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": winning_trades / total_trades if total_trades > 0 else 0,
            "average_profit_percent": np.mean([t["profit_percent"] for t in self.strategy_history]),
            "total_score": self.get_current_strategy_score(),
            "best_symbol_score": max(self.scores.values()) if self.scores else 0,
            "strategy_params": self.strategy_params,
            "training_iterations": len(self.training_results)
        }
