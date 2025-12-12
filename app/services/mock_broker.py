from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict


@dataclass
class MockTrade:
    symbol: str
    quantity: int
    price: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MockBroker:
    """Simple in-memory broker for sandbox testing."""

    def __init__(self):
        self.trades: List[MockTrade] = []

    def connect(self) -> bool:
        return True

    def place_order(self, symbol: str, qty: int, side: str, order_type: str = "market") -> Dict:
        trade = MockTrade(symbol=symbol, quantity=qty, price=0.0)
        self.trades.append(trade)
        return {
            "status": "filled",
            "order_id": f"MOCK-{len(self.trades)}",
            "symbol": symbol,
            "quantity": qty,
            "side": side,
            "order_type": order_type,
            "timestamp": trade.timestamp.isoformat()
        }

    def get_trades(self) -> List[MockTrade]:
        return list(self.trades)
