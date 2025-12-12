"""
Portfolio Tracker - Tracks holdings and calculates real P&L based on live prices
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Tuple
import pandas as pd
from .stock_data import get_stock_service

logger = logging.getLogger(__name__)

class PortfolioTracker:
    """Track portfolio holdings and calculate real P&L"""
    
    def __init__(self):
        self.portfolio_file = "/app/data/portfolio.json"
        self.history_file = "/app/data/portfolio_history.json"
        self.stock_service = get_stock_service()
        
        # Initialize default portfolio with realistic cost basis from 6 months ago
        self.default_portfolio = {
            'AAPL': {'shares': 100, 'cost_basis': 201.03, 'purchase_date': '2025-06-09'},
            'MSFT': {'shares': 50, 'cost_basis': 471.09, 'purchase_date': '2025-06-09'},
            'GOOGL': {'shares': 25, 'cost_basis': 175.82, 'purchase_date': '2025-06-09'},
            'TSLA': {'shares': 10, 'cost_basis': 308.58, 'purchase_date': '2025-06-09'},
            'NVDA': {'shares': 5, 'cost_basis': 142.60, 'purchase_date': '2025-06-09'},
        }
        
        self.cash_balance = 0  # Will be loaded from file
        self.load_portfolio()
    
    def load_portfolio(self):
        """Load portfolio from file or create default"""
        try:
            os.makedirs("/app/data", exist_ok=True)
            if os.path.exists(self.portfolio_file):
                with open(self.portfolio_file, 'r') as f:
                    data = json.load(f)
                    # Handle both old format (dict of holdings) and new format (with cash_balance)
                    if isinstance(data, dict) and 'cash_balance' in data:
                        self.cash_balance = data.get('cash_balance', 25000)
                        self.holdings = data.get('holdings', {})
                    else:
                        # Old format - assume it's all holdings
                        self.cash_balance = 25000
                        self.holdings = data if data else {}
                logger.info(f"✅ Loaded portfolio with {len(self.holdings)} holdings, cash: ${self.cash_balance:,.2f}")
            else:
                # Create default portfolio and fetch real historical prices
                self.cash_balance = 25000
                self.holdings = self._initialize_with_historical_prices()
                self.save_portfolio()
                logger.info(f"✅ Created default portfolio with 5 holdings (historical prices fetched)")
        except Exception as e:
            logger.error(f"Error loading portfolio: {e}")
            self.cash_balance = 25000
            self.holdings = self.default_portfolio
    
    def _initialize_with_historical_prices(self) -> dict:
        """Initialize portfolio with real historical prices from purchase date"""
        try:
            import yfinance as yf
            from datetime import datetime
            
            portfolio = {}
            purchase_date = "2025-06-09"
            
            for symbol, holding in self.default_portfolio.items():
                try:
                    ticker = yf.Ticker(symbol)
                    # Fetch price on exact purchase date
                    hist = ticker.history(start="2025-06-08", end="2025-06-10")
                    
                    if not hist.empty:
                        # Get the close price from June 9
                        if "2025-06-09" in hist.index:
                            price = float(hist.loc["2025-06-09"]['Close'])
                        else:
                            price = float(hist['Close'].iloc[0])
                        
                        portfolio[symbol] = {
                            'shares': holding['shares'],
                            'cost_basis': round(price, 2),
                            'purchase_date': purchase_date
                        }
                        logger.info(f"✅ {symbol}: ${price:.2f} on {purchase_date}")
                    else:
                        # Fallback to default if no data
                        portfolio[symbol] = holding
                        logger.warning(f"⚠️ {symbol}: No historical data, using default")
                
                except Exception as e:
                    logger.warning(f"⚠️ {symbol}: Error fetching price - {e}, using default")
                    portfolio[symbol] = holding
            
            return portfolio
        except Exception as e:
            logger.error(f"Error fetching historical prices: {e}")
            return self.default_portfolio
    
    def save_portfolio(self):
        """Save portfolio to file"""
        try:
            os.makedirs("/app/data", exist_ok=True)
            portfolio_data = {
                'cash_balance': self.cash_balance,
                'holdings': self.holdings
            }
            with open(self.portfolio_file, 'w') as f:
                json.dump(portfolio_data, f, indent=2)
            logger.info("✅ Saved portfolio")
        except Exception as e:
            logger.error(f"Error saving portfolio: {e}")
    
    def get_portfolio_value(self) -> Tuple[float, float, float]:
        """
        Get current portfolio value with gains/losses
        Returns: (total_portfolio_value_including_cash, total_cost_basis, total_gain)
        """
        holdings_value = 0
        total_cost = 0
        
        for symbol, holding in self.holdings.items():
            shares = holding['shares']
            cost_per_share = holding['cost_basis']
            
            # Get current price
            current_price, _, _ = self.stock_service.get_current_price(symbol)
            
            if current_price > 0:
                position_value = shares * current_price
                position_cost = shares * cost_per_share
                
                holdings_value += position_value
                total_cost += position_cost
                
                logger.debug(f"{symbol}: {shares} @ ${current_price:.2f} = ${position_value:.2f}")
        
        # Total portfolio value is holdings + cash
        total_portfolio_value = holdings_value + self.cash_balance
        total_gain = holdings_value - total_cost
        
        return total_portfolio_value, total_cost, total_gain
    
    def get_portfolio_dataframe(self) -> pd.DataFrame:
        """Get portfolio as pandas DataFrame with current prices"""
        data = []
        total_value = 0
        
        for symbol, holding in self.holdings.items():
            shares = holding['shares']
            cost_per_share = holding['cost_basis']
            
            # Get current price
            current_price, change, change_pct = self.stock_service.get_current_price(symbol)
            
            if current_price > 0:
                position_value = shares * current_price
                position_cost = shares * cost_per_share
                position_gain = position_value - position_cost
                position_gain_pct = (position_gain / position_cost * 100) if position_cost > 0 else 0
                
                total_value += position_value
                
                data.append({
                    'Symbol': symbol,
                    'Shares': shares,
                    'Cost Basis': f"${cost_per_share:.2f}",
                    'Current Price': f"${current_price:.2f}",
                    'Position Value': f"${position_value:.2f}",
                    'Gain/Loss': f"${position_gain:+.2f}",
                    'Gain/Loss %': f"{position_gain_pct:+.1f}%",
                    'Market Change': f"{change_pct:+.2f}%"
                })
        
        df = pd.DataFrame(data)
        return df, total_value
    
    def get_portfolio_summary(self) -> Dict:
        """Get complete portfolio summary"""
        total_value, total_cost, total_gain = self.get_portfolio_value()
        total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0
        
        return {
            'total_value': total_value,
            'total_cost_basis': total_cost,
            'total_gain': total_gain,
            'total_gain_pct': total_gain_pct,
            'num_holdings': len(self.holdings)
        }
    
    def add_holding(self, symbol: str, shares: int, cost_basis: float):
        """Add or update a holding"""
        if symbol in self.holdings:
            self.holdings[symbol]['shares'] += shares
        else:
            self.holdings[symbol] = {
                'shares': shares,
                'cost_basis': cost_basis
            }
        self.save_portfolio()
        logger.info(f"✅ Added {shares} {symbol} @ ${cost_basis:.2f}")
    
    def remove_holding(self, symbol: str, shares: int = None):
        """Remove shares from a holding or delete entirely"""
        if symbol not in self.holdings:
            logger.warning(f"Symbol {symbol} not in portfolio")
            return False
        
        if shares is None or shares >= self.holdings[symbol]['shares']:
            del self.holdings[symbol]
            logger.info(f"✅ Removed all {symbol} from portfolio")
        else:
            self.holdings[symbol]['shares'] -= shares
            logger.info(f"✅ Removed {shares} {symbol} from portfolio")
        
        self.save_portfolio()
        return True
    
    def record_history(self):
        """Record portfolio value to history"""
        try:
            total_value, total_cost, total_gain = self.get_portfolio_value()
            
            history_entry = {
                'timestamp': datetime.now().isoformat(),
                'total_value': total_value,
                'total_cost': total_cost,
                'total_gain': total_gain,
                'gain_pct': (total_gain / total_cost * 100) if total_cost > 0 else 0
            }
            
            # Load existing history
            history = []
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
            
            history.append(history_entry)
            
            # Keep only last 100 entries
            if len(history) > 100:
                history = history[-100:]
            
            # Save history
            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=2)
            
            logger.debug(f"✅ Recorded portfolio history entry")
        except Exception as e:
            logger.error(f"Error recording history: {e}")
    
    def get_history(self, days: int = 30) -> pd.DataFrame:
        """Get portfolio history for charting"""
        try:
            if not os.path.exists(self.history_file):
                logger.warning("No portfolio history found")
                return pd.DataFrame()
            
            with open(self.history_file, 'r') as f:
                history = json.load(f)
            
            # Convert to DataFrame
            df = pd.DataFrame(history)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Return only last N days if needed
            if len(df) > days:
                df = df.tail(days)
            
            logger.info(f"✅ Loaded {len(df)} history entries")
            return df
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return pd.DataFrame()


# Global instance
_portfolio = None

def get_portfolio() -> PortfolioTracker:
    """Get or create portfolio tracker"""
    global _portfolio
    if _portfolio is None:
        _portfolio = PortfolioTracker()
    return _portfolio
