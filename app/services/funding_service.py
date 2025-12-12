"""
Funding Service for Sandbox Account Management
Manages account funding, balance tracking, and portfolio allocation
In sandbox mode, no bank account information is required
"""

import logging
import threading
from datetime import datetime
try:
    # Prefer top-level utils when available (development/workspace)
    from utils.time_utils import now_utc_iso  # type: ignore
except Exception:
    try:
        # Fallback to package-local location when running inside container where
        # top-level `utils` may not be on sys.path
        from app.utils.time_utils import now_utc_iso  # type: ignore
    except Exception:
        # Last-resort local implementation
        from datetime import datetime, timezone

        def now_utc_iso() -> str:  # type: ignore
            return datetime.now(timezone.utc).isoformat()
from typing import Dict, Optional, List
import json
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class FundingService:
    """
    Manages sandbox account funding and portfolio capital allocation
    """
    
    def __init__(self, data_file: Path = None):
        """Initialize funding service"""
        self.funding_history: List[Dict] = []
        self.current_balance = 0.0
        self.portfolio_allocation = 0.0
        self.reserved = 0.0  # funds reserved for pending orders
        # Persistence setup
        self.data_file = data_file or (Path(__file__).parent.parent / "data" / "funding.json")
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        # Load persisted state if present
        self._load_state()

        # Persistent pending trades queue (survives restarts)
        self.pending_trades = getattr(self, 'pending_trades', [])
        self._pending_lock = threading.Lock()

        # Callbacks when funds are added (listeners receive (amount, summary) args)
        self._on_funds_added_list = []
        # Last reconcile audit result (cached)
        self._last_reconcile_audit = None

        logger.info("✅ Funding Service initialized")

    def add_funds(self, amount: float, source: str = "Direct Transfer") -> bool:
        """
        Add funds to sandbox account (no bank info required)
        
        Args:
            amount: Amount to add in USD
            source: Source description (default: "Direct Transfer")
            
        Returns:
            True if successful
        """
        try:
            # Debug previously printed to help investigate test race conditions; removed in final commit
            if amount <= 0:
                logger.warning(f"⚠️ Invalid amount: ${amount:.2f}")
                return False
            
            self.current_balance += amount
            pass
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "DEPOSIT",
                "amount": amount,
                "source": source,
                "balance_after": self.current_balance
            }
            
            self.funding_history.append(transaction)
            logger.info(f"✅ Funds added: ${amount:,.2f} | New balance: ${self.current_balance:,.2f}")
            self._save_state()

            # Notify listeners (Background Trader etc.)
            try:
                summary = self.get_balance_summary()
                for cb in list(self._on_funds_added_list):
                    try:
                        cb(amount, summary)
                    except Exception:
                        # Don't crash the funding service if a listener fails
                        logger.warning("⚠️ FundingService funds added listener raised an exception")
            except Exception:
                logger.warning("⚠️ Error notifying funds added listeners")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding funds: {e}")
            return False

    def withdraw_funds(self, amount: float) -> bool:
        """
        Withdraw funds from sandbox account
        
        Args:
            amount: Amount to withdraw
            
        Returns:
            True if successful
        """
        try:
            if amount <= 0:
                logger.warning(f"⚠️ Invalid amount: ${amount:.2f}")
                return False
            
            # Prevent withdrawing funds that are allocated to the portfolio
            available_to_withdraw = self.current_balance - self.portfolio_allocation
            if amount > available_to_withdraw:
                logger.warning(f"⚠️ Insufficient unallocated balance. Available: ${available_to_withdraw:,.2f}, Requested: ${amount:,.2f}")
                return False
            
            self.current_balance -= amount
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "WITHDRAWAL",
                "amount": amount,
                "balance_after": self.current_balance
            }
            
            self.funding_history.append(transaction)
            logger.info(f"✅ Funds withdrawn: ${amount:,.2f} | Remaining balance: ${self.current_balance:,.2f}")
            self._save_state()
            # Notify listeners that allocation changed (treat as funds available event)
            try:
                summary = self.get_balance_summary()
                for cb in list(self._on_funds_added_list):
                    try:
                        cb(0.0, summary)
                    except Exception:
                        logger.warning("⚠️ FundingService allocation listener raised an exception")
            except Exception:
                logger.warning("⚠️ Error notifying allocation listeners")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error withdrawing funds: {e}")
            return False

    def allocate_to_portfolio(self, amount: float) -> bool:
        """
        Allocate funds to trading portfolio
        This is the capital available for the autonomous trader to use
        
        Args:
            amount: Amount to allocate for trading
            
        Returns:
            True if successful
        """
        try:
            # Debug print removed
            if amount < 0:
                logger.warning(f"⚠️ Invalid allocation: ${amount:.2f}")
                return False
            
            if amount > self.current_balance:
                logger.warning(f"⚠️ Cannot allocate more than available balance. Available: ${self.current_balance:,.2f}, Requested: ${amount:,.2f}")
                return False
            
            old_allocation = self.portfolio_allocation
            self.portfolio_allocation = amount
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "ALLOCATION",
                "amount": amount,
                "previous_allocation": old_allocation,
                "unallocated_balance": self.current_balance - amount
            }
            
            self.funding_history.append(transaction)
            logger.info(f"✅ Portfolio allocated: ${amount:,.2f} | Available: ${self.current_balance - amount:,.2f}")
            self._save_state()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error allocating funds: {e}")
            return False

    def get_balance_summary(self) -> Dict:
        """Get current balance summary"""
        return {
            "total_balance": self.current_balance,
            "allocated_to_portfolio": self.portfolio_allocation,
            "reserved": self.reserved,
            "unallocated": self.current_balance - self.portfolio_allocation,
            "last_update": now_utc_iso()
        }

    def reload(self) -> Dict:
        """
        Reload funding state from disk (useful after manual resets)
        
        Returns:
            Updated balance summary
        """
        try:
            self._load_state()
            logger.info("✅ Funding service reloaded from disk")
            return self.get_balance_summary()
        except Exception as e:
            logger.error(f"❌ Error reloading funding state: {e}")
            return self.get_balance_summary()

    def reserve_funds(self, amount: float) -> bool:
        """
        Reserve funds for a pending trade. Reservations reduce available allocation
        but do not immediately deduct from total balance until trade is filled.
        """
        try:
            if amount <= 0:
                return False
            available = self.portfolio_allocation - self.reserved
            if amount > available:
                logger.warning(f"⚠️ Not enough available allocated funds to reserve ${amount:,.2f} (available: ${available:,.2f})")
                return False
            self.reserved += amount
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "RESERVE",
                "amount": amount,
                "reserved_after": self.reserved
            }
            self.funding_history.append(transaction)
            logger.info(f"🔒 Reserved ${amount:,.2f} for pending trade | Reserved now: ${self.reserved:,.2f}")
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"❌ Error reserving funds: {e}")
            return False

    def release_reserved(self, amount: float) -> bool:
        """Release previously reserved funds (e.g., when an order fails/canceled)"""
        try:
            if amount <= 0:
                return False
            if amount > self.reserved:
                logger.warning(f"⚠️ Cannot release ${amount:,.2f} - only ${self.reserved:,.2f} reserved")
                return False
            self.reserved -= amount
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "RELEASE",
                "amount": amount,
                "reserved_after": self.reserved
            }
            self.funding_history.append(transaction)
            logger.info(f"🔓 Released ${amount:,.2f} from reserved funds | Reserved now: ${self.reserved:,.2f}")
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"❌ Error releasing reserved funds: {e}")
            return False

    def apply_trade_debit(self, amount: float) -> bool:
        """
        Apply a debit for an executed trade. This reduces both the total balance and
        the portfolio allocation (and reduces reserved if the amount was reserved).
        """
        try:
            if amount <= 0:
                return False
            # Ensure the debit can be applied against the current balance before modifying reserved
            if amount > self.current_balance:
                logger.warning(f"⚠️ Applying trade debit ${amount:,.2f} exceeds total balance ${self.current_balance:,.2f}")
                return False

            # Reduce reserved first if present
            reserved_debit = min(self.reserved, amount)
            self.reserved -= reserved_debit
            remaining = amount - reserved_debit

            self.current_balance -= amount
            # Reduce portfolio allocation accordingly (if allocation > current balance, clamp)
            self.portfolio_allocation = min(self.portfolio_allocation, self.current_balance)

            transaction = {
                "timestamp": now_utc_iso(),
                "type": "TRADE_DEBIT",
                "amount": amount,
                "balance_after": self.current_balance,
                "reserved_after": self.reserved
            }
            self.funding_history.append(transaction)
            logger.info(f"💳 Applied trade debit ${amount:,.2f} | Balance: ${self.current_balance:,.2f}")
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"❌ Error applying trade debit: {e}")
            return False

    def get_funding_history(self, limit: int = 20) -> List[Dict]:
        """Get recent funding history"""
        return self.funding_history[-limit:]

    # ===== Pending trades persistence API =====
    def add_pending_trade(self, trade: Dict) -> None:
        """Add a pending trade to be persisted and retried later."""
        try:
            with self._pending_lock:
                if not hasattr(self, 'pending_trades'):
                    self.pending_trades = []
                # Ensure each pending trade has a unique identifier for safe removal
                if isinstance(trade, dict) and 'id' not in trade:
                    trade = dict(trade)
                    trade['id'] = str(uuid.uuid4())
                self.pending_trades.append(trade)
            self._save_state()
            logger.info(f"🔁 Pending trade added for persistence: {trade.get('symbol')} @ ${trade.get('trade_cost')}")
        except Exception as e:
            logger.warning(f"⚠️ Could not persist pending trade: {e}")

    def pop_pending_trade(self) -> Optional[Dict]:
        """Pop one pending trade from the persisted list (FIFO), return None if empty."""
        try:
            with self._pending_lock:
                if not getattr(self, 'pending_trades', None):
                    return None
                trade = self.pending_trades.pop(0)
            self._save_state()
            return trade
        except Exception as e:
            logger.warning(f"⚠️ Could not pop pending trade: {e}")
            return None

    def get_pending_trades(self) -> List[Dict]:
        """Get a shallow copy of pending trades persisted."""
        try:
            with self._pending_lock:
                return list(getattr(self, 'pending_trades', []))
        except Exception:
            return []

    def clear_pending_trades(self) -> None:
        """Clear all persisted pending trades."""
        try:
            with self._pending_lock:
                self.pending_trades = []
            self._save_state()
        except Exception:
            pass

    def remove_pending_trade_by_id(self, trade_id: str) -> bool:
        """Remove a persisted pending trade by its generated id"""
        try:
            with self._pending_lock:
                if not getattr(self, 'pending_trades', None):
                    return False
                for i, t in enumerate(list(self.pending_trades)):
                    if t.get('id') == trade_id:
                        self.pending_trades.pop(i)
                        self._save_state()
                        return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ Could not remove pending trade by id: {e}")
            return False

    def reset_balance(self, initial_amount: float = 0.0) -> bool:
        """
        Reset account balance (for testing)
        
        Args:
            initial_amount: New starting balance
            
        Returns:
            True if successful
        """
        try:
            self.current_balance = initial_amount
            self.portfolio_allocation = 0.0
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "RESET",
                "amount": initial_amount,
                "reason": "Account reset"
            }
            
            self.funding_history.append(transaction)
            
            logger.info(f"✅ Account reset to ${initial_amount:,.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error resetting account: {e}")
            return False

    def sync_with_trader_portfolio_size(self, portfolio_size: float) -> None:
        """
        Sync portfolio allocation with trader's portfolio size setting
        This ensures the trader only has access to the configured portfolio size
        """
        try:
            if portfolio_size <= 0:
                return
            self.portfolio_allocation = min(self.current_balance, portfolio_size)
            self._save_state()
        except Exception:
            pass

    # Persistence helpers
    def _load_state(self) -> None:
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.current_balance = float(data.get('current_balance', self.current_balance))
                    self.portfolio_allocation = float(data.get('portfolio_allocation', self.portfolio_allocation))
                    self.reserved = float(data.get('reserved', self.reserved))
                    self.funding_history = data.get('funding_history', list(self.funding_history))
                    self.pending_trades = data.get('pending_trades', list(getattr(self, 'pending_trades', [])))
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            data = {
                'current_balance': self.current_balance,
                'portfolio_allocation': self.portfolio_allocation,
                'reserved': self.reserved,
                'funding_history': self.funding_history,
                'pending_trades': getattr(self, 'pending_trades', [])
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    # Callbacks registration
    def register_on_funds_added(self, cb):
        try:
            if callable(cb):
                self._on_funds_added_list.append(cb)
        except Exception:
            pass

    def deregister_on_funds_added(self, cb):
        try:
            if cb in self._on_funds_added_list:
                self._on_funds_added_list.remove(cb)
        except Exception:
            pass
"""
Funding Service for Sandbox Account Management
Manages account funding, balance tracking, and portfolio allocation
In sandbox mode, no bank account information is required
"""

import logging
import threading
from datetime import datetime
from utils.time_utils import now_utc_iso
from typing import Dict, Optional, List
import json
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class FundingService:
    """
    Manages sandbox account funding and portfolio capital allocation
    """
    
    def __init__(self, data_file: Path = None):
        """Initialize funding service"""
        self.funding_history: List[Dict] = []
        self.current_balance = 0.0
        self.portfolio_allocation = 0.0
        self.reserved = 0.0  # funds reserved for pending orders
        # Persistence setup
        self.data_file = data_file or (Path(__file__).parent.parent / "data" / "funding.json")
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        # Load persisted state if present
        self._load_state()

        # Persistent pending trades queue (survives restarts)
        self.pending_trades = getattr(self, 'pending_trades', [])
        self._pending_lock = threading.Lock()

        # Callbacks when funds are added (listeners receive (amount, summary) args)
        self._on_funds_added_list = []
        # Last reconcile audit result (cached)
        self._last_reconcile_audit = None

        logger.info("✅ Funding Service initialized")
    
    def add_funds(self, amount: float, source: str = "Direct Transfer") -> bool:
        """
        Add funds to sandbox account (no bank info required)
        
        Args:
            amount: Amount to add in USD
            source: Source description (default: "Direct Transfer")
            
        Returns:
            True if successful
        """
        try:
            # Debug previously printed to help investigate test race conditions; removed in final commit
            if amount <= 0:
                logger.warning(f"⚠️ Invalid amount: ${amount:.2f}")
                return False
            
            self.current_balance += amount
            pass
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "DEPOSIT",
                "amount": amount,
                "source": source,
                "balance_after": self.current_balance
            }
            
            self.funding_history.append(transaction)
            logger.info(f"✅ Funds added: ${amount:,.2f} | New balance: ${self.current_balance:,.2f}")
            self._save_state()

            # Notify listeners (Background Trader etc.)
            try:
                summary = self.get_balance_summary()
                for cb in list(self._on_funds_added_list):
                    try:
                        cb(amount, summary)
                    except Exception:
                        # Don't crash the funding service if a listener fails
                        logger.warning("⚠️ FundingService funds added listener raised an exception")
            except Exception:
                logger.warning("⚠️ Error notifying funds added listeners")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding funds: {e}")
            return False
    
    def withdraw_funds(self, amount: float) -> bool:
        """
        Withdraw funds from sandbox account
        
        Args:
            amount: Amount to withdraw
            
        Returns:
            True if successful
        """
        try:
            if amount <= 0:
                logger.warning(f"⚠️ Invalid amount: ${amount:.2f}")
                return False
            
            # Prevent withdrawing funds that are allocated to the portfolio
            available_to_withdraw = self.current_balance - self.portfolio_allocation
            if amount > available_to_withdraw:
                logger.warning(f"⚠️ Insufficient unallocated balance. Available: ${available_to_withdraw:,.2f}, Requested: ${amount:,.2f}")
                return False
            
            self.current_balance -= amount
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "WITHDRAWAL",
                "amount": amount,
                "balance_after": self.current_balance
            }
            
            self.funding_history.append(transaction)
            logger.info(f"✅ Funds withdrawn: ${amount:,.2f} | Remaining balance: ${self.current_balance:,.2f}")
            self._save_state()
            # Notify listeners that allocation changed (treat as funds available event)
            try:
                summary = self.get_balance_summary()
                for cb in list(self._on_funds_added_list):
                    try:
                        cb(0.0, summary)
                    except Exception:
                        logger.warning("⚠️ FundingService allocation listener raised an exception")
            except Exception:
                logger.warning("⚠️ Error notifying allocation listeners")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error withdrawing funds: {e}")
            return False
    
    def allocate_to_portfolio(self, amount: float) -> bool:
        """
        Allocate funds to trading portfolio
        This is the capital available for the autonomous trader to use
        
        Args:
            amount: Amount to allocate for trading
            
        Returns:
            True if successful
        """
        try:
            # Debug print removed
            if amount < 0:
                logger.warning(f"⚠️ Invalid allocation: ${amount:.2f}")
                return False
            
            if amount > self.current_balance:
                logger.warning(f"⚠️ Cannot allocate more than available balance. Available: ${self.current_balance:,.2f}, Requested: ${amount:,.2f}")
                return False
            
            old_allocation = self.portfolio_allocation
            self.portfolio_allocation = amount
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "ALLOCATION",
                "amount": amount,
                "previous_allocation": old_allocation,
                "unallocated_balance": self.current_balance - amount
            }
            
            self.funding_history.append(transaction)
            logger.info(f"✅ Portfolio allocated: ${amount:,.2f} | Available: ${self.current_balance - amount:,.2f}")
            self._save_state()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error allocating funds: {e}")
            return False
    
    def get_balance_summary(self) -> Dict:
        """Get current balance summary"""
        return {
            "total_balance": self.current_balance,
            "allocated_to_portfolio": self.portfolio_allocation,
            "reserved": self.reserved,
            "unallocated": self.current_balance - self.portfolio_allocation,
            "last_update": now_utc_iso()
        }

    def reload(self) -> Dict:
        """
        Reload funding state from disk (useful after manual resets)
        
        Returns:
            Updated balance summary
        """
        try:
            self._load_state()
            logger.info("✅ Funding service reloaded from disk")
            return self.get_balance_summary()
        except Exception as e:
            logger.error(f"❌ Error reloading funding state: {e}")
            return self.get_balance_summary()

    def reserve_funds(self, amount: float) -> bool:
        """
        Reserve funds for a pending trade. Reservations reduce available allocation
        but do not immediately deduct from total balance until trade is filled.
        """
        try:
            if amount <= 0:
                return False
            available = self.portfolio_allocation - self.reserved
            if amount > available:
                logger.warning(f"⚠️ Not enough available allocated funds to reserve ${amount:,.2f} (available: ${available:,.2f})")
                return False
            self.reserved += amount
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "RESERVE",
                "amount": amount,
                "reserved_after": self.reserved
            }
            self.funding_history.append(transaction)
            logger.info(f"🔒 Reserved ${amount:,.2f} for pending trade | Reserved now: ${self.reserved:,.2f}")
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"❌ Error reserving funds: {e}")
            return False

    def release_reserved(self, amount: float) -> bool:
        """Release previously reserved funds (e.g., when an order fails/canceled)"""
        try:
            if amount <= 0:
                return False
            if amount > self.reserved:
                logger.warning(f"⚠️ Cannot release ${amount:,.2f} - only ${self.reserved:,.2f} reserved")
                return False
            self.reserved -= amount
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "RELEASE",
                "amount": amount,
                "reserved_after": self.reserved
            }
            self.funding_history.append(transaction)
            logger.info(f"🔓 Released ${amount:,.2f} from reserved funds | Reserved now: ${self.reserved:,.2f}")
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"❌ Error releasing reserved funds: {e}")
            return False

    def apply_trade_debit(self, amount: float) -> bool:
        """
        Apply a debit for an executed trade. This reduces both the total balance and
        the portfolio allocation (and reduces reserved if the amount was reserved).
        """
        try:
            if amount <= 0:
                return False
            # Ensure the debit can be applied against the current balance before modifying reserved
            if amount > self.current_balance:
                logger.warning(f"⚠️ Applying trade debit ${amount:,.2f} exceeds total balance ${self.current_balance:,.2f}")
                return False

            # Reduce reserved first if present
            reserved_debit = min(self.reserved, amount)
            self.reserved -= reserved_debit
            remaining = amount - reserved_debit

            self.current_balance -= amount
            # Reduce portfolio allocation accordingly (if allocation > current balance, clamp)
            self.portfolio_allocation = min(self.portfolio_allocation, self.current_balance)

            transaction = {
                "timestamp": now_utc_iso(),
                "type": "TRADE_DEBIT",
                "amount": amount,
                "balance_after": self.current_balance,
                "reserved_after": self.reserved
            }
            self.funding_history.append(transaction)
            logger.info(f"💳 Applied trade debit ${amount:,.2f} | Balance: ${self.current_balance:,.2f}")
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"❌ Error applying trade debit: {e}")
            return False
    
    def get_funding_history(self, limit: int = 20) -> List[Dict]:
        """Get recent funding history"""
        return self.funding_history[-limit:]

    # ===== Pending trades persistence API =====
    def add_pending_trade(self, trade: Dict) -> None:
        """Add a pending trade to be persisted and retried later."""
        try:
            with self._pending_lock:
                if not hasattr(self, 'pending_trades'):
                    self.pending_trades = []
                # Ensure each pending trade has a unique identifier for safe removal
                if isinstance(trade, dict) and 'id' not in trade:
                    trade = dict(trade)
                    trade['id'] = str(uuid.uuid4())
                self.pending_trades.append(trade)
            self._save_state()
            logger.info(f"🔁 Pending trade added for persistence: {trade.get('symbol')} @ ${trade.get('trade_cost')}")
        except Exception as e:
            logger.warning(f"⚠️ Could not persist pending trade: {e}")

    def pop_pending_trade(self) -> Optional[Dict]:
        """Pop one pending trade from the persisted list (FIFO), return None if empty."""
        try:
            with self._pending_lock:
                if not getattr(self, 'pending_trades', None):
                    return None
                trade = self.pending_trades.pop(0)
            self._save_state()
            return trade
        except Exception as e:
            logger.warning(f"⚠️ Could not pop pending trade: {e}")
            return None

    def get_pending_trades(self) -> List[Dict]:
        """Get a shallow copy of pending trades persisted."""
        try:
            with self._pending_lock:
                return list(getattr(self, 'pending_trades', []))
        except Exception:
            return []

    def clear_pending_trades(self) -> None:
        """Clear all persisted pending trades."""
        try:
            with self._pending_lock:
                self.pending_trades = []
            self._save_state()
        except Exception:
            pass

    def remove_pending_trade_by_id(self, trade_id: str) -> bool:
        """Remove a persisted pending trade by its generated id"""
        try:
            with self._pending_lock:
                if not getattr(self, 'pending_trades', None):
                    return False
                for i, t in enumerate(list(self.pending_trades)):
                    if t.get('id') == trade_id:
                        self.pending_trades.pop(i)
                        self._save_state()
                        return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ Could not remove pending trade by id: {e}")
            return False
    
    def reset_balance(self, initial_amount: float = 0.0) -> bool:
        """
        Reset account balance (for testing)
        
        Args:
            initial_amount: New starting balance
            
        Returns:
            True if successful
        """
        try:
            self.current_balance = initial_amount
            self.portfolio_allocation = 0.0
            
            transaction = {
                "timestamp": now_utc_iso(),
                "type": "RESET",
                "amount": initial_amount,
                "reason": "Account reset"
            }
            
            self.funding_history.append(transaction)
            
            logger.info(f"✅ Account reset to ${initial_amount:,.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error resetting account: {e}")
            return False
    
    def sync_with_trader_portfolio_size(self, portfolio_size: float) -> None:
        """
        Sync portfolio allocation with trader's portfolio size setting
        This ensures the trader only has access to the configured portfolio size
        
        Args:
            portfolio_size: Portfolio size from settings (trader's capital allocation)
        """
        try:
            # Ensure portfolio allocation doesn't exceed available balance
            if portfolio_size > self.current_balance:
                logger.warning(
                    f"⚠️ Portfolio size (${portfolio_size:,.2f}) exceeds available balance (${self.current_balance:,.2f}). "
                    f"Allocating all available funds."
                )
                self.portfolio_allocation = self.current_balance
            else:
                self.portfolio_allocation = portfolio_size
            
            logger.info(
                f"✅ Portfolio synced: ${portfolio_size:,.2f} allocated for trading | "
                f"${self.current_balance - portfolio_size:,.2f} unallocated"
            )
            
        except Exception as e:
            logger.error(f"❌ Error syncing portfolio: {e}")

    def _load_state(self) -> None:
        """Load funding state from disk if available"""
        try:
            if hasattr(self, 'data_file') and self.data_file.exists():
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                self.current_balance = float(data.get('current_balance', self.current_balance))
                self.portfolio_allocation = float(data.get('portfolio_allocation', self.portfolio_allocation))
                self.reserved = float(data.get('reserved', self.reserved))
                self.funding_history = data.get('funding_history', self.funding_history)
                # Load persisted pending trades if present
                self.pending_trades = data.get('pending_trades', getattr(self, 'pending_trades', []))
                logger.info(f"✅ Funding state loaded from {self.data_file}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load funding state: {e}")

    def _save_state(self) -> None:
        """Persist funding state to disk (atomic write)"""
        try:
            data = {
                'current_balance': self.current_balance,
                'portfolio_allocation': self.portfolio_allocation,
                'reserved': self.reserved,
                'funding_history': self.funding_history[-200:],
                'pending_trades': list(getattr(self, 'pending_trades', []))
            }
            # Ensure parent directory exists (defensive - tests may pass custom tmp files)
            try:
                self.data_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                # Best-effort: continue and let file operations report detailed errors
                pass

            # Use a NamedTemporaryFile in the same directory for a safer atomic write
            try:
                import tempfile, os
                dirpath = str(self.data_file.parent)
                with tempfile.NamedTemporaryFile('w', delete=False, dir=dirpath, suffix='.tmp') as tf:
                    json.dump(data, tf)
                    try:
                        tf.flush()
                        os.fsync(tf.fileno())
                    except Exception:
                        pass
                    tmpname = tf.name

                # Move into place
                try:
                    os.replace(tmpname, str(self.data_file))
                except Exception as e:
                    logger.error(f"❌ Failed to atomically replace tmp with data file: {e}")
                    # Cleanup temp file if still exists
                    try:
                        if os.path.exists(tmpname):
                            os.remove(tmpname)
                    except Exception:
                        pass
                    raise
            except Exception:
                # Let outer except catch and log
                raise
            # Also create a timestamped backup copy
            try:
                backups_dir = self.data_file.parent / 'backups'
                backups_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d-%H%M%S')
                backup_file = backups_dir / f'funding-{ts}.json'
                with open(backup_file, 'w') as bf:
                    json.dump(data, bf)
                logger.info(f"✅ Funding backup saved to {backup_file}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to write funding backup: {e}")
            logger.info(f"✅ Funding state saved to {self.data_file}")
        except Exception as e:
            logger.error(f"❌ Failed to save funding state: {e}")

    def reconcile_with_etrade(self, etrade_service=None, account_id: Optional[str] = None, sandbox_mode: bool = False) -> tuple:
        """Perform a reconciliation audit against E*TRADE (or provided brokerage service). Returns (ok, audit_dict).

        audit_dict includes: broker_balance, local_balance, delta, timestamp
        """
        try:
            if not etrade_service:
                return False, {"message": "No etrade service provided"}

            # Query broker for account balance (prefers cash, falls back to buying_power)
            try:
                acct = etrade_service.get_account_balance(account_id) if hasattr(etrade_service, 'get_account_balance') else None
                broker_balance = 0.0
                if acct:
                    broker_balance = float(acct.get('cash') or acct.get('buying_power') or 0.0)
            except Exception as e:
                return False, {"message": f"Failed to get broker account: {e}"}

            audit = {
                'timestamp': now_utc_iso(),
                'broker_balance': float(broker_balance),
                'local_balance': float(self.current_balance),
                'delta': float(broker_balance - float(self.current_balance))
            }
            # Cache last reconcile audit for application
            self._last_reconcile_audit = audit

            # Append an audit entry to funding_history
            entry = {
                'timestamp': audit['timestamp'],
                'type': 'RECONCILE_AUDIT',
                'broker_balance': audit['broker_balance'],
                'local_balance': audit['local_balance'],
                'delta': audit['delta']
            }
            self.funding_history.append(entry)
            self._save_state()
            return True, audit
        except Exception as e:
            logger.error(f"❌ Reconcile failed: {e}")
            return False, {"message": str(e)}

    def apply_reconcile(self) -> tuple:
        """Apply the last reconcile audit to the funding balance. Returns (ok, new_balance|message)."""
        try:
            if not self._last_reconcile_audit:
                return False, "No reconcile audit available"
            delta = float(self._last_reconcile_audit.get('delta', 0.0))
            if delta == 0.0:
                return True, self.current_balance

            # Apply delta to current_balance (this reflects broker actual balance)
            self.current_balance = float(self.current_balance + delta)
            # Adjust portfolio_allocation if necessary so it doesn't exceed current balance
            self.portfolio_allocation = min(self.portfolio_allocation, self.current_balance)

            entry = {
                'timestamp': now_utc_iso(),
                'type': 'RECONCILE_APPLY',
                'applied_delta': delta,
                'balance_after': self.current_balance
            }
            self.funding_history.append(entry)
            # Clear last reconcile audit
            self._last_reconcile_audit = None
            self._save_state()
            return True, self.current_balance
        except Exception as e:
            logger.error(f"❌ Apply reconcile failed: {e}")
            return False, str(e)

    def register_on_funds_added(self, callback) -> None:
        """Register a callback to be called when funds are added. Callback signature: fn(amount, summary)"""
        try:
            if callback not in self._on_funds_added_list:
                self._on_funds_added_list.append(callback)
        except Exception:
            pass

    def deregister_on_funds_added(self, callback) -> None:
        """Deregister a funds-added callback"""
        try:
            if callback in self._on_funds_added_list:
                self._on_funds_added_list.remove(callback)
        except Exception:
            pass

    def export_state(self) -> Dict:
        """Return an exportable copy of the current funding state"""
        return {
            'current_balance': self.current_balance,
            'portfolio_allocation': self.portfolio_allocation,
            'reserved': self.reserved,
            'funding_history': list(self.funding_history)
            , 'pending_trades': list(getattr(self, 'pending_trades', []))
        }

    def ensure_initialized(self, amount: float = 0.0, source: str = "Initialize Sandbox Balance") -> bool:
        """Ensure initial funding is present; if current balance is zero, add amount. Returns True if added or already initialized."""
        try:
            if self.current_balance <= 0 and amount > 0:
                return self.add_funds(amount, source=source)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Ensure initialized failed: {e}")
            return False

    def import_state(self, data: Dict) -> bool:
        """Import funding state from a dict and persist it"""
        try:
            if not isinstance(data, dict):
                raise ValueError('Imported data must be a dict')
            self.current_balance = float(data.get('current_balance', self.current_balance))
            self.portfolio_allocation = float(data.get('portfolio_allocation', self.portfolio_allocation))
            self.reserved = float(data.get('reserved', self.reserved))
            self.funding_history = data.get('funding_history', list(self.funding_history))
            self._save_state()
            logger.info("✅ Funding state imported successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to import funding state: {e}")
            return False

    def list_backups(self) -> List[str]:
        """List available backup filenames (sorted newest first)"""
        try:
            backups_dir = self.data_file.parent / 'backups'
            if not backups_dir.exists():
                return []
            backups = [p.name for p in backups_dir.iterdir() if p.is_file()]
            backups_sorted = sorted(backups, reverse=True)
            return backups_sorted
        except Exception as e:
            logger.warning(f"⚠️ Could not list backups: {e}")
            return []
    def restore_backup(self, backup_name: str) -> bool:
        """Restore a backup by filename (located in backups directory)"""
        try:
            backups_dir = self.data_file.parent / 'backups'
            bf = backups_dir / backup_name
            if not bf.exists():
                logger.warning(f"⚠️ Backup not found: {bf}")
                return False
            with open(bf, 'r') as f:
                data = json.load(f)
            return self.import_state(data)
        except Exception as e:
            logger.error(f"❌ Failed to restore backup: {e}")
            return False
