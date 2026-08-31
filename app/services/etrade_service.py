"""
E*TRADE Trading Service
Real-time stock quotes, account management, and order execution
"""

import os
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

try:
    from pyetrade import ETradeClient
except ImportError:
    ETradeClient = None

logger = logging.getLogger(__name__)


class ETradeService:
    """
    E*TRADE API integration for real-time trading
    Handles quotes, accounts, balances, and order execution
    """

    def __init__(self, access_token: str = None, access_token_secret: str = None):
        try:
            from .etrade_config import load_etrade_env, load_credentials, is_sandbox
        except ImportError:
            from app.services.etrade_config import load_etrade_env, load_credentials, is_sandbox
        load_etrade_env()
        self.credentials_file = os.getenv(
            'ETRADE_CREDENTIALS_FILE',
            '/app/config/etrade-credentials.json'
        )
        creds = load_credentials(load_files=False)
        self.access_token = access_token or creds.access_token or os.getenv('ETRADE_ACCESS_TOKEN')
        self.access_token_secret = access_token_secret or creds.access_token_secret or os.getenv('ETRADE_ACCESS_TOKEN_SECRET')
        self.use_sandbox = is_sandbox()
        self.credentials = self._load_credentials()
        if creds.consumer_key:
            self.credentials.setdefault('etrade', {}).setdefault('oauth', {})
            self.credentials['etrade']['oauth']['consumer_key'] = creds.consumer_key
            self.credentials['etrade']['oauth']['consumer_secret'] = creds.consumer_secret
            self.credentials['etrade']['oauth']['sandbox_mode'] = self.use_sandbox
        self.client = None
        self.broker = None
        self.is_authenticated = False

        if self.access_token and self.access_token_secret:
            self._initialize_client()
        else:
            logger.warning("E*TRADE tokens not found - authenticate via OAuth before live/sandbox trading")

    def _load_credentials(self) -> dict:
        """Load E*TRADE credentials from JSON file"""
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
            logger.info(f"✅ Credentials loaded from {self.credentials_file}")
            return creds
        except FileNotFoundError:
            logger.error(f"❌ Credentials file not found: {self.credentials_file}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in credentials file: {e}")
            return {}

    def _initialize_client(self):
        """Initialize authenticated E*TRADE client via the existing broker path."""
        try:
            from .broker import ETradeBroker
        except ImportError:
            from app.services.broker import ETradeBroker
        try:
            self.broker = ETradeBroker(use_sandbox=self.use_sandbox)
            self.broker.access_token = self.access_token
            self.broker.access_token_secret = self.access_token_secret
            oauth = (self.credentials or {}).get('etrade', {}).get('oauth', {})
            if oauth.get('consumer_key'):
                self.broker.consumer_key = oauth['consumer_key']
            if oauth.get('consumer_secret'):
                self.broker.consumer_secret = oauth['consumer_secret']
            if self.broker.connect():
                self.client = self.broker.client
                self.is_authenticated = True
                env = "Sandbox" if self.use_sandbox else "Production"
                logger.info("E*TRADE client authenticated (%s)", env)
            else:
                self.is_authenticated = False
        except Exception as e:
            logger.error("Failed to initialize E*TRADE client: %s", e)
            self.is_authenticated = False

    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        Get real-time stock quote for a symbol
        
        Args:
            symbol: Stock ticker symbol (e.g., 'TSLA', 'F')
            
        Returns:
            Dict with quote data or None on failure
        """
        if not self.is_authenticated:
            logger.warning(f"⚠️  Not authenticated - cannot get quote for {symbol}")
            return None

        try:
            response = self.client.get_quote(symbol)
            
            if not response:
                logger.warning(f"No quote data for {symbol}")
                return None

            quote_data = response.get('QuoteResponse', {}).get('Quote', [])
            if not quote_data:
                return None

            quote = quote_data[0] if isinstance(quote_data, list) else quote_data

            return {
                'symbol': symbol,
                'price': float(quote.get('LastTrade', 0)),
                'bid': float(quote.get('Bid', 0)),
                'ask': float(quote.get('Ask', 0)),
                'change': float(quote.get('Change', 0)),
                'change_percent': float(quote.get('ChangePercent', 0)),
                'volume': int(quote.get('Volume', 0)),
                'market_cap': quote.get('MarketCap', 'N/A'),
                'pe_ratio': quote.get('PEJump', 'N/A'),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Failed to get quote for {symbol}: {e}")
            return None

    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get quotes for multiple symbols
        
        Args:
            symbols: List of stock ticker symbols
            
        Returns:
            Dict with symbol: quote_data pairs
        """
        quotes = {}
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                quotes[symbol] = quote
        
        return quotes

    def get_accounts(self) -> List[Dict]:
        """
        Get user's E*TRADE accounts
        
        Returns:
            List of account dictionaries
        """
        if not self.is_authenticated:
            logger.warning("⚠️  Not authenticated - cannot get accounts")
            return []

        try:
            response = self.client.get_account_list()
            accounts = []

            account_list = response.get('AccountListResponse', {}).get('Accounts', {}).get('Account', [])
            
            for account in (account_list if isinstance(account_list, list) else [account_list]):
                accounts.append({
                    'account_id': account.get('accountId'),
                    'account_name': account.get('accountName'),
                    'account_type': account.get('accountType'),
                    'option_level': account.get('optionLevel'),
                    'balance': 0  # Will be populated separately
                })

            logger.info(f"✅ Retrieved {len(accounts)} accounts")
            return accounts

        except Exception as e:
            logger.error(f"❌ Failed to get accounts: {e}")
            return []

    def get_account_balance(self, account_id: str) -> Optional[Dict]:
        """
        Get account balance and portfolio value
        
        Args:
            account_id: E*TRADE account ID
            
        Returns:
            Dict with balance information or None on failure
        """
        if not self.is_authenticated:
            logger.warning(f"⚠️  Not authenticated - cannot get balance for {account_id}")
            return None

        try:
            response = self.client.get_account_balance(account_id)
            balance_data = response.get('BalanceResponse', {})

            return {
                'account_id': account_id,
                'cash': float(balance_data.get('Cash', 0)),
                'portfolio_value': float(balance_data.get('PortfolioValue', 0)),
                'total_value': float(balance_data.get('TotalValue', 0)),
                'buying_power': float(balance_data.get('BuyingPower', 0)),
                'reserved_cash': float(balance_data.get('ReservedCash', 0)),
                'currency': balance_data.get('Currency', 'USD')
            }

        except Exception as e:
            logger.error(f"❌ Failed to get account balance for {account_id}: {e}")
            return None

    def get_portfolio(self, account_id: str) -> List[Dict]:
        """
        Get portfolio holdings for an account
        
        Args:
            account_id: E*TRADE account ID
            
        Returns:
            List of position dictionaries
        """
        if not self.is_authenticated:
            logger.warning(f"⚠️  Not authenticated - cannot get portfolio for {account_id}")
            return []

        try:
            response = self.client.get_portfolio(account_id)
            positions = []

            portfolio_response = response.get('PortfolioResponse', {})
            position_list = portfolio_response.get('Position', [])

            for position in (position_list if isinstance(position_list, list) else [position_list]):
                positions.append({
                    'symbol': position.get('symbol'),
                    'quantity': int(position.get('quantity', 0)),
                    'price': float(position.get('price', 0)),
                    'position_value': float(position.get('positionValue', 0)),
                    'open_price': float(position.get('openPrice', 0)),
                    'gain_loss': float(position.get('gainLoss', 0)),
                    'gain_loss_percent': float(position.get('gainLossPercent', 0)),
                    'last_update': position.get('lastUpdate')
                })

            logger.info(f"✅ Retrieved {len(positions)} positions from portfolio")
            return positions

        except Exception as e:
            logger.error(f"❌ Failed to get portfolio for {account_id}: {e}")
            return []

    def place_order(
        self,
        account_id: str,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str = 'Limit',
        price: Optional[float] = None,
        preview: bool = True,
        preview_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        confirm_live: bool = False,
    ) -> Optional[Dict]:
        """Preview or place via ETradeBroker. Live never one-shots preview+place."""
        if not self.is_authenticated or not self.broker:
            logger.error("Not authenticated - cannot place order")
            return None

        raw_side = (side or "").strip().upper().replace(" ", "_")
        side_map = {
            "BUY": "Buy",
            "SELL": "Sell",
            "SELL_SHORT": "SELL_SHORT",
            "SHORT": "SELL_SHORT",
            "SHORT_SELL": "SELL_SHORT",
            "BUY_TO_COVER": "BUY_TO_COVER",
            "COVER": "BUY_TO_COVER",
        }
        if raw_side not in side_map:
            logger.error("Invalid side: %s", side)
            return None
        side_norm = side_map[raw_side]

        if (order_type or "").lower() in ('limit', 'stop', 'stop_limit') and not price:
            logger.error("Price required for %s orders", order_type)
            return None

        try:
            kwargs = dict(
                symbol=symbol,
                qty=int(quantity),
                side=side_norm,
                order_type=(order_type or "limit").lower(),
                limit_price=price if (order_type or "").lower() in ("limit", "stop_limit") else None,
                stop_price=price if (order_type or "").lower() in ("stop", "stop_limit") else None,
                account_id=account_id,
                client_order_id=client_order_id,
            )
            if preview:
                logger.info("Previewing order: %s %s %s", side_norm, quantity, symbol)
                result = self.broker.preview_order(**kwargs)
                if result.get("status") == "ERROR":
                    logger.error("Preview failed: %s", result.get("message"))
                    return result
                return {
                    "status": "preview",
                    "message": "Order preview successful - ready to place",
                    "preview_id": result.get("preview_id"),
                    "client_order_id": result.get("client_order_id"),
                    "order_data": result,
                }

            logger.info("Placing previously previewed order: %s %s %s", side_norm, quantity, symbol)
            result = self.broker.place_order(
                **kwargs,
                preview_id=preview_id,
                confirm_live=confirm_live,
            )
            try:
                from .ahana_memory import get_ahana_memory
                get_ahana_memory().ingest({
                    "kind": "fill" if (result or {}).get("status") == "PLACED" else "alert",
                    "symbol": symbol,
                    "payload": {"preview_id": preview_id, "result": result, "side": side_norm, "qty": quantity},
                })
            except Exception:
                logger.debug("fill ingest skipped", exc_info=False)
            return result
        except Exception as e:
            logger.error("Failed to place order: %s", e)
            return {"status": "ERROR", "message": str(e)}

    def cancel_order(self, account_id: str, order_id: str) -> bool:
        """
        Cancel an existing order
        
        Args:
            account_id: E*TRADE account ID
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_authenticated:
            logger.error("❌ Not authenticated - cannot cancel order")
            return False

        try:
            self.client.cancel_order(account_id, order_id)
            logger.info(f"✅ Order {order_id} cancelled")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to cancel order {order_id}: {e}")
            return False

    def get_orders(self, account_id: str) -> List[Dict]:
        """
        Get open orders for an account
        
        Args:
            account_id: E*TRADE account ID
            
        Returns:
            List of order dictionaries
        """
        if not self.is_authenticated:
            logger.warning(f"⚠️  Not authenticated - cannot get orders for {account_id}")
            return []

        try:
            response = self.client.get_orders(account_id)
            orders = []

            order_list = response.get('OrderResponse', {}).get('Order', [])

            for order in (order_list if isinstance(order_list, list) else [order_list]):
                orders.append({
                    'order_id': order.get('orderId'),
                    'symbol': order.get('symbol'),
                    'quantity': int(order.get('quantity', 0)),
                    'side': order.get('side'),
                    'order_type': order.get('orderType'),
                    'price': float(order.get('price', 0)) if order.get('price') else None,
                    'status': order.get('status'),
                    'placed_time': order.get('placedTime'),
                    'executed_price': float(order.get('executedPrice', 0)) if order.get('executedPrice') else None
                })

            logger.info(f"✅ Retrieved {len(orders)} open orders")
            return orders

        except Exception as e:
            logger.error(f"❌ Failed to get orders for {account_id}: {e}")
            return []

    def get_status(self) -> Dict:
        """Get E*TRADE connection status"""
        env = 'Sandbox' if self.use_sandbox else 'Production'
        return {
            'is_authenticated': self.is_authenticated,
            'environment': env,
            'sandbox': self.use_sandbox,
            'status': f'Connected ({env})' if self.is_authenticated else 'Disconnected',
            'has_tokens': bool(self.access_token and self.access_token_secret),
            'pdt_enforced': False,
        }
