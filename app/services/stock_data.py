"""
Real Stock Data Service
Fetches live stock prices and data from APIs
"""

try:
    import yfinance as yf
except ImportError:  # paper/test environments may omit yfinance
    yf = None
import pandas as pd
import logging
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class StockDataService:
    """Fetch real stock data from Yahoo Finance API"""
    
    def __init__(self):
        self.cache_file = "/app/data/stock_cache.json"
        self.cache_duration = 300  # 5 minutes
        self.cache = {}
        self.yfinance_available = yf is not None
        if not self.yfinance_available:
            logger.warning("yfinance not installed — StockDataService will return placeholders")
        self.load_cache()

    def _require_yf(self):
        if yf is None:
            raise RuntimeError("yfinance not installed — pip install yfinance for live quotes")
    
    def load_cache(self):
        """Load cached stock data from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
                logger.info(f"✅ Loaded stock cache with {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self.cache = {}
    
    def save_cache(self):
        """Save cache to file"""
        try:
            os.makedirs("/app/data", exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def is_cache_valid(self, symbol: str) -> bool:
        """Check if cache entry is still valid"""
        if symbol not in self.cache:
            return False
        
        cached_time = self.cache[symbol].get("timestamp")
        if not cached_time:
            return False
        
        cache_age = datetime.now().timestamp() - cached_time
        return cache_age < self.cache_duration
    
    def get_current_price(self, symbol: str) -> Tuple[float, float, float]:
        """
        Get current price, change amount, and change percentage for a stock
        Returns: (current_price, change_amount, change_percent)
        """
        try:
            # Check cache first
            if self.is_cache_valid(symbol):
                data = self.cache[symbol]
                return (
                    data["price"],
                    data["change"],
                    data["change_percent"]
                )
            
            # Fetch from API
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            
            if data.empty:
                logger.warning(f"No data found for {symbol}")
                return (0.0, 0.0, 0.0)
            
            current_price = data['Close'].iloc[-1]
            prev_close = ticker.info.get('previousClose', current_price)
            
            change = current_price - prev_close
            change_percent = (change / prev_close * 100) if prev_close > 0 else 0
            
            # Cache the result
            self.cache[symbol] = {
                "price": float(current_price),
                "change": float(change),
                "change_percent": float(change_percent),
                "timestamp": datetime.now().timestamp()
            }
            self.save_cache()
            
            logger.info(f"✅ Fetched {symbol}: ${current_price:.2f} ({change_percent:+.2f}%)")
            return (float(current_price), float(change), float(change_percent))
        
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return (0.0, 0.0, 0.0)
    
    def get_historical_data(self, symbol: str, period: str = "3mo") -> pd.DataFrame:
        """
        Get historical OHLCV data for a symbol
        period: "1d", "5d", "1mo", "3mo", "1y", "5y", "max"
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            
            if data.empty:
                logger.warning(f"No historical data for {symbol}")
                return pd.DataFrame()
            
            logger.info(f"✅ Fetched {len(data)} days of history for {symbol}")
            return data
        
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get current prices for multiple symbols"""
        results = {}
        
        for symbol in symbols:
            price, change, change_pct = self.get_current_price(symbol)
            results[symbol] = {
                "price": price,
                "change": change,
                "change_percent": change_pct
            }
        
        return results
    
    def get_stock_info(self, symbol: str) -> Dict:
        """Get detailed info about a stock"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            return {
                "symbol": symbol,
                "name": info.get("longName", symbol),
                "price": info.get("currentPrice", 0),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "dividend_yield": info.get("dividendYield", 0),
                "52week_high": info.get("fiftyTwoWeekHigh", 0),
                "52week_low": info.get("fiftyTwoWeekLow", 0),
                "volume": info.get("volume", 0),
                "avg_volume": info.get("averageVolume", 0),
            }
        
        except Exception as e:
            logger.error(f"Error fetching info for {symbol}: {e}")
            return {}
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators (RSI, MACD, Bollinger Bands, SMA)
        """
        try:
            # SMA (Simple Moving Average)
            df['SMA_20'] = df['Close'].rolling(window=20).mean()
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            
            # RSI (Relative Strength Index)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD
            ema_12 = df['Close'].ewm(span=12).mean()
            ema_26 = df['Close'].ewm(span=26).mean()
            df['MACD'] = ema_12 - ema_26
            df['Signal'] = df['MACD'].ewm(span=9).mean()
            df['MACD_Histogram'] = df['MACD'] - df['Signal']
            
            # Bollinger Bands
            bb_sma = df['Close'].rolling(window=20).mean()
            bb_std = df['Close'].rolling(window=20).std()
            df['BB_Upper'] = bb_sma + (bb_std * 2)
            df['BB_Lower'] = bb_sma - (bb_std * 2)
            
            logger.info(f"✅ Calculated technical indicators for {len(df)} rows")
            return df
        
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return df
    
    def get_trading_signals(self, symbol: str, period: str = "3mo") -> Dict:
        """
        Analyze stock and generate trading signals
        Returns: {"signal": "BUY/SELL/HOLD", "confidence": 0-100, "analysis": {...}}
        """
        try:
            df = self.get_historical_data(symbol, period)
            
            if df.empty:
                return {"signal": "UNKNOWN", "confidence": 0}
            
            df = self.calculate_technical_indicators(df)
            
            # Latest values
            latest = df.iloc[-1]
            
            
            # Ensure we have enough data for indicators
            if len(df) < 50:  # Need at least 50 days for proper SMA_50
                logger.warning(f'⚠️ Insufficient data for {symbol}: only {len(df)} days')
                return {'signal': 'UNKNOWN', 'confidence': 0}
            
            # Ensure we have enough data for indicators
            if len(df) < 50:  # Need at least 50 days for proper SMA_50
                logger.warning(f'⚠️ Insufficient data for {symbol}: only {len(df)} days')
                return {'signal': 'UNKNOWN', 'confidence': 0}
            
            current_price = latest['Close']
            
            signals = []
            
            # RSI Signal - handle NaN values properly
            rsi = latest['RSI'] if 'RSI' in latest.index and not pd.isna(latest['RSI']) else 50
            if rsi < 40:
                signals.append(("RSI", "BUY", 75))  # Oversold
            elif rsi > 60:
                signals.append(("RSI", "SELL", 75))  # Overbought
            else:
                signals.append(("RSI", "HOLD", 50))
            
            # MACD Signal
            macd_hist = latest['MACD_Histogram'] if 'MACD_Histogram' in latest.index and not pd.isna(latest['MACD_Histogram']) else 0
            prev_macd_hist = df['MACD_Histogram'].iloc[-2] if len(df) > 1 and 'MACD_Histogram' in df.columns else 0
            if not pd.isna(macd_hist) and not pd.isna(prev_macd_hist):
                if macd_hist > 0 and prev_macd_hist <= 0:
                    signals.append(("MACD", "BUY", 65))  # Bullish crossover
                elif macd_hist < 0 and prev_macd_hist >= 0:
                    signals.append(("MACD", "SELL", 65))  # Bearish crossover
                else:
                    signals.append(("MACD", "HOLD", 50))
            else:
                signals.append(("MACD", "HOLD", 50))
            
            # Moving Average Signal
            sma_20 = latest['SMA_20'] if 'SMA_20' in latest.index and not pd.isna(latest['SMA_20']) else current_price
            sma_50 = latest['SMA_50'] if 'SMA_50' in latest.index and not pd.isna(latest['SMA_50']) else current_price
            if sma_20 > sma_50 and current_price > sma_20:
                signals.append(("MA", "BUY", 60))  # Uptrend
            elif sma_20 < sma_50 and current_price < sma_20:
                signals.append(("MA", "SELL", 60))  # Downtrend
            else:
                signals.append(("MA", "HOLD", 50))
            
            # Bollinger Bands Signal (using 1.5 std dev bands for more sensitivity)
            bb_upper = latest['BB_Upper'] if 'BB_Upper' in latest.index and not pd.isna(latest['BB_Upper']) else current_price
            bb_lower = latest['BB_Lower'] if 'BB_Lower' in latest.index and not pd.isna(latest['BB_Lower']) else current_price
            bb_mid = (bb_upper + bb_lower) / 2
            if current_price < bb_lower:
                signals.append(("BB", "BUY", 70))  # Strong oversold
            elif current_price > bb_upper:
                signals.append(("BB", "SELL", 70))  # Strong overbought
            elif current_price < bb_mid:
                signals.append(("BB", "BUY", 55))  # Below midline
            elif current_price > bb_mid:
                signals.append(("BB", "SELL", 55))  # Above midline  
            else:
                signals.append(("BB", "HOLD", 50))
            
            # Aggregate signals
            buy_count = sum(1 for _, s, _ in signals if s == "BUY")
            sell_count = sum(1 for _, s, _ in signals if s == "SELL")
            avg_confidence = sum(c for _, _, c in signals) / len(signals)
            
            # WEIGHTED SIGNAL AGGREGATION
            # Use weighted majority with stronger signals
            buy_weight = sum(c for _, s, c in signals if s == "BUY") 
            sell_weight = sum(c for _, s, c in signals if s == "SELL")
            hold_weight = sum(c for _, s, c in signals if s == "HOLD")
            
            total_weight = buy_weight + sell_weight + hold_weight
            
            if buy_weight > total_weight * 0.40:  # Buy if 40%+ of weight
                final_signal = "BUY"
                avg_confidence = min(95, int((buy_weight / total_weight * 100)))
            elif sell_weight > total_weight * 0.40:  # Sell if 40%+ of weight
                final_signal = "SELL"
                avg_confidence = min(95, int((sell_weight / total_weight * 100)))
            else:
                final_signal = "HOLD"
                avg_confidence = int((hold_weight / total_weight * 100)) if total_weight > 0 else 50
            
            # Log signal details for debugging
            logger.info(f"📊 {symbol} signals: {[(s, c) for _, s, c in signals]}")
            logger.info(f"   → Final: {final_signal} ({int(avg_confidence)}%) | RSI:{float(rsi):.1f} SMA20:{float(sma_20):.2f} SMA50:{float(sma_50):.2f}")
            
            return {
                "symbol": symbol,
                "signal": final_signal,
                "confidence": int(avg_confidence),
                "current_price": float(current_price),
                "analysis": {
                    "rsi": float(rsi) if not pd.isna(rsi) else 0,
                    "macd": float(latest.get('MACD', 0)) if not pd.isna(latest.get('MACD', 0)) else 0,
                    "sma_20": float(sma_20) if not pd.isna(sma_20) else 0,
                    "sma_50": float(sma_50) if not pd.isna(sma_50) else 0,
                    "bb_upper": float(bb_upper) if not pd.isna(bb_upper) else 0,
                    "bb_lower": float(bb_lower) if not pd.isna(bb_lower) else 0,
                    "signal_agreement": f"{buy_count + sell_count}/4 indicators aligned"
                },
                "signals": [(name, sig, conf) for name, sig, conf in signals]
            }
        
        except Exception as e:
            logger.error(f"Error generating signals for {symbol}: {e}")
            return {"signal": "UNKNOWN", "confidence": 0}


# Global instance
_stock_service = None

def get_stock_service() -> StockDataService:
    """Get or create the stock data service"""
    global _stock_service
    if _stock_service is None:
        _stock_service = StockDataService()
    return _stock_service
