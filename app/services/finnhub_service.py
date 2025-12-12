"""
Finnhub API Service - Backup market data source
Provides real-time quotes, company info, and market data when E*TRADE is unavailable
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class FinnhubService:
    """Finnhub API wrapper for market data retrieval"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Finnhub service with credentials
        
        Args:
            config_path: Path to finnhub_credentials.json. Uses default if None.
        """
        self.config_path = config_path or Path(__file__).parent.parent / "config" / "finnhub_credentials.json"
        self.config = self._load_config()
        self.api_key = self.config.get("api_key")
        self.webhook_secret = self.config.get("webhook_secret")
        self.base_url = self.config.get("base_url", "https://finnhub.io/api/v1")
        self.enabled = self.config.get("enabled", True)
        self.session = requests.Session()
        self._rate_limit_reset = None
        self._call_count = 0

    def _load_config(self) -> Dict:
        """Load Finnhub credentials from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                return data.get("finnhub", {})
        except FileNotFoundError:
            logger.error(f"Finnhub config not found at {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Finnhub config: {e}")
            return {}

    def _make_request(self, endpoint: str, params: Optional[Dict] = None, timeout: int = 10) -> Optional[Dict]:
        """
        Make API request to Finnhub
        
        Args:
            endpoint: API endpoint (e.g., '/quote')
            params: Query parameters
            timeout: Request timeout in seconds
            
        Returns:
            Response JSON or None if failed
        """
        if not self.enabled or not self.api_key:
            logger.warning("Finnhub service not enabled or API key missing")
            return None

        try:
            # Add API key to params
            if params is None:
                params = {}
            params['token'] = self.api_key

            # Make request
            url = f"{self.base_url}{endpoint}"
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()

            self._call_count += 1
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"Finnhub request timeout: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Finnhub connection error: {endpoint}")
            return None
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                logger.warning("Finnhub rate limit exceeded")
            else:
                logger.error(f"Finnhub HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"Finnhub request error: {e}")
            return None

    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        Get real-time quote for a symbol
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            
        Returns:
            Quote data: {
                'c': current price,
                'h': high price,
                'l': low price,
                'o': open price,
                'pc': previous close,
                't': timestamp,
                'v': volume (if available)
            }
        """
        data = self._make_request("/quote", {"symbol": symbol})
        
        if data and 'c' in data:
            return {
                'symbol': symbol,
                'price': data.get('c'),
                'high': data.get('h'),
                'low': data.get('l'),
                'open': data.get('o'),
                'previous_close': data.get('pc'),
                'timestamp': data.get('t'),
                'source': 'finnhub'
            }
        
        return None

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get quotes for multiple symbols
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dictionary mapping symbols to quote data
        """
        quotes = {}
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                quotes[symbol] = quote
        return quotes

    def get_company_info(self, symbol: str) -> Optional[Dict]:
        """
        Get company information
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Company info: {
                'name': company name,
                'country': country,
                'currency': currency,
                'exchange': exchange,
                'ipo': IPO date,
                'industry': industry,
                'logo': logo URL,
                'weburl': website
            }
        """
        data = self._make_request("/stock/profile2", {"symbol": symbol})
        
        if data:
            return {
                'symbol': symbol,
                'name': data.get('name'),
                'country': data.get('country'),
                'currency': data.get('currency'),
                'exchange': data.get('exchange'),
                'ipo': data.get('ipo'),
                'industry': data.get('finnhubIndustry'),
                'logo': data.get('logo'),
                'website': data.get('weburl'),
                'source': 'finnhub'
            }
        
        return None

    def get_news(self, symbol: str, limit: int = 10) -> List[Dict]:
        """
        Get company news
        
        Args:
            symbol: Stock symbol
            limit: Number of articles to return (max 100)
            
        Returns:
            List of news articles with headline, summary, URL, source, timestamp
        """
        limit = min(limit, 100)  # Finnhub max is 100
        data = self._make_request("/company-news", {
            "symbol": symbol,
            "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "to": datetime.now().strftime("%Y-%m-%d")
        })
        
        if not isinstance(data, list):
            return []
        
        news = []
        for article in data[:limit]:
            news.append({
                'headline': article.get('headline'),
                'summary': article.get('summary'),
                'source': article.get('source'),
                'url': article.get('url'),
                'image': article.get('image'),
                'datetime': article.get('datetime'),
                'category': article.get('category')
            })
        
        return news

    def get_market_status(self) -> Optional[Dict]:
        """
        Get overall market status and holidays
        
        Returns:
            Market status info: {
                'isOpen': boolean,
                'session': 'market' | 'pre' | 'post',
                'holidays': [list of holidays],
                'trading_days': [list of upcoming trading days]
            }
        """
        data = self._make_request("/stock/market-status")
        
        if data:
            return {
                'is_open': data.get('isOpen'),
                'session': data.get('session'),
                'timestamp': datetime.now().isoformat(),
                'source': 'finnhub'
            }
        
        return None

    def get_candles(
        self,
        symbol: str,
        resolution: str = 'D',
        count: int = 100
    ) -> List[Dict]:
        """
        Get historical candle data
        
        Args:
            symbol: Stock symbol
            resolution: Time resolution ('1', '5', '15', '30', '60', 'D', 'W', 'M')
            count: Number of candles to return
            
        Returns:
            List of candles with OHLCV data
        """
        # Calculate time range (rough estimate based on resolution)
        resolution_to_days = {
            '1': 1/1440,  # 1 minute
            '5': 5/1440,
            '15': 15/1440,
            '30': 30/1440,
            '60': 1,
            'D': 1,
            'W': 7,
            'M': 30
        }
        
        days_back = count * resolution_to_days.get(resolution, 1)
        from_date = int((datetime.now() - timedelta(days=days_back)).timestamp())
        to_date = int(datetime.now().timestamp())
        
        data = self._make_request("/stock/candle", {
            "symbol": symbol,
            "resolution": resolution,
            "from": from_date,
            "to": to_date
        })
        
        if not data or data.get('s') != 'ok':
            return []
        
        candles = []
        for i in range(len(data.get('t', []))):
            candles.append({
                'timestamp': data['t'][i],
                'open': data['o'][i],
                'high': data['h'][i],
                'low': data['l'][i],
                'close': data['c'][i],
                'volume': data.get('v', [None])[i] if 'v' in data else None
            })
        
        return candles

    def get_earnings_surprises(self, symbol: str) -> List[Dict]:
        """
        Get earnings surprises
        
        Args:
            symbol: Stock symbol
            
        Returns:
            List of earnings surprises
        """
        data = self._make_request("/stock/earnings", {"symbol": symbol})
        
        if not isinstance(data, list):
            return []
        
        surprises = []
        for earning in data[:10]:  # Return last 10
            surprises.append({
                'period': earning.get('period'),
                'actual': earning.get('actual'),
                'estimate': earning.get('estimate'),
                'surprise': earning.get('surprise'),
                'surprise_pct': earning.get('surprisePercent')
            })
        
        return surprises

    def validate_webhook_secret(self, received_secret: str) -> bool:
        """
        Validate webhook secret
        
        Args:
            received_secret: Secret from webhook request header
            
        Returns:
            True if secret is valid
        """
        return received_secret == self.webhook_secret

    def get_status(self) -> Dict:
        """
        Get service status
        
        Returns:
            Status information
        """
        return {
            'service': 'finnhub',
            'enabled': self.enabled,
            'api_key_configured': bool(self.api_key),
            'webhook_secret_configured': bool(self.webhook_secret),
            'api_calls_made': self._call_count,
            'base_url': self.base_url,
            'last_error': None,
            'status': 'ready' if self.enabled and self.api_key else 'unconfigured'
        }


def get_finnhub_service(config_path: Optional[str] = None) -> FinnhubService:
    """
    Factory function to get Finnhub service instance
    
    Args:
        config_path: Optional path to credentials file
        
    Returns:
        FinnhubService instance
    """
    return FinnhubService(config_path)
