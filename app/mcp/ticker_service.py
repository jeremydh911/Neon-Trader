"""
Simple MCP-style microservice exposing ticker and charting data.
Runs as a FastAPI app and can be scaled horizontally for throughput.
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from datetime import datetime, timedelta
import random

app = FastAPI(title="AhanaTrade Ticker Service")


class TickerPoint(BaseModel):
    timestamp: datetime
    price: float


@app.get("/ticker/{symbol}")
def get_ticker(symbol: str, points: int = 50):
    """Return synthetic ticker data for a symbol"""
    now = datetime.utcnow()
    data = []
    price = 100.0 + random.random() * 10
    for i in range(points):
        data.append({"timestamp": (now - timedelta(seconds=points - i)).isoformat(), "price": round(price + random.gauss(0, 1), 2)})
    return {"symbol": symbol, "points": data}


@app.get("/symbols")
def get_symbols():
    return {"symbols": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9001)
