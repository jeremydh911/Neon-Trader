#!/usr/bin/env python3.11
"""
Neon Trader - GPU-Accelerated Trading Platform
Main entry point with early startup support
"""

import os
import sys
import time
import logging
import requests
import threading
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://ollama-gpu:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'mistral:latest')
ALLOW_EARLY_START = os.getenv('ALLOW_EARLY_START', 'true').lower() == 'true'
CHECK_INTERVAL = 5  # Check LLM every 5 seconds

def check_ollama_health():
    """Check if Ollama is responding"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Ollama not ready: {e}")
        return False

def wait_for_model_load():
    """Wait for a model to be loaded in Ollama"""
    logger.info(f"Waiting for Ollama at {OLLAMA_URL}...")
    max_wait = 300  # 5 minutes max wait
    elapsed = 0
    
    while elapsed < max_wait:
        try:
            response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                if models:
                    logger.info(f"✓ Found {len(models)} model(s): {[m['name'] for m in models]}")
                    return True
                else:
                    logger.info("Ollama ready but no models loaded yet. Pulling model...")
                    # Try to pull the model
                    pull_model()
                    return True
        except Exception as e:
            logger.debug(f"Waiting for Ollama... ({elapsed}s)")
        
        time.sleep(CHECK_INTERVAL)
        elapsed += CHECK_INTERVAL
    
    return False

def pull_model():
    """Pull the specified model"""
    try:
        logger.info(f"Pulling model {OLLAMA_MODEL}...")
        response = requests.post(
            f"{OLLAMA_URL}/api/pull",
            json={"name": OLLAMA_MODEL},
            timeout=600,
            stream=True
        )
        if response.status_code == 200:
            logger.info("✓ Model pull completed")
            return True
    except Exception as e:
        logger.error(f"Failed to pull model: {e}")
    return False

def start_streamlit():
    """Start Streamlit application"""
    logger.info("Starting Neon Trader Streamlit application...")
    os.system("streamlit run app/main.py --server.port=8501 --server.address=0.0.0.0")

def start_api():
    """Start FastAPI backend"""
    logger.info("Starting Neon Trader API...")
    os.system("uvicorn app.api:app --host 0.0.0.0 --port 8000")

def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("🚀 Neon Trader - GPU-Accelerated Trading Platform")
    logger.info("=" * 60)
    
    # Check if we should wait for LLM
    if ALLOW_EARLY_START:
        logger.info("⚡ Early start enabled - starting UI without waiting for LLM")
        
        # Start LLM checker in background
        def monitor_llm():
            while True:
                if check_ollama_health():
                    logger.info("✓ Ollama LLM is now available!")
                    break
                time.sleep(CHECK_INTERVAL)
        
        monitor_thread = threading.Thread(target=monitor_llm, daemon=True)
        monitor_thread.start()
    else:
        logger.info("Waiting for Ollama LLM to be ready...")
        if not wait_for_model_load():
            logger.warning("Ollama not available, but starting anyway...")
    
    # Create required directories
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    Path("/app/logs").mkdir(parents=True, exist_ok=True)
    Path("/app/models").mkdir(parents=True, exist_ok=True)
    
    # Start services in threads
    logger.info("Starting services...")
    
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    logger.info("Waiting 5 seconds for API to start...")
    time.sleep(5)
    
    # Start Streamlit (blocks)
    start_streamlit()

if __name__ == "__main__":
    main()
