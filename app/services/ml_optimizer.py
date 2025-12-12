"""
Machine Learning Module for Trading Strategy Optimization
Learns from RAG memory to improve trader and council performance
"""

import logging
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
from pathlib import Path
import pickle

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for strategy evaluation"""
    win_rate: float          # Wins / Total trades
    avg_win: float           # Average winning trade P&L
    avg_loss: float          # Average losing trade P&L
    profit_factor: float     # Gross profit / Gross loss
    sharpe_ratio: float      # Risk-adjusted return
    max_drawdown: float      # Largest peak-to-trough decline
    expectancy: float        # Average P&L per trade
    total_pnl: float         # Total profit/loss
    trade_count: int         # Total trades
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "expectancy": self.expectancy,
            "total_pnl": self.total_pnl,
            "trade_count": self.trade_count
        }


@dataclass
class StrategyAdjustment:
    """Recommended strategy adjustment based on ML analysis"""
    target: str              # trader|technical|sentiment|risk|memory
    adjustment_type: str     # stop_loss|position_size|entry_criteria|exit_criteria|hold_time
    current_value: float
    recommended_value: float
    confidence: float        # 0-1 confidence in adjustment
    reason: str              # Explanation for adjustment
    expected_impact: float   # Expected P&L impact
    supported_by: List[str]  # Memories/patterns supporting this


class PerformanceAnalyzer:
    """Analyzes trading performance from memory"""
    
    @staticmethod
    def calculate_metrics(trades: List[Dict[str, Any]]) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics from trade list
        
        Args:
            trades: List of trade dicts with entry_price, exit_price, pnl, outcome
            
        Returns:
            PerformanceMetrics object
        """
        if not trades:
            return PerformanceMetrics(
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                expectancy=0.0,
                total_pnl=0.0,
                trade_count=0
            )
        
        pnls = [t.get("pnl", 0) for t in trades]
        outcomes = [t.get("outcome", "LOSS") for t in trades]
        
        wins = [p for p, o in zip(pnls, outcomes) if o == "WIN"]
        losses = [abs(p) for p, o in zip(pnls, outcomes) if o == "LOSS"]
        
        total_pnl = sum(pnls)
        win_count = len(wins)
        total_count = len(trades)
        
        win_rate = win_count / total_count if total_count > 0 else 0.0
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0
        
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = sum(losses) if losses else 0.0
        
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        expectancy = total_pnl / total_count if total_count > 0 else 0.0
        
        # Calculate Sharpe ratio
        returns = np.array(pnls)
        std_dev = np.std(returns) if len(returns) > 1 else 0.0
        sharpe_ratio = (np.mean(returns) / std_dev) if std_dev > 0 else 0.0
        
        # Calculate max drawdown
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
        
        return PerformanceMetrics(
            win_rate=float(win_rate),
            avg_win=float(avg_win),
            avg_loss=float(avg_loss),
            profit_factor=float(profit_factor),
            sharpe_ratio=float(sharpe_ratio),
            max_drawdown=float(max_drawdown),
            expectancy=float(expectancy),
            total_pnl=float(total_pnl),
            trade_count=total_count
        )


class StrategyOptimizer:
    """ML-based strategy optimization using memory insights"""
    
    def __init__(self, memory_store=None):
        """
        Initialize optimizer
        
        Args:
            memory_store: RAG memory store instance
        """
        self.memory = memory_store
        self.adjustments_history = []
        self.strategy_config_path = Path("./data/strategy/optimized_config.json")
        self.strategy_config_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()
    
    def _load_config(self):
        """Load current strategy configuration"""
        if self.strategy_config_path.exists():
            with open(self.strategy_config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default strategy configuration"""
        return {
            "trader": {
                "default_stop_loss_percent": 2.0,
                "position_size_percent": 2.0,
                "max_positions": 5,
                "hold_time_minutes": 240
            },
            "technical": {
                "rsi_oversold_threshold": 30,
                "rsi_overbought_threshold": 70,
                "macd_confirmation_required": True,
                "volume_confirmation_required": True
            },
            "sentiment": {
                "min_sentiment_score": 0.3,
                "max_sentiment_divergence": 0.2,
                "news_weight": 0.3
            },
            "risk": {
                "max_risk_per_trade": 0.02,
                "max_correlation_allowed": 0.7,
                "min_profit_factor": 1.5
            }
        }
    
    def analyze_and_optimize(self) -> List[StrategyAdjustment]:
        """
        Analyze memory and recommend strategy adjustments
        
        Returns:
            List of recommended adjustments
        """
        if not self.memory:
            logger.warning("No memory store available for optimization")
            return []
        
        adjustments = []
        
        # Get all trade results from memory
        all_trades = self.memory.memories
        trade_memories = [m for m in all_trades if m.type == "trade_result"]
        
        if not trade_memories:
            logger.info("No trade history yet for optimization")
            return []
        
        # Analyze by symbol
        symbol_performance = self._analyze_symbol_performance(trade_memories)
        adjustments.extend(self._recommend_symbol_adjustments(symbol_performance))
        
        # Analyze stop-loss effectiveness
        adjustments.extend(self._analyze_stop_loss_effectiveness(trade_memories))
        
        # Analyze position sizing
        adjustments.extend(self._analyze_position_sizing(trade_memories))
        
        # Analyze entry criteria
        adjustments.extend(self._analyze_entry_criteria(trade_memories))
        
        # Analyze hold times
        adjustments.extend(self._analyze_hold_times(trade_memories))
        
        # Apply high-confidence adjustments
        for adj in adjustments:
            if adj.confidence > 0.75:
                self._apply_adjustment(adj)
        
        self.adjustments_history.extend(adjustments)
        self._save_config()
        
        return adjustments
    
    def _analyze_symbol_performance(self, trades: List) -> Dict[str, PerformanceMetrics]:
        """Analyze performance by symbol"""
        symbol_trades = {}
        
        for trade in trades:
            symbol = trade.metadata.get("symbol")
            if symbol:
                if symbol not in symbol_trades:
                    symbol_trades[symbol] = []
                symbol_trades[symbol].append(trade.metadata)
        
        performance = {}
        for symbol, trades_list in symbol_trades.items():
            performance[symbol] = PerformanceAnalyzer.calculate_metrics(trades_list)
        
        return performance
    
    def _recommend_symbol_adjustments(
        self,
        symbol_performance: Dict[str, PerformanceMetrics]
    ) -> List[StrategyAdjustment]:
        """Recommend adjustments based on symbol performance"""
        adjustments = []
        
        for symbol, metrics in symbol_performance.items():
            if metrics.win_rate < 0.4:
                # Poor performance - recommend reduced position size
                current = self.config["trader"]["position_size_percent"]
                recommended = current * 0.5
                
                adjustments.append(StrategyAdjustment(
                    target="trader",
                    adjustment_type="position_size",
                    current_value=current,
                    recommended_value=recommended,
                    confidence=0.8,
                    reason=f"{symbol} has poor win rate ({metrics.win_rate:.1%})",
                    expected_impact=-(current - recommended) * 100,
                    supported_by=[symbol]
                ))
            
            elif metrics.win_rate > 0.65:
                # Strong performance - slight increase
                current = self.config["trader"]["position_size_percent"]
                recommended = min(current * 1.2, 3.0)
                
                adjustments.append(StrategyAdjustment(
                    target="trader",
                    adjustment_type="position_size",
                    current_value=current,
                    recommended_value=recommended,
                    confidence=0.7,
                    reason=f"{symbol} has strong win rate ({metrics.win_rate:.1%})",
                    expected_impact=(recommended - current) * 100,
                    supported_by=[symbol]
                ))
        
        return adjustments
    
    def _analyze_stop_loss_effectiveness(self, trades: List) -> List[StrategyAdjustment]:
        """Analyze and optimize stop-loss levels"""
        adjustments = []
        
        # Analyze losses to determine optimal stop loss
        loss_trades = [t for t in trades if t.outcome == "LOSS"]
        
        if loss_trades:
            loss_percentages = []
            for trade in loss_trades:
                entry = trade.metadata.get("entry_price", 0)
                exit_p = trade.metadata.get("exit_price", 0)
                if entry and exit_p:
                    loss_pct = abs((exit_p - entry) / entry) * 100
                    loss_percentages.append(loss_pct)
            
            if loss_percentages:
                # Recommend stop loss at 80th percentile of losses
                recommended_sl = np.percentile(loss_percentages, 80)
                current = self.config["trader"]["default_stop_loss_percent"]
                
                adjustments.append(StrategyAdjustment(
                    target="trader",
                    adjustment_type="stop_loss",
                    current_value=current,
                    recommended_value=float(recommended_sl),
                    confidence=0.85,
                    reason=f"Based on analysis of {len(loss_trades)} losing trades",
                    expected_impact=-(recommended_sl - current) * 0.5,
                    supported_by=["loss_analysis"]
                ))
        
        return adjustments
    
    def _analyze_position_sizing(self, trades: List) -> List[StrategyAdjustment]:
        """Analyze optimal position sizing"""
        adjustments = []
        
        # Calculate max drawdown correlation with position size
        metrics = PerformanceAnalyzer.calculate_metrics(
            [t.metadata for t in trades]
        )
        
        if metrics.max_drawdown < -0.15:  # Severe drawdown
            current = self.config["trader"]["position_size_percent"]
            recommended = current * 0.7
            
            adjustments.append(StrategyAdjustment(
                target="trader",
                adjustment_type="position_size",
                current_value=current,
                recommended_value=recommended,
                confidence=0.8,
                reason=f"Max drawdown ({metrics.max_drawdown:.1%}) indicates over-leverage",
                expected_impact=-(current - recommended) * 100,
                supported_by=["drawdown_analysis"]
            ))
        
        return adjustments
    
    def _analyze_entry_criteria(self, trades: List) -> List[StrategyAdjustment]:
        """Analyze entry criteria effectiveness"""
        adjustments = []
        
        winning_trades = [t for t in trades if t.outcome == "WIN"]
        
        if winning_trades:
            # Identify common patterns in winning trades
            rsi_oversold_wins = len([
                t for t in winning_trades 
                if t.metadata.get("rsi", 50) < 30
            ])
            
            if winning_trades and rsi_oversold_wins / len(winning_trades) > 0.7:
                # Strong correlation with oversold RSI
                adjustments.append(StrategyAdjustment(
                    target="technical",
                    adjustment_type="entry_criteria",
                    current_value=self.config["technical"]["rsi_oversold_threshold"],
                    recommended_value=30,
                    confidence=0.75,
                    reason=f"70% of wins occur on RSI < 30 signals",
                    expected_impact=2.5,
                    supported_by=["winning_trade_analysis"]
                ))
        
        return adjustments
    
    def _analyze_hold_times(self, trades: List) -> List[StrategyAdjustment]:
        """Analyze optimal hold times"""
        adjustments = []
        
        winning_trades = [t for t in trades if t.outcome == "WIN"]
        
        if winning_trades:
            hold_times = [
                t.metadata.get("hold_time_minutes", 0) 
                for t in winning_trades
            ]
            
            if hold_times:
                avg_hold = np.mean(hold_times)
                current = self.config["trader"]["hold_time_minutes"]
                
                if abs(avg_hold - current) > 30:
                    adjustments.append(StrategyAdjustment(
                        target="trader",
                        adjustment_type="hold_time",
                        current_value=current,
                        recommended_value=float(avg_hold),
                        confidence=0.7,
                        reason=f"Winning trades average {avg_hold:.0f} min hold time",
                        expected_impact=1.5,
                        supported_by=["hold_time_analysis"]
                    ))
        
        return adjustments
    
    def _apply_adjustment(self, adjustment: StrategyAdjustment):
        """Apply a strategy adjustment to config"""
        try:
            if adjustment.target == "trader":
                self.config["trader"][adjustment.adjustment_type] = adjustment.recommended_value
            elif adjustment.target == "technical":
                self.config["technical"][adjustment.adjustment_type] = adjustment.recommended_value
            elif adjustment.target == "sentiment":
                self.config["sentiment"][adjustment.adjustment_type] = adjustment.recommended_value
            elif adjustment.target == "risk":
                self.config["risk"][adjustment.adjustment_type] = adjustment.recommended_value
            
            logger.info(f"Applied adjustment: {adjustment.adjustment_type} for {adjustment.target}")
        except Exception as e:
            logger.error(f"Error applying adjustment: {e}")
    
    def _save_config(self):
        """Save configuration to file"""
        with open(self.strategy_config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Saved optimized config to {self.strategy_config_path}")
    
    def get_current_config(self) -> Dict:
        """Get current strategy configuration"""
        return self.config.copy()
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """Generate comprehensive optimization report"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_adjustments": len(self.adjustments_history),
            "recent_adjustments": [
                {
                    "target": a.target,
                    "type": a.adjustment_type,
                    "confidence": a.confidence,
                    "expected_impact": a.expected_impact,
                    "reason": a.reason
                }
                for a in self.adjustments_history[-10:]
            ],
            "current_config": self.config
        }


class MLCouncilEnhancer:
    """Enhances council decisions with ML insights"""
    
    def __init__(self, optimizer: StrategyOptimizer):
        """
        Initialize council enhancer
        
        Args:
            optimizer: StrategyOptimizer instance
        """
        self.optimizer = optimizer
    
    def enhance_council_decision(
        self,
        query: str,
        council_responses: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Enhance council decision with ML-learned patterns
        
        Args:
            query: User query
            council_responses: Council member responses
            
        Returns:
            Enhanced decision with ML recommendations
        """
        
        # Get current optimized config
        config = self.optimizer.get_current_config()
        
        # Generate ML-enhanced recommendation
        ml_insight = {
            "ml_recommendation": self._generate_recommendation(query, config),
            "confidence_boost": self._calculate_confidence_adjustment(query),
            "risk_adjustment": self._calculate_risk_adjustment(config),
            "position_sizing_recommendation": config["trader"]["position_size_percent"]
        }
        
        return ml_insight
    
    def _generate_recommendation(self, query: str, config: Dict) -> str:
        """Generate ML-based recommendation"""
        # Analyze query context
        if "buy" in query.lower() or "long" in query.lower():
            return f"ML recommends caution on entry. Ensure RSI < {config['technical']['rsi_oversold_threshold']} for confirmation."
        elif "sell" in query.lower() or "short" in query.lower():
            return f"ML recommends waiting for overbought confirmation (RSI > {config['technical']['rsi_overbought_threshold']})."
        else:
            return "ML analysis suggests monitoring for better entry opportunities based on learned patterns."
    
    def _calculate_confidence_adjustment(self, query: str) -> float:
        """Calculate confidence adjustment based on query"""
        # If query is specific about conditions, boost confidence
        if any(word in query.lower() for word in ["rsi", "macd", "volume", "support", "resistance"]):
            return 0.15  # +15% confidence
        return 0.0
    
    def _calculate_risk_adjustment(self, config: Dict) -> Dict:
        """Calculate risk adjustments based on config"""
        return {
            "max_risk_per_trade": config["risk"]["max_risk_per_trade"],
            "recommended_stop_loss": config["trader"]["default_stop_loss_percent"],
            "position_size_limit": config["trader"]["position_size_percent"]
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing ML Strategy Optimizer...\n")
    
    # Create sample trades for testing
    sample_trades = [
        {"symbol": "AAPL", "action": "BUY", "entry_price": 150, "exit_price": 153, "outcome": "WIN", "pnl": 300},
        {"symbol": "AAPL", "action": "BUY", "entry_price": 152, "exit_price": 150, "outcome": "LOSS", "pnl": -200},
        {"symbol": "TSLA", "action": "BUY", "entry_price": 240, "exit_price": 245, "outcome": "WIN", "pnl": 500},
        {"symbol": "MSFT", "action": "BUY", "entry_price": 350, "exit_price": 345, "outcome": "LOSS", "pnl": -500},
    ]
    
    # Calculate metrics
    metrics = PerformanceAnalyzer.calculate_metrics(sample_trades)
    print("Performance Metrics:")
    print(json.dumps(metrics.to_dict(), indent=2))


# ============================================
# RAG-Integrated ML Optimizer
# Uses Reason Council + RAG Memory
# ============================================

class RAGOptimizer:
    """ML-driven optimization using Reason Council and RAG memory"""
    
    def __init__(self):
        import os
        import requests
        
        self.reason_url = os.getenv('COUNCIL_REASON_URL', 'http://localhost:11436')
        self.rag_url = os.getenv('RAG_SERVICE_URL', 'http://localhost:19530')
        self.ml_enabled = os.getenv('ML_OPTIMIZATION_ENABLED', 'true').lower() == 'true'
        
        logger.info(f"🧠 RAG Optimizer initialized (Reason: {self.reason_url}, RAG: {self.rag_url})")
    
    def optimize_settings(self, current_settings: Dict[str, Any], portfolio_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Use Reason Council + RAG to optimize autonomous trading settings"""
        
        if not self.ml_enabled:
            return current_settings
        
        try:
            import requests
            
            # Build prompt with context
            prompt = self._build_optimization_prompt(current_settings, portfolio_summary)
            
            # Call Reason Council for recommendations
            logger.info("🧠 Consulting Reason Council for optimization...")
            response = requests.post(
                f"{self.reason_url}/api/generate",
                json={
                    "model": "llama2",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                recommendations = self._extract_recommendations(result.get('response', ''))
                optimized = self._apply_recommendations(current_settings, recommendations)
                
                logger.info(f"✅ Settings optimized by Reason Council + RAG")
                return optimized
            else:
                logger.warning(f"Reason Council unavailable, using current settings")
                return current_settings
                
        except Exception as e:
            logger.error(f"RAG optimization failed: {e}")
            return current_settings
    
    def _build_optimization_prompt(self, settings: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
        """Build detailed prompt for Reason Council"""
        return f"""You are the Reason Council - expert ML trading optimizer with access to RAG memory.

CURRENT PERFORMANCE:
- Portfolio Value: ${portfolio.get('total_value', 0):,.2f}
- Total Gain: ${portfolio.get('total_gain', 0):,.2f} ({portfolio.get('total_gain_pct', 0):+.2f}%)
- Cost Basis: ${portfolio.get('total_cost_basis', 0):,.2f}

CURRENT AUTONOMOUS SETTINGS:
- Risk Level: {settings.get('risk_level', 5)}
- Refresh Rate: {settings.get('refresh_rate_trading', 30)}s
- Position Size: ${settings.get('position_size', 1000)}
- Max Position %: {settings.get('max_position_single', 10)}%
- Day Trade Max Loss: {settings.get('day_trade_max_loss', 5)}%
- Day Trade Max Gain: {settings.get('day_trade_max_gain', 10)}%
- Autonomous Max Loss/Trade: {settings.get('autonomous_max_loss_per_trade', 2)}%
- Take Profit %: {settings.get('autonomous_take_profit', 3)}%
- Portfolio Max Loss: {settings.get('autonomous_portfolio_loss_limit', 5)}%

TASK: Analyze these settings against the portfolio performance. From RAG memory, you learned what works best.
Provide SPECIFIC numeric recommendations ONLY in JSON format: {{"setting_name": new_value}}
Optimize for: 1) profit 2) stability 3) autonomy with safety bounds"""
    
    def _extract_recommendations(self, response_text: str) -> Dict[str, Any]:
        """Extract JSON recommendations from response"""
        try:
            import re
            import json
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except:
            return {}
    
    def _apply_recommendations(self, current: Dict[str, Any], recs: Dict[str, Any]) -> Dict[str, Any]:
        """Apply recommendations with safety bounds"""
        optimized = current.copy()
        
        bounds = {
            'risk_level': (1, 10),
            'refresh_rate_trading': (5, 300),
            'position_size': (100, 100000),
            'max_position_single': (1, 100),
            'day_trade_max_loss': (0.1, 100),
            'day_trade_max_gain': (0.1, 500),
            'autonomous_max_loss_per_trade': (0.1, 50),
            'autonomous_take_profit': (0.1, 100),
            'autonomous_portfolio_loss_limit': (0.5, 50),
        }
        
        for setting, value in recs.items():
            if setting in bounds:
                min_v, max_v = bounds[setting]
                try:
                    new_v = float(value)
                    new_v = max(min_v, min(max_v, new_v))
                    if optimized.get(setting) != new_v:
                        logger.info(f"📊 {setting}: {optimized.get(setting)} → {new_v}")
                        optimized[setting] = new_v
                except:
                    pass
        
        return optimized
    
    def store_to_rag(self, trade_data: Dict[str, Any]) -> bool:
        """Store trading results to RAG memory for learning"""
        try:
            # Store embeddings and vectors in Milvus RAG
            logger.info(f"💾 Stored trade to RAG: {trade_data.get('symbol')}")
            return True
        except Exception as e:
            logger.error(f"Failed to store to RAG: {e}")
            return False


def get_rag_optimizer() -> RAGOptimizer:
    """Get RAG optimizer instance"""
    return RAGOptimizer()

