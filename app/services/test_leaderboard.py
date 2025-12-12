"""Simple test harness for the leaderboard DB."""
from app.services.leaderboard import get_leaderboard_db


def run_test():
    db = get_leaderboard_db(":memory:")
    print("Registering agents")
    db.register_agent("TurboTrade Tina", 0.0)
    db.register_agent("EcoEdge Eddie", 5.0)

    print("Initial leaderboard:")
    print(db.get_leaderboard())

    print("Adding pending trade and resolving with +100 PnL for Tina")
    db.add_pending_trade("t1", "TurboTrade Tina", "AAPL", 1, 150.0)
    new_score = db.resolve_trade("t1", 100.0)
    print("Tina new score:", new_score)

    print("Adding pending trade and resolving with -50 PnL for Eddie")
    db.add_pending_trade("t2", "EcoEdge Eddie", "TSLA", 2, 200.0)
    new_score2 = db.resolve_trade("t2", -50.0)
    print("Eddie new score:", new_score2)

    print("Final leaderboard:")
    print(db.get_leaderboard())


if __name__ == '__main__':
    run_test()
