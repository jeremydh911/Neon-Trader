"""
Strategy RAG Memory Helper Module

Provides easy access functions for ML System and Autonomous Trader
to retrieve and utilize saved training strategies from RAG memory.
"""

import logging
from typing import Dict, List, Any, Optional
from services.rag_memory import RAGMemoryStore, MemoryEntry

logger = logging.getLogger(__name__)


class StrategyRAGHelper:
    """Helper class for accessing training strategies from RAG memory"""
    
    def __init__(self, rag_memory: RAGMemoryStore):
        """
        Initialize the helper with a RAG memory store instance
        
        Args:
            rag_memory: RAGMemoryStore instance
        """
        self.memory = rag_memory
    
    def get_best_strategies(
        self,
        symbol: Optional[str] = None,
        limit: int = 5,
        min_win_rate: float = 0.0
    ) -> List[MemoryEntry]:
        """
        Get the best saved training strategies
        
        Args:
            symbol: Stock symbol to filter by (optional)
            limit: Maximum strategies to return
            min_win_rate: Minimum win rate threshold
            
        Returns:
            List of best training strategies
        """
        tags = ["strategy", "best"]
        if symbol:
            tags.append(symbol)
        
        strategies = self.memory.search_by_tags(tags=tags, limit=limit * 2)
        
        # Filter by win rate if specified
        if min_win_rate > 0:
            strategies = [
                s for s in strategies
                if s.metadata.get('win_rate', 0) >= min_win_rate
            ]
        
        return strategies[:limit]
    
    def get_strategies_for_symbol(
        self,
        symbol: str,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Get all saved training strategies for a specific symbol
        
        Args:
            symbol: Stock symbol
            limit: Maximum strategies to return
            
        Returns:
            List of strategies for the symbol
        """
        return self.memory.search_by_tags(
            tags=["strategy", symbol],
            limit=limit
        )
    
    def get_strategies_by_training_mode(
        self,
        mode: str,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Get strategies filtered by training mode
        
        Args:
            mode: Training mode (e.g., 'paper_trading', 'backtest')
            limit: Maximum strategies to return
            
        Returns:
            List of strategies matching the mode
        """
        mode_tag = mode.lower().replace(" ", "_")
        return self.memory.search_by_tags(
            tags=["strategy", mode_tag],
            limit=limit
        )
    
    def get_highest_scoring_strategy(
        self,
        symbol: Optional[str] = None
    ) -> Optional[MemoryEntry]:
        """
        Get the single highest-scoring strategy
        
        Args:
            symbol: Stock symbol to filter by (optional)
            
        Returns:
            The highest-scoring strategy or None
        """
        strategies = self.get_best_strategies(symbol=symbol, limit=1)
        return strategies[0] if strategies else None
    
    def get_strategy_parameters(
        self,
        strategy: MemoryEntry
    ) -> Dict[str, Any]:
        """
        Extract trading parameters from a strategy
        
        Args:
            strategy: MemoryEntry representing a strategy
            
        Returns:
            Dictionary of strategy parameters
        """
        if not strategy or not strategy.metadata:
            return {}
        
        return strategy.metadata.get('parameters', {})
    
    def get_ml_learning_strategies(self, limit: int = 10) -> List[MemoryEntry]:
        """
        Get strategies available for ML system learning
        
        Args:
            limit: Maximum strategies to return
            
        Returns:
            List of strategies for ML learning
        """
        return self.memory.search_by_tags(
            tags=["ml_learning", "strategy"],
            limit=limit
        )
    
    def get_autonomous_trader_strategies(self, limit: int = 10) -> List[MemoryEntry]:
        """
        Get strategies available for autonomous trader use
        
        Args:
            limit: Maximum strategies to return
            
        Returns:
            List of strategies for autonomous trading
        """
        return self.memory.search_by_tags(
            tags=["autonomous_trader_learning", "strategy"],
            limit=limit
        )
    
    def get_high_confidence_strategies(
        self,
        win_rate_threshold: float = 0.60,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Get high-confidence strategies above win rate threshold
        
        Args:
            win_rate_threshold: Minimum win rate (0.0-1.0)
            limit: Maximum strategies to return
            
        Returns:
            List of high-confidence strategies
        """
        all_strategies = self.memory.search_by_tags(
            tags=["strategy", "best"],
            limit=limit * 3
        )
        
        high_confidence = [
            s for s in all_strategies
            if s.metadata.get('win_rate', 0) >= win_rate_threshold
        ]
        
        # Sort by win rate descending
        high_confidence.sort(
            key=lambda x: x.metadata.get('win_rate', 0),
            reverse=True
        )
        
        return high_confidence[:limit]
    
    def get_strategy_summary(self, strategy: MemoryEntry) -> Dict[str, Any]:
        """
        Get a summary of strategy performance
        
        Args:
            strategy: MemoryEntry representing a strategy
            
        Returns:
            Dictionary with strategy summary
        """
        if not strategy or not strategy.metadata:
            return {}
        
        meta = strategy.metadata
        return {
            "symbol": meta.get('symbol'),
            "best_score": meta.get('best_score'),
            "final_score": meta.get('final_score'),
            "win_rate": meta.get('win_rate'),
            "winning_trades": meta.get('winning_trades'),
            "total_iterations": meta.get('total_iterations'),
            "training_mode": meta.get('training_mode'),
            "parameters": meta.get('parameters'),
            "timestamp": strategy.timestamp
        }
    
    def get_strategies_by_score_range(
        self,
        min_score: float,
        max_score: Optional[float] = None,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """
        Get strategies within a score range
        
        Args:
            min_score: Minimum best score
            max_score: Maximum best score (optional)
            limit: Maximum strategies to return
            
        Returns:
            List of strategies in score range
        """
        all_strategies = self.memory.search_by_tags(
            tags=["strategy"],
            limit=limit * 2
        )
        
        filtered = []
        for strategy in all_strategies:
            score = strategy.metadata.get('best_score', 0)
            if score >= min_score:
                if max_score is None or score <= max_score:
                    filtered.append(strategy)
        
        return filtered[:limit]
    
    def search_strategies(
        self,
        query: str,
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Search for strategies using natural language
        
        Args:
            query: Natural language query
            limit: Maximum results to return
            
        Returns:
            List of matching strategies
        """
        results = self.memory.search(
            query=query,
            limit=limit,
            memory_type="decision"
        )
        
        # Filter to only strategy entries
        return [r for r in results if "strategy" in r.tags]
    
    def apply_strategy_to_system(
        self,
        strategy: MemoryEntry,
        target_system: Any
    ) -> bool:
        """
        Apply a saved strategy's parameters to a trading system
        
        Args:
            strategy: MemoryEntry representing a strategy
            target_system: The system to apply parameters to (ML or Trader)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            parameters = self.get_strategy_parameters(strategy)
            if not parameters:
                logger.warning("No parameters found in strategy")
                return False
            
            # Apply parameters to the system
            if hasattr(target_system, 'strategy_params'):
                target_system.strategy_params.update(parameters)
                logger.info(f"Applied strategy parameters: {parameters}")
                return True
            else:
                logger.error("Target system does not support parameter updates")
                return False
        
        except Exception as e:
            logger.error(f"Error applying strategy: {e}")
            return False
    
    def get_strategy_effectiveness_metrics(
        self,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregate effectiveness metrics for strategies
        
        Args:
            symbol: Stock symbol to filter by (optional)
            
        Returns:
            Dictionary with aggregate metrics
        """
        strategies = self.get_strategies_for_symbol(symbol) if symbol else self.memory.search_by_tags(
            tags=["strategy"],
            limit=100
        )
        
        if not strategies:
            return {}
        
        scores = [s.metadata.get('best_score', 0) for s in strategies]
        win_rates = [s.metadata.get('win_rate', 0) for s in strategies]
        
        return {
            "total_strategies": len(strategies),
            "avg_best_score": sum(scores) / len(scores) if scores else 0,
            "max_best_score": max(scores) if scores else 0,
            "min_best_score": min(scores) if scores else 0,
            "avg_win_rate": sum(win_rates) / len(win_rates) if win_rates else 0,
            "max_win_rate": max(win_rates) if win_rates else 0,
            "min_win_rate": min(win_rates) if win_rates else 0,
            "strategies": [self.get_strategy_summary(s) for s in strategies[:5]]
        }


# Usage Examples
if __name__ == "__main__":
    from services.rag_memory import get_memory_store
    
    # Initialize helper
    memory = get_memory_store()
    helper = StrategyRAGHelper(memory)
    
    print("=" * 70)
    print("STRATEGY RAG HELPER EXAMPLES")
    print("=" * 70)
    
    # Example 1: Get best strategies
    print("\n1. Getting best strategies:")
    best = helper.get_best_strategies(limit=3)
    for strategy in best:
        summary = helper.get_strategy_summary(strategy)
        print(f"   - {summary['symbol']}: Score={summary['best_score']}, WinRate={summary['win_rate']:.1%}")
    
    # Example 2: Get strategies for ML system
    print("\n2. Getting strategies for ML learning:")
    ml_strategies = helper.get_ml_learning_strategies(limit=3)
    print(f"   Found {len(ml_strategies)} strategies available for ML learning")
    
    # Example 3: Get high confidence strategies
    print("\n3. Getting high-confidence strategies (>60% win rate):")
    high_conf = helper.get_high_confidence_strategies(win_rate_threshold=0.60, limit=3)
    for strategy in high_conf:
        summary = helper.get_strategy_summary(strategy)
        print(f"   - {summary['symbol']}: WinRate={summary['win_rate']:.1%}")
    
    # Example 4: Search strategies
    print("\n4. Searching for AAPL strategies:")
    search_results = helper.search_strategies("AAPL best strategy", limit=3)
    print(f"   Found {len(search_results)} matching strategies")
    
    # Example 5: Get effectiveness metrics
    print("\n5. Overall strategy effectiveness metrics:")
    metrics = helper.get_strategy_effectiveness_metrics()
    print(f"   Total strategies: {metrics.get('total_strategies', 0)}")
    print(f"   Avg win rate: {metrics.get('avg_win_rate', 0):.1%}")
    print(f"   Max best score: {metrics.get('max_best_score', 0):.2f}")
    
    print("\n" + "=" * 70)
