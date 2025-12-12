"""
Pattern Vectorization System
Extracts chart patterns and converts them to embeddings for RAG memory
Date-blind encoding (only charts, patterns, and indicators)
"""

import numpy as np
import logging
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Types of chart patterns"""
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIANGLE = "triangle"
    FLAG = "flag"
    WEDGE = "wedge"
    CUP_AND_HANDLE = "cup_and_handle"
    CHANNEL = "channel"
    SUPPORT_RESISTANCE = "support_resistance"


@dataclass
class Pattern:
    """A recognized chart pattern"""
    type: PatternType
    strength: float  # 0-1
    vector: np.ndarray  # Vector representation
    indicators_state: Dict[str, float]
    predicted_direction: str  # "UP", "DOWN", "NEUTRAL"
    confidence: float  # 0-1
    metadata: Dict[str, Any]


class PatternVectorizer:
    """Converts chart patterns to vector embeddings"""
    
    def __init__(self, embedding_dim: int = 64):
        self.embedding_dim = embedding_dim
        self.pattern_cache = {}
        
        # Pattern characteristics (what makes each pattern unique)
        self.pattern_signatures = {
            PatternType.UPTREND: np.array([1.0, 0.1, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6] + [0]*56),
            PatternType.DOWNTREND: np.array([0.0, 0.8, 0.7, 0.2, 0.7, 0.3, 0.6, 0.4] + [0]*56),
            PatternType.HEAD_AND_SHOULDERS: np.array([0.5, 0.5, 0.9, 0.5, 0.4, 0.6, 0.7, 0.3] + [0]*56),
            PatternType.DOUBLE_TOP: np.array([0.7, 0.3, 0.8, 0.4, 0.5, 0.5, 0.3, 0.7] + [0]*56),
            PatternType.DOUBLE_BOTTOM: np.array([0.3, 0.7, 0.2, 0.6, 0.5, 0.5, 0.7, 0.3] + [0]*56),
            PatternType.TRIANGLE: np.array([0.5, 0.5, 0.6, 0.5, 0.8, 0.4, 0.5, 0.5] + [0]*56),
            PatternType.FLAG: np.array([0.6, 0.4, 0.7, 0.4, 0.5, 0.6, 0.6, 0.4] + [0]*56),
            PatternType.WEDGE: np.array([0.55, 0.45, 0.65, 0.45, 0.7, 0.5, 0.55, 0.45] + [0]*56),
            PatternType.CUP_AND_HANDLE: np.array([0.4, 0.6, 0.5, 0.6, 0.6, 0.4, 0.8, 0.2] + [0]*56),
            PatternType.CHANNEL: np.array([0.5, 0.5, 0.5, 0.5, 0.4, 0.6, 0.5, 0.5] + [0]*56),
            PatternType.SUPPORT_RESISTANCE: np.array([0.5, 0.5, 0.3, 0.7, 0.9, 0.2, 0.5, 0.5] + [0]*56),
        }
    
    def extract_patterns_from_candles(
        self,
        candles: List[Dict[str, float]],
        indicators: Optional[Dict[str, List[float]]] = None
    ) -> List[Pattern]:
        """
        Extract all recognizable patterns from candlestick data
        Input: Only OHLCV data and indicators (NO dates)
        """
        patterns = []
        
        if len(candles) < 5:
            return patterns
        
        # Extract dates are removed - only work with sequence position
        closes = np.array([c.get("close", c.get("c", 0)) for c in candles])
        highs = np.array([c.get("high", c.get("h", 0)) for c in candles])
        lows = np.array([c.get("low", c.get("l", 0)) for c in candles])
        volumes = np.array([c.get("volume", c.get("v", 0)) for c in candles])
        
        # Normalize indicators if provided
        ind_state = {}
        if indicators:
            ind_state = {
                "rsi": indicators.get("rsi", [50]*len(closes))[-1],
                "macd": indicators.get("macd", [0]*len(closes))[-1],
                "bb_position": indicators.get("bb_position", [0.5]*len(closes))[-1],
            }
        
        # Detect patterns at different timescales
        # Short-term patterns (5-20 candles)
        patterns.extend(self._detect_trends(closes[-20:], ind_state))
        patterns.extend(self._detect_reversals(closes[-20:], highs[-20:], lows[-20:], ind_state))
        
        # Medium-term patterns (20-50 candles)
        if len(closes) >= 20:
            patterns.extend(self._detect_formations(closes[-50:], highs[-50:], lows[-50:], ind_state))
        
        # Volume-based patterns
        patterns.extend(self._detect_volume_patterns(closes[-20:], volumes[-20:], ind_state))
        
        return patterns
    
    def _detect_trends(self, closes: np.ndarray, ind_state: Dict) -> List[Pattern]:
        """Detect uptrend/downtrend patterns"""
        patterns = []
        
        # Check for uptrend: each close higher than previous
        if len(closes) >= 5:
            diffs = np.diff(closes)
            uptrend_strength = np.mean(diffs[diffs > 0]) / np.mean(np.abs(diffs)) if np.mean(np.abs(diffs)) > 0 else 0
            
            if np.sum(diffs > 0) >= len(diffs) * 0.7:  # 70% up moves
                vector = self._encode_indicator_state(ind_state, PatternType.UPTREND)
                patterns.append(Pattern(
                    type=PatternType.UPTREND,
                    strength=min(1.0, uptrend_strength),
                    vector=vector,
                    indicators_state=ind_state,
                    predicted_direction="UP",
                    confidence=min(1.0, np.sum(diffs > 0) / len(diffs)),
                    metadata={"consecutive_up_candles": int(np.sum(diffs > 0))}
                ))
            
            # Check for downtrend
            downtrend_strength = np.mean(np.abs(diffs[diffs < 0])) / np.mean(np.abs(diffs)) if np.mean(np.abs(diffs)) > 0 else 0
            if np.sum(diffs < 0) >= len(diffs) * 0.7:
                vector = self._encode_indicator_state(ind_state, PatternType.DOWNTREND)
                patterns.append(Pattern(
                    type=PatternType.DOWNTREND,
                    strength=min(1.0, downtrend_strength),
                    vector=vector,
                    indicators_state=ind_state,
                    predicted_direction="DOWN",
                    confidence=min(1.0, np.sum(diffs < 0) / len(diffs)),
                    metadata={"consecutive_down_candles": int(np.sum(diffs < 0))}
                ))
        
        return patterns
    
    def _detect_reversals(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        ind_state: Dict
    ) -> List[Pattern]:
        """Detect reversal patterns (head & shoulders, double top/bottom)"""
        patterns = []
        
        if len(closes) < 5:
            return patterns
        
        # Head and Shoulders: high, higher high, medium high
        if (closes[-5] < closes[-3] and closes[-3] > closes[-1] and 
            closes[-4] < closes[-2] and closes[-2] > closes[-4]):
            vector = self._encode_indicator_state(ind_state, PatternType.HEAD_AND_SHOULDERS)
            patterns.append(Pattern(
                type=PatternType.HEAD_AND_SHOULDERS,
                strength=0.7,
                vector=vector,
                indicators_state=ind_state,
                predicted_direction="DOWN",
                confidence=0.6,
                metadata={"last_5_candles_pattern": "H&S"}
            ))
        
        # Double Top: high, drop, high again, drop
        local_max_indices = self._find_local_extrema(closes, "max")
        if len(local_max_indices) >= 2:
            top1, top2 = closes[local_max_indices[-2]], closes[local_max_indices[-1]]
            if abs(top1 - top2) / top1 < 0.05:  # Within 5% of each other
                vector = self._encode_indicator_state(ind_state, PatternType.DOUBLE_TOP)
                patterns.append(Pattern(
                    type=PatternType.DOUBLE_TOP,
                    strength=0.8,
                    vector=vector,
                    indicators_state=ind_state,
                    predicted_direction="DOWN",
                    confidence=0.7,
                    metadata={"top_similarity": abs(top1 - top2) / top1}
                ))
        
        # Double Bottom
        local_min_indices = self._find_local_extrema(closes, "min")
        if len(local_min_indices) >= 2:
            bot1, bot2 = closes[local_min_indices[-2]], closes[local_min_indices[-1]]
            if abs(bot1 - bot2) / bot1 < 0.05:
                vector = self._encode_indicator_state(ind_state, PatternType.DOUBLE_BOTTOM)
                patterns.append(Pattern(
                    type=PatternType.DOUBLE_BOTTOM,
                    strength=0.8,
                    vector=vector,
                    indicators_state=ind_state,
                    predicted_direction="UP",
                    confidence=0.7,
                    metadata={"bottom_similarity": abs(bot1 - bot2) / bot1}
                ))
        
        return patterns
    
    def _detect_formations(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        ind_state: Dict
    ) -> List[Pattern]:
        """Detect chart formations (triangles, flags, wedges)"""
        patterns = []
        
        if len(closes) < 10:
            return patterns
        
        # Calculate high and low range over period
        high_range = highs.max()
        low_range = lows.min()
        total_range = high_range - low_range
        
        if total_range == 0:
            return patterns
        
        # Triangle: highs decreasing, lows increasing
        recent_highs = highs[-10:]
        recent_lows = lows[-10:]
        
        high_trend = np.diff(recent_highs)
        low_trend = np.diff(recent_lows)
        
        if np.sum(high_trend < 0) > 5 and np.sum(low_trend > 0) > 5:
            vector = self._encode_indicator_state(ind_state, PatternType.TRIANGLE)
            patterns.append(Pattern(
                type=PatternType.TRIANGLE,
                strength=0.75,
                vector=vector,
                indicators_state=ind_state,
                predicted_direction="UP" if closes[-1] > closes[-5] else "DOWN",
                confidence=0.65,
                metadata={"range_compression": (high_range - low_range) / high_range}
            ))
        
        # Flag: small range after big move
        if len(closes) >= 20:
            recent_range = (highs[-5:].max() - lows[-5:].min()) / closes[-5]
            prior_range = (highs[-15:-5].max() - lows[-15:-5].min()) / closes[-10]
            
            if recent_range < prior_range * 0.5:
                vector = self._encode_indicator_state(ind_state, PatternType.FLAG)
                patterns.append(Pattern(
                    type=PatternType.FLAG,
                    strength=0.8,
                    vector=vector,
                    indicators_state=ind_state,
                    predicted_direction="UP" if np.mean(np.diff(closes[-15:-5])) > 0 else "DOWN",
                    confidence=0.75,
                    metadata={"consolidation_ratio": recent_range / prior_range}
                ))
        
        return patterns
    
    def _detect_volume_patterns(
        self,
        closes: np.ndarray,
        volumes: np.ndarray,
        ind_state: Dict
    ) -> List[Pattern]:
        """Detect volume-based patterns"""
        patterns = []
        
        # High volume breakout
        avg_volume = np.mean(volumes)
        if len(volumes) > 0 and volumes[-1] > avg_volume * 1.5:
            direction = "UP" if closes[-1] > closes[-2] else "DOWN"
            vector = self._encode_indicator_state(ind_state, PatternType.FLAG)
            patterns.append(Pattern(
                type=PatternType.FLAG,
                strength=0.6,
                vector=vector,
                indicators_state=ind_state,
                predicted_direction=direction,
                confidence=0.5,
                metadata={"volume_ratio": volumes[-1] / avg_volume}
            ))
        
        return patterns
    
    def _find_local_extrema(self, data: np.ndarray, extrema_type: str) -> List[int]:
        """Find local maxima or minima"""
        indices = []
        
        for i in range(1, len(data) - 1):
            if extrema_type == "max":
                if data[i] > data[i-1] and data[i] > data[i+1]:
                    indices.append(i)
            else:  # min
                if data[i] < data[i-1] and data[i] < data[i+1]:
                    indices.append(i)
        
        return indices
    
    def _encode_indicator_state(self, ind_state: Dict, pattern_type: PatternType) -> np.ndarray:
        """Encode current indicator state + pattern signature"""
        vector = np.zeros(self.embedding_dim)
        
        # Start with pattern signature
        if pattern_type in self.pattern_signatures:
            vector[:len(self.pattern_signatures[pattern_type])] = self.pattern_signatures[pattern_type]
        
        # Encode RSI
        rsi = ind_state.get("rsi", 50)
        vector[8] = rsi / 100.0
        
        # Encode MACD
        macd = ind_state.get("macd", 0)
        vector[9] = np.tanh(macd / 10.0)  # Normalize to [-1, 1]
        
        # Encode Bollinger Band position
        bb_pos = ind_state.get("bb_position", 0.5)
        vector[10] = bb_pos
        
        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        return vector
    
    def similarity(self, pattern1: Pattern, pattern2: Pattern) -> float:
        """Calculate similarity between two patterns (0-1)"""
        if pattern1.type == pattern2.type:
            # Same pattern type gets base similarity
            type_similarity = 0.6
        else:
            type_similarity = 0.0
        
        # Vector similarity (cosine)
        vector_dot = np.dot(pattern1.vector, pattern2.vector)
        vector_similarity = (vector_dot + 1) / 2  # Convert from [-1,1] to [0,1]
        
        # Direction match
        direction_match = 1.0 if pattern1.predicted_direction == pattern2.predicted_direction else 0.3
        
        # Combine
        total_similarity = (
            type_similarity * 0.4 +
            vector_similarity * 0.4 +
            direction_match * 0.2
        )
        
        return min(1.0, max(0.0, total_similarity))
    
    def find_similar_patterns(
        self,
        pattern: Pattern,
        pattern_memory: List[Pattern],
        threshold: float = 0.7
    ) -> List[Tuple[Pattern, float]]:
        """Find similar patterns from memory"""
        similar = []
        
        for stored_pattern in pattern_memory:
            sim = self.similarity(pattern, stored_pattern)
            if sim >= threshold:
                similar.append((stored_pattern, sim))
        
        # Sort by similarity (descending)
        similar.sort(key=lambda x: x[1], reverse=True)
        
        return similar


class PatternMemoryRAG:
    """RAG memory for storing and retrieving patterns"""
    
    def __init__(self, vectorizer: PatternVectorizer):
        self.vectorizer = vectorizer
        self.pattern_memory: List[Pattern] = []
        self.symbol_patterns: Dict[str, List[Pattern]] = {}
        self.pattern_outcomes: Dict[int, Dict[str, Any]] = {}  # Pattern ID -> outcome
    
    def store_pattern(self, symbol: str, pattern: Pattern, outcome: Optional[Dict] = None):
        """Store a pattern with optional outcome"""
        pattern_id = len(self.pattern_memory)
        self.pattern_memory.append(pattern)
        
        if symbol not in self.symbol_patterns:
            self.symbol_patterns[symbol] = []
        self.symbol_patterns[symbol].append(pattern)
        
        if outcome:
            self.pattern_outcomes[pattern_id] = outcome
    
    def retrieve_similar_patterns(
        self,
        pattern: Pattern,
        symbol: Optional[str] = None,
        top_k: int = 5
    ) -> List[Tuple[Pattern, float, Optional[Dict]]]:
        """Retrieve similar patterns with their outcomes"""
        search_space = self.symbol_patterns.get(symbol, []) if symbol else self.pattern_memory
        
        similar = self.vectorizer.find_similar_patterns(pattern, search_space)[:top_k]
        
        results = []
        for pat, sim in similar:
            pattern_id = self.pattern_memory.index(pat) if pat in self.pattern_memory else -1
            outcome = self.pattern_outcomes.get(pattern_id)
            results.append((pat, sim, outcome))
        
        return results
    
    def get_pattern_statistics(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics about stored patterns"""
        patterns = self.symbol_patterns.get(symbol, []) if symbol else self.pattern_memory
        
        if not patterns:
            return {}
        
        successful_outcomes = sum(
            1 for outcome in self.pattern_outcomes.values()
            if outcome and outcome.get("profit_percent", 0) > 0
        )
        
        return {
            "total_patterns": len(patterns),
            "pattern_types": len(set(p.type for p in patterns)),
            "successful_outcomes": successful_outcomes,
            "win_rate": successful_outcomes / len(self.pattern_outcomes) if self.pattern_outcomes else 0,
            "avg_confidence": np.mean([p.confidence for p in patterns]),
            "avg_strength": np.mean([p.strength for p in patterns])
        }
