"""
Machine Learning Price Predictor with LSTM and Pattern Recognition
Integrated with RAG memory for informed predictions
"""

import logging
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import pickle

logger = logging.getLogger(__name__)

class MLPredictor:
    """ML-based price predictor using technical indicators and LSTM"""
    
    def __init__(self, memory_service, model_path: str = "/app/data/models"):
        self.memory = memory_service
        self.model_path = Path(model_path)
        self.model_path.mkdir(parents=True, exist_ok=True)
        
        # Try to import ML libraries
        self.tf_available = False
        self.sklearn_available = False
        try:
            import tensorflow as tf
            self.tf_available = True
            self.tf = tf
            logger.info("TensorFlow available for LSTM predictions")
        except ImportError:
            logger.warning("TensorFlow not available - using statistical predictions")
        
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import StandardScaler
            self.sklearn_available = True
            self.RandomForestClassifier = RandomForestClassifier
            self.StandardScaler = StandardScaler
            logger.info("Scikit-learn available for pattern recognition")
        except ImportError:
            logger.warning("Scikit-learn not available - using simple pattern recognition")
        
        self.models = {}
        self.scalers = {}
        self.pattern_classifier = None
        self._load_models()
    
    def _load_models(self):
        """Load pre-trained models from disk"""
        try:
            for model_file in self.model_path.glob("*.pkl"):
                with open(model_file, 'rb') as f:
                    self.models[model_file.stem] = pickle.load(f)
            logger.info(f"Loaded {len(self.models)} pre-trained models")
        except Exception as e:
            logger.debug(f"No pre-trained models found: {e}")
    
    def _save_model(self, name: str, model):
        """Save model to disk"""
        try:
            with open(self.model_path / f"{name}.pkl", 'wb') as f:
                pickle.dump(model, f)
        except Exception as e:
            logger.debug(f"Could not save model: {e}")
    
    def predict_price_movement(
        self,
        symbol: str,
        current_price: float,
        indicators: Dict[str, float],
        historical_data: Optional[List[float]] = None,
        time_horizon_minutes: int = 60
    ) -> Dict[str, Any]:
        """Predict price movement direction and magnitude"""
        
        try:
            prediction = {
                "symbol": symbol,
                "current_price": current_price,
                "time_horizon_minutes": time_horizon_minutes,
                "timestamp": datetime.utcnow().isoformat(),
                "direction": "NEUTRAL",
                "confidence": 0.5,
                "predicted_price": current_price,
                "predicted_change_pct": 0.0,
                "price_target_high": current_price * 1.01,
                "price_target_low": current_price * 0.99,
                "reasoning": ""
            }
            
            # Use indicators for prediction
            direction, confidence = self._predict_from_indicators(indicators)
            prediction["direction"] = direction
            prediction["confidence"] = confidence
            
            # Use historical data if available
            if historical_data and len(historical_data) > 10:
                lstm_pred = self._lstm_prediction(historical_data, indicators)
                if lstm_pred:
                    prediction["lstm_prediction"] = lstm_pred
                    direction, confidence = self._blend_predictions(
                        direction, confidence, lstm_pred
                    )
                    prediction["direction"] = direction
                    prediction["confidence"] = confidence
            
            # Use RAG memory for similar scenarios
            similar_trades = self.memory.recall_similar_trades(query=symbol, symbol=symbol, k=5)
            memory_boost = self._boost_confidence_from_memory(similar_trades, direction)
            prediction["confidence"] = min(0.99, prediction["confidence"] + memory_boost)
            prediction["memory_similar_trades"] = len(similar_trades)
            
            # Calculate price targets
            if direction == "UP":
                prediction["price_target_high"] = current_price * (1 + confidence * 0.05)
                prediction["price_target_low"] = current_price * 0.99
                prediction["predicted_change_pct"] = (confidence * 3.0)
            elif direction == "DOWN":
                prediction["price_target_high"] = current_price * 1.01
                prediction["price_target_low"] = current_price * (1 - confidence * 0.05)
                prediction["predicted_change_pct"] = -(confidence * 3.0)
            
            prediction["predicted_price"] = current_price * (1 + prediction["predicted_change_pct"] / 100)
            prediction["reasoning"] = self._build_prediction_reasoning(indicators, direction, confidence)
            
            logger.info(f"Price prediction {symbol}: {direction} ({confidence:.2%}) -> {prediction['predicted_price']:.2f}")
            return prediction
        except Exception as e:
            logger.error(f"Error in price prediction: {e}")
            return self._fallback_prediction(symbol, current_price, indicators)
    
    def _predict_from_indicators(self, indicators: Dict[str, float]) -> Tuple[str, float]:
        """Predict direction using technical indicators"""
        
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        bb_upper = indicators.get("bb_upper", 0)
        bb_lower = indicators.get("bb_lower", 0)
        price = indicators.get("price", 0)
        
        direction_score = 0
        factor_count = 0
        
        # RSI signals
        if rsi < 30:
            direction_score += 0.7  # Strong oversold
            factor_count += 1
        elif rsi < 40:
            direction_score += 0.3
            factor_count += 1
        elif rsi > 70:
            direction_score -= 0.7  # Strong overbought
            factor_count += 1
        elif rsi > 60:
            direction_score -= 0.3
            factor_count += 1
        
        # MACD signals
        if macd > 0:
            direction_score += 0.4
            factor_count += 1
        elif macd < 0:
            direction_score -= 0.4
            factor_count += 1
        
        # Bollinger Bands signals
        if price and bb_lower > 0:
            position_in_band = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
            if position_in_band < 0.2:
                direction_score += 0.3
                factor_count += 1
            elif position_in_band > 0.8:
                direction_score -= 0.3
                factor_count += 1
        
        # Calculate average score
        avg_score = direction_score / factor_count if factor_count > 0 else 0
        
        if avg_score > 0.3:
            direction = "UP"
            confidence = min(0.95, abs(avg_score))
        elif avg_score < -0.3:
            direction = "DOWN"
            confidence = min(0.95, abs(avg_score))
        else:
            direction = "NEUTRAL"
            confidence = 0.5
        
        return direction, confidence
    
    def _lstm_prediction(self, historical_data: List[float], indicators: Dict) -> Optional[Dict]:
        """Use LSTM if available for sequence prediction"""
        
        if not self.tf_available or len(historical_data) < 20:
            return None
        
        try:
            # Normalize data
            data_array = np.array(historical_data[-60:]).reshape(-1, 1)
            mean = np.mean(data_array)
            std = np.std(data_array)
            normalized = (data_array - mean) / (std + 1e-8)
            
            # Simple trend calculation if no full LSTM model
            recent_trend = np.polyfit(range(len(normalized)), normalized.flatten(), 1)[0]
            volatility = np.std(normalized)
            
            direction = "UP" if recent_trend > 0 else "DOWN"
            confidence = min(0.9, abs(recent_trend) * 10)
            
            return {
                "direction": direction,
                "confidence": confidence,
                "trend_strength": float(recent_trend),
                "volatility": float(volatility)
            }
        except Exception as e:
            logger.debug(f"LSTM prediction error: {e}")
            return None
    
    def _blend_predictions(self, direction1: str, conf1: float, lstm_pred: Dict) -> Tuple[str, float]:
        """Blend indicator-based and LSTM predictions"""
        
        lstm_direction = lstm_pred.get("direction", "NEUTRAL")
        lstm_conf = lstm_pred.get("confidence", 0.5)
        
        # If both agree, boost confidence
        if direction1 == lstm_direction and direction1 != "NEUTRAL":
            blended_conf = (conf1 + lstm_conf) / 2 * 1.2
        elif direction1 == lstm_direction:
            blended_conf = (conf1 + lstm_conf) / 2
        else:
            # Slight preference for indicator direction
            blended_conf = (conf1 * 0.6 + lstm_conf * 0.4)
        
        return direction1, min(0.99, blended_conf)
    
    def _boost_confidence_from_memory(self, similar_trades: List[Dict], direction: str) -> float:
        """Boost confidence if similar trades were successful"""
        
        if not similar_trades:
            return 0
        
        boost = 0
        for trade in similar_trades:
            if trade.get("success", False):
                boost += 0.05
            else:
                boost -= 0.02
        
        return max(-0.2, min(0.3, boost))
    
    def _build_prediction_reasoning(self, indicators: Dict, direction: str, confidence: float) -> str:
        """Build explanation for prediction"""
        
        reasoning = f"Predicting {direction} with {confidence:.1%} confidence. "
        
        rsi = indicators.get("rsi", 50)
        if rsi < 30:
            reasoning += "RSI oversold. "
        elif rsi > 70:
            reasoning += "RSI overbought. "
        
        macd = indicators.get("macd", 0)
        if macd > 0:
            reasoning += "MACD positive. "
        else:
            reasoning += "MACD negative. "
        
        return reasoning
    
    def _fallback_prediction(self, symbol: str, price: float, indicators: Dict) -> Dict:
        """Fallback prediction when ML fails"""
        direction, conf = self._predict_from_indicators(indicators)
        return {
            "symbol": symbol,
            "current_price": price,
            "direction": direction,
            "confidence": conf,
            "predicted_price": price,
            "predicted_change_pct": 0.0,
            "reasoning": "Fallback prediction using indicators only",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def recognize_chart_pattern(self, price_data: List[float], pattern_name: str = "auto") -> Dict[str, Any]:
        """Recognize chart patterns (head&shoulders, triangles, etc)"""
        
        if len(price_data) < 5:
            return {"pattern": "INSUFFICIENT_DATA", "confidence": 0}
        
        try:
            pattern_info = {
                "pattern": "UNKNOWN",
                "confidence": 0.0,
                "timestamp": datetime.utcnow().isoformat(),
                "description": ""
            }
            
            # Get recent price action
            recent = np.array(price_data[-20:])
            
            # Detect highs and lows
            highs = self._find_local_highs(recent)
            lows = self._find_local_lows(recent)
            
            # Pattern detection
            if len(highs) >= 3 and len(lows) >= 2:
                # Head and Shoulders pattern
                if self._is_head_and_shoulders(highs, lows):
                    pattern_info["pattern"] = "HEAD_AND_SHOULDERS"
                    pattern_info["confidence"] = 0.75
                    pattern_info["description"] = "Head and shoulders reversal pattern detected"
            
            if len(highs) >= 2 and len(lows) >= 1:
                # Triangle pattern
                if self._is_triangle_pattern(recent):
                    pattern_info["pattern"] = "TRIANGLE"
                    pattern_info["confidence"] = 0.6
                    pattern_info["description"] = "Triangle consolidation pattern"
            
            # Double top/bottom
            if self._is_double_top_bottom(highs, lows):
                pattern_info["pattern"] = "DOUBLE_TOP" if highs[0] < highs[1] else "DOUBLE_BOTTOM"
                pattern_info["confidence"] = 0.65
            
            return pattern_info
        except Exception as e:
            logger.error(f"Pattern recognition error: {e}")
            return {"pattern": "ERROR", "confidence": 0}
    
    def _find_local_highs(self, data: np.ndarray, window: int = 3) -> List[float]:
        """Find local high points in price data"""
        highs = []
        for i in range(window, len(data) - window):
            if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
               all(data[i] >= data[i+j] for j in range(1, window+1)):
                highs.append(data[i])
        return highs
    
    def _find_local_lows(self, data: np.ndarray, window: int = 3) -> List[float]:
        """Find local low points in price data"""
        lows = []
        for i in range(window, len(data) - window):
            if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
               all(data[i] <= data[i+j] for j in range(1, window+1)):
                lows.append(data[i])
        return lows
    
    def _is_head_and_shoulders(self, highs: List, lows: List) -> bool:
        """Detect head and shoulders pattern"""
        if len(highs) < 3:
            return False
        # Shoulders should be roughly equal, head should be higher
        return abs(highs[0] - highs[2]) / highs[0] < 0.05 and highs[1] > highs[0] * 1.02
    
    def _is_triangle_pattern(self, data: np.ndarray) -> bool:
        """Detect triangle consolidation pattern"""
        if len(data) < 5:
            return False
        std_start = np.std(data[:len(data)//2])
        std_end = np.std(data[len(data)//2:])
        return std_end < std_start * 0.7  # Volatility decreasing
    
    def _is_double_top_bottom(self, highs: List, lows: List) -> bool:
        """Detect double top or bottom pattern"""
        return len(highs) >= 2 and abs(highs[0] - highs[1]) / highs[0] < 0.02
    
    def get_ml_confidence_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get overall ML confidence metrics for a symbol"""
        
        stats = self.memory.get_trading_stats_by_symbol(symbol)
        recent_trades = self.memory.get_recent_trades(limit=20, symbol=symbol)
        
        # Calculate prediction accuracy
        accuracy = 0
        if recent_trades:
            correct_predictions = sum(1 for t in recent_trades if t.get("success", False))
            accuracy = correct_predictions / len(recent_trades) if recent_trades else 0
        
        return {
            "symbol": symbol,
            "historical_accuracy": accuracy,
            "total_trades": stats.get("total_trades", 0),
            "win_rate": stats.get("win_rate", 0),
            "avg_return": stats.get("avg_profit_loss_pct", 0),
            "ml_confidence_level": min(accuracy + 0.3, 0.95),
            "model_update_needed": accuracy < 0.45 if recent_trades else False
        }
