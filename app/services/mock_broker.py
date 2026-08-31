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
        self.connected = True
        self.use_sandbox = True

    def connect(self) -> bool:
        self.connected = True
        return True

    def preview_order(self, symbol: str, qty: int, side: str, order_type: str = "limit", **kwargs) -> Dict:
        return {
            "status": "PREVIEW",
            "preview_id": f"MOCK-PREV-{len(self.trades) + 1}",
            "client_order_id": f"MOCKCID{len(self.trades) + 1:08d}",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": order_type,
            "broker": "MOCK",
        }

    def place_order(self, symbol: str, qty: int, side: str, order_type: str = "market", **kwargs) -> Dict:
        trade = MockTrade(symbol=symbol, quantity=qty, price=float(kwargs.get("limit_price") or 0.0))
        self.trades.append(trade)
        return {
            "status": "filled",
            "order_id": f"MOCK-{len(self.trades)}",
            "preview_id": kwargs.get("preview_id"),
            "symbol": symbol,
            "quantity": qty,
            "qty": qty,
            "side": side,
            "order_type": order_type,
            "timestamp": trade.timestamp.isoformat(),
        }

    def get_trades(self) -> List[MockTrade]:
        return list(self.trades)

    def get_account(self) -> Dict:
        return {"portfolio_value": 10000.0, "cash": 10000.0, "buying_power": 10000.0}

    def get_positions(self) -> Dict:
        return {}
