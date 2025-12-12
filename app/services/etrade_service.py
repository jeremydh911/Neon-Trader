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
        self.credentials_file = os.getenv(
            'ETRADE_CREDENTIALS_FILE',
            '/app/config/etrade-credentials.json'
        )
        self.access_token = access_token or os.getenv('ETRADE_ACCESS_TOKEN')
        self.access_token_secret = access_token_secret or os.getenv('ETRADE_ACCESS_TOKEN_SECRET')
        
        self.credentials = self._load_credentials()
        self.client = None
        self.is_authenticated = False

        if self.access_token and self.access_token_secret:
            self._initialize_client()
        else:
            logger.warning("⚠️  E*TRADE tokens not found - using paper trading mode")

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
        """Initialize authenticated E*TRADE client"""
        if not ETradeClient:
            logger.error("pyetrade not installed")
            return

        try:
            self.client = ETradeClient(
                client_key=self.credentials['etrade']['oauth']['consumer_key'],
                client_secret=self.credentials['etrade']['oauth']['consumer_secret'],
                resource_owner_key=self.access_token,
                resource_owner_secret=self.access_token_secret,
                sandbox=True
            )
            self.is_authenticated = True
            logger.info("✅ E*TRADE client authenticated successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize E*TRADE client: {e}")
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
        order_type: str = 'Market',
        price: Optional[float] = None,
        preview: bool = True
    ) -> Optional[Dict]:
        """
        Place a buy/sell order
        
        Args:
            account_id: E*TRADE account ID
            symbol: Stock ticker symbol
            quantity: Number of shares
            side: 'Buy' or 'Sell'
            order_type: 'Market', 'Limit', or 'Stop'
            price: Limit/stop price (required for non-market orders)
            preview: If True, preview order without placing
            
        Returns:
            Order confirmation or None on failure
        """
        if not self.is_authenticated:
            logger.error("❌ Not authenticated - cannot place order")
            return None

        if side not in ['Buy', 'Sell']:
            logger.error(f"❌ Invalid side: {side}")
            return None

        if order_type in ['Limit', 'Stop'] and not price:
            logger.error(f"❌ Price required for {order_type} orders")
            return None

        try:
            logger.info(f"📋 {'Previewing' if preview else 'Placing'} order: {side} {quantity} {symbol} @ ${price if price else 'Market'}")

            order_response = self.client.place_order(
                account_id=account_id,
                symbol=symbol,
                quantity=quantity,
                order_type=side,  # E*TRADE uses 'Buy'/'Sell' not 'BUY'/'SELL'
                order_side=order_type,  # Market, Limit, Stop
                limit_price=price if order_type == 'Limit' else None,
                stop_price=price if order_type == 'Stop' else None,
                preview=preview
            )

            if preview:
                logger.info(f"✅ Order preview successful")
                return {
                    'status': 'preview',
                    'message': 'Order preview successful - ready to place',
                    'order_data': order_response
                }
            else:
                logger.info(f"✅ Order placed: {symbol} {quantity} @ ${price if price else 'Market'}")
                return {
                    'status': 'placed',
                    'message': f'Order placed successfully',
                    'order_data': order_response
                }

        except Exception as e:
            logger.error(f"❌ Failed to place order: {e}")
            return None

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
        return {
            'is_authenticated': self.is_authenticated,
            'environment': 'Sandbox',
            'status': '✅ Connected' if self.is_authenticated else '❌ Disconnected',
            'has_tokens': bool(self.access_token and self.access_token_secret)
        }
