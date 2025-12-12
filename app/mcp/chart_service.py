"""
Simple charting microservice returning aggregated chart series.
"""
from fastapi import FastAPI
from datetime import datetime, timedelta
import random

app = FastAPI(title="Neon Trader Chart Service")


@app.get("/chart/{symbol}")
def get_chart(symbol: str, days: int = 30):
    now = datetime.utcnow()
    data = []
    price = 100.0 + random.random() * 10
    for i in range(days):
        data.append({"date": (now - timedelta(days=days - i)).date().isoformat(), "price": round(price + random.gauss(0, 2), 2)})
    return {"symbol": symbol, "series": data}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9002)
