"""
Git Stonks Backup Service - Alternative data source for charts and info
Uses https://github.com/nk2028/stonks for fallback stock data
"""

import requests
import logging
from typing import Dict, Optional
import json

logger = logging.getLogger(__name__)


class StonksBackupService:
    """Backup service using Git Stonks for charts and stock info"""
    
    def __init__(self):
        self.base_url = "https://raw.githubusercontent.com/nk2028/stonks/main/data"
        self.cache = {}
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        """Get stock info from Stonks as backup"""
        try:
            # Stonks has limited data, mainly for popular stocks
            # Returns: OHLCV data in JSON format
            url = f"{self.base_url}/{symbol}.json"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                logger.info(f"✅ Stonks backup: Got data for {symbol}")
                return response.json()
            else:
                logger.warning(f"Stonks: No data for {symbol}")
                return None
        except Exception as e:
            logger.warning(f"Stonks backup failed for {symbol}: {e}")
            return None
    
    def get_chart_data(self, symbol: str, period: str = "1y") -> Optional[list]:
        """Get chart data from Stonks as backup for yfinance"""
        try:
            data = self.get_stock_info(symbol)
            if data and isinstance(data, list):
                # Convert Stonks format to our standard format
                chart_data = []
                for item in data[:100]:  # Limit to 100 most recent
                    if isinstance(item, dict):
                        chart_data.append({
                            'date': item.get('date', ''),
                            'open': item.get('o', 0),
                            'high': item.get('h', 0),
                            'low': item.get('l', 0),
                            'close': item.get('c', 0),
                            'volume': item.get('v', 0)
                        })
                
                logger.info(f"✅ Stonks chart: {len(chart_data)} points for {symbol}")
                return chart_data if chart_data else None
        except Exception as e:
            logger.warning(f"Stonks chart failed: {e}")
        
        return None
    
    def verify_symbol_exists(self, symbol: str) -> bool:
        """Check if symbol is available in Stonks backup"""
        try:
            data = self.get_stock_info(symbol)
            return data is not None
        except:
            return False


# Singleton instance
_stonks_service = None


def get_stonks_backup_service():
    """Get or create stonks backup service instance"""
    global _stonks_service
    if _stonks_service is None:
        _stonks_service = StonksBackupService()
    return _stonks_service
