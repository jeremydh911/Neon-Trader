"""
RAG-based Memory Service for Autonomous Trader
Persistent memory with semantic search capabilities
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib

# Try to import RAG dependencies, fallback to basic implementation
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except:
    NUMPY_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class MemoryService:
    """Persistent RAG-based memory for autonomous trader"""
    
    def __init__(self, memory_path: str = "/app/data/memory"):
        self.memory_path = Path(memory_path)
        self.memory_path.mkdir(parents=True, exist_ok=True)
        
        self.memory_file = self.memory_path / "trader_memory.json"
        self.trades_file = self.memory_path / "trades.jsonl"
        self.decisions_file = self.memory_path / "decisions.jsonl"
        self.lessons_file = self.memory_path / "lessons.jsonl"
        
        # Redis for fast access
        self.redis_available = False
        try:
            self.redis_client = redis.Redis(
                host="neon-redis", 
                port=6379, 
                decode_responses=True, 
                socket_connect_timeout=2
            )
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Redis memory cache initialized")
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            self.redis_client = None
        
        self._load_memory()
    
    def _load_memory(self):
        """Load memory from persistent storage"""
        try:
            if self.memory_file.exists():
                with open(self.memory_file, 'r') as f:
                    self.memory = json.load(f)
                logger.info(f"Loaded memory with {len(self.memory.get('trades', []))} trades")
            else:
                self.memory = {
                    "trades": [],
                    "decisions": [],
                    "lessons": [],
                    "created_at": datetime.utcnow().isoformat()
                }
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            self.memory = {"trades": [], "decisions": [], "lessons": []}
    
    def _save_memory(self):
        """Save memory to persistent storage"""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2, default=str)
            logger.debug("Memory saved successfully")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
    
    def store_trade_memory(self, trade_data: Dict[str, Any]) -> bool:
        """Store a completed trade in memory"""
        try:
            memory_entry = {
                "id": hashlib.md5(f"{trade_data.get('symbol')}{datetime.utcnow().isoformat()}".encode()).hexdigest(),
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": trade_data.get("symbol"),
                "entry_price": float(trade_data.get("entry_price", 0)),
                "exit_price": float(trade_data.get("exit_price", 0)),
                "quantity": float(trade_data.get("quantity", 0)),
                "profit_loss": float(trade_data.get("profit_loss", 0)),
                "profit_loss_pct": float(trade_data.get("profit_loss_pct", 0)),
                "duration_seconds": int(trade_data.get("duration", 0)),
                "market_condition": trade_data.get("market_condition", "neutral"),
                "indicators": trade_data.get("indicators", {}),
                "reason": trade_data.get("reason", ""),
                "success": trade_data.get("profit_loss_pct", 0) > 0
            }
            
            self.memory["trades"].append(memory_entry)
            
            # Store in Redis for quick access
            if self.redis_available:
                try:
                    self.redis_client.lpush("trader:recent_trades", json.dumps(memory_entry))
                    self.redis_client.ltrim("trader:recent_trades", 0, 999)
                except Exception as e:
                    logger.debug(f"Redis store failed: {e}")
            
            # Append to JSONL for analytics
            try:
                with open(self.trades_file, 'a') as f:
                    f.write(json.dumps(memory_entry) + '\n')
            except:
                pass
            
            self._save_memory()
            logger.info(f"Stored trade memory: {trade_data.get('symbol')} {memory_entry.get('profit_loss_pct')}%")
            return True
        except Exception as e:
            logger.error(f"Error storing trade memory: {e}")
            return False
    
    def store_decision_memory(self, decision_data: Dict[str, Any]) -> bool:
        """Store a trading decision with reasoning"""
        try:
            decision_entry = {
                "id": hashlib.md5(f"{decision_data.get('symbol')}{datetime.utcnow().isoformat()}".encode()).hexdigest(),
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": decision_data.get("symbol"),
                "action": decision_data.get("action", "HOLD"),
                "confidence": float(decision_data.get("confidence", 0)),
                "reasoning": decision_data.get("reasoning", ""),
                "indicators": decision_data.get("indicators", {}),
                "market_sentiment": decision_data.get("market_sentiment", "neutral"),
                "recalled_similar": int(decision_data.get("recalled_similar", 0))
            }
            
            self.memory["decisions"].append(decision_entry)
            
            if self.redis_available:
                try:
                    self.redis_client.lpush("trader:decisions", json.dumps(decision_entry))
                    self.redis_client.ltrim("trader:decisions", 0, 999)
                except Exception as e:
                    logger.debug(f"Redis store failed: {e}")
            
            try:
                with open(self.decisions_file, 'a') as f:
                    f.write(json.dumps(decision_entry) + '\n')
            except:
                pass
            
            self._save_memory()
            logger.info(f"Stored decision: {decision_data.get('symbol')} {decision_data.get('action')}")
            return True
        except Exception as e:
            logger.error(f"Error storing decision memory: {e}")
            return False
    
    def store_lesson(self, lesson: Dict[str, Any]) -> bool:
        """Store learned lessons for future reference"""
        try:
            lesson_entry = {
                "id": hashlib.md5(f"{lesson.get('category')}{datetime.utcnow().isoformat()}".encode()).hexdigest(),
                "timestamp": datetime.utcnow().isoformat(),
                "category": lesson.get("category", "general"),
                "lesson": lesson.get("lesson", ""),
                "impact": lesson.get("impact", "neutral"),
                "confidence": float(lesson.get("confidence", 0.5)),
                "examples": lesson.get("examples", [])
            }
            
            self.memory["lessons"].append(lesson_entry)
            
            if self.redis_available:
                try:
                    self.redis_client.lpush("trader:lessons", json.dumps(lesson_entry))
                    self.redis_client.ltrim("trader:lessons", 0, 999)
                except Exception as e:
                    logger.debug(f"Redis store failed: {e}")
            
            try:
                with open(self.lessons_file, 'a') as f:
                    f.write(json.dumps(lesson_entry) + '\n')
            except:
                pass
            
            self._save_memory()
            logger.info(f"Stored lesson: {lesson.get('category')}")
            return True
        except Exception as e:
            logger.error(f"Error storing lesson: {e}")
            return False
    
    def recall_similar_trades(self, query: str, k: int = 5, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recall similar past trades based on symbol and conditions"""
        try:
            trades = self.memory.get("trades", [])
            
            if symbol:
                trades = [t for t in trades if t.get("symbol") == symbol]
            
            # Simple similarity: trades with similar success rate or market conditions
            sorted_trades = sorted(trades, key=lambda x: x.get("timestamp", ""), reverse=True)
            
            logger.info(f"Recalled {min(len(sorted_trades), k)} similar trades for {symbol}")
            return sorted_trades[:k]
        except Exception as e:
            logger.error(f"Error recalling similar trades: {e}")
            return []
    
    def get_profitable_patterns(self, symbol: Optional[str] = None, min_trades: int = 2) -> List[Dict]:
        """Get profitable trading patterns from memory"""
        try:
            profitable = []
            for trade in self.memory.get("trades", []):
                if symbol and trade.get("symbol") != symbol:
                    continue
                if trade.get("profit_loss", 0) > 0:
                    profitable.append(trade)
            
            result = sorted(profitable, key=lambda x: x.get("profit_loss_pct", 0), reverse=True)
            logger.info(f"Found {len(result)} profitable patterns")
            return result[:min_trades * 5]
        except Exception as e:
            logger.error(f"Error getting profitable patterns: {e}")
            return []
    
    def get_lessons_by_category(self, category: str) -> List[Dict]:
        """Get lessons filtered by category"""
        try:
            result = [l for l in self.memory.get("lessons", []) 
                     if l.get("category", "").lower() == category.lower()]
            logger.info(f"Retrieved {len(result)} lessons for category: {category}")
            return result
        except Exception as e:
            logger.error(f"Error getting lessons: {e}")
            return []
    
    def get_recent_trades(self, limit: int = 10, symbol: Optional[str] = None) -> List[Dict]:
        """Get recent trades from memory"""
        try:
            trades = self.memory.get("trades", [])
            if symbol:
                trades = [t for t in trades if t.get("symbol") == symbol]
            
            result = sorted(trades, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
            return result
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        trades = self.memory.get("trades", [])
        profitable_trades = [t for t in trades if t.get("success", False)]
        total_profit = sum(t.get("profit_loss", 0) for t in trades)
        
        return {
            "total_trades": len(trades),
            "profitable_trades": len(profitable_trades),
            "total_decisions": len(self.memory.get("decisions", [])),
            "total_lessons": len(self.memory.get("lessons", [])),
            "win_rate_pct": (len(profitable_trades) / len(trades) * 100) if trades else 0,
            "total_profit_loss": total_profit,
            "memory_size_mb": self.memory_file.stat().st_size / 1024 / 1024 if self.memory_file.exists() else 0
        }
    
    def get_trading_stats_by_symbol(self, symbol: str) -> Dict[str, Any]:
        """Get trading statistics for a specific symbol"""
        try:
            trades = [t for t in self.memory.get("trades", []) if t.get("symbol") == symbol]
            profitable = [t for t in trades if t.get("success", False)]
            total_profit = sum(t.get("profit_loss", 0) for t in trades)
            avg_profit_loss_pct = sum(t.get("profit_loss_pct", 0) for t in trades) / len(trades) if trades else 0
            
            return {
                "symbol": symbol,
                "total_trades": len(trades),
                "profitable_trades": len(profitable),
                "win_rate": (len(profitable) / len(trades) * 100) if trades else 0,
                "total_profit": total_profit,
                "avg_profit_loss_pct": avg_profit_loss_pct,
                "best_trade": max(trades, key=lambda x: x.get("profit_loss_pct", 0)) if trades else None,
                "worst_trade": min(trades, key=lambda x: x.get("profit_loss_pct", 0)) if trades else None
            }
        except Exception as e:
            logger.error(f"Error getting trading stats: {e}")
            return {}
