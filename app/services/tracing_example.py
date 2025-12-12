"""Example demonstrating tracing in the Neon Trader orchestrator.

This shows how to use OpenTelemetry tracing with the multi-agent system.
Run this standalone or as a test to see tracing in action.

To view traces:
1. Start a local OpenTelemetry collector (e.g., Jaeger in Docker)
2. Set OTLP_ENDPOINT=http://localhost:4317 (or your collector endpoint)
3. Run this script
4. View traces at http://localhost:16686 (Jaeger UI)
"""

import logging
from datetime import datetime

# Initialize tracing
from tracing_config import setup_tracing

setup_tracing(endpoint="http://localhost:4317", enable_sensitive=True)

# Now import and use the orchestrator
from agent_framework import CouncilOrchestrator, SpecialistAgent
from trading_council import TradingCouncil
from autonomous_trader import AutonomousTrader
from memory_service import MemoryService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_traced_example():
    """Run a simple orchestrator cycle with full tracing."""
    logger.info("Starting traced orchestrator example...")

    # Initialize components
    memory = MemoryService(memory_path="./data/example_memory")
    trader = AutonomousTrader(memory_service=memory, use_sandbox=True)
    council = TradingCouncil()

    # Create orchestrator
    orchestrator = CouncilOrchestrator(council=council, backend_trader=trader)

    # Register agents
    agents = [
        SpecialistAgent("Technical Agent", "Technical", "RSI/MACD"),
        SpecialistAgent("Momentum Agent", "Momentum", "Trend following"),
        SpecialistAgent("Value Agent", "Value", "Fundamental analysis"),
    ]
    for agent in agents:
        orchestrator.register_agent(agent)

    # Run a traced cycle
    logger.info("Running orchestrator cycle with tracing...")
    result = orchestrator.run_cycle(
        symbol="AAPL",
        current_price=180.0,
        indicators={
            "rsi": 35.0,
            "macd": 2.5,
            "bb_position": 0.3,
        },
        available_capital=10000.0,
        market_sentiment="bullish"
    )

    logger.info(f"Cycle result: {result}")
    logger.info("Traces have been sent to OTLP endpoint (check Jaeger at http://localhost:16686)")


if __name__ == "__main__":
    run_traced_example()
