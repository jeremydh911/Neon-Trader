"""
Trading Council System
Multiple AI agents debate and vote on trading decisions
"""

import logging
from typing import Dict, List, Any, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)


class CouncilRole(Enum):
    """Roles within the trading council"""
    TECHNICAL_ANALYST = "technical_analyst"
    SENTIMENT_ANALYST = "sentiment_analyst"
    RISK_MANAGER = "risk_manager"
    MEMORY_CURATOR = "memory_curator"


class VoteDecision(Enum):
    """Vote decision options"""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class CouncilMemberVote:
    """A single council member's vote on a trade"""
    member_name: str
    role: CouncilRole
    decision: VoteDecision
    confidence: float  # 0-1
    reasoning: str
    additional_data: Dict[str, Any] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "member_name": self.member_name,
            "role": self.role.value,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "additional_data": self.additional_data or {}
        }


@dataclass
class CouncilDecision:
    """Final council decision on a trade"""
    symbol: str
    action: str  # BUY, SELL, HOLD
    approved: bool
    approval_percentage: float  # 0-100
    total_votes: int
    approve_votes: int
    reject_votes: int
    abstain_votes: int
    council_votes: List[CouncilMemberVote]
    final_confidence: float
    timestamp: str
    discussion_summary: str
    consensus_achieved: bool
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "approved": self.approved,
            "approval_percentage": self.approval_percentage,
            "total_votes": self.total_votes,
            "approve_votes": self.approve_votes,
            "reject_votes": self.reject_votes,
            "abstain_votes": self.abstain_votes,
            "final_confidence": self.final_confidence,
            "timestamp": self.timestamp,
            "discussion_summary": self.discussion_summary,
            "consensus_achieved": self.consensus_achieved,
            "votes": [vote.to_dict() for vote in self.council_votes]
        }


class TradingCouncil:
    """Council of AI agents that debate and vote on trades"""
    
    def __init__(self, news_service=None, memory_service=None):
        """
        Initialize the trading council
        
        Args:
            news_service: Optional service for fetching news
            memory_service: Optional service for accessing trading memory
        """
        self.news_service = news_service
        self.memory = memory_service
        self.council_members = {}
        self.voting_history = []
        self.approval_threshold = 0.5  # 50% approval needed
        self.consensus_threshold = 0.8  # 80% agreement = consensus
        
        # Initialize council members
        self._initialize_council()
    
    def _initialize_council(self):
        """Initialize council members"""
        self.council_members = {
            "technical": {
                "role": CouncilRole.TECHNICAL_ANALYST,
                "description": "Analyzes technical indicators and price action",
                "expertise": ["RSI", "MACD", "Bollinger Bands", "Support/Resistance"]
            },
            "sentiment": {
                "role": CouncilRole.SENTIMENT_ANALYST,
                "description": "Analyzes market sentiment and news",
                "expertise": ["News sentiment", "Market conditions", "Volatility"]
            },
            "risk": {
                "role": CouncilRole.RISK_MANAGER,
                "description": "Evaluates risk and position sizing",
                "expertise": ["Risk/Reward ratio", "Position sizing", "Stop losses"]
            },
            "memory": {
                "role": CouncilRole.MEMORY_CURATOR,
                "description": "Recalls historical patterns and lessons",
                "expertise": ["Past trades", "Patterns", "Lessons learned"]
            }
        }
        logger.info(f"Trading council initialized with {len(self.council_members)} members")
    
    def discuss_trade(
        self,
        symbol: str,
        action: str,
        current_price: float,
        indicators: Dict[str, Any],
        available_capital: float,
        market_sentiment: str = "neutral"
    ) -> Tuple[CouncilDecision, bool]:
        """
        Have council discuss and vote on a trade
        
        Returns:
            Tuple of (CouncilDecision, authorized: bool)
        """
        
        logger.info(f"\n{'='*60}")
        logger.info(f"COUNCIL DISCUSSION: {symbol} - {action}")
        logger.info(f"{'='*60}")
        
        # Gather council votes
        votes = []
        
        # Technical Analyst
        tech_vote = self._technical_analysis_vote(symbol, action, indicators)
        votes.append(tech_vote)
        logger.info(f"\n📊 Technical Analyst: {tech_vote.decision.value}")
        logger.info(f"   Confidence: {tech_vote.confidence:.1%}")
        logger.info(f"   Reasoning: {tech_vote.reasoning}")
        
        # Sentiment Analyst
        sent_vote = self._sentiment_analysis_vote(symbol, action, market_sentiment)
        votes.append(sent_vote)
        logger.info(f"\n📰 Sentiment Analyst: {sent_vote.decision.value}")
        logger.info(f"   Confidence: {sent_vote.confidence:.1%}")
        logger.info(f"   Reasoning: {sent_vote.reasoning}")
        
        # Risk Manager
        risk_vote = self._risk_analysis_vote(symbol, action, current_price, available_capital, indicators)
        votes.append(risk_vote)
        logger.info(f"\n⚠️  Risk Manager: {risk_vote.decision.value}")
        logger.info(f"   Confidence: {risk_vote.confidence:.1%}")
        logger.info(f"   Reasoning: {risk_vote.reasoning}")
        
        # Memory Curator
        mem_vote = self._memory_analysis_vote(symbol, action)
        votes.append(mem_vote)
        logger.info(f"\n🧠 Memory Curator: {mem_vote.decision.value}")
        logger.info(f"   Confidence: {mem_vote.confidence:.1%}")
        logger.info(f"   Reasoning: {mem_vote.reasoning}")
        
        # Calculate final decision
        council_decision = self._calculate_decision(symbol, action, votes)
        
        # Log final decision
        logger.info(f"\n{'='*60}")
        logger.info(f"COUNCIL DECISION: {council_decision.approved}")
        logger.info(f"Approval: {council_decision.approval_percentage:.1f}%")
        logger.info(f"Consensus: {council_decision.consensus_achieved}")
        logger.info(f"Final Confidence: {council_decision.final_confidence:.1%}")
        logger.info(f"{'='*60}\n")
        
        # Store in history
        self.voting_history.append(council_decision)
        
        return council_decision, council_decision.approved
    
    def _technical_analysis_vote(
        self,
        symbol: str,
        action: str,
        indicators: Dict[str, Any]
    ) -> CouncilMemberVote:
        """Technical analyst votes based on indicators"""
        
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        bb_position = indicators.get("bb_position", 0.5)
        
        reasoning = ""
        confidence = 0.5
        decision = VoteDecision.ABSTAIN
        
        # BUY signal analysis
        if action == "BUY":
            if rsi < 30:
                reasoning += "RSI oversold (bullish). "
                confidence += 0.2
            elif rsi < 45:
                reasoning += "RSI low (mildly bullish). "
                confidence += 0.1
            
            if macd > 0:
                reasoning += "MACD positive (bullish). "
                confidence += 0.15
            
            if bb_position < 0.3:
                reasoning += "Price near lower Bollinger Band (reversal signal). "
                confidence += 0.15
            
            if confidence > 0.5:
                decision = VoteDecision.APPROVE
                reasoning = f"Strong buy signals detected. {reasoning}"
            else:
                decision = VoteDecision.REJECT
                reasoning = f"Weak buy signals. {reasoning}"
        
        # SELL signal analysis
        elif action == "SELL":
            if rsi > 70:
                reasoning += "RSI overbought (bearish). "
                confidence += 0.2
            elif rsi > 55:
                reasoning += "RSI high (mildly bearish). "
                confidence += 0.1
            
            if macd < 0:
                reasoning += "MACD negative (bearish). "
                confidence += 0.15
            
            if bb_position > 0.7:
                reasoning += "Price near upper Bollinger Band (reversal signal). "
                confidence += 0.15
            
            if confidence > 0.5:
                decision = VoteDecision.APPROVE
                reasoning = f"Strong sell signals detected. {reasoning}"
            else:
                decision = VoteDecision.REJECT
                reasoning = f"Weak sell signals. {reasoning}"
        
        confidence = min(1.0, max(0.0, confidence))
        
        return CouncilMemberVote(
            member_name="Technical Analyst",
            role=CouncilRole.TECHNICAL_ANALYST,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning.strip(),
            additional_data={"indicators": indicators}
        )
    
    def _sentiment_analysis_vote(
        self,
        symbol: str,
        action: str,
        market_sentiment: str
    ) -> CouncilMemberVote:
        """Sentiment analyst votes based on market conditions and news"""
        
        reasoning = f"Market sentiment: {market_sentiment}. "
        confidence = 0.5
        decision = VoteDecision.ABSTAIN
        news_data = {}
        
        # Check news if available
        if self.news_service:
            try:
                news = self.news_service.get_news(symbol)
                positive_articles = len([n for n in news if n.get("sentiment", "neutral") == "positive"])
                negative_articles = len([n for n in news if n.get("sentiment", "neutral") == "negative"])
                
                if positive_articles > negative_articles:
                    reasoning += f"Positive news sentiment ({positive_articles} positive articles). "
                    confidence += 0.15
                    if action == "BUY":
                        decision = VoteDecision.APPROVE
                    else:
                        decision = VoteDecision.ABSTAIN
                
                elif negative_articles > positive_articles:
                    reasoning += f"Negative news sentiment ({negative_articles} negative articles). "
                    confidence -= 0.15
                    if action == "BUY":
                        decision = VoteDecision.REJECT
                    else:
                        decision = VoteDecision.APPROVE
                else:
                    reasoning += "Mixed news sentiment."
                    decision = VoteDecision.ABSTAIN
                
                news_data = {
                    "positive_articles": positive_articles,
                    "negative_articles": negative_articles,
                    "total_articles": len(news)
                }
            except Exception as e:
                logger.debug(f"Error fetching news: {e}")
                reasoning += "Unable to fetch news. "
        
        # Sentiment-based decision
        if market_sentiment == "bullish" and action == "BUY":
            confidence += 0.1
            decision = VoteDecision.APPROVE
        elif market_sentiment == "bearish" and action == "SELL":
            confidence += 0.1
            decision = VoteDecision.APPROVE
        elif market_sentiment == "bearish" and action == "BUY":
            decision = VoteDecision.REJECT
        
        confidence = min(1.0, max(0.0, confidence))
        
        return CouncilMemberVote(
            member_name="Sentiment Analyst",
            role=CouncilRole.SENTIMENT_ANALYST,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning.strip(),
            additional_data=news_data
        )
    
    def _risk_analysis_vote(
        self,
        symbol: str,
        action: str,
        current_price: float,
        available_capital: float,
        indicators: Dict[str, Any]
    ) -> CouncilMemberVote:
        """Risk manager votes based on position sizing and risk/reward"""
        
        reasoning = ""
        confidence = 0.5
        decision = VoteDecision.ABSTAIN
        
        # Check if HOLD action
        if action == "HOLD":
            decision = VoteDecision.APPROVE
            reasoning = "HOLD is always safe. Minimal risk."
            confidence = 1.0
            return CouncilMemberVote(
                member_name="Risk Manager",
                role=CouncilRole.RISK_MANAGER,
                decision=decision,
                confidence=confidence,
                reasoning=reasoning,
                additional_data={"position_size_check": "passed"}
            )
        
        # Position size check
        max_position_pct = 0.05  # 5% of portfolio
        max_position_value = available_capital * max_position_pct
        position_value = current_price * 100  # Assume 100 shares
        
        if position_value <= max_position_value:
            reasoning += "Position size acceptable (< 5% of capital). "
            confidence += 0.2
        else:
            reasoning += "Position size too large (> 5% of capital). "
            confidence -= 0.3
            decision = VoteDecision.REJECT
        
        # Risk/Reward check
        atr = indicators.get("atr", current_price * 0.02)
        stop_loss_pct = 1.0
        take_profit_pct = 2.0
        risk_reward = take_profit_pct / stop_loss_pct
        
        if risk_reward >= 2.0:
            reasoning += f"Good risk/reward ratio ({risk_reward:.1f}:1). "
            confidence += 0.15
        elif risk_reward >= 1.0:
            reasoning += f"Acceptable risk/reward ({risk_reward:.1f}:1). "
            confidence += 0.05
        else:
            reasoning += f"Poor risk/reward ({risk_reward:.1f}:1). "
            confidence -= 0.2
        
        # Capital check
        if available_capital < 5000:
            reasoning += "Insufficient capital for safe trading. "
            confidence -= 0.25
            decision = VoteDecision.REJECT
        else:
            if decision != VoteDecision.REJECT:
                decision = VoteDecision.APPROVE if confidence > 0.5 else VoteDecision.ABSTAIN
        
        confidence = min(1.0, max(0.0, confidence))
        
        return CouncilMemberVote(
            member_name="Risk Manager",
            role=CouncilRole.RISK_MANAGER,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning.strip(),
            additional_data={
                "position_value": position_value,
                "max_position_value": max_position_value,
                "risk_reward_ratio": risk_reward,
                "available_capital": available_capital
            }
        )
    
    def _memory_analysis_vote(
        self,
        symbol: str,
        action: str
    ) -> CouncilMemberVote:
        """Memory curator votes based on historical patterns"""
        
        reasoning = ""
        confidence = 0.5
        decision = VoteDecision.ABSTAIN
        memory_data = {}
        
        if self.memory:
            try:
                # Get symbol stats
                stats = self.memory.get_trading_stats_by_symbol(symbol)
                similar_trades = self.memory.recall_similar_trades(symbol=symbol, k=5)
                profitable_patterns = self.memory.get_profitable_patterns(symbol=symbol, min_trades=2)
                
                if stats:
                    win_rate = stats.get("win_rate", 0) / 100 if stats.get("win_rate") else 0
                    total_trades = stats.get("total_trades", 0)
                    
                    if total_trades > 0:
                        reasoning += f"Historical {win_rate:.0%} win rate on {symbol} ({total_trades} trades). "
                        
                        if win_rate > 0.55:
                            confidence += 0.2
                            if action == "BUY":
                                decision = VoteDecision.APPROVE
                        elif win_rate < 0.45:
                            confidence -= 0.2
                            if action == "BUY":
                                decision = VoteDecision.REJECT
                    
                    memory_data["stats"] = stats
                
                if similar_trades:
                    successful = sum(1 for t in similar_trades if t.get("success", False))
                    reasoning += f"Found {len(similar_trades)} similar past trades ({successful} profitable). "
                    
                    if successful > len(similar_trades) / 2:
                        confidence += 0.15
                        if decision == VoteDecision.ABSTAIN:
                            decision = VoteDecision.APPROVE
                    
                    memory_data["similar_trades"] = len(similar_trades)
                    memory_data["successful_similar"] = successful
                
                if profitable_patterns:
                    reasoning += f"Pattern matches {len(profitable_patterns)} profitable historical patterns. "
                    confidence += 0.2
                    decision = VoteDecision.APPROVE
                    memory_data["patterns"] = len(profitable_patterns)
            
            except Exception as e:
                logger.debug(f"Error accessing memory: {e}")
                reasoning += "Memory unavailable. "
        else:
            reasoning += "No historical data available. "
            decision = VoteDecision.ABSTAIN
        
        confidence = min(1.0, max(0.0, confidence))
        
        return CouncilMemberVote(
            member_name="Memory Curator",
            role=CouncilRole.MEMORY_CURATOR,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning.strip(),
            additional_data=memory_data
        )
    
    def _calculate_decision(
        self,
        symbol: str,
        action: str,
        votes: List[CouncilMemberVote]
    ) -> CouncilDecision:
        """Calculate final council decision from votes"""
        
        approve_count = sum(1 for v in votes if v.decision == VoteDecision.APPROVE)
        reject_count = sum(1 for v in votes if v.decision == VoteDecision.REJECT)
        abstain_count = sum(1 for v in votes if v.decision == VoteDecision.ABSTAIN)
        
        total_votes = len(votes)
        approval_pct = (approve_count / total_votes * 100) if total_votes > 0 else 0
        
        # Approved if more approve than reject and meets threshold
        approved = approve_count > reject_count and approval_pct >= (self.approval_threshold * 100)
        
        # Calculate average confidence
        avg_confidence = sum(v.confidence for v in votes) / total_votes if total_votes > 0 else 0
        
        # Check consensus
        max_vote_pct = max(approve_count, reject_count, abstain_count) / total_votes if total_votes > 0 else 0
        consensus = max_vote_pct >= self.consensus_threshold
        
        # Build discussion summary
        summary = self._build_discussion_summary(votes, approve_count, reject_count, abstain_count)
        
        return CouncilDecision(
            symbol=symbol,
            action=action,
            approved=approved,
            approval_percentage=approval_pct,
            total_votes=total_votes,
            approve_votes=approve_count,
            reject_votes=reject_count,
            abstain_votes=abstain_count,
            council_votes=votes,
            final_confidence=avg_confidence,
            timestamp=datetime.utcnow().isoformat(),
            discussion_summary=summary,
            consensus_achieved=consensus
        )
    
    def _build_discussion_summary(
        self,
        votes: List[CouncilMemberVote],
        approve: int,
        reject: int,
        abstain: int
    ) -> str:
        """Build a summary of the council discussion"""
        
        summary = f"Council voted: {approve} approve, {reject} reject, {abstain} abstain. "
        
        # Get key points
        key_points = []
        for vote in votes:
            if vote.decision == VoteDecision.APPROVE:
                key_points.append(f"✓ {vote.member_name}: {vote.reasoning[:60]}")
            elif vote.decision == VoteDecision.REJECT:
                key_points.append(f"✗ {vote.member_name}: {vote.reasoning[:60]}")
        
        if key_points:
            summary += "Key points: " + "; ".join(key_points)
        
        return summary
    
    def get_council_history(self, symbol: str = None, limit: int = 10) -> List[Dict]:
        """Get council voting history"""
        
        history = self.voting_history
        if symbol:
            history = [v for v in history if v.symbol == symbol]
        
        return [v.to_dict() for v in history[-limit:]]
    
    def get_council_statistics(self) -> Dict[str, Any]:
        """Get council statistics"""
        
        if not self.voting_history:
            return {"total_votes": 0, "accuracy": 0}
        
        total = len(self.voting_history)
        approved = sum(1 for v in self.voting_history if v.approved)
        
        return {
            "total_decisions": total,
            "approved_trades": approved,
            "rejected_trades": total - approved,
            "approval_rate": approved / total if total > 0 else 0,
            "consensus_rate": sum(1 for v in self.voting_history if v.consensus_achieved) / total if total > 0 else 0,
            "average_confidence": sum(v.final_confidence for v in self.voting_history) / total if total > 0 else 0
        }
