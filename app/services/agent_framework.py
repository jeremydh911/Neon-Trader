"""
Agent framework for Neon Trader 2.0
Provides base agent classes, a council orchestrator and a simple reward manager.
This module is intended to integrate with existing `trading_council.py` and
`autonomous_trader.py` services as the multi-agent orchestration layer.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .trading_council import TradingCouncil, CouncilDecision
from .autonomous_trader import AutonomousTrader
from .rag_memory import RAGMemoryStore
from .tracing_config import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class AgentLearner:
    """Lightweight online learner wrapper.

    Uses sklearn's SGDRegressor when available; otherwise falls back to a simple running average predictor.
    The learner predicts expected PnL given a feature vector and can be updated incrementally.
    """

    def __init__(self):
        self.model = None
        self.is_sklearn = False
        try:
            from sklearn.linear_model import SGDRegressor
            import numpy as _np
            self.model = SGDRegressor(max_iter=1000, tol=1e-3)
            # Warm-start with a dummy fit to avoid errors on first partial_fit
            self.model.partial_fit(_np.zeros((1, 5)), _np.zeros(1))
            self.is_sklearn = True
            self._np = _np
            logger.info("AgentLearner: using sklearn SGDRegressor for online learning")
        except Exception:
            # Fallback: running average
            self.count = 0
            self.total = 0.0
            logger.info("AgentLearner: sklearn not available, using running-average fallback")

    def _to_vector(self, features: Dict[str, Any]) -> List[float]:
        # Select feature keys with safe defaults: rsi, macd, bb_position, confidence, position_size
        rsi = float(features.get("rsi", 50.0))
        macd = float(features.get("macd", 0.0))
        bb = float(features.get("bb_position", 0.5))
        conf = float(features.get("confidence", 0.0))
        pos = float(features.get("position_size", 0.0))
        return [rsi, macd, bb, conf, pos]

    def update(self, features: Dict[str, Any], pnl: float) -> None:
        if self.is_sklearn:
            vec = self._np.array([self._to_vector(features)])
            try:
                self.model.partial_fit(vec, self._np.array([pnl]))
            except Exception as e:
                logger.debug(f"AgentLearner sklearn partial_fit error: {e}")
        else:
            self.count += 1
            self.total += pnl

    def predict(self, features: Dict[str, Any]) -> float:
        if self.is_sklearn:
            vec = self._np.array([self._to_vector(features)])
            try:
                return float(self.model.predict(vec)[0])
            except Exception:
                return 0.0
        else:
            return (self.total / self.count) if self.count > 0 else 0.0


class AgentBase:
    """Base class for specialist council agents.

    Each agent has its own RAG memory store and an online learner. Agents should
    store trade outcomes in their memory and call the learner update to improve
    predictions over time.
    """

    def __init__(self, name: str, role: str, specialty: str, points: float = 0.0, metadata: Optional[Dict[str, Any]] = None, memory_path: Optional[str] = None):
        self.name = name
        self.role = role
        self.specialty = specialty
        self.points = float(points)
        self.metadata = metadata or {}

        # Per-agent memory store
        mem_path = memory_path or f"./data/memory/agents/{self.name.replace(' ', '_')}"
        try:
            self.memory = RAGMemoryStore(storage_path=mem_path)
        except Exception:
            logger.debug("Failed to initialize per-agent RAGMemoryStore; falling back to global store")
            self.memory = RAGMemoryStore()

        # Learner
        self.learner = AgentLearner()

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Research called by orchestrator; traced for observability."""
        with tracer.start_as_current_span(f"agent_research_{self.name}") as span:
            span.set_attribute("agent", self.name)
            span.set_attribute("symbol", symbol)
            span.set_attribute("specialty", self.specialty)
            result = self._research(symbol, context)
            span.set_attribute("action", result.get("action"))
            span.set_attribute("confidence", result.get("confidence"))
            return result

    def _research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Default: abstain
        """
        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": "HOLD",
            "confidence": 0.01,
            "plan": "No strong signal from this agent",
            "timestamp": datetime.utcnow().isoformat()
        }

    def on_trade_result(self, trade_record: Dict[str, Any]) -> None:
        """Default hook: store trade result in agent memory and update learner if pnl available."""
        try:
            # Store trade result in agent memory
            symbol = trade_record.get("symbol") if isinstance(trade_record, dict) else None
            pnl = None
            metadata = {}
            if isinstance(trade_record, dict):
                pnl = trade_record.get("pnl") or trade_record.get("profit_loss") or trade_record.get("profit_loss_amt")
                metadata = trade_record

            content = f"Trade result: {symbol} - {json_safe_str(trade_record)}"
            self.memory.add_trade_result(symbol or "unknown", trade_record.get("action", ""), trade_record.get("entry_price", 0), trade_record.get("exit_price", None), outcome=("WIN" if pnl and pnl > 0 else ("LOSS" if pnl and pnl < 0 else "UNKN")), pnl=pnl, metadata=metadata)

            # Update learner if pnl numeric
            if pnl is not None:
                try:
                    features = {
                        "rsi": metadata.get("indicators", {}).get("rsi", 50),
                        "macd": metadata.get("indicators", {}).get("macd", 0),
                        "bb_position": metadata.get("indicators", {}).get("bb_position", 0.5),
                        "confidence": metadata.get("decision", {}).get("confidence", 0) if metadata.get("decision") else metadata.get("confidence", 0),
                        "position_size": metadata.get("qty") or metadata.get("position_size") or 0
                    }
                    self.learner.update(features, float(pnl))
                except Exception as e:
                    logger.debug(f"Agent {self.name} learner update failed: {e}")

        except Exception as e:
            logger.debug(f"Agent {self.name} on_trade_result error: {e}")


def json_safe_str(obj: Any) -> str:
    try:
        import json as _json
        return _json.dumps(obj, default=str)
    except Exception:
        return str(obj)


class SpecialistAgent(AgentBase):
    """A simple specialist agent that can implement domain heuristics."""

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        indicators = context.get("indicators", {})
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)

        # Basic rule-based signals for demo purposes
        if rsi < 30 and macd > 0:
            action = "BUY"
            confidence = 0.6
            plan = f"Buy signal: RSI {rsi}, MACD {macd}"
        elif rsi > 70 and macd < 0:
            action = "SELL"
            confidence = 0.55
            plan = f"Sell signal: RSI {rsi}, MACD {macd}"
        else:
            action = "HOLD"
            confidence = 0.1
            plan = "No clear technical signal"

        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "plan": plan,
            "timestamp": datetime.utcnow().isoformat()
        }


class RewardManager:
    """Persistent reward manager backed by SQLite leaderboard.

    Uses `app.services.leaderboard.LeaderboardDB` to persist scores and track pending trades.
    """

    def __init__(self, db_path: Optional[str] = None):
        try:
            from .leaderboard import get_leaderboard_db
            self.db = get_leaderboard_db(db_path)
        except Exception:
            # Fall back to in-memory dict if DB not available
            self.db = None
            self.scores: Dict[str, float] = {}

    def register_agent(self, agent: AgentBase) -> None:
        if getattr(self, "db", None):
            self.db.register_agent(agent.name, float(agent.points))
        else:
            self.scores.setdefault(agent.name, float(agent.points))

    def apply_pnl(self, agent_name: str, pnl: float) -> float:
        if getattr(self, "db", None):
            return self.db.apply_pnl(agent_name, float(pnl))
        # In-memory fallback
        prev = self.scores.get(agent_name, 0.0)
        delta = pnl if pnl >= 0 else pnl * 1.3
        new = prev + delta
        self.scores[agent_name] = new
        logger.info(f"RewardManager(fallback): {agent_name} pnl={pnl:.2f} -> delta={delta:.2f} -> score={new:.2f}")
        return new

    def get_leaderboard(self) -> Dict[str, float]:
        if getattr(self, "db", None):
            rows = self.db.get_leaderboard()
            return {r['agent']: r['score'] for r in rows}
        return dict(sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True))

    def add_pending_trade(self, trade_id: str, agent_name: str, symbol: str, qty: float, entry_price: float, order_id: Optional[str] = None) -> None:
        if getattr(self, "db", None):
            try:
                self.db.add_pending_trade(trade_id=trade_id, agent=agent_name, symbol=symbol, qty=qty, entry_price=entry_price, order_id=order_id)
            except Exception:
                logger.debug("Failed to add pending trade to leaderboard DB")

    def resolve_trade(self, trade_id: str, pnl: float) -> Optional[float]:
        if getattr(self, "db", None):
            try:
                return self.db.resolve_trade(trade_id, float(pnl))
            except Exception:
                logger.debug("Failed to resolve trade in leaderboard DB")
        return None


class CouncilOrchestrator:
    """Orchestrates research, council deliberation and backend execution."""

    def __init__(self, council: Optional[TradingCouncil] = None, backend_trader: Optional[AutonomousTrader] = None):
        self.council = council or TradingCouncil()
        self.backend = backend_trader
        self.agents: List[AgentBase] = []
        self.reward_manager = RewardManager()

    def register_agent(self, agent: AgentBase) -> None:
        self.agents.append(agent)
        self.reward_manager.register_agent(agent)
        logger.info(f"Registered agent: {agent.name} ({agent.specialty})")

    def run_cycle(self, symbol: str, current_price: float, indicators: Dict[str, Any], available_capital: float = 10000.0, market_sentiment: str = "neutral") -> Dict[str, Any]:
        """Single decision cycle: agents research -> council deliberates -> backend executes if approved."""
        with tracer.start_as_current_span(f"orchestrator_cycle_{symbol}") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("price", current_price)
            span.set_attribute("num_agents", len(self.agents))

            # Plug-in brain (AHANA_BRAIN_URL) replaces local agents when configured.
            plugin_top = None
            try:
                from .brain_plugin import plugin_proposal
                plugin_top = plugin_proposal(
                    symbol=symbol,
                    current_price=current_price,
                    indicators=indicators,
                    available_capital=available_capital,
                    market_sentiment=market_sentiment,
                )
            except Exception:
                logger.debug("brain plugin not used")
                plugin_top = None

            # Gather proposals
            with tracer.start_as_current_span("gather_proposals") as prop_span:
                if plugin_top:
                    proposals = [plugin_top]
                else:
                    proposals = [agent.research(symbol, {"indicators": indicators, "market_sentiment": market_sentiment}) for agent in self.agents]
                prop_span.set_attribute("num_proposals", len(proposals))
                prop_span.set_attribute("brain", "plugin" if plugin_top else "council")

            # Pick top proposal by confidence
            proposals_sorted = sorted(proposals, key=lambda p: p.get("confidence", 0), reverse=True)
            top = proposals_sorted[0] if proposals_sorted else None

            if not top:
                span.add_event("no_proposals")
                return {"status": "no_proposals"}

            action = top.get("action", "HOLD")

            # Submit to trading council unless the plug-in brain is the desk.
            if plugin_top:
                decision, approved = None, bool(plugin_top.get("approved"))
            else:
                with tracer.start_as_current_span("council_deliberation") as council_span:
                    council_span.set_attribute("action", action)
                    council_span.set_attribute("symbol", symbol)
                    decision, approved = self.council.discuss_trade(
                        symbol=symbol,
                        action=action,
                        current_price=current_price,
                        indicators=indicators,
                        available_capital=available_capital,
                        market_sentiment=market_sentiment
                    )
                    council_span.set_attribute("approved", approved)
                    if decision:
                        council_span.set_attribute("approval_pct", decision.approval_percentage)

            result = {
                "symbol": symbol,
                "proposal": top,
                "council_decision": decision.to_dict() if isinstance(decision, CouncilDecision) else None,
                "approved": approved,
                "brain": "plugin" if plugin_top else "council",
            }

            # If approved and backend available, execute via backend trader
            if approved and self.backend:
                with tracer.start_as_current_span("backend_execution") as exec_span:
                    exec_result = self.backend.execute_advised_trade(
                        symbol=symbol,
                        current_price=current_price,
                        indicators=indicators,
                        market_sentiment=market_sentiment,
                        available_capital=available_capital
                    )
                    exec_span.set_attribute("execution_status", exec_result.get("status", "unknown"))

                    result["execution"] = exec_result

                    # Find proposing agent object
                    proposer_name = top.get("agent")
                    proposer = next((a for a in self.agents if a.name == proposer_name), None)

                    # Give proposer a chance to process the execution (store memory + learn)
                    try:
                        trade_obj = exec_result.get("trade_record") or exec_result.get("order") or exec_result
                        if proposer and trade_obj:
                            proposer.on_trade_result(trade_obj if isinstance(trade_obj, dict) else {"order": trade_obj})

                        # If execution returns immediate pnl, update rewards
                        pnl = None
                        if isinstance(exec_result, dict):
                            pnl = exec_result.get("pnl") or exec_result.get("profit_loss")
                        if pnl is not None and proposer:
                            try:
                                new_score = self.reward_manager.apply_pnl(proposer.name, float(pnl))
                                result.setdefault("rewards", {})[proposer.name] = new_score
                                exec_span.set_attribute("reward_applied", pnl)
                            except Exception:
                                pass
                    except Exception:
                        logger.debug("Error processing post-execution learning/rewards")

                    # If execution did not return immediate pnl, register a pending trade for later reconciliation
                    try:
                        import uuid
                        # Determine a trade id (prefer order_id if present)
                        order_id = None
                        if isinstance(exec_result, dict):
                            order_id = (exec_result.get("order") or {}).get("order_id") if exec_result.get("order") else None
                        trade_id = order_id or f"trade-{uuid.uuid4().hex[:12]}"

                        # If we have a proposer, record pending trade to reward manager DB
                        if proposer:
                            # Try to determine entry price and qty
                            entry_price = None
                            qty = 0
                            if isinstance(exec_result, dict) and exec_result.get("trade_record"):
                                tr = exec_result.get("trade_record")
                                entry_price = tr.get("entry_price") or tr.get("price")
                                qty = tr.get("qty") or tr.get("quantity") or 0
                            # Fallback to current_price
                            entry_price = entry_price if entry_price is not None else current_price
                            self.reward_manager.add_pending_trade(trade_id=trade_id, agent_name=proposer.name, symbol=symbol, qty=qty or 0, entry_price=entry_price, order_id=order_id)
                            result.setdefault("pending_trade_id", trade_id)
                            exec_span.set_attribute("pending_trade_id", trade_id)
                    except Exception:
                        logger.debug("Failed to register pending trade for later reconciliation")

            return result


__all__ = ["AgentBase", "SpecialistAgent", "CouncilOrchestrator", "RewardManager"]
