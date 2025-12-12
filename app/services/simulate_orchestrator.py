"""
Simple simulation runner for the CouncilOrchestrator.
Registers a few demo specialist agents and runs cycles for sample symbols.
This is intended to be run inside the CPU worker container for testing and simulation.
"""
import logging
import time
import json

from app.services.agent_framework import CouncilOrchestrator, SpecialistAgent
from app.services.rag_memory import get_memory_store
from app.services.trading_council import TradingCouncil
from app.services.autonomous_trader import AutonomousTrader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simulate_orchestrator")


def main():
    # Set up memory and council
    memory = get_memory_store()
    council = TradingCouncil(news_service=None, memory_service=memory)

    # Backend: use AutonomousTrader in sandbox mode (does not require real broker)
    backend = AutonomousTrader(memory_service=memory, llm_service=None, council=council, use_sandbox=True)
    backend.enable_autonomous_trading(False)  # start disabled by default for safety

    orchestrator = CouncilOrchestrator(council=council, backend_trader=backend)

    # Register some demo agents
    orchestrator.register_agent(SpecialistAgent(name="TechBot", role="technical", specialty="stocks"))
    orchestrator.register_agent(SpecialistAgent(name="SentimentBot", role="sentiment", specialty="news"))
    orchestrator.register_agent(SpecialistAgent(name="RiskBot", role="risk", specialty="sizing"))

    symbols = ["AAPL", "TSLA", "MSFT"]

    # Run a few cycles
    for i in range(3):
        symbol = symbols[i % len(symbols)]
        indicators = {"rsi": 25 + i * 10, "macd": 0.5 - i * 0.6, "bb_position": 0.2 + i * 0.3}
        logger.info(f"Running cycle for {symbol} indicators={indicators}")
        result = orchestrator.run_cycle(
            symbol=symbol,
            current_price=100.0 + i * 5,
            indicators=indicators,
            available_capital=20000.0,
            market_sentiment="neutral"
        )

        print(json.dumps(result, indent=2, default=str))
        time.sleep(1)


if __name__ == "__main__":
    main()
