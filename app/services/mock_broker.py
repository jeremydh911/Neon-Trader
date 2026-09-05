from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional


@dataclass
class MockTrade:
    symbol: str
    quantity: int
    price: float
    side: str = "buy"
    order_type: str = "market"
    stop_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MockBroker:
    """Simple in-memory broker for sandbox testing."""

    def __init__(self):
        self.trades: List[MockTrade] = []
        self.connected = True

    def connect(self) -> bool:
        self.connected = True
        return True

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        limit_price: float = None,
        stop_price: float = None,
    ) -> Dict:
        trade = MockTrade(
            symbol=symbol,
            quantity=qty,
            price=float(limit_price or stop_price or 0.0),
            side=side,
            order_type=order_type,
            stop_price=stop_price,
        )
        self.trades.append(trade)
        # Mirror E*TRADE acceptance for stop orders; market fills immediately
        status = "filled" if str(order_type).lower() in ("market", "limit") else "PLACED"
        return {
            "status": status,
            "order_id": f"MOCK-{len(self.trades)}",
            "symbol": symbol,
            "quantity": qty,
            "side": side,
            "order_type": order_type,
            "stop_price": stop_price,
            "timestamp": trade.timestamp.isoformat(),
        }

    def get_trades(self) -> List[MockTrade]:
        return list(self.trades)
