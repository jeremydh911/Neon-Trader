"""
Tim Copilot — AI + engine bridge for the cockpit UX.

Engines decide. AI narrates and routes intent. Never the other way around.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimCopilot:
    """AI-centric trading co-pilot backed by momentum + stop engines."""

    def __init__(self, trader=None, funding_service=None, paper_mode: bool = True, memory=None):
        self.paper_mode = paper_mode or os.getenv("PAPER_MODE", "1").lower() in ("1", "true", "yes")
        self.funding_service = funding_service
        self.trader = trader
        self.memory = memory
        self.history: List[Dict[str, Any]] = []
        self._init_memory()
        self._init_trader()

    def _init_memory(self) -> None:
        if self.memory is not None:
            return
        try:
            from .ahanaflow_memory import get_memory_store

            self.memory = get_memory_store()
            logger.info(
                "Tim memory backend=%s",
                getattr(self.memory, "_backend", type(self.memory).__name__),
            )
        except Exception as e:
            logger.warning("Tim memory init failed: %s", e)
            self.memory = None

    def _init_trader(self) -> None:
        if self.trader is not None:
            return
        try:
            from .autonomous_trader import AutonomousTrader

            broker_type = "mock" if (
                self.paper_mode
                or os.getenv("USE_MOCK_BROKER", "").lower() in ("1", "true", "yes")
            ) else "etrade"
            self.trader = AutonomousTrader(
                memory_service=self.memory,
                llm_service=None,
                council=None,
                broker_type=broker_type,
                use_sandbox=True,
            )
            if hasattr(self.trader, "enable_autonomous_trading"):
                self.trader.enable_autonomous_trading(True)
            logger.info("TimCopilot trader ready (%s)", broker_type)
        except Exception as e:
            logger.error("TimCopilot trader init failed: %s", e)
            self.trader = None

    def _remember_decision(self, decision: Dict[str, Any]) -> None:
        if not self.memory or not decision:
            return
        try:
            content = (
                f"{decision.get('action')} {decision.get('symbol')} "
                f"conf={decision.get('confidence')} — {decision.get('reason')}"
            )
            meta = {
                "action": decision.get("action"),
                "confidence": decision.get("confidence"),
                "reason": decision.get("reason"),
                "symbol": decision.get("symbol"),
            }
            if hasattr(self.memory, "add_decision"):
                try:
                    self.memory.add_decision(
                        content, decision=decision, tags=["tim", "engine"]
                    )
                except TypeError:
                    self.memory.add_decision(
                        content, metadata=meta, tags=["tim", "engine"]
                    )
            elif hasattr(self.memory, "remember"):
                self.memory.remember(
                    content,
                    kind="decision",
                    symbol=decision.get("symbol"),
                    tags=["tim", "engine"],
                    metadata=meta,
                )
        except Exception as e:
            logger.warning("Tim remember decision failed: %s", e)

    def _recall_for(self, query: str, symbol: Optional[str] = None) -> str:
        if not self.memory:
            return ""
        try:
            if hasattr(self.memory, "recall_context"):
                return self.memory.recall_context(query, top_k=3, symbol=symbol) or ""
            hits = self.memory.search(query, limit=3)
            if not hits:
                return ""
            lines = ["[memory]"]
            for h in hits:
                text = getattr(h, "content", None) or (h.get("content") if isinstance(h, dict) else str(h))
                lines.append(f"- {str(text)[:160]}")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("Tim recall failed: %s", e)
            return ""

    def extract_symbol(self, text: str) -> Optional[str]:
        common = {
            "AAPL", "MSFT", "GOOGL", "GOOG", "TSLA", "NVDA", "META", "AMZN",
            "AMD", "NFLX", "SPY", "QQQ", "IWM", "JPM", "BAC", "XOM", "COIN",
        }
        upper = (text or "").upper()
        for sym in common:
            if re.search(rf"\b{sym}\b", upper):
                return sym
        stop = {"BUY", "SELL", "HOLD", "WHAT", "SHOW", "ANALYZE", "SNIPE", "TIM", "THE", "FOR", "AND", "RISK"}
        for m in re.findall(r"\b[A-Z]{1,5}\b", upper):
            if m not in stop:
                return m
        return None

    def available_capital(self) -> float:
        if self.funding_service:
            try:
                s = self.funding_service.get_balance_summary()
                return float(s.get("allocated_to_portfolio", 0) or 0)
            except Exception:
                pass
        return 10_000.0

    def analyze(self, symbol: str) -> Dict[str, Any]:
        symbol = (symbol or "").upper().strip()
        if not symbol:
            return {"status": "error", "message": "Need a symbol", "action": "HOLD"}

        from .momentum_engine import momentum_gate_report, risk_based_shares

        research: Dict[str, Any] = {}
        indicators: Dict[str, Any] = {}
        price = 0.0

        if self.trader and hasattr(self.trader, "perform_research"):
            try:
                research = self.trader.perform_research(symbol) or {}
                indicators = dict(research.get("indicators") or {})
                raw_price = research.get("price") or 0
                price = float(raw_price)
                import math
                if math.isnan(price) or math.isinf(price) or price <= 0:
                    price = 0.0
            except Exception as e:
                logger.warning("research failed for %s: %s", symbol, e)
                price = 0.0

        demo = False
        if price <= 0:
            price = 100.0
            indicators = {
                "sma_20": 98.0, "sma_50": 95.0, "rsi": 58.0, "macd": 0.4,
                "volume_ratio": 2.0, "momentum_pct": 70.0, "vwap": 99.0, "atr": 1.5,
            }
            demo = True
            research["demo_indicators"] = True

        report = momentum_gate_report(price, indicators)
        levels = report.get("levels") or {}
        capital = self.available_capital()
        stop_px = float(levels.get("stop_loss_price") or price * 0.98)
        shares = risk_based_shares(
            capital=capital,
            entry_price=price,
            stop_price=stop_px,
        )
        memory_ctx = self._recall_for(f"{symbol} momentum {report['action']}", symbol=symbol)
        narration = self._narrate(symbol, report, shares, capital, demo=demo, memory_ctx=memory_ctx)

        result = {
            "status": "success",
            "symbol": symbol,
            "price": price,
            "action": report["action"],
            "confidence": float(report["confidence"]),
            "reason": report["reason"],
            "gates": report["gates"],
            "gates_passed": report["gates_passed"],
            "gates_total": report["gates_total"],
            "levels": levels,
            "shares": int(shares),
            "capital": capital,
            "narration": narration,
            "memory_context": memory_ctx,
            "research": research,
            "demo": demo,
            "paper_mode": self.paper_mode,
            "timestamp": _now(),
        }
        self._remember_decision(result)
        self.history.append({"type": "analyze", "symbol": symbol, "action": result["action"]})
        return result

    def snipe(self, symbol: str, force: bool = False) -> Dict[str, Any]:
        decision = self.analyze(symbol)
        if decision.get("action") != "BUY" and not force:
            return {
                "status": "blocked",
                "message": f"Tim refuses the snipe — {decision.get('reason')}",
                "decision": decision,
            }
        if not self.trader:
            return {"status": "error", "message": "Trader offline", "decision": decision}

        price = float(decision["price"])
        shares = max(1, int(decision.get("shares") or 1))
        levels = decision.get("levels") or {}

        order = self.trader.execute_order(symbol, "BUY", shares, price=price, price_type="MARKET")
        if order.get("status") != "SUCCESS":
            return {
                "status": "error",
                "message": f"Order failed: {order}",
                "decision": decision,
                "order": order,
            }

        indicators = (decision.get("research") or {}).get("indicators") or {}
        position = self.trader.open_position_with_stop_loss(
            symbol=symbol,
            entry_price=price,
            quantity=shares,
            stop_loss_percent=levels.get("stop_loss_pct"),
            take_profit_percent=levels.get("take_profit_pct"),
            indicators=indicators,
            place_broker_stop=True,
        )

        if self.funding_service and hasattr(self.funding_service, "apply_trade_debit"):
            try:
                self.funding_service.apply_trade_debit(price * shares)
            except Exception:
                pass

        out = {
            "status": "success",
            "message": f"Snipe filled — {shares} {symbol} @ ${price:.2f} · stop armed",
            "decision": decision,
            "order": order,
            "position": position,
            "timestamp": _now(),
        }
        if self.memory and hasattr(self.memory, "remember"):
            try:
                self.memory.remember(
                    f"SNIPE {shares} {symbol} @ {price:.2f} stop armed",
                    kind="trade_result",
                    symbol=symbol,
                    tags=["tim", "snipe", "paper" if self.paper_mode else "live"],
                    metadata={"shares": shares, "price": price, "side": "BUY"},
                )
            except Exception as e:
                logger.warning("Tim remember snipe failed: %s", e)
        self.history.append({"type": "snipe", "symbol": symbol, "shares": shares})
        return out

    def chat(self, message: str) -> Dict[str, Any]:
        msg = (message or "").strip()
        if not msg:
            return {"status": "error", "response": "Say a ticker, snipe, or ask for risk."}

        lower = msg.lower()
        symbol = self.extract_symbol(msg)

        if any(w in lower for w in ("position", "risk", "pnl", "stops", "open trades")):
            return self._risk_reply()

        wants_snipe = any(w in lower for w in ("snipe", "execute", "buy now", "enter now"))
        wants_buy_advice = ("buy" in lower or "long" in lower or "enter" in lower) and not wants_snipe

        if wants_snipe:
            if not symbol:
                return {
                    "status": "need_symbol",
                    "response": "Name the ticker. Example: **snipe NVDA**",
                }
            result = self.snipe(symbol)
            d = result.get("decision") or {}
            text = result.get("message", "")
            if d.get("narration"):
                text = f"{text}\n\n{d['narration']}"
            return {
                "status": result.get("status"),
                "response": text,
                "decision": d,
                "snipe": result,
            }

        if symbol or any(w in lower for w in ("analyze", "check", "look at", "scan", "tim")) or wants_buy_advice:
            if not symbol:
                return {
                    "status": "need_symbol",
                    "response": "Give me a ticker. I’ll stack momentum gates and tell you if it’s a snipe.",
                }
            decision = self.analyze(symbol)
            return {
                "status": "success",
                "response": decision.get("narration") or decision.get("reason"),
                "decision": decision,
            }

        return {
            "status": "success",
            "response": (
                "I’m **Tim** — momentum sniper, not a diary.\n\n"
                "Try: `analyze NVDA` · `snipe AAPL` · `show risk`\n"
                "I only buy strength with stops armed. Engines decide. I narrate."
            ),
        }

    def _risk_reply(self) -> Dict[str, Any]:
        positions: Dict[str, Any] = {}
        risk: Dict[str, Any] = {}
        if self.trader:
            try:
                positions = self.trader.get_positions_status() or {}
            except Exception:
                positions = {}
            try:
                risk = self.trader.get_risk_summary() or {}
            except Exception:
                risk = {}
        lines = ["**Risk desk**", f"Open positions: **{len(positions)}**"]
        daily = risk.get("daily_pnl")
        if daily is None and hasattr(self.trader, "_daily_pnl"):
            daily = getattr(self.trader, "_daily_pnl", 0)
        if daily is not None:
            lines.append(f"Daily PnL: **${float(daily):,.2f}**")
        for sym, pos in list(positions.items())[:8]:
            stop = pos.get("stop_loss_price") or pos.get("effective_stop")
            lines.append(f"- `{sym}` entry ${pos.get('entry_price')} · stop ${stop}")
        if not positions:
            lines.append("_Flat. Waiting for a clean snipe._")
        return {"status": "success", "response": "\n".join(lines), "positions": positions, "risk": risk}

    def _narrate(
        self,
        symbol: str,
        report: Dict[str, Any],
        shares: int,
        capital: float,
        demo: bool = False,
        memory_ctx: str = "",
    ) -> str:
        action = report["action"]
        conf = float(report["confidence"])
        reason = report["reason"]
        levels = report.get("levels") or {}
        gates_ok = report.get("gates_passed", 0)
        gates_n = report.get("gates_total", 0)
        demo_note = " _(demo tape — live feed offline)_" if demo else ""

        if action == "BUY":
            base = (
                f"**{symbol} — SNIPE WINDOW**{demo_note}\n"
                f"Confidence **{conf:.0%}** · Gates **{gates_ok}/{gates_n}**\n"
                f"{reason}\n"
                f"Size: **{shares}** sh on ${capital:,.0f}\n"
                f"Stop **${levels.get('stop_loss_price', '—')}** "
                f"({levels.get('stop_loss_pct', '—')}%) · "
                f"Target **${levels.get('take_profit_price', '—')}** "
                f"({levels.get('take_profit_pct', '—')}%)\n"
                f"_Engines green. Feelings offline._"
            )
        elif action == "SELL":
            base = (
                f"**{symbol} — FADE / EXIT**{demo_note}\n"
                f"{reason}\nGates {gates_ok}/{gates_n}. Don’t marry the loser."
            )
        else:
            base = (
                f"**{symbol} — NO SNIPE**{demo_note}\n"
                f"{reason}\nGates {gates_ok}/{gates_n}. Waiting for stacked confirmation."
            )

        if memory_ctx:
            base = f"{base}\n\n{memory_ctx}"

        polished = self._llm_polish(symbol, action, reason)
        if polished:
            return f"{base}\n\n_{polished}_"
        return base

    def _llm_polish(self, symbol: str, action: str, reason: str) -> Optional[str]:
        try:
            import requests

            base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            model = os.getenv("OLLAMA_MODEL", "mistral:latest")
            prompt = (
                f"You are Tim, a terse momentum trader. One short sentence confirming "
                f"engine decision {action} on {symbol}. Reason: {reason}. "
                f"Do not invent numbers. No emojis."
            )
            r = requests.post(
                f"{base}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=2.0,
            )
            if r.status_code == 200:
                text = (r.json() or {}).get("response", "").strip()
                return text[:240] if text else None
        except Exception:
            return None
        return None

    def risk_strip(self) -> Dict[str, Any]:
        capital = self.available_capital()
        positions: Dict[str, Any] = {}
        daily_pnl = 0.0
        if self.trader:
            try:
                positions = self.trader.get_positions_status() or {}
            except Exception:
                pass
            if hasattr(self.trader, "_daily_pnl"):
                daily_pnl = float(getattr(self.trader, "_daily_pnl") or 0)
            else:
                try:
                    risk = self.trader.get_risk_summary() or {}
                    daily_pnl = float(risk.get("daily_pnl") or 0)
                except Exception:
                    pass
        mem_stats: Dict[str, Any] = {}
        if self.memory:
            try:
                if hasattr(self.memory, "stats"):
                    mem_stats = self.memory.stats() or {}
                elif hasattr(self.memory, "get_memory_summary"):
                    mem_stats = self.memory.get_memory_summary() or {}
            except Exception:
                mem_stats = {}
        return {
            "capital": capital,
            "open_positions": len(positions),
            "daily_pnl": daily_pnl,
            "paper_mode": self.paper_mode,
            "positions": positions,
            "memory": mem_stats,
            "memory_backend": mem_stats.get("backend")
            or ("ahanaflow" if type(self.memory).__name__ == "AhanaFlowMemory" else "legacy"),
            "memory_vectors": mem_stats.get("vectors") or mem_stats.get("total_memories") or 0,
        }


    def speak(self, text: str, *, slot: Optional[str] = None) -> Dict[str, Any]:
        """Narrate through Jeremiah's AhanaVoice tiny pack (~16KB seats)."""
        try:
            from .ahanavoice_client import speak_tim

            result = speak_tim(text, slot=slot)
            return {
                "status": "success",
                "audio": result.audio,
                "content_type": result.content_type,
                **result.as_dict(),
            }
        except Exception as exc:
            logger.warning("Tim speak failed: %s", exc)
            return {"status": "error", "message": str(exc)}


def get_tim_copilot(funding_service=None) -> TimCopilot:
    return TimCopilot(funding_service=funding_service, paper_mode=True)
