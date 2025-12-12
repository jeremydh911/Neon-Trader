"""
Trading Council LLM Integration
Connects Ollama instances to council members for AI-powered voting
"""

import requests
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class OllamaLLMClient:
    """Client for communicating with Ollama instances"""
    
    def __init__(self, base_url: str, model: str, timeout: int = 30):
        """
        Initialize Ollama client
        
        Args:
            base_url: Ollama server URL (e.g., http://localhost:11434)
            model: Model name (e.g., mistral, neural-chat, orca-mini)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.api_endpoint = f"{self.base_url}/api/generate"
        self.tags_endpoint = f"{self.base_url}/api/tags"
    
    def is_available(self) -> bool:
        """Check if Ollama instance is available"""
        try:
            response = requests.get(self.tags_endpoint, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def generate(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """
        Generate response from LLM
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text or None if error
        """
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                    "temperature": 0.7
                }
            }
            
            response = requests.post(
                self.api_endpoint,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "").strip()
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"Error generating with {self.model}: {e}")
            return None


class LLMPoweredCouncilMember:
    """Base class for LLM-powered council members"""
    
    def __init__(self, name: str, role: str, llm_client: OllamaLLMClient):
        """
        Initialize LLM council member
        
        Args:
            name: Member name
            role: Member role/expertise
            llm_client: Ollama client instance
        """
        self.name = name
        self.role = role
        self.llm = llm_client
        self.voting_history = []
    
    def generate_analysis(self, context: str) -> str:
        """
        Generate analysis using LLM
        
        Args:
            context: Analysis context/prompt
            
        Returns:
            Generated analysis text
        """
        if not self.llm.is_available():
            logger.warning(f"LLM for {self.name} not available")
            return "LLM unavailable"
        
        response = self.llm.generate(context, max_tokens=300)
        return response or "No response generated"


class TechnicalAnalystLLM(LLMPoweredCouncilMember):
    """LLM-powered technical analyst"""
    
    def analyze_indicators(self, symbol: str, indicators: Dict[str, Any]) -> Dict:
        """
        Analyze technical indicators using LLM
        
        Args:
            symbol: Stock symbol
            indicators: Technical indicators dict
            
        Returns:
            Analysis result with vote and reasoning
        """
        prompt = f"""
You are a professional technical analyst. Analyze these trading indicators for {symbol}:

RSI: {indicators.get('rsi', 50)}
MACD: {indicators.get('macd', 0)}
Bollinger Band Position: {indicators.get('bb_position', 0.5)}
ATR: {indicators.get('atr', 1.0)}

Provide:
1. Brief technical analysis (1-2 sentences)
2. Trading signal: BUY, SELL, or HOLD
3. Confidence level: 0-100

Format: SIGNAL: [SIGNAL] | CONFIDENCE: [0-100] | ANALYSIS: [text]
"""
        
        response = self.generate_analysis(prompt)
        return self._parse_response(response, "Technical Analysis")
    
    def _parse_response(self, response: str, context: str) -> Dict:
        """Parse LLM response into structured format"""
        return {
            "member": self.name,
            "role": self.role,
            "context": context,
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }


class SentimentAnalystLLM(LLMPoweredCouncilMember):
    """LLM-powered sentiment analyst"""
    
    def analyze_sentiment(self, symbol: str, sentiment: str, news_headlines: list = None) -> Dict:
        """
        Analyze market sentiment using LLM
        
        Args:
            symbol: Stock symbol
            sentiment: Overall market sentiment (bullish/bearish/neutral)
            news_headlines: Recent news headlines
            
        Returns:
            Sentiment analysis with vote and reasoning
        """
        news_context = ""
        if news_headlines:
            news_context = "\nRecent headlines:\n" + "\n".join(f"- {h}" for h in news_headlines[:5])
        
        prompt = f"""
You are a financial sentiment analyst. Evaluate the trading sentiment for {symbol}:

Current Market Sentiment: {sentiment}
{news_context}

Provide:
1. Sentiment assessment impact on {symbol}
2. Recommended action: BUY, SELL, or HOLD
3. Risk level: Low, Medium, High
4. Confidence: 0-100

Format: ACTION: [ACTION] | RISK: [LEVEL] | CONFIDENCE: [0-100] | ASSESSMENT: [text]
"""
        
        response = self.generate_analysis(prompt)
        return self._parse_response(response, "Sentiment Analysis")
    
    def _parse_response(self, response: str, context: str) -> Dict:
        """Parse LLM response"""
        return {
            "member": self.name,
            "role": self.role,
            "context": context,
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }


class MemoryCuratorLLM(LLMPoweredCouncilMember):
    """LLM-powered memory curator - pattern recognition and learning"""
    
    def analyze_patterns(self, symbol: str, similar_trades: list = None) -> Dict:
        """
        Analyze historical patterns and lessons using LLM
        
        Args:
            symbol: Stock symbol
            similar_trades: Similar historical trades
            
        Returns:
            Pattern analysis with recommendation
        """
        trades_summary = ""
        if similar_trades:
            wins = sum(1 for t in similar_trades if t.get('success'))
            trades_summary = f"\n{len(similar_trades)} similar trades found ({wins} profitable)"
        
        prompt = f"""
You are a trading pattern recognition expert. Analyze patterns for {symbol}:
{trades_summary}

Based on historical patterns and similar trades:
1. Pattern recognition assessment
2. Historical success rate evaluation
3. Risk/reward recommendation: BUY, SELL, or HOLD
4. Confidence in pattern: 0-100

Format: RECOMMENDATION: [ACTION] | PATTERN_STRENGTH: [0-100] | INSIGHTS: [text]
"""
        
        response = self.generate_analysis(prompt)
        return self._parse_response(response, "Pattern Analysis")
    
    def _parse_response(self, response: str, context: str) -> Dict:
        """Parse LLM response"""
        return {
            "member": self.name,
            "role": self.role,
            "context": context,
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }


class CouncilLLMOrchestrator:
    """Orchestrates multiple Ollama instances for trading council"""
    
    def __init__(
        self,
        technical_url: str = "http://localhost:11434",
        sentiment_url: str = "http://localhost:11435",
        memory_url: str = "http://localhost:11436"
    ):
        """
        Initialize council LLM orchestrator
        
        Args:
            technical_url: Technical analyst Ollama URL
            sentiment_url: Sentiment analyst Ollama URL
            memory_url: Memory curator Ollama URL
        """
        self.technical_client = OllamaLLMClient(technical_url, "mistral")
        self.sentiment_client = OllamaLLMClient(sentiment_url, "neural-chat")
        self.memory_client = OllamaLLMClient(memory_url, "orca-mini")
        
        self.technical = TechnicalAnalystLLM(
            "Technical Analyst LLM",
            "technical_analysis",
            self.technical_client
        )
        
        self.sentiment = SentimentAnalystLLM(
            "Sentiment Analyst LLM",
            "sentiment_analysis",
            self.sentiment_client
        )
        
        self.memory = MemoryCuratorLLM(
            "Memory Curator LLM",
            "pattern_recognition",
            self.memory_client
        )
    
    def check_all_available(self) -> Dict[str, bool]:
        """Check if all LLM instances are available"""
        return {
            "technical": self.technical_client.is_available(),
            "sentiment": self.sentiment_client.is_available(),
            "memory": self.memory_client.is_available()
        }
    
    def conduct_trade_analysis(
        self,
        symbol: str,
        current_price: float,
        indicators: Dict[str, Any],
        market_sentiment: str,
        similar_trades: list = None
    ) -> Dict:
        """
        Conduct full trade analysis with all LLM council members
        
        Args:
            symbol: Stock symbol
            current_price: Current price
            indicators: Technical indicators
            market_sentiment: Market sentiment
            similar_trades: Similar historical trades
            
        Returns:
            Combined analysis from all members
        """
        
        results = {
            "symbol": symbol,
            "price": current_price,
            "timestamp": datetime.utcnow().isoformat(),
            "analyses": {}
        }
        
        # Technical analysis
        try:
            results["analyses"]["technical"] = self.technical.analyze_indicators(
                symbol, indicators
            )
        except Exception as e:
            logger.error(f"Technical analysis error: {e}")
            results["analyses"]["technical"] = {"error": str(e)}
        
        # Sentiment analysis
        try:
            results["analyses"]["sentiment"] = self.sentiment.analyze_sentiment(
                symbol, market_sentiment
            )
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            results["analyses"]["sentiment"] = {"error": str(e)}
        
        # Pattern analysis
        try:
            results["analyses"]["memory"] = self.memory.analyze_patterns(
                symbol, similar_trades
            )
        except Exception as e:
            logger.error(f"Pattern analysis error: {e}")
            results["analyses"]["memory"] = {"error": str(e)}
        
        return results
    
    def get_status(self) -> Dict:
        """Get orchestrator status"""
        availability = self.check_all_available()
        
        return {
            "orchestrator_status": "operational" if all(availability.values()) else "partial",
            "instances": {
                "technical": {
                    "available": availability["technical"],
                    "model": "mistral",
                    "url": "http://localhost:11434"
                },
                "sentiment": {
                    "available": availability["sentiment"],
                    "model": "neural-chat",
                    "url": "http://localhost:11435"
                },
                "memory": {
                    "available": availability["memory"],
                    "model": "orca-mini",
                    "url": "http://localhost:11436"
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================
# INITIALIZATION HELPER
# ============================================

def initialize_llm_council(
    technical_url: str = "http://localhost:11434",
    sentiment_url: str = "http://localhost:11435",
    memory_url: str = "http://localhost:11436"
) -> CouncilLLMOrchestrator:
    """
    Initialize the LLM-powered trading council
    
    Args:
        technical_url: Technical analyst Ollama URL
        sentiment_url: Sentiment analyst Ollama URL  
        memory_url: Memory curator Ollama URL
        
    Returns:
        CouncilLLMOrchestrator instance
    """
    logger.info("Initializing LLM-powered Trading Council")
    
    orchestrator = CouncilLLMOrchestrator(technical_url, sentiment_url, memory_url)
    
    status = orchestrator.check_all_available()
    available_count = sum(status.values())
    total_count = len(status)
    
    logger.info(f"Council LLM Status: {available_count}/{total_count} instances available")
    
    if available_count < total_count:
        logger.warning(f"Not all LLM instances available: {status}")
    
    return orchestrator


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test initialization
    print("Testing LLM Council Initialization...")
    orchestrator = initialize_llm_council()
    
    status = orchestrator.get_status()
    print("\nOrchestrator Status:")
    print(json.dumps(status, indent=2))
