"""
Concrete specialist agents for Neon Trader 2.0
Includes rule-based specialists and an LLM-backed specialist that uses the existing
`app/services/council_llm.py` client when available.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .agent_framework import AgentBase, SpecialistAgent
from .council_llm import CouncilLLMOrchestrator, OllamaLLMClient
from .rag_memory import get_memory_store

logger = logging.getLogger(__name__)


class OptionsAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="OptionsAgent", role="options", specialty="options_spreads")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Very simple heuristic: options agent focuses on volatility (using bb_position as proxy)
        bb = context.get("indicators", {}).get("bb_position", 0.5)
        if bb > 0.8:
            action = "SELL"
            confidence = 0.6
            plan = "Consider selling premium due to high dispersion"
        elif bb < 0.2:
            action = "BUY"
            confidence = 0.55
            plan = "Long gamma candidate near lower band"
        else:
            action = "HOLD"
            confidence = 0.1
            plan = "No options edge"

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


class BondsAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="BondsAgent", role="bonds", specialty="fixed_income")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Bonds agent rarely trades equities; acts conservatively
        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": "HOLD",
            "confidence": 0.05,
            "plan": "Prefer fixed income allocation; no equity action",
            "timestamp": datetime.utcnow().isoformat()
        }


class ShortsAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="ShortsAgent", role="shorts", specialty="short_selling")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        rsi = context.get("indicators", {}).get("rsi", 50)
        macd = context.get("indicators", {}).get("macd", 0)
        if rsi > 70 and macd < 0:
            return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                    "symbol": symbol, "action": "SELL", "confidence": 0.7,
                    "plan": "Short candidate: overbought with negative momentum",
                    "timestamp": datetime.utcnow().isoformat()}
        return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                "symbol": symbol, "action": "HOLD", "confidence": 0.1,
                "plan": "No short opportunity", "timestamp": datetime.utcnow().isoformat()}


class LongTermAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="LongTermAgent", role="long_term", specialty="buy_and_hold")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Uses memory and fundamentals if available; fallback to hold
        mem = get_memory_store()
        stats = mem.get_symbol_history(symbol)
        win_rate = stats.get("win_rate", 0) if stats else 0
        if win_rate and win_rate > 0.6:
            return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                    "symbol": symbol, "action": "BUY", "confidence": 0.6,
                    "plan": "Historically strong performer; build position gradually",
                    "timestamp": datetime.utcnow().isoformat()}
        return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                "symbol": symbol, "action": "HOLD", "confidence": 0.08,
                "plan": "No long-term conviction", "timestamp": datetime.utcnow().isoformat()}


class ShortTermAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="ShortTermAgent", role="short_term", specialty="intraday")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Aggressive intraday heuristics
        rsi = context.get("indicators", {}).get("rsi", 50)
        if rsi < 35:
            return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                    "symbol": symbol, "action": "BUY", "confidence": 0.65,
                    "plan": "Mean-revert intraday buy", "timestamp": datetime.utcnow().isoformat()}
        return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                "symbol": symbol, "action": "HOLD", "confidence": 0.12,
                "plan": "Waiting for intraday signal", "timestamp": datetime.utcnow().isoformat()}


class SpreadsAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="SpreadsAgent", role="spreads", specialty="complex_spreads")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Placeholder - prefers options spreads when volatility high
        return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                "symbol": symbol, "action": "HOLD", "confidence": 0.1,
                "plan": "Evaluate spread candidates offline", "timestamp": datetime.utcnow().isoformat()}


class FuturesAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(name="FuturesAgent", role="futures", specialty="futures_prediction")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Naive prediction stub
        indicator = context.get("indicators", {}).get("bb_position", 0.5)
        if indicator < 0.3:
            return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                    "symbol": symbol, "action": "BUY", "confidence": 0.5,
                    "plan": "Short-term futures up-tick expected", "timestamp": datetime.utcnow().isoformat()}
        return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                "symbol": symbol, "action": "HOLD", "confidence": 0.1,
                "plan": "No futures edge", "timestamp": datetime.utcnow().isoformat()}


class LLMSpecialistAgent(AgentBase):
    """Agent that uses local Ollama-like LLM endpoints via CouncilLLMOrchestrator clients."""

    def __init__(self, name: str, role: str, specialty: str, orchestrator: Optional[CouncilLLMOrchestrator] = None):
        super().__init__(name=name, role=role, specialty=specialty)
        self.orch = orchestrator or CouncilLLMOrchestrator()

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Use the LLM orchestrator to run an analysis for the symbol
            analyses = self.orch.conduct_trade_analysis(
                symbol=symbol,
                current_price=context.get("current_price", 0.0),
                indicators=context.get("indicators", {}),
                market_sentiment=context.get("market_sentiment", "neutral"),
                similar_trades=context.get("similar_trades", [])
            )

            # Parse LLM results heuristically
            tech = analyses.get("analyses", {}).get("technical", {})
            sent = analyses.get("analyses", {}).get("sentiment", {})
            mem = analyses.get("analyses", {}).get("memory", {})

            # Simple rule: if tech or sentiment recommends BUY -> BUY
            action = "HOLD"
            confidence = 0.2
            plan_lines = []
            for name, a in [("technical", tech), ("sentiment", sent), ("memory", mem)]:
                resp = a.get("response") if isinstance(a, dict) else None
                if resp and "BUY" in resp.upper():
                    action = "BUY"
                    confidence = max(confidence, 0.6)
                if resp and "SELL" in resp.upper():
                    action = "SELL"
                    confidence = max(confidence, 0.6)
                if resp:
                    plan_lines.append(f"{name}: {resp[:140]}")

            return {
                "agent": self.name,
                "role": self.role,
                "specialty": self.specialty,
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "plan": " | ".join(plan_lines)[:800],
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.debug(f"LLM agent error: {e}")
            return {"agent": self.name, "role": self.role, "specialty": self.specialty,
                    "symbol": symbol, "action": "HOLD", "confidence": 0.05,
                    "plan": "LLM unavailable or error", "timestamp": datetime.utcnow().isoformat()}


__all__ = [
    "OptionsAgent", "BondsAgent", "ShortsAgent", "LongTermAgent",
    "ShortTermAgent", "SpreadsAgent", "FuturesAgent", "LLMSpecialistAgent"
]


# =========================
# Team Agents (named)
# =========================


class TurboTradeTina(ShortTermAgent):
    """High-velocity day-trading momentum specialist (TurboTrade Tina)."""

    def __init__(self):
        super().__init__()
        self.name = "TurboTrade Tina"
        self.role = "momentum"
        self.specialty = "day_trading"

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        indicators = context.get("indicators", {})
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        bb_pos = indicators.get("bb_position", 0.5)

        # Aggressive momentum rules
        if rsi < 40 and macd > 0.2 and bb_pos < 0.4:
            action = "BUY"
            confidence = 0.8
            plan = "Momentum entry: oversold reversal with rising MACD"
        elif rsi > 65 and macd < -0.1 and bb_pos > 0.7:
            action = "SELL"
            confidence = 0.75
            plan = "Momentum exit: overbought with negative momentum"
        else:
            action = "HOLD"
            confidence = 0.12
            plan = "No high-confidence momentum signal"

        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "plan": plan,
            "chant": "Let’s rocket to the moon!",
            "timestamp": datetime.utcnow().isoformat()
        }


class EcoEdgeEddie(AgentBase):
    """Sustainable investment specialist (EcoEdge Eddie)."""

    def __init__(self):
        super().__init__(name="EcoEdge Eddie", role="esg", specialty="sustainable_investing")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Use memory to find ESG-tagged trades as a proxy
        mem = get_memory_store()
        tags = context.get("tags", [])
        indicators = context.get("indicators", {})
        rsi = indicators.get("rsi", 50)

        # Favor ESG symbols (simple tag match) and steady performers
        score = 0.0
        if "ESG" in tags or "green" in tags or symbol.lower().startswith("eco"):
            score += 0.3

        history = mem.get_symbol_history(symbol)
        win_rate = history.get("win_rate", 0)
        if win_rate and win_rate > 0.55:
            score += 0.25

        if score > 0.4 and rsi < 65:
            action = "BUY"
            confidence = min(0.9, 0.5 + score)
            plan = "ESG-backed growth candidate with decent historical win rate"
        else:
            action = "HOLD"
            confidence = 0.08
            plan = "No clear sustainable edge"

        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "plan": plan,
            "chant": "Green means go for points!",
            "timestamp": datetime.utcnow().isoformat()
        }


class GlobalGainsGloria(AgentBase):
    """International markets and FX specialist (GlobalGains Gloria)."""

    def __init__(self):
        super().__init__(name="GlobalGains Gloria", role="global", specialty="international_markets")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Use a proxy for global momentum: check market_sentiment and bb_position
        indicators = context.get("indicators", {})
        sentiment = context.get("market_sentiment", "neutral")
        bb = indicators.get("bb_position", 0.5)

        if sentiment == "bullish" and bb < 0.4:
            action = "BUY"
            confidence = 0.6
            plan = "Global tailwinds favor building exposure"
        elif sentiment == "bearish" and bb > 0.6:
            action = "SELL"
            confidence = 0.6
            plan = "Reduce exposure given global headwinds"
        else:
            action = "HOLD"
            confidence = 0.1
            plan = "Await clearer geopolitical signals"

        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "plan": plan,
            "chant": "Bonjour, hola, hello—world markets are calling!",
            "timestamp": datetime.utcnow().isoformat()
        }


class ValueVaultVictor(AgentBase):
    """Long-term value investor (ValueVault Victor)."""

    def __init__(self):
        super().__init__(name="ValueVault Victor", role="value", specialty="fundamentals")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Fundamental proxy: look at memory summary and low volatility
        mem = get_memory_store()
        history = mem.get_symbol_history(symbol)
        win_rate = history.get("win_rate", 0)
        total_pnl = history.get("total_pnl", 0)

        # Conservative buy when positive history and low short-term volatility
        indicators = context.get("indicators", {})
        bb = indicators.get("bb_position", 0.5)

        if win_rate and win_rate > 0.55 and bb > 0.3 and bb < 0.7:
            action = "BUY"
            confidence = 0.65
            plan = "Buy undervalued steady performer for long-term growth"
        else:
            action = "HOLD"
            confidence = 0.07
            plan = "No compelling value entry"

        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "plan": plan,
            "chant": "Rise and shine, investors—value awaits!",
            "timestamp": datetime.utcnow().isoformat()
        }


class RiskRushRiley(AgentBase):
    """High-risk, high-reward specialist (RiskRush Riley)."""

    def __init__(self):
        super().__init__(name="RiskRush Riley", role="risk_taker", specialty="speculative")

    def research(self, symbol: str, context: Dict[str, Any]) -> Dict[str, Any]:
        indicators = context.get("indicators", {})
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)

        # Look for breakout or extreme moves to capitalize on
        if rsi < 35 and macd > 0.3:
            action = "BUY"
            confidence = 0.7
            plan = "Speculative breakout long with aggressive sizing"
        elif rsi > 75 and macd < -0.25:
            action = "SELL"
            confidence = 0.75
            plan = "Aggressive short candidate with options/futures overlay"
        else:
            action = "HOLD"
            confidence = 0.15
            plan = "No high-conviction speculative setup"

        return {
            "agent": self.name,
            "role": self.role,
            "specialty": self.specialty,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "plan": plan,
            "chant": "Buckle up, brokers—adventure and points are on the horizon!",
            "timestamp": datetime.utcnow().isoformat()
        }


# Update exported names
__all__.extend([
    "TurboTradeTina", "EcoEdgeEddie", "GlobalGainsGloria", "ValueVaultVictor", "RiskRushRiley"
])
