
"""
Persistent leaderboard and pending trade tracker using SQLite.

Provides:
- LeaderboardDB: register agents, apply PnL scoring rules (+1 per $ win, -1.3 per $ loss),
  store pending trades and resolve them later when PnL is known.

This is intentionally minimal and dependency-free (uses stdlib sqlite3).
"""
import sqlite3
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

DEFAULT_DB = "./data/leaderboard.db"


class LeaderboardDB:
    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    agent TEXT PRIMARY KEY,
                    score REAL DEFAULT 0,
                    last_updated TEXT
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_trades (
                    trade_id TEXT PRIMARY KEY,
                    agent TEXT,
                    symbol TEXT,
                    qty REAL,
                    entry_price REAL,
                    order_id TEXT,
                    created_at TEXT,
                    resolved INTEGER DEFAULT 0,
                    pnl REAL
                )
                """
            )

            self._conn.commit()

    def register_agent(self, agent_name: str, initial_score: float = 0.0) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("INSERT OR IGNORE INTO scores(agent, score, last_updated) VALUES(?,?,?)",
                        (agent_name, float(initial_score), datetime.utcnow().isoformat()))
            self._conn.commit()

    def _get_score(self, agent_name: str) -> float:
        cur = self._conn.cursor()
        cur.execute("SELECT score FROM scores WHERE agent = ?", (agent_name,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0

    def apply_pnl(self, agent_name: str, pnl: float) -> float:
        """Apply PnL according to rules and return new score"""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT score FROM scores WHERE agent = ?", (agent_name,))
            row = cur.fetchone()
            prev = float(row[0]) if row else 0.0

            if pnl >= 0:
                delta = pnl
            else:
                delta = pnl * 1.3

            new_score = prev + float(delta)

            cur.execute("INSERT OR REPLACE INTO scores(agent, score, last_updated) VALUES(?,?,?)",
                        (agent_name, new_score, datetime.utcnow().isoformat()))
            self._conn.commit()
            return new_score

    def get_leaderboard(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        cur = self._conn.cursor()
        query = "SELECT agent, score, last_updated FROM scores ORDER BY score DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        cur.execute(query)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def add_pending_trade(self, trade_id: str, agent: str, symbol: str, qty: float, entry_price: float, order_id: Optional[str] = None) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO pending_trades(trade_id, agent, symbol, qty, entry_price, order_id, created_at, resolved, pnl) VALUES(?,?,?,?,?,?,?,0,NULL)",
                (trade_id, agent, symbol, float(qty), float(entry_price), order_id or "", datetime.utcnow().isoformat())
            )
            self._conn.commit()

    def resolve_trade(self, trade_id: str, pnl: float) -> Optional[float]:
        """Mark pending trade resolved and apply pnl to agent score; return new agent score"""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT agent, resolved FROM pending_trades WHERE trade_id = ?", (trade_id,))
            row = cur.fetchone()
            if not row:
                return None
            if row["resolved"]:
                return None

            agent = row["agent"]
            # Mark resolved and store pnl
            cur.execute("UPDATE pending_trades SET resolved=1, pnl=? WHERE trade_id=?", (float(pnl), trade_id))
            # Apply to leaderboard
            new_score = self.apply_pnl(agent, float(pnl))
            self._conn.commit()
            return new_score

    def get_pending_trades(self) -> List[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM pending_trades WHERE resolved=0 ORDER BY created_at ASC")
        rows = cur.fetchall()
        return [dict(r) for r in rows]


# Singleton convenience
_leaderboard_instance: Optional[LeaderboardDB] = None

def get_leaderboard_db(path: Optional[str] = None) -> LeaderboardDB:
    global _leaderboard_instance
    if _leaderboard_instance is None:
        _leaderboard_instance = LeaderboardDB(db_path=path or DEFAULT_DB)
    return _leaderboard_instance
