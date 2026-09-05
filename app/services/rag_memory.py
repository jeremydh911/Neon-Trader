"""
RAG Memory System for Trading Council and Autonomous Trader
Stores and retrieves previous discussions, decisions, and trading history
"""

import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import hashlib
from pathlib import Path
import pickle

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Single memory entry for discussions and decisions"""
    id: str
    timestamp: str
    type: str  # 'discussion', 'decision', 'trade_result', 'pattern'
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    council_votes: Optional[Dict[str, str]] = None
    outcome: Optional[str] = None
    relevance_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


class VectorEmbedder:
    """Simple vector embedding for text similarity"""
    
    @staticmethod
    def embed(text: str) -> List[float]:
        """
        Create simple embedding from text
        In production, use proper embedding models (e.g., sentence-transformers)
        """
        # Simple TF-IDF-like embedding for demo
        words = text.lower().split()
        # Create a simple hash-based vector representation
        vector = []
        for i in range(768):  # Standard embedding dimension
            hash_val = hashlib.md5(f"{i}".encode()).digest()
            value = 0.0
            for j, word in enumerate(words):
                word_hash = int(hashlib.md5(word.encode()).hexdigest(), 16)
                value += ((word_hash ^ int.from_bytes(hash_val[:4], 'big')) / (2**32)) / (j + 1)
            vector.append(value % 1.0)
        return vector
    
    @staticmethod
    def similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between vectors"""
        if not vec1 or not vec2:
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)


class RAGMemoryStore:
    """
    RAG Memory Store for trading discussions and decisions
    Stores memories with embeddings for semantic search
    """
    
    def __init__(self, storage_path: str = "./data/memory"):
        """
        Initialize memory store
        
        Args:
            storage_path: Path to store memory files
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.memories: List[MemoryEntry] = []
        self.embeddings: Dict[str, List[float]] = {}
        self.embedder = VectorEmbedder()
        
        self.memories_file = self.storage_path / "memories.json"
        self.embeddings_file = self.storage_path / "embeddings.pkl"
        
        self._load_memories()
    
    def _load_memories(self):
        """Load memories from disk"""
        try:
            if self.memories_file.exists():
                with open(self.memories_file, 'r') as f:
                    data = json.load(f)
                    self.memories = [MemoryEntry(**m) for m in data]
                logger.info(f"Loaded {len(self.memories)} memories from disk")
            
            if self.embeddings_file.exists():
                with open(self.embeddings_file, 'rb') as f:
                    self.embeddings = pickle.load(f)
                logger.info(f"Loaded {len(self.embeddings)} embeddings from disk")
        except Exception as e:
            logger.error(f"Error loading memories: {e}")
    
    def _save_memories(self):
        """Save memories to disk"""
        try:
            with open(self.memories_file, 'w') as f:
                json.dump([m.to_dict() for m in self.memories], f, indent=2)
            
            with open(self.embeddings_file, 'wb') as f:
                pickle.dump(self.embeddings, f)
        except Exception as e:
            logger.error(f"Error saving memories: {e}")
    
    def add_discussion(
        self,
        content: str,
        council_votes: Optional[Dict[str, str]] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Add a discussion to memory
        
        Args:
            content: Discussion content
            council_votes: Votes from council members
            tags: Tags for categorization
            
        Returns:
            Memory entry ID
        """
        memory_id = self._generate_id()
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.utcnow().isoformat(),
            type="discussion",
            content=content,
            council_votes=council_votes,
            tags=tags or []
        )
        
        self.memories.append(entry)
        self.embeddings[memory_id] = self.embedder.embed(content)
        
        self._save_memories()
        logger.info(f"Added discussion memory: {memory_id}")
        
        return memory_id
    
    def add_decision(
        self,
        content: str,
        outcome: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Add a trading decision to memory
        
        Args:
            content: Decision content
            outcome: Trade outcome (if known)
            metadata: Additional metadata
            tags: Tags for categorization
            
        Returns:
            Memory entry ID
        """
        memory_id = self._generate_id()
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.utcnow().isoformat(),
            type="decision",
            content=content,
            outcome=outcome,
            metadata=metadata or {},
            tags=tags or []
        )
        
        self.memories.append(entry)
        self.embeddings[memory_id] = self.embedder.embed(content)
        
        self._save_memories()
        logger.info(f"Added decision memory: {memory_id}")
        
        return memory_id
    
    def add_trade_result(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        exit_price: Optional[float],
        outcome: str,
        pnl: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a trade result to memory
        
        Args:
            symbol: Stock symbol
            action: BUY, SELL, HOLD
            entry_price: Entry price
            exit_price: Exit price (if closed)
            outcome: WIN, LOSS, BREAKEVEN
            pnl: Profit/loss amount
            metadata: Additional metadata
            
        Returns:
            Memory entry ID
        """
        memory_id = self._generate_id()
        
        content = f"{symbol} {action} @ {entry_price}"
        if exit_price:
            content += f" → {exit_price} ({outcome})"
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.utcnow().isoformat(),
            type="trade_result",
            content=content,
            outcome=outcome,
            metadata={
                "symbol": symbol,
                "action": action,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                **(metadata or {})
            },
            tags=["trade", symbol, action.lower()]
        )
        
        self.memories.append(entry)
        self.embeddings[memory_id] = self.embedder.embed(content)
        
        self._save_memories()
        logger.info(f"Added trade result memory: {memory_id}")
        
        return memory_id
    
    def search(
        self,
        query: str,
        limit: int = 5,
        time_limit: Optional[int] = None,
        memory_type: Optional[str] = None
    ) -> List[MemoryEntry]:
        """
        Search memories using semantic similarity
        
        Args:
            query: Search query
            limit: Maximum results to return
            time_limit: Only return memories from last N days
            memory_type: Filter by memory type
            
        Returns:
            List of relevant memory entries
        """
        if not self.memories:
            return []
        
        query_embedding = self.embedder.embed(query)
        results = []
        
        cutoff_date = None
        if time_limit:
            cutoff_date = (datetime.utcnow() - timedelta(days=time_limit)).isoformat()
        
        for memory in self.memories:
            # Filter by time
            if cutoff_date and memory.timestamp < cutoff_date:
                continue
            
            # Filter by type
            if memory_type and memory.type != memory_type:
                continue
            
            # Calculate similarity
            if memory.id in self.embeddings:
                similarity = self.embedder.similarity(query_embedding, self.embeddings[memory.id])
                memory.relevance_score = similarity
                results.append(memory)
        
        # Sort by relevance and return top results
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]
    
    def search_by_tags(
        self,
        tags: List[str],
        limit: int = 5
    ) -> List[MemoryEntry]:
        """
        Search memories by tags
        
        Args:
            tags: Tags to search for
            limit: Maximum results
            
        Returns:
            List of matching memory entries
        """
        results = []
        for memory in self.memories:
            if any(tag in memory.tags for tag in tags):
                results.append(memory)
        
        return results[:limit]
    
    def get_recent_decisions(self, limit: int = 5) -> List[MemoryEntry]:
        """Get recent trading decisions"""
        decisions = [m for m in self.memories if m.type == "decision"]
        decisions.sort(key=lambda x: x.timestamp, reverse=True)
        return decisions[:limit]
    
    def get_successful_trades(self, symbol: Optional[str] = None) -> List[MemoryEntry]:
        """Get successful trade results"""
        trades = [m for m in self.memories if m.type == "trade_result" and m.outcome == "WIN"]
        
        if symbol:
            trades = [m for m in trades if m.metadata.get("symbol") == symbol]
        
        return trades
    
    def get_failed_trades(self, symbol: Optional[str] = None) -> List[MemoryEntry]:
        """Get failed trade results"""
        trades = [m for m in self.memories if m.type == "trade_result" and m.outcome == "LOSS"]
        
        if symbol:
            trades = [m for m in trades if m.metadata.get("symbol") == symbol]
        
        return trades
    
    def get_symbol_history(self, symbol: str) -> Dict[str, Any]:
        """Get trading history for a symbol"""
        symbol_trades = [m for m in self.memories if m.type == "trade_result" and m.metadata.get("symbol") == symbol]
        
        wins = len([t for t in symbol_trades if t.outcome == "WIN"])
        losses = len([t for t in symbol_trades if t.outcome == "LOSS"])
        total_pnl = sum(t.metadata.get("pnl", 0) for t in symbol_trades)
        
        return {
            "symbol": symbol,
            "total_trades": len(symbol_trades),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(symbol_trades) if symbol_trades else 0,
            "total_pnl": total_pnl,
            "trades": symbol_trades
        }
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get overall memory summary"""
        return {
            "total_memories": len(self.memories),
            "discussions": len([m for m in self.memories if m.type == "discussion"]),
            "decisions": len([m for m in self.memories if m.type == "decision"]),
            "trades": len([m for m in self.memories if m.type == "trade_result"]),
            "oldest_memory": min(self.memories, key=lambda x: x.timestamp).timestamp if self.memories else None,
            "newest_memory": max(self.memories, key=lambda x: x.timestamp).timestamp if self.memories else None
        }
    
    def _generate_id(self) -> str:
        """Generate unique memory ID"""
        timestamp = datetime.utcnow().isoformat()
        unique_hash = hashlib.md5(f"{timestamp}{len(self.memories)}".encode()).hexdigest()[:12]
        return unique_hash


class TraderMemoryAgent:
    """Memory-aware autonomous trader"""
    
    def __init__(self, memory_store: Optional[RAGMemoryStore] = None):
        """
        Initialize trader with memory
        
        Args:
            memory_store: RAG memory store instance
        """
        self.memory = memory_store or RAGMemoryStore()
    
    def analyze_with_memory(self, query: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze query with memory context
        
        Args:
            query: Analysis query
            symbol: Stock symbol for context
            
        Returns:
            Analysis with memory insights
        """
        # Search relevant memories
        relevant_memories = self.memory.search(query, limit=3)
        
        # Get symbol history if provided
        symbol_history = None
        if symbol:
            symbol_history = self.memory.get_symbol_history(symbol)
        
        return {
            "query": query,
            "relevant_memories": relevant_memories,
            "symbol_history": symbol_history,
            "memory_context": self._format_memory_context(relevant_memories, symbol_history)
        }
    
    def _format_memory_context(
        self,
        memories: List[MemoryEntry],
        symbol_history: Optional[Dict] = None
    ) -> str:
        """Format memory context for analysis"""
        context = []
        
        if memories:
            context.append("Recent relevant discussions:")
            for mem in memories:
                context.append(f"- {mem.content[:100]}... ({mem.type})")
        
        if symbol_history:
            context.append(f"\n{symbol_history['symbol']} Trading History:")
            context.append(f"- Win Rate: {symbol_history['win_rate']:.1%}")
            context.append(f"- Total P&L: ${symbol_history['total_pnl']:.2f}")
        
        return "\n".join(context) if context else "No relevant memory found"


class CouncilMemoryAgent:
    """Memory-aware trading council"""
    
    def __init__(self, memory_store: Optional[RAGMemoryStore] = None):
        """
        Initialize council with memory
        
        Args:
            memory_store: RAG memory store instance
        """
        self.memory = memory_store or RAGMemoryStore()
    
    def deliberate_with_memory(self, query: str) -> Dict[str, Any]:
        """
        Council deliberation with memory context
        
        Args:
            query: Discussion query
            
        Returns:
            Deliberation with memory insights
        """
        # Search for similar discussions
        similar_discussions = self.memory.search(
            query,
            limit=3,
            memory_type="discussion"
        )
        
        # Search for relevant decisions
        relevant_decisions = self.memory.search(
            query,
            limit=3,
            memory_type="decision"
        )
        
        return {
            "query": query,
            "similar_past_discussions": similar_discussions,
            "relevant_decisions": relevant_decisions,
            "council_context": self._format_council_context(
                similar_discussions,
                relevant_decisions
            )
        }
    
    def _format_council_context(
        self,
        discussions: List[MemoryEntry],
        decisions: List[MemoryEntry]
    ) -> str:
        """Format council memory context"""
        context = []
        
        if discussions:
            context.append("Similar past discussions:")
            for disc in discussions:
                context.append(f"- {disc.content[:80]}...")
        
        if decisions:
            context.append("\nRelevant past decisions:")
            for dec in decisions:
                outcome = f" (Result: {dec.outcome})" if dec.outcome else ""
                context.append(f"- {dec.content[:80]}...{outcome}")
        
        return "\n".join(context) if context else "No relevant memory found"
    
    def get_consensus_from_memory(self, topic: str) -> Dict[str, Any]:
        """
        Find past consensus on similar topics
        
        Args:
            topic: Topic to search
            
        Returns:
            Past consensus and voting patterns
        """
        past_votes = self.memory.search(topic, limit=5, memory_type="discussion")
        
        consensus_votes = {}
        for vote_mem in past_votes:
            if vote_mem.council_votes:
                for member, vote in vote_mem.council_votes.items():
                    if member not in consensus_votes:
                        consensus_votes[member] = []
                    consensus_votes[member].append(vote)
        
        return {
            "topic": topic,
            "past_discussions": past_votes,
            "voting_patterns": consensus_votes
        }


# Singleton instance
_memory_store = None


def get_memory_store():
    """
    Get or create singleton memory store.

    Prefers AhanaFlow compressed RAG (vendor/AhanaFlow) when available;
    falls back to the local JSON/pickle RAGMemoryStore.
    Set AHANAFLOW_MEMORY=0 to force legacy.
    """
    global _memory_store
    if _memory_store is None:
        try:
            from .ahanaflow_memory import get_memory_store as ahana_get

            _memory_store = ahana_get()
        except Exception as e:
            logger.warning("AhanaFlow memory unavailable (%s) — legacy RAG", e)
            _memory_store = RAGMemoryStore()
    return _memory_store


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing RAG Memory System...\n")
    
    # Initialize memory store
    memory = RAGMemoryStore()
    
    # Add some sample memories
    print("Adding sample memories...")
    disc_id = memory.add_discussion(
        "AAPL showing strong technical setup with RSI oversold",
        council_votes={"technical": "approve", "sentiment": "approve", "risk": "reject", "memory": "approve"},
        tags=["AAPL", "technical", "oversold"]
    )
    print(f"Discussion added: {disc_id}\n")
    
    dec_id = memory.add_decision(
        "Buy AAPL at support level 150",
        tags=["AAPL", "buy", "support"]
    )
    print(f"Decision added: {dec_id}\n")
    
    trade_id = memory.add_trade_result(
        symbol="AAPL",
        action="BUY",
        entry_price=150.0,
        exit_price=155.0,
        outcome="WIN",
        pnl=500.0
    )
    print(f"Trade result added: {trade_id}\n")
    
    # Search memories
    print("Searching for AAPL memories...")
    results = memory.search("AAPL technical analysis", limit=3)
    for mem in results:
        print(f"- {mem.type}: {mem.content[:60]}... (relevance: {mem.relevance_score:.2f})")
    
    print("\n" + "="*60)
    print("Memory Summary:")
    summary = memory.get_memory_summary()
    print(json.dumps(summary, indent=2))
    
    print("\n" + "="*60)
    print("AAPL History:")
    history = memory.get_symbol_history("AAPL")
    print(json.dumps(history, indent=2, default=str))
