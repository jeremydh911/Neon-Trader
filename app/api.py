"""
Neon Trader FastAPI Backend
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import os
import requests
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Neon Trader API",
    description="GPU-Accelerated Trading Platform API",
    version="1.0.0"
)

OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://ollama-gpu:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'mistral:latest')

@app.on_event("startup")
async def startup_event():
    logger.info("Neon Trader API starting...")
    logger.info(f"Ollama URL: {OLLAMA_URL}")
    logger.info(f"Ollama Model: {OLLAMA_MODEL}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "neon-trader-api"
    }

@app.get("/llm/status")
async def llm_status():
    """Check LLM status"""
    try:
        # Try container network first
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return {
                "status": "ready" if models else "loading",
                "connection": "connected",
                "models": len(models),
                "model_list": [m.get('name', '') for m in models],
                "url": OLLAMA_URL
            }
    except requests.exceptions.ConnectionError as e:
        # Try localhost fallback
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return {
                    "status": "ready" if models else "loading",
                    "connection": "connected_fallback",
                    "models": len(models),
                    "model_list": [m.get('name', '') for m in models],
                    "url": "http://127.0.0.1:11434"
                }
        except:
            pass
        return {
            "status": "offline",
            "connection": "failed",
            "error": "Cannot connect to Ollama",
            "attempted_url": OLLAMA_URL
        }
    except Exception as e:
        return {
            "status": "error",
            "connection": "failed",
            "error": str(e)
        }

@app.post("/trade/analyze")
async def analyze_trade(symbol: str, quantity: int, order_type: str = "market"):
    """Analyze trade using LLM"""
    try:
        # Check if LLM is available
        llm_response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if llm_response.status_code != 200:
            return {"error": "LLM not available"}
        
        # Get LLM analysis
        prompt = f"Analyze trading signal for {symbol} with {quantity} shares, {order_type} order"
        
        llm_request = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        
        if llm_request.status_code == 200:
            analysis = llm_request.json().get('response', 'No analysis available')
            return {
                "symbol": symbol,
                "quantity": quantity,
                "order_type": order_type,
                "analysis": analysis,
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logger.error(f"Error analyzing trade: {e}")
        return {"error": str(e)}

@app.get("/portfolio")
async def get_portfolio():
    """Get portfolio data"""
    return {
        "portfolio": [
            {"symbol": "AAPL", "shares": 100, "price": 150.25},
            {"symbol": "MSFT", "shares": 50, "price": 320.50},
            {"symbol": "GOOGL", "shares": 25, "price": 140.75},
        ],
        "total_value": 41447.00,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/trades")
async def get_trades(limit: int = 10):
    """Get recent trades"""
    return {
        "trades": [
            {"symbol": "AAPL", "action": "buy", "price": 150.25, "quantity": 10},
            {"symbol": "MSFT", "action": "sell", "price": 325.00, "quantity": 5},
        ],
        "count": 2,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
