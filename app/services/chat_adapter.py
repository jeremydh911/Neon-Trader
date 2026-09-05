"""
Chat Integration Module
Bridges chat interface with autonomous trader and trading council
Includes RAG memory for contextual analysis
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class TraderChatAdapter:
    """Adapts autonomous trader for chat interface"""
    
    def __init__(self, memory_store=None):
        """Initialize trader adapter"""
        self.trader = None
        self.memory = memory_store
        self.stock_data_service = None
        self._init_stock_data_service()
        self._init_trader()
        self._init_memory()
    
    def _init_stock_data_service(self):
        """Initialize stock data service"""
        try:
            from .stock_data_service import get_stock_data_service
            self.stock_data_service = get_stock_data_service()
            logger.info("✅ Stock data service initialized")
        except Exception as e:
            logger.warning(f"Could not initialize stock data service: {e}")
            self.stock_data_service = None
    
    def _init_memory(self):
        """Initialize memory store"""
        if not self.memory:
            try:
                from .rag_memory import get_memory_store
                self.memory = get_memory_store()
            except ImportError as e:
                logger.warning(f"Could not import memory store: {e}")

    def _init_trader(self):
        """Initialize autonomous trader with memory service and broker access"""
        try:
            from .autonomous_trader import AutonomousTrader
            # Initialize memory first if not already done
            if not self.memory:
                self._init_memory()
            # Create trader with memory service and broker access (E*TRADE)
            self.trader = AutonomousTrader(
                memory_service=self.memory,
                broker_type='etrade',
                use_sandbox=True  # Use sandbox for safety
            )
        except Exception as e:
            logger.error(f"Failed to initialize autonomous trader: {e}")
            self.trader = None

    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process user query and get trader response with memory context
        Automatically fetches stock data if a ticker is mentioned
        
        Args:
            query: User message
            
        Returns:
            Response dict with analysis
        """
        if not self.trader:
            return {
                "status": "error",
                "message": "Trader not available",
                "response": "The autonomous trader is not currently available. Please try again later."
            }
        
        try:
            # Extract intent and symbol from query
            intent = self._extract_intent(query)
            symbol = self._extract_symbol(query)
            
            # Fetch stock data if symbol found
            stock_data = None
            stock_data_context = ""
            
            if symbol and self.stock_data_service:
                logger.info(f"📊 Fetching stock data for {symbol}...")
                stock_data = self.stock_data_service.get_stock_data(symbol)
                
                if stock_data and not stock_data.get('error'):
                    # Format stock data for response context
                    stock_data_context = self._format_stock_data_for_llm(symbol, stock_data)
                    logger.info(f"✅ Stock data fetched for {symbol}")
            
            # Get memory context if available
            memory_context = ""
            if self.memory:
                try:
                    if hasattr(self.memory, "recall_context"):
                        memory_context = self.memory.recall_context(query, top_k=3, symbol=symbol) or ""
                    else:
                        from .rag_memory import TraderMemoryAgent
                        memory_agent = TraderMemoryAgent(self.memory)
                        memory_data = memory_agent.analyze_with_memory(query, symbol)
                        memory_context = memory_data.get("memory_context", "")
                except Exception as mem_err:
                    logger.debug("memory context skipped: %s", mem_err)
            
            # Combine stock and memory context
            combined_context = stock_data_context + (f"\n\n{memory_context}" if memory_context else "")
            
            # Tim engines first — AI narrates after gates fire
            tim_decision = None
            try:
                from .tim_copilot import TimCopilot
                tim = TimCopilot(trader=self.trader, paper_mode=True)
                if symbol and ("analyze" in intent or "trade" in intent or "buy" in intent or "sell" in intent or "chart" in query.lower()):
                    tim_reply = tim.chat(query)
                    response = tim_reply.get("response") or ""
                    tim_decision = tim_reply.get("decision")
                elif "portfolio" in intent or "position" in intent or "risk" in query.lower():
                    tim_reply = tim.chat(query if query else "show risk")
                    response = tim_reply.get("response") or ""
                else:
                    response = None
            except Exception as _tim_err:
                logger.debug(f"TimCopilot fallback: {_tim_err}")
                response = None

            if not response:
                if "analyze" in intent or "what" in intent.lower() or "chart" in query.lower():
                    response = self._get_analysis(query, combined_context)
                elif "trade" in intent or "buy" in intent or "sell" in intent:
                    response = self._get_trade_advice(query, combined_context)
                elif "portfolio" in intent or "position" in intent:
                    response = self._get_portfolio_analysis(query, combined_context)
                else:
                    response = self._get_general_response(query, combined_context)
            
            # Store in memory if it's a significant query
            if self.memory and intent != "general":
                try:
                    self.memory.add_discussion(
                        f"Query: {query}\nResponse: {response}",
                        tags=[intent, symbol] if symbol else [intent]
                    )
                except Exception as e:
                    logger.debug(f"Could not store in memory: {e}")
            
            return {
                "status": "success",
                "intent": intent,
                "response": response,
                "memory_context": memory_context,
                "stock_data": stock_data,
                "stock_symbol": symbol,
                "tim_decision": tim_decision,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "status": "error",
                "message": str(e),
                "response": f"Error processing your request: {str(e)}"
            }
    
    def _extract_symbol(self, query: str) -> Optional[str]:
        """Extract stock symbol from query"""
        common_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN", "JPM", "IBM", "BAC"]
        query_upper = query.upper()
        
        for symbol in common_symbols:
            if symbol in query_upper:
                return symbol
        
        # Try to find 4-letter symbols
        import re
        matches = re.findall(r'\b[A-Z]{1,5}\b', query)
        if matches:
            return matches[0]
        
        return None
    
    def _extract_intent(self, query: str) -> str:
        """Extract intent from query"""
        query_lower = query.lower()
        
        keywords = {
            "analyze": ["analyze", "analysis", "what", "how", "is", "chart"],
            "trade": ["buy", "sell", "trade", "execute", "place"],
            "portfolio": ["portfolio", "position", "holding", "stock"],
            "general": ["think", "view", "opinion", "suggest"]
        }
        
        for intent, words in keywords.items():
            if any(word in query_lower for word in words):
                return intent
        
        return "general"
    
    def _format_stock_data_for_llm(self, symbol: str, stock_data: Dict[str, Any]) -> str:
        """Format stock data into detailed context for trader analysis"""
        if not stock_data or stock_data.get('error'):
            return ""
        
        try:
            # Extract key data
            price = stock_data.get('current_price', 'N/A')
            change_pct = stock_data.get('price_change_pct', 0)
            pe_ratio = stock_data.get('pe_ratio', 'N/A')
            high_52w = stock_data.get('high_52w', 'N/A')
            low_52w = stock_data.get('low_52w', 'N/A')
            company_name = stock_data.get('company_name', symbol)
            volume = stock_data.get('volume', 'N/A')
            avg_volume = stock_data.get('avg_volume', 'N/A')
            
            # Technical indicators
            technicals = stock_data.get('technicals', {})
            sma_20 = technicals.get('sma_20', 'N/A')
            sma_50 = technicals.get('sma_50', 'N/A')
            sma_200 = technicals.get('sma_200', 'N/A')
            rsi = technicals.get('rsi_14', 'N/A')
            rsi_signal = technicals.get('rsi_signal', 'N/A')
            macd = technicals.get('macd', 'N/A')
            volume_trend = technicals.get('volume_trend', 'N/A')
            volume_ratio = technicals.get('volume_ratio', 1.0)
            momentum_pct = technicals.get('momentum_pct', 'N/A')
            price_vs_sma50 = technicals.get('price_vs_sma50', 'N/A')
            distance_from_sma50 = technicals.get('distance_from_sma50_pct', 'N/A')
            atr = technicals.get('atr_14', 'N/A')
            bb_upper = technicals.get('bb_upper', 'N/A')
            bb_lower = technicals.get('bb_lower', 'N/A')
            suggested_stop = technicals.get('suggested_stop_distance', 'N/A')
            suggested_target = technicals.get('suggested_target_distance', 'N/A')
            
            # Calculate distance from 52-week range
            if isinstance(price, (int, float)) and isinstance(high_52w, (int, float)) and isinstance(low_52w, (int, float)):
                distance_from_high = round(((high_52w - price) / high_52w * 100), 1)
                distance_from_low = round(((price - low_52w) / low_52w * 100), 1)
            else:
                distance_from_high = 'N/A'
                distance_from_low = 'N/A'
            
            # Format context
            context = f"""
╔═══════════════════════════════════════════════════════════════════╗
║ REAL-TIME MARKET DATA FOR {symbol} ({company_name})
╚═══════════════════════════════════════════════════════════════════╝

PRICE & VALUATION:
  • Current Price: ${price} ({change_pct:+.2f}%)
  • 52-Week Range: ${low_52w} ─── ${high_52w}
  • Distance from High: {distance_from_high}% | Distance from Low: {distance_from_low}%
  • P/E Ratio: {pe_ratio} (valuation indicator)

VOLUME ANALYSIS:
  • Current Volume: {volume:,} shares
  • Average Volume (20-day): {avg_volume:,} shares
  • Volume Ratio: {volume_ratio}x (Trend: {volume_trend})

MOVING AVERAGES & TREND:
  • SMA(20): ${sma_20}   [Short-term trend]
  • SMA(50): ${sma_50}   [{price_vs_sma50}]  (Distance: {distance_from_sma50}%)
  • SMA(200): ${sma_200}  [Long-term trend]

MOMENTUM INDICATORS:
  • RSI(14): {rsi} ({rsi_signal})
  • MACD: {macd}
  • Momentum: {momentum_pct}% (within 20-day range)
  • ATR(14): ${atr} (volatility measure)

BOLLINGER BANDS:
  • Upper Band: ${bb_upper}
  • Lower Band: ${bb_lower}

SUGGESTED RISK/REWARD (based on ATR):
  • Suggested Stop Distance: ${suggested_stop}
  • Suggested Target Distance: ${suggested_target}

INTERPRETATION GUIDE FOR TRADER:
─────────────────────────────────
RSI: <30 (oversold), >70 (overbought), 30-70 (neutral)
SMA Position: Price above SMAs = uptrend, below = downtrend
Volume Ratio >1.5 = high volume (strong signal), <0.7 = low volume
ATR: Higher ATR = more volatility, lower ATR = less volatility
Momentum %: Near 100% = price near 20-day high (strong), near 0% = price near 20-day low

ACTIONABLE INSIGHTS:
Use this real-time data to provide SPECIFIC trading analysis directly addressing the user's question about {symbol}.
Reference exact price levels, indicators, and patterns. Suggest entry/stop/target levels where applicable.
"""
            return context
        
        except Exception as e:
            logger.warning(f"Error formatting stock data: {e}")
            return ""
    
    def _get_analysis(self, query: str, memory_context: str = "") -> str:
        """Get analysis response with stock data and memory context"""
        try:
            # Extract symbol to provide more specific analysis
            symbol = self._extract_symbol(query)
            
            if symbol and memory_context and "Current Price:" in memory_context:
                # Use LLM to analyze with real stock data
                try:
                    from .council_llm import OllamaLLMClient
                    
                    client = OllamaLLMClient(
                        base_url="http://council-ollama-technical:11434",
                        model="mistral",
                        timeout=15
                    )
                    
                    prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational market analysis, not financial advice.

You are a technical trader analyzing {symbol}. Directly address the user's specific question.

User Query: {query}

{memory_context}

Provide specific, fact-based technical analysis based on the real-time data above. Address:
- Current price position relative to moving averages
- RSI levels and what they indicate (overbought >70, oversold <30)
- Support/resistance based on 52-week range
- Chart patterns and trends
- Specific entry/exit levels if relevant

Keep response under 250 words. Focus on facts from the data provided."""
                    
                    response = client.generate(prompt, max_tokens=250)
                    if response:
                        return f"📊 Technical Analysis for {symbol}:\n{response.strip()}"
                except Exception as e:
                    logger.warning(f"Could not get LLM analysis: {e}")
            
            # Fallback response with data if available
            if memory_context and "Current Price:" in memory_context:
                return f"📊 Analysis: {memory_context}\n\nBased on the real-time data above, analyze the price action and technicals to make an informed trading decision."
            
            return "📊 Analysis: Based on current market conditions and your query, further investigation needed."
            
        except Exception as e:
            logger.error(f"Error in analysis: {e}")
            return "📊 Analysis: Unable to generate analysis at this time."
    
    def _get_trade_advice(self, query: str, memory_context: str = "") -> str:
        """Get trade advice with stock data and memory context"""
        try:
            symbol = self._extract_symbol(query)
            
            if symbol and memory_context and "Current Price:" in memory_context:
                try:
                    from .council_llm import OllamaLLMClient
                    
                    client = OllamaLLMClient(
                        base_url="http://council-ollama-technical:11434",
                        model="mistral",
                        timeout=15
                    )
                    
                    prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational analysis, not financial advice.

You are an experienced trader evaluating {symbol}. Directly address the user's question about trading this stock.

User Query: {query}

{memory_context}

Based on the real-time technical data provided:
1. What is the current market setup? (Uptrend, downtrend, ranging)
2. What are key support and resistance levels?
3. If considering a trade, what would be optimal entry/exit levels?
4. What risk management considerations apply?
5. What probability-weighted outcome do you see?

Keep response under 250 words and focus on the actual data provided."""
                    
                    response = client.generate(prompt, max_tokens=250)
                    if response:
                        return f"💡 Trading Analysis for {symbol}:\n{response.strip()}"
                except Exception as e:
                    logger.warning(f"Could not get LLM trading advice: {e}")
            
            if memory_context:
                return f"💡 Trading Analysis:\n{memory_context}"
            
            return "💡 Trade Advice: Analyzing your trading request. Ensure adequate risk management before executing."
            
        except Exception as e:
            logger.error(f"Error in trade advice: {e}")
            return "💡 Trade Advice: Unable to generate analysis at this time."
    
    def _get_portfolio_analysis(self, query: str, memory_context: str = "") -> str:
        """Get portfolio analysis with stock data and memory context"""
        try:
            symbol = self._extract_symbol(query)
            
            if symbol and memory_context and "Current Price:" in memory_context:
                try:
                    from .council_llm import OllamaLLMClient
                    
                    client = OllamaLLMClient(
                        base_url="http://council-ollama-technical:11434",
                        model="mistral",
                        timeout=15
                    )
                    
                    prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational analysis, not financial advice.

You are analyzing a position or considering adding {symbol} to a portfolio.

User Query: {query}

{memory_context}

Consider:
1. Is this stock in an uptrend or downtrend currently?
2. What is the valuation (P/E ratio shown above)?
3. Relative strength compared to the 52-week range
4. Risk/reward profile based on current technicals
5. Portfolio diversification implications

Keep response under 250 words."""
                    
                    response = client.generate(prompt, max_tokens=250)
                    if response:
                        return f"📈 Portfolio Analysis for {symbol}:\n{response.strip()}"
                except Exception as e:
                    logger.warning(f"Could not get LLM portfolio analysis: {e}")
            
            if memory_context:
                return f"📈 Portfolio Analysis:\n{memory_context}"
            
            return "📈 Portfolio Analysis: Reviewing your holdings and opportunities. Diversification and rebalancing may be relevant."
            
        except Exception as e:
            logger.error(f"Error in portfolio analysis: {e}")
            return "📈 Portfolio Analysis: Unable to generate analysis at this time."
    
    def _get_general_response(self, query: str, memory_context: str = "") -> str:
        """Get general response with stock data and memory context"""
        response = f"💬 Response: Thank you for your question. "
        
        # If we have stock data, include it
        if memory_context and "Current Price:" in memory_context:
            response += f"\n\n{memory_context}"
        else:
            response += "Please provide more specific details for a more targeted analysis."
        
        return response
    
    def execute_trade(self, symbol: str, qty: int, side: str, 
                     order_type: str = "market", limit_price: float = None) -> Dict[str, Any]:
        """Execute a trade through the autonomous trader's broker connection"""
        if not self.trader:
            return {"status": "error", "message": "Trader not available"}
        
        try:
            logger.info(f"📤 Trade request: {side} {qty} {symbol}")
            
            if side.upper() == "BUY":
                result = self.trader.buy(symbol=symbol, qty=qty, limit_price=limit_price)
            elif side.upper() == "SELL":
                result = self.trader.sell(symbol=symbol, qty=qty, limit_price=limit_price)
            else:
                return {"status": "error", "message": f"Invalid side: {side}"}
            
            return result
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get broker account information"""
        if not self.trader:
            return {"status": "error", "message": "Trader not available"}
        
        try:
            return self.trader.get_account_info()
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_positions(self) -> Dict[str, Any]:
        """Get open positions from broker"""
        if not self.trader:
            return {"status": "error", "message": "Trader not available"}
        
        try:
            return self.trader.get_positions()
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {"status": "error", "message": str(e)}
    
    def enable_trading(self, enable: bool = True) -> Dict[str, str]:
        """Enable/disable autonomous trading"""
        if not self.trader:
            return {"status": "error", "message": "Trader not available"}
        
        try:
            self.trader.enable_autonomous_trading(enable=enable)
            status = "enabled" if enable else "disabled"
            return {
                "status": "success",
                "message": f"Autonomous trading {status}",
                "trading_enabled": self.trader.trading_enabled
            }
        except Exception as e:
            logger.error(f"Error toggling trading: {e}")
            return {"status": "error", "message": str(e)}


class CouncilChatAdapter:
    """Adapts trading council for chat interface"""
    
    def __init__(self, memory_store=None):
        """Initialize council adapter"""
        self.council = None
        self.memory = memory_store
        self.stock_data_service = None
        self._init_stock_data_service()
        self._init_council()
        self._init_memory()
    
    def _init_stock_data_service(self):
        """Initialize stock data service"""
        try:
            from .stock_data_service import get_stock_data_service
            self.stock_data_service = get_stock_data_service()
            logger.info("✅ Stock data service initialized")
        except Exception as e:
            logger.warning(f"Could not initialize stock data service: {e}")
            self.stock_data_service = None
    
    def _init_memory(self):
        """Initialize memory store"""
        if not self.memory:
            try:
                from .rag_memory import get_memory_store
                self.memory = get_memory_store()
            except ImportError as e:
                logger.warning(f"Could not import memory store: {e}")
    
    def _init_council(self):
        """Initialize trading council with memory service"""
        try:
            from .trading_council import TradingCouncil
            # Initialize memory first if not already done
            if not self.memory:
                self._init_memory()
            # Create council with memory service
            self.council = TradingCouncil(memory_service=self.memory)
        except Exception as e:
            logger.error(f"Failed to initialize trading council: {e}")
            self.council = None

    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process user query and get council responses with memory context
        Automatically fetches stock data if a ticker is mentioned
        
        Args:
            query: User message
            
        Returns:
            Response dict with all council member responses and stock data
        """
        if not self.council:
            return {
                "status": "error",
                "message": "Council not available",
                "responses": {
                    "technical": "Technical Analyst unavailable",
                    "sentiment": "Sentiment Analyst unavailable",
                    "risk": "Risk Manager unavailable",
                    "memory": "Memory Curator unavailable"
                }
            }
        
        try:
            # Extract symbol from query and fetch stock data if available
            symbol = self._extract_symbol(query)
            stock_data = None
            stock_data_context = ""
            
            if symbol and self.stock_data_service:
                logger.info(f"📊 Fetching stock data for {symbol}...")
                stock_data = self.stock_data_service.get_stock_data(symbol)
                
                if stock_data and not stock_data.get('error'):
                    # Format stock data for LLM context
                    stock_data_context = self._format_stock_data_for_llm(symbol, stock_data)
                    logger.info(f"✅ Stock data fetched for {symbol}")
                else:
                    logger.warning(f"Could not fetch stock data for {symbol}")
            
            # Get memory context if available
            memory_context = ""
            past_consensus = None
            if self.memory:
                from .rag_memory import CouncilMemoryAgent
                memory_agent = CouncilMemoryAgent(self.memory)
                memory_data = memory_agent.deliberate_with_memory(query)
                memory_context = memory_data.get("council_context", "")
                past_consensus = memory_agent.get_consensus_from_memory(query)
            
            # Combine stock data context with memory context
            combined_context = stock_data_context + (f"\n\n{memory_context}" if memory_context else "")
            
            responses = {
                "technical": self._get_technical_perspective(query, combined_context),
                "sentiment": self._get_sentiment_perspective(query, combined_context),
                "risk": self._get_risk_perspective(query, combined_context),
                "memory": self._get_memory_perspective(query, combined_context)
            }
            
            # Store in memory
            if self.memory:
                try:
                    self.memory.add_discussion(
                        f"Council Discussion - Query: {query}",
                        council_votes={k: "participated" for k in responses.keys()},
                        tags=["council", "discussion"]
                    )
                except Exception as e:
                    logger.debug(f"Could not store in memory: {e}")
            
            return {
                "status": "success",
                "responses": responses,
                "timestamp": datetime.utcnow().isoformat(),
                "consensus": self._calculate_consensus(responses),
                "memory_context": memory_context,
                "past_consensus": past_consensus,
                "stock_data": stock_data,
                "stock_symbol": symbol
            }
        
        except Exception as e:
            logger.error(f"Error processing council query: {e}")
            return {
                "status": "error",
                "message": str(e),
                "responses": {}
            }
    
    
    def _extract_symbol(self, query: str) -> Optional[str]:
        """Extract stock symbol from query"""
        common_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN", "JPM", "IBM", "BAC", "SPY", "QQQ", "IWM", "DIA"]
        query_upper = query.upper()
        
        for symbol in common_symbols:
            if symbol in query_upper:
                return symbol
        
        # Try to find 4-letter symbols
        import re
        matches = re.findall(r'\b[A-Z]{1,5}\b', query)
        if matches:
            return matches[0]
        
        return None
    
    def _format_stock_data_for_llm(self, symbol: str, stock_data: Dict[str, Any]) -> str:
        """Format stock data into context for LLM analysis"""
        if not stock_data or stock_data.get('error'):
            return ""
        
        try:
            # Extract key data
            price = stock_data.get('current_price', 'N/A')
            change_pct = stock_data.get('price_change_pct', 0)
            pe_ratio = stock_data.get('pe_ratio', 'N/A')
            market_cap = stock_data.get('market_cap', 0)
            high_52w = stock_data.get('high_52w', 'N/A')
            low_52w = stock_data.get('low_52w', 'N/A')
            company_name = stock_data.get('company_name', symbol)
            sector = stock_data.get('sector', 'N/A')
            
            # Technical indicators
            technicals = stock_data.get('technicals', {})
            sma_20 = technicals.get('sma_20', 'N/A')
            sma_50 = technicals.get('sma_50', 'N/A')
            sma_200 = technicals.get('sma_200', 'N/A')
            rsi = technicals.get('rsi_14', 'N/A')
            rsi_signal = technicals.get('rsi_signal', 'N/A')
            macd = technicals.get('macd', 'N/A')
            bb_upper = technicals.get('bb_upper', 'N/A')
            bb_lower = technicals.get('bb_lower', 'N/A')
            price_vs_sma20 = technicals.get('price_vs_sma20', 'N/A')
            volume_trend = technicals.get('volume_trend', 'N/A')
            
            # Format context
            context = f"""
REAL-TIME STOCK DATA FOR {symbol} ({company_name})
═══════════════════════════════════════════════════════

PRICE & MARKET DATA:
• Current Price: ${price}
• Daily Change: {change_pct}% 
• 52-Week Range: ${low_52w} - ${high_52w}
• Sector: {sector}
• Market Cap: ${market_cap:,} if isinstance(market_cap, int) else 'N/A'
• P/E Ratio: {pe_ratio}

TECHNICAL INDICATORS:
• Price vs SMA(20): {price_vs_sma20} (SMA 20: ${sma_20})
• SMA(50): ${sma_50}
• SMA(200): ${sma_200}
• RSI(14): {rsi} ({rsi_signal})
• MACD: {macd}
• Bollinger Bands: ${bb_lower} - ${bb_upper}
• Volume Trend: {volume_trend}

Use this real-time market data to provide specific, fact-based analysis directly addressing the user's question about {symbol}.
Base your analysis on these actual metrics and patterns.
"""
            return context
        
        except Exception as e:
            logger.warning(f"Error formatting stock data: {e}")
            return ""
    
    def _get_technical_perspective(self, query: str, memory_context: str = "") -> str:
        """Get technical analyst perspective using LLM"""
        try:
            from .council_llm import OllamaLLMClient
            
            # Use the technical council (port 11434, mistral model)
            client = OllamaLLMClient(
                base_url="http://council-ollama-technical:11434",
                model="mistral",
                timeout=15
            )
            
            prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational market analysis, not financial advice.

You are a technical analysis expert specializing in chart patterns, indicators, and price action. Directly address the user's specific question.

User Query: {query}

{f"Historical Technical Context: {memory_context}" if memory_context else ""}

Provide specific technical analysis directly answering their question. Reference specific patterns, support/resistance levels, indicators like RSI, MACD, or moving averages that are relevant to their query. Be direct and specific about upside/downside potential, trends, or technical levels mentioned.

Keep response under 250 words. Remember this is educational analysis only."""
            
            response = client.generate(prompt, max_tokens=250)
            if response:
                return f"📊 Technical Analysis: {response.strip()}"
            
        except Exception as e:
            logger.warning(f"Could not get LLM response for technical analysis: {e}")
        
        # Fallback to basic response if LLM unavailable
        return "📊 Technical Analysis: Unable to generate analysis at this time. Please try again."
    
    def _get_sentiment_perspective(self, query: str, memory_context: str = "") -> str:
        """Get sentiment analyst perspective using LLM"""
        try:
            from .council_llm import OllamaLLMClient
            
            # Use the sentiment council (port 11435, neural-chat model)
            client = OllamaLLMClient(
                base_url="http://council-ollama-sentiment:11435",
                model="neural-chat",
                timeout=15
            )
            
            prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational market analysis, not financial advice.

You are a market sentiment and psychology expert. Directly address the user's specific question about market sentiment, investor psychology, or news impact.

User Query: {query}

{f"Historical Sentiment Patterns: {memory_context}" if memory_context else ""}

Provide sentiment analysis specific to their question. Discuss investor sentiment, news flow impact, social media trends, fear/greed index, sector rotation, or psychological levels relevant to their query.

Keep response under 250 words. Remember this is educational analysis only."""
            
            response = client.generate(prompt, max_tokens=250)
            if response:
                return f"📰 Sentiment Analysis: {response.strip()}"
            
        except Exception as e:
            logger.warning(f"Could not get LLM response for sentiment analysis: {e}")
        
        # Fallback to basic response if LLM unavailable
        return "📰 Sentiment Analysis: Unable to generate analysis at this time. Please try again."
    
    def _get_risk_perspective(self, query: str, memory_context: str = "") -> str:
        """Get risk manager perspective using LLM"""
        try:
            from .council_llm import OllamaLLMClient
            
            # Use the reason/risk council (port 11436, llama2 model)
            client = OllamaLLMClient(
                base_url="http://council-ollama-reason:11436",
                model="llama2",
                timeout=15
            )
            
            prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational market analysis, not financial advice.

You are a risk management expert. Directly address the user's specific question about risk, position sizing, stops, or portfolio safety.

User Query: {query}

{f"Past Risk Lessons: {memory_context}" if memory_context else ""}

Provide risk management insights specific to their question. Discuss position sizing principles, stop loss placement, portfolio correlation, diversification, or risk/reward ratios relevant to their situation.

Keep response under 250 words. Remember this is educational analysis only."""
            
            response = client.generate(prompt, max_tokens=250)
            if response:
                return f"⚠️ Risk Management: {response.strip()}"
            
        except Exception as e:
            logger.warning(f"Could not get LLM response for risk analysis: {e}")
        
        # Fallback to basic response if LLM unavailable
        return "⚠️ Risk Management: Unable to generate analysis at this time. Please try again."
    
    def _get_memory_perspective(self, query: str, memory_context: str = "") -> str:
        """Get memory curator perspective using LLM"""
        try:
            from .council_llm import OllamaLLMClient
            
            # Use the reason council (port 11436, llama2 model) for pattern recognition
            client = OllamaLLMClient(
                base_url="http://council-ollama-reason:11436",
                model="llama2",
                timeout=15
            )
            
            prompt = f"""FOR EDUCATIONAL PURPOSES ONLY - This is educational market analysis, not financial advice.

You are a pattern recognition and market history expert. Directly address the user's specific question by identifying relevant historical patterns or precedents.

User Query: {query}

{f"Previous Similar Occurrences: {memory_context}" if memory_context else ""}

Provide insights about historical patterns, market cycles, past precedents, or similar setups that are relevant to their specific question. Reference specific time periods or historical events when relevant.

Keep response under 250 words. Remember this is educational analysis only."""
            
            response = client.generate(prompt, max_tokens=250)
            if response:
                return f"🧠 Pattern Recognition: {response.strip()}"
            
        except Exception as e:
            logger.warning(f"Could not get LLM response for pattern analysis: {e}")
        
        # Fallback to basic response if LLM unavailable
        return "🧠 Pattern Recognition: Unable to generate analysis at this time. Please try again."
    
    def _calculate_consensus(self, responses: Dict[str, str]) -> str:
        """Calculate council consensus"""
        # Simple consensus calculation - more sophisticated logic can be added
        valid_responses = len([r for r in responses.values() if r and "unavailable" not in r.lower()])
        
        if valid_responses == 4:
            return "strong"
        elif valid_responses >= 3:
            return "moderate"
        else:
            return "weak"


class CombinedChatAdapter:
    """Combines trader and council for all-in-one discussion with memory"""
    
    def __init__(self, memory_store=None):
        """Initialize combined adapter"""
        self.trader_adapter = TraderChatAdapter(memory_store)
        self.council_adapter = CouncilChatAdapter(memory_store)
        self.memory = memory_store
        if not self.memory:
            try:
                from .rag_memory import get_memory_store
                self.memory = get_memory_store()
            except ImportError:
                pass
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process query with both trader and council using memory
        
        Args:
            query: User message
            
        Returns:
            Combined response with trader and all council perspectives
        """
        trader_result = self.trader_adapter.process_query(query)
        council_result = self.council_adapter.process_query(query)
        
        # Store combined discussion in memory
        if self.memory and trader_result.get("status") == "success":
            try:
                self.memory.add_discussion(
                    f"All-in-One Discussion: {query}",
                    council_votes={"trader": "participated"} | {k: "participated" for k in council_result.get("responses", {}).keys()},
                    tags=["all-in-one", "comprehensive"]
                )
            except Exception as e:
                logger.debug(f"Could not store combined discussion: {e}")
        
        return {
            "status": "success" if trader_result.get("status") == "success" and council_result.get("status") == "success" else "partial",
            "trader": {
                "response": trader_result.get("response"),
                "intent": trader_result.get("intent"),
                "memory_context": trader_result.get("memory_context")
            },
            "council": council_result.get("responses", {}),
            "consensus": council_result.get("consensus", "weak"),
            "council_memory_context": council_result.get("memory_context"),
            "timestamp": datetime.utcnow().isoformat()
        }


class CombinedChatAdapter:
    """Combines trader and council for all-in-one discussion"""
    
    def __init__(self):
        """Initialize combined adapter"""
        self.trader_adapter = TraderChatAdapter()
        self.council_adapter = CouncilChatAdapter()
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process query with both trader and council
        
        Args:
            query: User message
            
        Returns:
            Combined response with trader and all council perspectives
        """
        trader_result = self.trader_adapter.process_query(query)
        council_result = self.council_adapter.process_query(query)
        
        return {
            "status": "success" if trader_result.get("status") == "success" and council_result.get("status") == "success" else "partial",
            "trader": {
                "response": trader_result.get("response"),
                "intent": trader_result.get("intent"),
                "memory_context": trader_result.get("memory_context")
            },
            "council": council_result.get("responses", {}),
            "consensus": council_result.get("consensus", "weak"),
            "council_memory_context": council_result.get("memory_context"),
            "timestamp": datetime.utcnow().isoformat()
        }


# Factory function
def get_chat_adapter(chat_type: str) -> Any:
    """
    Get appropriate chat adapter
    
    Args:
        chat_type: 'trader', 'council', or 'all'
        
    Returns:
        Chat adapter instance
    """
    if chat_type == "trader":
        return TraderChatAdapter()
    elif chat_type == "council":
        return CouncilChatAdapter()
    elif chat_type == "all":
        return CombinedChatAdapter()
    else:
        raise ValueError(f"Unknown chat type: {chat_type}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test adapters
    print("Testing Chat Adapters...\n")
    
    # Test trader
    print("=" * 60)
    print("TRADER ADAPTER TEST")
    print("=" * 60)
    trader = TraderChatAdapter()
    result = trader.process_query("What's your analysis on AAPL?")
    print(json.dumps(result, indent=2))
    
    # Test council
    print("\n" + "=" * 60)
    print("COUNCIL ADAPTER TEST")
    print("=" * 60)
    council = CouncilChatAdapter()
    result = council.process_query("What do you think about market conditions?")
    print(json.dumps(result, indent=2))
    
    # Test combined
    print("\n" + "=" * 60)
    print("COMBINED ADAPTER TEST")
    print("=" * 60)
    combined = CombinedChatAdapter()
    result = combined.process_query("Should I buy TSLA now?")
    print(json.dumps(result, indent=2))
