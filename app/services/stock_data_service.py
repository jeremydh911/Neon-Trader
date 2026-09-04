"""
Stock Data Service
Fetches real-time stock data, technical indicators, and chart data
Uses yfinance for data retrieval and caching for performance
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class StockDataService:
    """Fetch and cache real stock data"""
    
    def __init__(self):
        """Initialize stock data service"""
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        self._init_yfinance()
    
    def _init_yfinance(self):
        """Initialize yfinance"""
        try:
            import yfinance as yf
            self.yf = yf
            self.yfinance_available = True
            logger.info("✅ yfinance available for stock data")
        except ImportError:
            self.yfinance_available = False
            logger.warning("❌ yfinance not available - install with: pip install yfinance")
    
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache entry is still valid"""
        if key not in self.cache:
            return False
        
        entry = self.cache[key]
        age = datetime.utcnow() - entry['timestamp']
        return age.total_seconds() < self.cache_ttl
    
    def get_stock_data(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """
        Get comprehensive stock data
        
        Args:
            symbol: Stock ticker symbol (e.g., 'TSLA')
            period: Data period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y')
            
        Returns:
            Dict with stock info, price, technicals, chart data
        """
        if not self.yfinance_available:
            return self._get_offline_placeholder(symbol)
        
        cache_key = f"{symbol}_{period}"
        if self._is_cache_valid(cache_key):
            logger.info(f"Using cached data for {symbol}")
            return self.cache[cache_key]['data']
        
        try:
            # Fetch ticker
            ticker = self.yf.Ticker(symbol)
            
            # Get historical data
            hist = ticker.history(period=period)
            
            if hist.empty:
                logger.warning(f"No data found for symbol {symbol}")
                return self._get_offline_placeholder(symbol)
            
            # Get current info
            info = ticker.info
            
            # Extract key data
            current_price = hist['Close'].iloc[-1]
            prev_close = info.get('previousClose', current_price)
            open_price = hist['Open'].iloc[-1] if len(hist) > 0 else current_price
            high_52w = info.get('fiftyTwoWeekHigh', current_price)
            low_52w = info.get('fiftyTwoWeekLow', current_price)
            market_cap = info.get('marketCap', 0)
            pe_ratio = info.get('trailingPE', 0)
            eps = info.get('trailingEps', 0)
            dividend_yield = info.get('dividendYield', 0)
            beta = info.get('beta', 0)
            
            # Calculate price change
            price_change = current_price - prev_close
            price_change_pct = (price_change / prev_close * 100) if prev_close else 0
            
            # Calculate technical indicators
            technical_data = self._calculate_technicals(hist)
            
            # Prepare chart data (last 100 days)
            chart_data = self._prepare_chart_data(hist)
            
            # Compile response
            data = {
                "symbol": symbol,
                "timestamp": datetime.utcnow().isoformat(),
                "current_price": round(current_price, 2),
                "prev_close": round(prev_close, 2),
                "open": round(open_price, 2),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "price_change": round(price_change, 2),
                "price_change_pct": round(price_change_pct, 2),
                "market_cap": market_cap,
                "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
                "eps": round(eps, 2) if eps else None,
                "dividend_yield": round(dividend_yield * 100, 2) if dividend_yield else 0,
                "beta": round(beta, 2) if beta else None,
                "volume": int(hist['Volume'].iloc[-1]) if len(hist) > 0 else 0,
                "avg_volume": int(hist['Volume'].mean()),
                "technicals": technical_data,
                "chart_data": chart_data,
                "company_name": info.get('longName', symbol),
                "sector": info.get('sector', 'N/A'),
                "industry": info.get('industry', 'N/A'),
                "description": info.get('longBusinessSummary', '')[:500] if info.get('longBusinessSummary') else '',
            }
            
            # Cache the data
            self.cache[cache_key] = {
                'data': data,
                'timestamp': datetime.utcnow()
            }
            
            logger.info(f"✅ Fetched fresh data for {symbol}")
            return data
            
        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}")
            return self._get_offline_placeholder(symbol)
    
    def _calculate_technicals(self, hist) -> Dict[str, Any]:
        """Calculate technical indicators"""
        try:
            technicals = {}
            
            if len(hist) < 20:
                return {"error": "Insufficient data for technical analysis"}
            
            close = hist['Close']
            high = hist['High']
            low = hist['Low']
            volume = hist['Volume']
            
            # Simple Moving Averages
            sma_20 = close.rolling(window=20).mean().iloc[-1]
            sma_50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None
            sma_200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None
            current_price = close.iloc[-1]
            
            technicals['sma_20'] = round(sma_20, 2) if sma_20 else None
            technicals['sma_50'] = round(sma_50, 2) if sma_50 else None
            technicals['sma_200'] = round(sma_200, 2) if sma_200 else None
            
            # Price relative to SMAs
            if sma_20:
                technicals['price_vs_sma20'] = "Above" if current_price > sma_20 else "Below"
                technicals['price_distance_sma20'] = round((current_price - sma_20) / sma_20 * 100, 2)
            if sma_50:
                technicals['price_vs_sma50'] = "Above" if current_price > sma_50 else "Below"
            if sma_200:
                technicals['price_vs_sma200'] = "Above" if current_price > sma_200 else "Below"
            
            # RSI (Relative Strength Index)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]
            
            technicals['rsi_14'] = round(current_rsi, 2) if not pd.isna(current_rsi) else None
            if current_rsi:
                if current_rsi > 70:
                    technicals['rsi_signal'] = "Overbought"
                elif current_rsi < 30:
                    technicals['rsi_signal'] = "Oversold"
                else:
                    technicals['rsi_signal'] = "Neutral"
            
            # MACD
            ema_12 = close.ewm(span=12, adjust=False).mean()
            ema_26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            
            technicals['macd'] = round(macd_line.iloc[-1], 4) if len(macd_line) > 0 else None
            technicals['macd_signal'] = round(signal_line.iloc[-1], 4) if len(signal_line) > 0 else None
            if technicals['macd'] and technicals['macd_signal']:
                technicals['macd_histogram'] = round(technicals['macd'] - technicals['macd_signal'], 4)
            
            # Bollinger Bands
            sma_bb = close.rolling(window=20).mean()
            std = close.rolling(window=20).std()
            upper_band = sma_bb + (std * 2)
            lower_band = sma_bb - (std * 2)
            
            technicals['bb_upper'] = round(upper_band.iloc[-1], 2) if len(upper_band) > 0 else None
            technicals['bb_middle'] = round(sma_bb.iloc[-1], 2) if len(sma_bb) > 0 else None
            technicals['bb_lower'] = round(lower_band.iloc[-1], 2) if len(lower_band) > 0 else None
            
            # Volume trend
            avg_vol = volume.rolling(window=20).mean()
            current_vol = volume.iloc[-1]
            vol_ratio = current_vol / avg_vol.iloc[-1] if avg_vol.iloc[-1] > 0 else 1
            technicals['volume_trend'] = "High" if vol_ratio > 1.5 else "Low" if vol_ratio < 0.7 else "Normal"
            technicals['volume_ratio'] = round(vol_ratio, 2)

            # Approximate VWAP from typical price * volume (session proxy on available bars)
            try:
                typical = (high + low + close) / 3.0
                cum_vol = volume.cumsum()
                cum_tp_vol = (typical * volume).cumsum()
                vwap = (cum_tp_vol / cum_vol).iloc[-1]
                technicals['vwap'] = round(float(vwap), 2) if cum_vol.iloc[-1] > 0 else None
            except Exception:
                technicals['vwap'] = None
            
            # Additional signals
            # Price momentum (% change from 20-day high/low)
            high_20 = high.rolling(window=20).max().iloc[-1]
            low_20 = low.rolling(window=20).min().iloc[-1]
            momentum_pct = ((current_price - low_20) / (high_20 - low_20) * 100) if (high_20 - low_20) > 0 else 50
            technicals['momentum_pct'] = round(momentum_pct, 1)
            
            # Trend strength: distance from SMA50 (if available)
            if len(close) >= 50:
                sma_50 = close.rolling(window=50).mean().iloc[-1]
                technicals['sma_50'] = round(sma_50, 2)
                trend_distance = ((current_price - sma_50) / sma_50 * 100) if sma_50 > 0 else 0
                technicals['price_vs_sma50'] = "Above" if current_price > sma_50 else "Below"
                technicals['distance_from_sma50_pct'] = round(trend_distance, 2)
            
            # ATR (Average True Range) for volatility
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1]
            technicals['atr_14'] = round(atr, 2) if atr else None
            
            # Suggested stops and targets
            if atr:
                technicals['suggested_stop_distance'] = round(atr * 1.5, 2)
                technicals['suggested_target_distance'] = round(atr * 3, 2)
            
            return technicals
            
        except Exception as e:
            logger.warning(f"Error calculating technicals: {e}")
            return {}
    
    def _prepare_chart_data(self, hist, days: int = 100) -> List[Dict[str, Any]]:
        """Prepare chart data for visualization"""
        try:
            chart_data = []
            hist_subset = hist.tail(days)
            
            for date, row in hist_subset.iterrows():
                chart_data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(row['Open'], 2),
                    "high": round(row['High'], 2),
                    "low": round(row['Low'], 2),
                    "close": round(row['Close'], 2),
                    "volume": int(row['Volume'])
                })
            
            return chart_data
        except Exception as e:
            logger.warning(f"Error preparing chart data: {e}")
            return []
    
    def _get_offline_placeholder(self, symbol: str) -> Dict[str, Any]:
        """Return placeholder data when API unavailable"""
        return {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "error": "Unable to fetch real-time data",
            "message": "Please ensure yfinance is installed: pip install yfinance",
            "current_price": None,
            "technicals": {},
            "chart_data": [],
            "company_name": symbol,
            "sector": "Unknown",
            "industry": "Unknown"
        }
    
    def get_fundamental_analysis(self, symbol: str) -> Dict[str, Any]:
        """Get fundamental analysis data"""
        if not self.yfinance_available:
            return {"error": "yfinance not available"}
        
        try:
            ticker = self.yf.Ticker(symbol)
            info = ticker.info
            
            fundamentals = {
                "symbol": symbol,
                "company_name": info.get('longName', symbol),
                "sector": info.get('sector', 'N/A'),
                "industry": info.get('industry', 'N/A'),
                "market_cap": info.get('marketCap', 0),
                "pe_ratio": info.get('trailingPE', None),
                "forward_pe": info.get('forwardPE', None),
                "pb_ratio": info.get('priceToBook', None),
                "peg_ratio": info.get('pegRatio', None),
                "dividend_yield": round(info.get('dividendYield', 0) * 100, 2) if info.get('dividendYield') else 0,
                "revenue": info.get('totalRevenue', 0),
                "net_income": info.get('netIncomeToCommon', 0),
                "roe": round(info.get('returnOnEquity', 0) * 100, 2) if info.get('returnOnEquity') else None,
                "roa": round(info.get('returnOnAssets', 0) * 100, 2) if info.get('returnOnAssets') else None,
                "debt_to_equity": info.get('debtToEquity', None),
                "current_ratio": info.get('currentRatio', None),
                "quick_ratio": info.get('quickRatio', None),
                "eps": info.get('trailingEps', None),
                "beta": info.get('beta', None),
                "description": info.get('longBusinessSummary', '')[:300]
            }
            
            return fundamentals
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {"error": str(e)}
    
    def get_news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent news for a symbol"""
        if not self.yfinance_available:
            return []
        
        try:
            ticker = self.yf.Ticker(symbol)
            news = ticker.news[:limit]
            
            formatted_news = []
            for article in news:
                formatted_news.append({
                    "title": article.get('title', ''),
                    "publisher": article.get('publisher', ''),
                    "link": article.get('link', ''),
                    "published": article.get('providerPublishTime', 0),
                    "summary": article.get('summary', '')
                })
            
            return formatted_news
            
        except Exception as e:
            logger.warning(f"Error fetching news for {symbol}: {e}")
            return []
    
    def compare_stocks(self, symbols: List[str]) -> Dict[str, Any]:
        """Compare multiple stocks"""
        comparison = {}
        
        for symbol in symbols:
            data = self.get_stock_data(symbol)
            comparison[symbol] = {
                "price": data.get('current_price'),
                "change_pct": data.get('price_change_pct'),
                "pe_ratio": data.get('pe_ratio'),
                "market_cap": data.get('market_cap')
            }
        
        return comparison


# Module-level imports for pandas
try:
    import pandas as pd
except ImportError:
    pd = None
    logger.warning("pandas not available")


def get_stock_data_service() -> StockDataService:
    """Factory function to get StockDataService instance"""
    return StockDataService()
