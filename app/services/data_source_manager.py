"""
Data Source Manager - Primary/Fallback data retrieval
Manages E*TRADE (primary) and Finnhub (fallback) data sources
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Available data sources"""
    ETRADE = "etrade"
    FINNHUB = "finnhub"
    STONKS = "stonks"


@dataclass
class QuoteData:
    """Standardized quote data"""
    symbol: str
    price: float
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    previous_close: Optional[float] = None
    timestamp: Optional[int] = None
    source: str = "unknown"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'price': self.price,
            'high': self.high,
            'low': self.low,
            'open': self.open,
            'previous_close': self.previous_close,
            'timestamp': self.timestamp,
            'source': self.source
        }


class DataSourceManager:
    """
    Manages multiple data sources with fallback strategy
    Primary: E*TRADE
    Fallback 1: Finnhub
    Fallback 2: Stonks (mock data)
    """

    def __init__(self, etrade_service=None, finnhub_service=None, stonks_service=None):
        """
        Initialize data source manager
        
        Args:
            etrade_service: Initialized ETradeService instance
            finnhub_service: Initialized FinnhubService instance
            stonks_service: Initialized StonksService instance
        """
        self.etrade_service = etrade_service
        self.finnhub_service = finnhub_service
        self.stonks_service = stonks_service
        self.source_priority = [DataSource.ETRADE, DataSource.FINNHUB, DataSource.STONKS]
        self.stats = {
            'etrade_calls': 0,
            'etrade_successes': 0,
            'etrade_failures': 0,
            'finnhub_calls': 0,
            'finnhub_successes': 0,
            'finnhub_failures': 0,
            'stonks_calls': 0,
            'stonks_successes': 0,
            'stonks_failures': 0,
        }

    def get_quote(self, symbol: str, prefer_source: Optional[DataSource] = None) -> Tuple[Optional[QuoteData], DataSource]:
        """
        Get quote for symbol with fallback
        
        Args:
            symbol: Stock symbol
            prefer_source: Preferred data source (still falls back if unavailable)
            
        Returns:
            Tuple of (QuoteData, source used) or (None, DataSource.STONKS)
        """
        # Determine order of sources to try
        if prefer_source:
            sources = [prefer_source] + [s for s in self.source_priority if s != prefer_source]
        else:
            sources = self.source_priority

        # Try each source in order
        for source in sources:
            if source == DataSource.ETRADE:
                quote = self._try_etrade_quote(symbol)
                if quote:
                    self.stats['etrade_successes'] += 1
                    logger.info(f"Quote {symbol} from E*TRADE")
                    return quote, DataSource.ETRADE
                else:
                    self.stats['etrade_failures'] += 1

            elif source == DataSource.FINNHUB:
                quote = self._try_finnhub_quote(symbol)
                if quote:
                    self.stats['finnhub_successes'] += 1
                    logger.info(f"Quote {symbol} from Finnhub")
                    return quote, DataSource.FINNHUB
                else:
                    self.stats['finnhub_failures'] += 1

            elif source == DataSource.STONKS:
                quote = self._try_stonks_quote(symbol)
                if quote:
                    self.stats['stonks_successes'] += 1
                    logger.info(f"Quote {symbol} from Stonks (mock)")
                    return quote, DataSource.STONKS
                else:
                    self.stats['stonks_failures'] += 1

        return None, DataSource.STONKS

    def get_quotes(self, symbols: List[str]) -> Dict[str, Tuple[Optional[QuoteData], DataSource]]:
        """
        Get quotes for multiple symbols
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dictionary mapping symbol to (QuoteData, source) tuple
        """
        quotes = {}
        for symbol in symbols:
            quotes[symbol] = self.get_quote(symbol)
        return quotes

    def get_company_info(self, symbol: str) -> Tuple[Optional[Dict], DataSource]:
        """
        Get company information with fallback
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Tuple of (company info dict, source used)
        """
        # Try E*TRADE first
        if self.etrade_service:
            try:
                info = self.etrade_service.get_account_info(symbol)
                if info:
                    logger.info(f"Company info {symbol} from E*TRADE")
                    return info, DataSource.ETRADE
            except Exception as e:
                logger.debug(f"E*TRADE company info failed for {symbol}: {e}")

        # Fall back to Finnhub
        if self.finnhub_service:
            try:
                info = self.finnhub_service.get_company_info(symbol)
                if info:
                    logger.info(f"Company info {symbol} from Finnhub")
                    return info, DataSource.FINNHUB
            except Exception as e:
                logger.debug(f"Finnhub company info failed for {symbol}: {e}")

        logger.warning(f"Company info unavailable for {symbol}")
        return None, DataSource.STONKS

    def get_news(self, symbol: str, limit: int = 10) -> Tuple[List[Dict], DataSource]:
        """
        Get news with fallback
        
        Args:
            symbol: Stock symbol
            limit: Number of articles
            
        Returns:
            Tuple of (news list, source used)
        """
        # Try Finnhub first for news
        if self.finnhub_service:
            try:
                news = self.finnhub_service.get_news(symbol, limit)
                if news:
                    logger.info(f"News for {symbol} from Finnhub")
                    return news, DataSource.FINNHUB
            except Exception as e:
                logger.debug(f"Finnhub news failed for {symbol}: {e}")

        # Try E*TRADE
        if self.etrade_service:
            try:
                news = self.etrade_service.get_news(symbol, limit)
                if news:
                    logger.info(f"News for {symbol} from E*TRADE")
                    return news, DataSource.ETRADE
            except Exception as e:
                logger.debug(f"E*TRADE news failed for {symbol}: {e}")

        logger.warning(f"News unavailable for {symbol}")
        return [], DataSource.STONKS

    def get_status(self) -> Dict[str, Any]:
        """
        Get data source manager status
        
        Returns:
            Status information for all sources
        """
        status = {
            'timestamp': datetime.now().isoformat(),
            'sources': {},
            'statistics': self.stats,
            'fallback_chain': [s.value for s in self.source_priority]
        }

        # E*TRADE status
        if self.etrade_service:
            try:
                etrade_status = self.etrade_service.is_authenticated()
                status['sources']['etrade'] = {
                    'available': etrade_status,
                    'authenticated': etrade_status
                }
            except Exception as e:
                status['sources']['etrade'] = {
                    'available': False,
                    'error': str(e)
                }
        else:
            status['sources']['etrade'] = {'available': False, 'reason': 'not_initialized'}

        # Finnhub status
        if self.finnhub_service:
            try:
                finnhub_status = self.finnhub_service.get_status()
                status['sources']['finnhub'] = {
                    'available': finnhub_status.get('enabled'),
                    'configured': finnhub_status.get('api_key_configured')
                }
            except Exception as e:
                status['sources']['finnhub'] = {
                    'available': False,
                    'error': str(e)
                }
        else:
            status['sources']['finnhub'] = {'available': False, 'reason': 'not_initialized'}

        # Stonks status
        if self.stonks_service:
            status['sources']['stonks'] = {
                'available': True,
                'type': 'mock_data'
            }
        else:
            status['sources']['stonks'] = {'available': False, 'reason': 'not_initialized'}

        return status

    def _try_etrade_quote(self, symbol: str) -> Optional[QuoteData]:
        """Try to get quote from E*TRADE"""
        if not self.etrade_service:
            return None
        
        try:
            self.stats['etrade_calls'] += 1
            quote = self.etrade_service.get_quotes([symbol])
            
            if quote and symbol in quote:
                q = quote[symbol]
                return QuoteData(
                    symbol=symbol,
                    price=q.get('lastTrade'),
                    high=q.get('high'),
                    low=q.get('low'),
                    open=q.get('open'),
                    previous_close=q.get('previousClose'),
                    timestamp=int(datetime.now().timestamp()),
                    source='etrade'
                )
        except Exception as e:
            logger.debug(f"E*TRADE quote failed for {symbol}: {e}")
        
        return None

    def _try_finnhub_quote(self, symbol: str) -> Optional[QuoteData]:
        """Try to get quote from Finnhub"""
        if not self.finnhub_service:
            return None
        
        try:
            self.stats['finnhub_calls'] += 1
            quote_dict = self.finnhub_service.get_quote(symbol)
            
            if quote_dict:
                return QuoteData(
                    symbol=symbol,
                    price=quote_dict.get('price'),
                    high=quote_dict.get('high'),
                    low=quote_dict.get('low'),
                    open=quote_dict.get('open'),
                    previous_close=quote_dict.get('previous_close'),
                    timestamp=quote_dict.get('timestamp'),
                    source='finnhub'
                )
        except Exception as e:
            logger.debug(f"Finnhub quote failed for {symbol}: {e}")
        
        return None

    def _try_stonks_quote(self, symbol: str) -> Optional[QuoteData]:
        """Try to get quote from Stonks (mock)"""
        if not self.stonks_service:
            return None
        
        try:
            self.stats['stonks_calls'] += 1
            quote = self.stonks_service.get_quote(symbol)
            
            if quote:
                return QuoteData(
                    symbol=symbol,
                    price=quote.get('price'),
                    high=quote.get('high'),
                    low=quote.get('low'),
                    open=quote.get('open'),
                    previous_close=quote.get('previous_close'),
                    timestamp=int(datetime.now().timestamp()),
                    source='stonks'
                )
        except Exception as e:
            logger.debug(f"Stonks quote failed for {symbol}: {e}")
        
        return None

    def reset_stats(self):
        """Reset statistics"""
        for key in self.stats:
            self.stats[key] = 0


def get_data_source_manager(
    etrade_service=None,
    finnhub_service=None,
    stonks_service=None
) -> DataSourceManager:
    """
    Factory function to create data source manager
    
    Args:
        etrade_service: E*TRADE service instance
        finnhub_service: Finnhub service instance
        stonks_service: Stonks service instance
        
    Returns:
        DataSourceManager instance
    """
    return DataSourceManager(etrade_service, finnhub_service, stonks_service)
