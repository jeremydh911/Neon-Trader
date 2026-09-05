"""
Broker Integration - Connects to Alpaca and E*TRADE for actual trade execution
Supports both paper/sandbox trading and live trading
"""

import logging
import os
from typing import Dict, Optional
from datetime import datetime
try:
    from utils.time_utils import now_utc_iso  # type: ignore
except Exception:
    try:
        from app.utils.time_utils import now_utc_iso  # type: ignore
    except Exception:
        from datetime import datetime, timezone

        def now_utc_iso() -> str:  # type: ignore
            return datetime.now(timezone.utc).isoformat()
import json

logger = logging.getLogger(__name__)

class BrokerConnection:
    """Base broker connection class"""
    
    def __init__(self):
        self.connected = False
        self.account_value = 0
        self.cash = 0
        self.positions = {}
    
    def connect(self) -> bool:
        raise NotImplementedError
    
    def disconnect(self) -> bool:
        raise NotImplementedError
    
    def place_order(self, symbol: str, qty: int, side: str, order_type: str = "market") -> Dict:
        raise NotImplementedError
    
    def get_positions(self) -> Dict:
        raise NotImplementedError
    
    def get_account(self) -> Dict:
        raise NotImplementedError


class AlpacaBroker(BrokerConnection):
    """Alpaca broker integration"""
    
    def __init__(self, use_paper_trading: bool = True):
        super().__init__()
        self.use_paper_trading = use_paper_trading
        self.api_key = os.getenv('ALPACA_API_KEY', '')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY', '')
        self.base_url = "https://paper-api.alpaca.markets" if use_paper_trading else "https://api.alpaca.markets"
        self.api = None
        self.orders_log = "/app/data/orders.json"
    
    def connect(self) -> bool:
        """Connect to Alpaca API"""
        try:
            import alpaca_trade_api as tradeapi
            self.api = tradeapi.REST(self.api_key, self.secret_key, self.base_url)
            account = self.api.get_account()
            self.account_value = float(account.portfolio_value)
            self.cash = float(account.cash)
            self.connected = True
            mode = "PAPER" if self.use_paper_trading else "LIVE"
            logger.info(f"✅ Connected to Alpaca {mode} Trading")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Alpaca: {e}")
            return False
    
    def disconnect(self) -> bool:
        self.connected = False
        return True
    
    def place_order(self, symbol: str, qty: int, side: str, order_type: str = "market", 
                   limit_price: float = None, stop_price: float = None) -> Dict:
        """Place an order on Alpaca"""
        if not self.connected:
            return {'status': 'ERROR', 'message': 'Not connected'}
        try:
            order_params = {'symbol': symbol, 'qty': qty, 'side': side, 'type': order_type, 'time_in_force': 'day'}
            if order_type == 'limit' and limit_price:
                order_params['limit_price'] = limit_price
            elif order_type == 'stop' and stop_price:
                order_params['stop_price'] = stop_price
            order = self.api.submit_order(**order_params)
            order_dict = {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': order.qty,
                'side': order.side,
                'type': order.order_type,
                'status': order.status,
                'timestamp': now_utc_iso()
            }
            self._log_order(order_dict)
            logger.info(f"✅ Order placed: {side.upper()} {qty} {symbol}")
            return order_dict
        except Exception as e:
            logger.error(f"❌ Failed to place order: {e}")
            return {'status': 'ERROR', 'message': str(e)}
    
    def _log_order(self, order: Dict):
        try:
            orders = []
            if os.path.exists(self.orders_log):
                with open(self.orders_log, 'r') as f:
                    orders = json.load(f)
            orders.append(order)
            os.makedirs("/app/data", exist_ok=True)
            with open(self.orders_log, 'w') as f:
                json.dump(orders, f, indent=2)
        except Exception as e:
            logger.error(f"Error logging order: {e}")
    
    def get_positions(self) -> Dict[str, Dict]:
        if not self.connected:
            return {}
        try:
            positions = self.api.list_positions()
            positions_dict = {}
            for pos in positions:
                positions_dict[pos.symbol] = {
                    'symbol': pos.symbol,
                    'qty': float(pos.qty),
                    'avg_fill_price': float(pos.avg_fill_price),
                    'market_value': float(pos.market_value),
                    'side': pos.side
                }
            return positions_dict
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {}
    
    def get_account(self) -> Dict:
        if not self.connected:
            return {}
        try:
            account = self.api.get_account()
            return {
                'account_number': account.account_number,
                'portfolio_value': float(account.portfolio_value),
                'cash': float(account.cash),
                'buying_power': float(account.buying_power),
                'day_trading_buying_power': float(account.daytrade_buying_power),
                'status': account.status
            }
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            return {}


class ETradeBroker(BrokerConnection):
    """E*TRADE broker integration"""
    
    def __init__(self, use_sandbox: bool = True):
        super().__init__()
        self.use_sandbox = use_sandbox
        self.consumer_key = os.getenv('ETRADE_CONSUMER_KEY', '')
        self.consumer_secret = os.getenv('ETRADE_CONSUMER_SECRET', '')
        self.access_token = os.getenv('ETRADE_ACCESS_TOKEN', '')
        self.access_token_secret = os.getenv('ETRADE_ACCESS_TOKEN_SECRET', '')
        self.base_url = "https://etwssandbox.etrade.com" if use_sandbox else "https://api.etrade.com"
        self.orders_log = "/app/data/etrade_orders.json"
    
    def connect(self) -> bool:
        """Connect to E*TRADE API"""
        try:
            import pyetrade
            # E*TRADE OAuth requires tokens - if empty, we're not authenticated yet
            if not self.access_token or not self.access_token_secret:
                logger.warning("⚠️  E*TRADE OAuth tokens empty - authentication required")
                logger.info("To authenticate, user must complete OAuth flow and set ETRADE_ACCESS_TOKEN and ETRADE_ACCESS_TOKEN_SECRET")
                # Don't fail - just return unconnected state
                self.connected = False
                return False
            
            # Initialize accounts client with OAuth tokens
            self.client = pyetrade.ETradeAccounts(
                self.consumer_key, self.consumer_secret,
                resource_owner_key=self.access_token,
                resource_owner_secret=self.access_token_secret,
                client_key=True
            )
            # Verify connection can reach accounts
            accounts = self.client.get_account_list()
            self.connected = True
            mode = "SANDBOX" if self.use_sandbox else "LIVE"
            logger.info(f"✅ Connected to E*TRADE {mode} Trading")
            return True
        except ImportError:
            logger.error("❌ pyetrade not installed")
            return False
        except Exception as e:
            logger.error(f"⚠️  E*TRADE connection issue (may need auth): {str(e)[:100]}")
            return False
    
    def disconnect(self) -> bool:
        self.connected = False
        return True
    
    def place_order(self, symbol: str, qty: int, side: str, order_type: str = "market",
                   limit_price: float = None, stop_price: float = None) -> Dict:
        if not self.connected:
            return {'status': 'ERROR', 'message': 'Not connected'}
        try:
            import pyetrade
            accounts = self.client.get_account_list()
            if not accounts:
                return {'status': 'ERROR', 'message': 'No accounts'}
            account_id = accounts[0]['accountId']
            trade_client = pyetrade.ETradeOrder(
                self.consumer_key, self.consumer_secret,
                self.access_token, self.access_token_secret,
                client_key=True
            )
            order_data = {
                'symbol': symbol,
                'quantity': qty,
                'side': side.upper(),
                'orderType': order_type.upper(),
                'limitPrice': limit_price,
                'stopPrice': stop_price,
            }
            preview = trade_client.preview_order(account_id, order_data)
            if not preview:
                return {'status': 'ERROR', 'message': 'Preview failed'}
            order_result = trade_client.place_order(account_id, preview)
            order_dict = {
                'order_id': order_result.get('OrderIds', [None])[0],
                'symbol': symbol,
                'qty': qty,
                'side': side,
                'type': order_type,
                'status': 'PLACED',
                'broker': 'ETRADE',
                'timestamp': now_utc_iso()
            }
            self._log_order(order_dict)
            logger.info(f"✅ E*TRADE Order placed: {side.upper()} {qty} {symbol}")
            return order_dict
        except Exception as e:
            logger.error(f"❌ Failed to place E*TRADE order: {e}")
            return {'status': 'ERROR', 'message': str(e)}
    
    def _log_order(self, order: Dict):
        try:
            orders = []
            if os.path.exists(self.orders_log):
                with open(self.orders_log, 'r') as f:
                    orders = json.load(f)
            orders.append(order)
            os.makedirs("/app/data", exist_ok=True)
            with open(self.orders_log, 'w') as f:
                json.dump(orders, f, indent=2)
        except Exception as e:
            logger.error(f"Error logging order: {e}")
    
    def get_positions(self) -> Dict[str, Dict]:
        if not self.connected:
            return {}
        try:
            accounts = self.client.get_account_list()
            if not accounts:
                return {}
            portfolio = self.client.get_account(accounts[0]['accountId'], assetcat='CASH')
            positions_dict = {}
            if 'PortfolioResponse' in portfolio:
                for position in portfolio['PortfolioResponse'].get('Position', []):
                    symbol = position.get('Product', {}).get('symbol')
                    if symbol:
                        positions_dict[symbol] = {
                            'symbol': symbol,
                            'qty': float(position.get('quantity', 0)),
                            'price': float(position.get('lastPrice', 0)),
                        }
            return positions_dict
        except Exception as e:
            logger.error(f"Error getting E*TRADE positions: {e}")
            return {}
    
    def get_account(self) -> Dict:
        if not self.connected:
            return {}
        try:
            accounts = self.client.get_account_list()
            if not accounts:
                return {}
            account_id = accounts[0]['accountId']
            account_data = self.client.get_account(account_id, assetcat='CASH')
            if 'AccountResponse' in account_data:
                account_info = account_data['AccountResponse']
                return {
                    'account_number': account_id,
                    'portfolio_value': float(account_info.get('Account', {}).get('accountValue', 0)),
                    'cash': float(account_info.get('Account', {}).get('cashBalance', 0)),
                    'buying_power': float(account_info.get('Account', {}).get('buyingPower', 0)),
                    'broker': 'ETRADE'
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting E*TRADE account: {e}")
            return {}


_broker = None

def get_broker(broker_type: str = 'etrade', use_sandbox: bool = True):
    """Get or create broker connection.

    Paper/test path:
      - broker_type='mock' OR env USE_MOCK_BROKER=1 / PAPER_MODE=1 → MockBroker
      - Never reuse a live singleton when mock is requested.
    """
    global _broker
    want_mock = (
        str(broker_type).lower() == 'mock'
        or os.getenv('USE_MOCK_BROKER', '').lower() in ('1', 'true', 'yes')
        or os.getenv('PAPER_MODE', '').lower() in ('1', 'true', 'yes')
    )
    if want_mock:
        from .mock_broker import MockBroker
        mock = MockBroker()
        mock.connect()
        logger.info("🧪 Using MockBroker (paper/test — no live orders)")
        return mock

    if _broker is None:
        if broker_type.lower() == 'etrade':
            _broker = ETradeBroker(use_sandbox=use_sandbox)
        else:
            _broker = AlpacaBroker(use_paper_trading=use_sandbox)
        _broker.connect()
    return _broker
