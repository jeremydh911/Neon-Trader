"""Test harness for reconciliation worker."""
from app.services.leaderboard import get_leaderboard_db
from app.services.reconciliation import ReconciliationWorker
from app.services.agent_framework import CouncilOrchestrator, SpecialistAgent
from app.services.autonomous_trader import AutonomousTrader
from app.services.memory_service import MemoryService


def run_test():
    # Prepare a lightweight memory-backed trader
    mem = MemoryService(memory_path="./data/test_memory")
    trader = AutonomousTrader(memory_service=mem, use_sandbox=True)

    # Create orchestrator and register a demo agent
    orchestrator = CouncilOrchestrator(council=None, backend_trader=trader)
    agent = SpecialistAgent("TurboTrade Tina", "Technical", "short-term")
    orchestrator.register_agent(agent)

    # Use in-memory DB for testing
    db = get_leaderboard_db(":memory:")
    db.register_agent(agent.name, 0.0)
    # Ensure orchestrator uses the same in-memory DB for rewards
    orchestrator.reward_manager.db = db

    # Add a pending trade that we will later emulate as resolved by memory
    db.add_pending_trade("test-trade-1", agent.name, "AAPL", 1, 150.0)

    # Emulate a completed trade stored in trader memory
    trader.memory.store_trade_memory({
        "symbol": "AAPL",
        "entry_price": 150.0,
        "exit_price": 160.0,
        "quantity": 1,
        "profit_loss": 10.0,
        "profit_loss_pct": 6.66,
        "timestamp": "2025-12-12T00:00:00"
    })

    worker = ReconciliationWorker(orchestrator=orchestrator, trader=trader, db_path=":memory:")
    resolved = worker.reconcile_once()
    print(f"Resolved: {resolved}")
    print("Leaderboard:", db.get_leaderboard())


if __name__ == '__main__':
    run_test()
