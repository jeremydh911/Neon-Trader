"""
Simulation Loop Engine
Runs iterative backtests with strategy adjustments
Optimizes for maximum score through reinforcement learning
"""

import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)


class SimulationLoopEngine:
    """Manages simulation loops for strategy optimization"""
    
    def __init__(self, ml_training_system, max_concurrent_loops: int = 1):
        self.ml_training = ml_training_system
        self.max_concurrent_loops = max_concurrent_loops
        self.active_loops: Dict[str, 'LoopState'] = {}
        self.loop_history: List[Dict[str, Any]] = []
    
    def start_optimization_loop(
        self,
        symbol: str,
        historical_data: List[Dict[str, Any]],
        max_iterations: int = 100,
        convergence_threshold: float = 99999.0,
        early_stop_patience: int = 10
    ) -> 'LoopState':
        """
        Start a new optimization loop for a symbol
        
        Loop runs:
        1. Simulate trading on historical data
        2. Score the strategy
        3. Adjust parameters
        4. Run again until convergence or max iterations
        
        Returns LoopState object for monitoring
        """
        
        if len(self.active_loops) >= self.max_concurrent_loops:
            logger.warning(f"Max concurrent loops ({self.max_concurrent_loops}) reached")
            return None
        
        loop_state = LoopState(
            symbol=symbol,
            max_iterations=max_iterations,
            convergence_threshold=convergence_threshold,
            early_stop_patience=early_stop_patience
        )
        
        self.active_loops[symbol] = loop_state
        
        logger.info(f"Starting optimization loop for {symbol}")
        logger.info(f"  Max iterations: {max_iterations}")
        logger.info(f"  Convergence threshold: {convergence_threshold}")
        logger.info(f"  Early stop patience: {early_stop_patience}")
        
        return loop_state
    
    def run_loop_iteration(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Run a single iteration of optimization loop"""
        
        if symbol not in self.active_loops:
            logger.error(f"No active loop for {symbol}")
            return None
        
        loop_state = self.active_loops[symbol]
        
        if loop_state.is_complete():
            logger.info(f"Loop for {symbol} already complete")
            return loop_state.get_summary()
        
        iteration = loop_state.current_iteration
        logger.info(f"Running iteration {iteration + 1}/{loop_state.max_iterations} for {symbol}")
        
        # Run backtest and get score
        try:
            score, trades, metrics = self._run_backtest(symbol)
            
            # Record iteration results
            iteration_result = {
                "iteration": iteration,
                "score": score,
                "trades_executed": len(trades),
                "winning_trades": sum(1 for t in trades if t.get("profit_percent", 0) > 0),
                "metrics": metrics,
                "parameters": dict(self.ml_training.strategy_params),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            loop_state.add_iteration_result(iteration_result)
            
            # Update best score
            if score > loop_state.best_score:
                loop_state.best_score = score
                loop_state.best_params = dict(self.ml_training.strategy_params)
                loop_state.iterations_without_improvement = 0
                logger.info(f"New best score: {score}")
            else:
                loop_state.iterations_without_improvement += 1
            
            # Check convergence
            if score >= loop_state.convergence_threshold:
                logger.info(f"CONVERGENCE REACHED! Score: {score}")
                loop_state.converged = True
                loop_state.end_loop()
                self._finalize_loop(symbol, loop_state)
                return loop_state.get_summary()
            
            # Check early stopping
            if loop_state.iterations_without_improvement >= loop_state.early_stop_patience:
                logger.info(f"Early stopping: No improvement for {loop_state.early_stop_patience} iterations")
                loop_state.end_loop()
                self._finalize_loop(symbol, loop_state)
                return loop_state.get_summary()
            
            # Adjust strategy for next iteration
            if not loop_state.is_complete():
                self._adjust_strategy(symbol, iteration_result)
            
            return iteration_result
        
        except Exception as e:
            logger.error(f"Error in loop iteration for {symbol}: {e}")
            loop_state.error = str(e)
            loop_state.end_loop()
            return None
    
    def run_loop_to_completion(
        self,
        symbol: str,
        historical_data: List[Dict[str, Any]],
        max_iterations: int = 100,
        convergence_threshold: float = 99999.0,
        log_interval: int = 5
    ) -> Dict[str, Any]:
        """Run complete optimization loop synchronously"""
        
        loop_state = self.start_optimization_loop(
            symbol,
            historical_data,
            max_iterations,
            convergence_threshold
        )
        
        if not loop_state:
            return {"error": "Could not start loop"}
        
        while not loop_state.is_complete() and loop_state.current_iteration < max_iterations:
            iteration_result = self.run_loop_iteration(symbol)
            
            if iteration_result is None:
                break
            
            if (loop_state.current_iteration + 1) % log_interval == 0:
                logger.info(f"Loop progress: {loop_state.current_iteration + 1}/{max_iterations} "
                           f"Best: {loop_state.best_score:.2f}")
        
        summary = loop_state.get_summary()
        self.loop_history.append(summary)
        
        return summary
    
    def _run_backtest(self, symbol: str) -> Tuple[float, List[Dict], Dict[str, Any]]:
        """Run a backtest and return score"""
        # Get historical data (would come from data service)
        trades = []
        score = 0
        
        # Simulate trades based on current strategy
        # This would use the actual trading logic
        
        metrics = {
            "total_trades": len(trades),
            "winning_trades": sum(1 for t in trades if t.get("profit_percent", 0) > 0),
            "average_profit": np.mean([t.get("profit_percent", 0) for t in trades]) if trades else 0,
            "max_profit": max([t.get("profit_percent", 0) for t in trades]) if trades else 0,
            "min_profit": min([t.get("profit_percent", 0) for t in trades]) if trades else 0,
        }
        
        if trades:
            for trade in trades:
                trade_score = self.ml_training.score_trade(
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
                score += trade_score["score"]
        
        return score, trades, metrics
    
    def _adjust_strategy(self, symbol: str, iteration_result: Dict):
        """Adjust strategy parameters based on iteration results"""
        metrics = iteration_result.get("metrics", {})
        trades = metrics.get("total_trades", 0)
        winning = metrics.get("winning_trades", 0)
        
        if trades == 0:
            return
        
        win_rate = winning / trades
        avg_profit = metrics.get("average_profit", 0)
        
        # If win rate is high, increase confidence threshold
        if win_rate > 0.65:
            self.ml_training.strategy_params["confidence_threshold"] = min(
                0.95,
                self.ml_training.strategy_params["confidence_threshold"] + 0.02
            )
        
        # If win rate is low, decrease confidence threshold
        elif win_rate < 0.45:
            self.ml_training.strategy_params["confidence_threshold"] = max(
                0.50,
                self.ml_training.strategy_params["confidence_threshold"] - 0.02
            )
        
        # Adjust based on average profit
        if avg_profit > 2.0:
            self.ml_training.strategy_params["position_size_multiplier"] = min(
                2.0,
                self.ml_training.strategy_params["position_size_multiplier"] * 1.05
            )
        elif avg_profit < -1.0:
            self.ml_training.strategy_params["position_size_multiplier"] = max(
                0.5,
                self.ml_training.strategy_params["position_size_multiplier"] * 0.95
            )
        
        logger.info(f"Strategy adjusted: win_rate={win_rate:.2%}, avg_profit={avg_profit:.2f}%")
    
    def _finalize_loop(self, symbol: str, loop_state: 'LoopState'):
        """Finalize loop and save best strategy"""
        # Apply best parameters found
        self.ml_training.strategy_params = loop_state.best_params
        self.ml_training.save_config()
        
        logger.info(f"Loop finalized for {symbol}: {loop_state.get_summary()}")
    
    def get_loop_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current status of optimization loop"""
        if symbol not in self.active_loops:
            return None
        
        return self.active_loops[symbol].get_status()
    
    def stop_loop(self, symbol: str):
        """Stop an active loop"""
        if symbol in self.active_loops:
            self.active_loops[symbol].end_loop()
            logger.info(f"Loop stopped for {symbol}")
    
    def get_all_loop_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all active loops"""
        return {
            symbol: loop.get_status()
            for symbol, loop in self.active_loops.items()
        }


class LoopState:
    """Tracks state of a single optimization loop"""
    
    def __init__(
        self,
        symbol: str,
        max_iterations: int,
        convergence_threshold: float,
        early_stop_patience: int
    ):
        self.symbol = symbol
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.early_stop_patience = early_stop_patience
        
        self.current_iteration = 0
        self.best_score = -float('inf')
        self.best_params = {}
        self.converged = False
        self.error = None
        self.iterations_without_improvement = 0
        
        self.start_time = datetime.utcnow()
        self.end_time = None
        self.iteration_results: List[Dict] = []
    
    def add_iteration_result(self, result: Dict):
        """Record an iteration result"""
        self.iteration_results.append(result)
        self.current_iteration += 1
    
    def is_complete(self) -> bool:
        """Check if loop is complete"""
        return (
            self.end_time is not None or
            self.converged or
            self.current_iteration >= self.max_iterations
        )
    
    def end_loop(self):
        """Mark loop as ended"""
        self.end_time = datetime.utcnow()
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        end = self.end_time or datetime.utcnow()
        delta = end - self.start_time
        return delta.total_seconds()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        return {
            "symbol": self.symbol,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "best_score": self.best_score,
            "converged": self.converged,
            "progress_percent": (self.current_iteration / self.max_iterations) * 100,
            "elapsed_seconds": self.get_elapsed_time(),
            "iterations_without_improvement": self.iterations_without_improvement,
            "error": self.error
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get complete summary of loop results"""
        elapsed = self.get_elapsed_time()
        
        if not self.iteration_results:
            return {
                "symbol": self.symbol,
                "status": "no_results",
                "error": self.error
            }
        
        scores = [r["score"] for r in self.iteration_results]
        
        return {
            "symbol": self.symbol,
            "total_iterations": self.current_iteration,
            "converged": self.converged,
            "best_score": self.best_score,
            "final_score": scores[-1] if scores else 0,
            "score_history": scores,
            "elapsed_seconds": elapsed,
            "average_iteration_time": elapsed / max(self.current_iteration, 1),
            "iterations_without_improvement": self.iterations_without_improvement,
            "best_parameters": self.best_params,
            "final_iteration_details": self.iteration_results[-1] if self.iteration_results else None,
            "improvement_percent": ((self.best_score - scores[0]) / abs(scores[0])) * 100 if scores[0] != 0 else 0,
            "timestamp": datetime.utcnow().isoformat()
        }


class MultiSymbolOptimizer:
    """Manages optimization across multiple symbols"""
    
    def __init__(self, simulation_loop_engine: SimulationLoopEngine):
        self.engine = simulation_loop_engine
        self.symbol_queue: List[str] = []
        self.completed_symbols: Dict[str, Dict[str, Any]] = {}
    
    def queue_symbols(self, symbols: List[str]):
        """Queue symbols for optimization"""
        self.symbol_queue.extend(symbols)
        logger.info(f"Queued {len(symbols)} symbols for optimization")
    
    def run_sequential_optimization(self, historical_data_map: Dict[str, List[Dict]]):
        """Run optimization sequentially for all queued symbols"""
        while self.symbol_queue:
            symbol = self.symbol_queue.pop(0)
            
            if symbol not in historical_data_map:
                logger.warning(f"No historical data for {symbol}")
                continue
            
            logger.info(f"Starting optimization for {symbol}")
            
            result = self.engine.run_loop_to_completion(
                symbol,
                historical_data_map[symbol],
                max_iterations=100
            )
            
            self.completed_symbols[symbol] = result
            
            logger.info(f"Completed optimization for {symbol}: {result['best_score']}")
    
    def get_best_strategies(self) -> Dict[str, Dict]:
        """Get best strategies across all completed symbols"""
        return {
            symbol: result.get("best_parameters", {})
            for symbol, result in self.completed_symbols.items()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all optimizations"""
        if not self.completed_symbols:
            return {"status": "no_completions"}
        
        scores = [r.get("best_score", 0) for r in self.completed_symbols.values()]
        
        return {
            "total_symbols": len(self.completed_symbols),
            "best_overall_score": max(scores) if scores else 0,
            "average_best_score": np.mean(scores) if scores else 0,
            "completed_symbols": list(self.completed_symbols.keys()),
            "symbol_scores": {
                symbol: result.get("best_score", 0)
                for symbol, result in self.completed_symbols.items()
            }
        }
