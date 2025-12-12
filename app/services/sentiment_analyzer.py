"""
Market Sentiment Analyzer
Analyzes market signals and combines with RAG memory for sentiment assessment
"""

import logging
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
import re

logger = logging.getLogger(__name__)

class SentimentAnalyzer:
    """Analyze market sentiment from signals and historical patterns"""
    
    def __init__(self, memory_service, llm_service=None):
        self.memory = memory_service
        self.llm = llm_service
        self.sentiment_history = []
        
        # Try to import NLP library
        self.nltk_available = False
        try:
            from nltk.sentiment import SentimentIntensityAnalyzer
            self.sia = SentimentIntensityAnalyzer()
            self.nltk_available = True
            logger.info("NLTK sentiment analyzer available")
        except ImportError:
            logger.warning("NLTK not available - using rule-based sentiment")
    
    def analyze_market_sentiment(
        self,
        symbol: str,
        indicators: Dict[str, float],
        recent_price_action: Optional[List[float]] = None,
        volume_data: Optional[List[float]] = None,
        news_sentiment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Comprehensive market sentiment analysis"""
        
        try:
            sentiment_scores = {}
            weights = {}
            
            # Analyze technical indicators
            tech_sentiment, tech_confidence = self._analyze_technical_sentiment(indicators)
            sentiment_scores['technical'] = tech_sentiment
            weights['technical'] = 0.35
            
            # Analyze price action
            if recent_price_action and len(recent_price_action) > 5:
                price_sentiment = self._analyze_price_action(recent_price_action)
                sentiment_scores['price_action'] = price_sentiment
                weights['price_action'] = 0.25
            
            # Analyze volume
            if volume_data and len(volume_data) > 5:
                volume_sentiment = self._analyze_volume(volume_data)
                sentiment_scores['volume'] = volume_sentiment
                weights['volume'] = 0.15
            
            # Analyze historical patterns from memory
            memory_sentiment = self._analyze_memory_patterns(symbol)
            sentiment_scores['memory_patterns'] = memory_sentiment
            weights['memory_patterns'] = 0.15
            
            # News sentiment if available
            if news_sentiment:
                news_score = self._analyze_news_sentiment(news_sentiment)
                sentiment_scores['news'] = news_score
                weights['news'] = 0.1
            
            # Calculate weighted sentiment
            total_weight = sum(weights.values())
            weighted_sentiment = sum(
                sentiment_scores.get(key, 0) * weight 
                for key, weight in weights.items()
            ) / total_weight if total_weight > 0 else 0
            
            # Determine overall sentiment
            overall_sentiment = self._interpret_sentiment(weighted_sentiment)
            
            analysis = {
                "symbol": symbol,
                "overall_sentiment": overall_sentiment,
                "sentiment_score": float(weighted_sentiment),
                "timestamp": datetime.utcnow().isoformat(),
                "components": sentiment_scores,
                "confidence": self._calculate_sentiment_confidence(sentiment_scores),
                "reasoning": self._build_sentiment_reasoning(sentiment_scores, overall_sentiment)
            }
            
            self.sentiment_history.append(analysis)
            logger.info(f"Sentiment for {symbol}: {overall_sentiment} ({weighted_sentiment:.2f})")
            return analysis
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return self._fallback_sentiment(symbol)
    
    def _analyze_technical_sentiment(self, indicators: Dict[str, float]) -> Tuple[float, float]:
        """Analyze sentiment from technical indicators"""
        
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        bb_signal = indicators.get("bb_signal", 0)
        atr = indicators.get("atr", 0)
        
        sentiment_score = 0
        factor_count = 0
        
        # RSI analysis
        if rsi < 20:
            sentiment_score += 1.0  # Extremely oversold (bullish)
            factor_count += 1
        elif rsi < 30:
            sentiment_score += 0.7
            factor_count += 1
        elif rsi > 80:
            sentiment_score -= 1.0  # Extremely overbought (bearish)
            factor_count += 1
        elif rsi > 70:
            sentiment_score -= 0.7
            factor_count += 1
        elif 40 <= rsi <= 60:
            sentiment_score += 0.1  # Neutral
            factor_count += 1
        
        # MACD analysis
        if macd > 0:
            sentiment_score += 0.4
            factor_count += 1
        elif macd < -0.5:
            sentiment_score -= 0.5
            factor_count += 1
        
        # Bollinger Bands
        if bb_signal > 0.7:
            sentiment_score -= 0.3  # At upper band
            factor_count += 1
        elif bb_signal < 0.3:
            sentiment_score += 0.3  # At lower band
            factor_count += 1
        
        # ATR for volatility context
        if atr > 2.0:
            sentiment_score *= 1.1  # High volatility amplifies signals
        elif atr < 0.5:
            sentiment_score *= 0.9  # Low volatility reduces signals
        
        avg_sentiment = sentiment_score / factor_count if factor_count > 0 else 0
        confidence = min(0.95, abs(avg_sentiment) * 0.8)
        
        return float(avg_sentiment), float(confidence)
    
    def _analyze_price_action(self, prices: List[float]) -> float:
        """Analyze sentiment from price action patterns"""
        
        if len(prices) < 3:
            return 0.0
        
        sentiment = 0.0
        
        # Recent uptrend/downtrend
        recent_change = (prices[-1] - prices[0]) / prices[0] * 100
        if recent_change > 2:
            sentiment += 0.6
        elif recent_change > 0.5:
            sentiment += 0.3
        elif recent_change < -2:
            sentiment -= 0.6
        elif recent_change < -0.5:
            sentiment -= 0.3
        
        # Volatility
        import numpy as np
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns)
        if volatility > 0.02:
            sentiment *= 1.1  # Higher volatility
        
        # Support/resistance levels
        high = max(prices)
        low = min(prices)
        mid = (high + low) / 2
        
        if prices[-1] > mid and prices[-1] > prices[-2]:
            sentiment += 0.2
        elif prices[-1] < mid and prices[-1] < prices[-2]:
            sentiment -= 0.2
        
        return float(np.clip(sentiment, -1, 1))
    
    def _analyze_volume(self, volumes: List[float]) -> float:
        """Analyze sentiment from volume patterns"""
        
        if len(volumes) < 3:
            return 0.0
        
        import numpy as np
        
        recent_volume = np.mean(volumes[-3:])
        historical_volume = np.mean(volumes[:-3]) if len(volumes) > 3 else recent_volume
        
        sentiment = 0.0
        
        if historical_volume > 0:
            volume_ratio = recent_volume / historical_volume
            if volume_ratio > 1.5:
                sentiment = 0.4  # Bullish high volume
            elif volume_ratio > 1.2:
                sentiment = 0.2
            elif volume_ratio < 0.7:
                sentiment = -0.2  # Bearish low volume
        
        return float(np.clip(sentiment, -1, 1))
    
    def _analyze_memory_patterns(self, symbol: str) -> float:
        """Analyze sentiment from historical trading patterns in memory"""
        
        try:
            stats = self.memory.get_trading_stats_by_symbol(symbol)
            
            win_rate = stats.get("win_rate", 50) / 100
            recent_trades = self.memory.get_recent_trades(limit=5, symbol=symbol)
            
            sentiment = 0.0
            
            # Win rate indicator
            if win_rate > 0.6:
                sentiment += 0.4
            elif win_rate > 0.5:
                sentiment += 0.2
            elif win_rate < 0.4:
                sentiment -= 0.4
            
            # Recent trade results
            if recent_trades:
                recent_wins = sum(1 for t in recent_trades if t.get("success", False))
                recent_win_rate = recent_wins / len(recent_trades)
                if recent_win_rate > win_rate:
                    sentiment += 0.2  # Recent performance improving
                elif recent_win_rate < win_rate:
                    sentiment -= 0.1  # Recent performance declining
            
            return float(np.clip(sentiment, -1, 1))
        except Exception as e:
            logger.debug(f"Memory pattern analysis error: {e}")
            return 0.0
    
    def _analyze_news_sentiment(self, news_text: str) -> float:
        """Analyze sentiment from news text"""
        
        try:
            # Simple keyword-based analysis
            bullish_words = ['surge', 'gain', 'bull', 'strength', 'rise', 'positive', 'profit', 'growth']
            bearish_words = ['fall', 'crash', 'bear', 'weakness', 'loss', 'negative', 'decline', 'cut']
            
            text_lower = news_text.lower()
            
            bullish_score = sum(1 for word in bullish_words if word in text_lower)
            bearish_score = sum(1 for word in bearish_words if word in text_lower)
            
            total = bullish_score + bearish_score
            if total == 0:
                return 0.0
            
            sentiment = (bullish_score - bearish_score) / total
            
            # Use NLTK if available
            if self.nltk_available:
                scores = self.sia.polarity_scores(news_text)
                compound = scores['compound']
                sentiment = sentiment * 0.6 + compound * 0.4
            
            return float(np.clip(sentiment, -1, 1))
        except Exception as e:
            logger.debug(f"News sentiment error: {e}")
            return 0.0
    
    def _interpret_sentiment(self, score: float) -> str:
        """Convert sentiment score to label"""
        
        if score >= 0.6:
            return "very_bullish"
        elif score >= 0.2:
            return "bullish"
        elif score >= -0.2:
            return "neutral"
        elif score >= -0.6:
            return "bearish"
        else:
            return "very_bearish"
    
    def _calculate_sentiment_confidence(self, components: Dict[str, float]) -> float:
        """Calculate confidence in sentiment based on agreement"""
        
        if not components:
            return 0.0
        
        scores = list(components.values())
        if len(scores) < 2:
            return 0.5
        
        # Low variance = high confidence
        import numpy as np
        variance = np.var(scores)
        confidence = 1.0 - variance
        
        return float(np.clip(confidence, 0, 0.95))
    
    def _build_sentiment_reasoning(self, components: Dict[str, float], sentiment: str) -> str:
        """Build explanation for sentiment assessment"""
        
        reasoning = f"Market sentiment is {sentiment.replace('_', ' ')}. "
        
        top_factor = max(components.items(), key=lambda x: abs(x[1]))
        if top_factor[1] > 0:
            reasoning += f"Primary bullish factor: {top_factor[0]}. "
        else:
            reasoning += f"Primary bearish factor: {top_factor[0]}. "
        
        return reasoning
    
    def _fallback_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Fallback sentiment when analysis fails"""
        return {
            "symbol": symbol,
            "overall_sentiment": "neutral",
            "sentiment_score": 0.0,
            "confidence": 0.0,
            "reasoning": "Unable to analyze sentiment",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_sentiment_trend(self, symbol: str, lookback: int = 10) -> Dict[str, Any]:
        """Get sentiment trend over time"""
        
        try:
            recent_sentiments = [
                s for s in self.sentiment_history 
                if s.get("symbol") == symbol
            ][-lookback:]
            
            if not recent_sentiments:
                return {"trend": "insufficient_data", "direction": "neutral"}
            
            scores = [s.get("sentiment_score", 0) for s in recent_sentiments]
            
            import numpy as np
            trend_direction = np.polyfit(range(len(scores)), scores, 1)[0]
            
            if trend_direction > 0.05:
                trend = "improving"
            elif trend_direction < -0.05:
                trend = "declining"
            else:
                trend = "stable"
            
            return {
                "trend": trend,
                "score_change": scores[-1] - scores[0] if len(scores) > 1 else 0,
                "current_score": scores[-1],
                "sample_size": len(scores)
            }
        except Exception as e:
            logger.debug(f"Sentiment trend error: {e}")
            return {"trend": "error", "direction": "neutral"}

# Import numpy at module level for calculations
import numpy as np
