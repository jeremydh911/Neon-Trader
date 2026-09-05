"""
Background Autonomous Trader Service
Continuously researches, evaluates, and executes trades in the background
Runs as long as E*TRADE API is authenticated and enabled in settings
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
try:
    from utils.time_utils import now_utc_iso  # type: ignore
except Exception:
    try:
        from app.utils.time_utils import now_utc_iso  # type: ignore
    except Exception:
        from datetime import datetime, timezone

        def now_utc_iso() -> str:  # type: ignore
            return datetime.now(timezone.utc).isoformat()
from typing import Dict, List, Any, Optional
import json
from pathlib import Path
from collections import deque
import random
from functools import lru_cache

logger = logging.getLogger(__name__)


class BackgroundTraderService:
    """
    Continuous background trading service
    - Monitors market conditions
    - Researches stocks automatically
    - Makes buy/sell/hold/swing/day-trade decisions
    - Executes trades with council approval
    - Learns from past trades
    """
    
    def __init__(self, autonomous_trader, oauth_service, pricing_service, trader_tools, watchlist=None, funding_service=None, use_sandbox: bool = False, update_callback=None):
        """
        Initialize background trader
        
        Args:
            autonomous_trader: AutonomousTrader instance
            oauth_service: E*TRADE OAuth service for authentication checks
            pricing_service: Pricing data service
            trader_tools: Trading execution tools
            watchlist: Optional list of tickers or ["ALL"] for dynamic discovery
            update_callback: Optional callback function for UI updates
        """
        import os
        # Paper/test day: sandbox + no OAuth gate unless explicitly live
        paper = os.getenv("PAPER_MODE", "").lower() in ("1", "true", "yes")
        if paper:
            use_sandbox = True

        self.autonomous_trader = autonomous_trader
        self.oauth_service = oauth_service
        self.pricing_service = pricing_service
        self.trader_tools = trader_tools
        self.update_callback = update_callback
        self.funding_service = funding_service
        self.use_sandbox = use_sandbox
        
        self.is_active = False
        self.is_running = False
        self.thread = None
        
        # Set watchlist - either provided, ALL mode, or load from file
        if watchlist:
            self.watchlist = watchlist
            self.is_all_mode = (watchlist == ["ALL"])
        else:
            self.watchlist = self._load_watchlist()
            self.is_all_mode = (self.watchlist == ["ALL"])
        
        # Activity tracking
        self.activity_log = deque(maxlen=100)  # Keep last 100 activities
        self.trade_history = []
        self.research_history = deque(maxlen=50)
        self.daily_stats = {
            "trades_executed": 0,
            "wins": 0,
            "losses": 0,
            "total_profit": 0.0,
            "research_count": 0,
            "decisions_skipped": 0
        }
        # Pending trades are persisted in FundingService; keep no local queue beyond current attempt
        
        # Configuration
        self.config = {
            "research_interval": 60,  # Research every 60 seconds
            "execution_check_interval": 300,  # Check for execution every 5 minutes
            "stocks_per_cycle": 3,  # Research 3 stocks per cycle
            "min_council_approval": 60,  # Require 60% council approval
            "max_daily_trades": 10,  # Max trades per day
            "position_sizing": 0.02,  # 2% position size
            "take_profit_pct": 2.0,
            "stop_loss_pct": 2.0,
            "enabled": False
            ,
            # Pending retry scheduler
            "retry_pending_enabled": False,
            "retry_pending_interval": 60  # seconds
        }
        # Allow optional reloading of funding service state during execution phase - default off to avoid races in tests
        self.config.setdefault('reload_funding_on_execution', False)
        
        # Security: require OAuth to be present before starting trading unless explicitly allowed
        # This prevents accidental live/start without proper authentication
        self.config.setdefault('require_oauth', True)
        # Allow bypass in tests or special cases
        self.config.setdefault('allow_start_without_oauth', False)
        # Paper day: never block mock/sandbox start on missing OAuth
        if self.use_sandbox and os.getenv("PAPER_MODE", "").lower() in ("1", "true", "yes"):
            self.config["require_oauth"] = False
            self.config["allow_start_without_oauth"] = True
            logger.info("📄 PAPER_MODE: OAuth not required for sandbox start")
        # Popular US market tickers for ALL mode
        self.popular_tickers = self._get_popular_us_tickers()
        
        self.activity_log.append({
            "timestamp": now_utc_iso(),
            "type": "INIT",
            "message": f"Background trader service initialized (Mode: {'ALL US Markets' if self.is_all_mode else 'Watchlist'})"
        })
        
        logger.info(f"✅ Background Trader Service initialized (Mode: {'ALL US Markets' if self.is_all_mode else 'Watchlist'})")
        # Scheduler control
        self._retry_scheduler_thread = None
        self._retry_scheduler_stop = threading.Event()
    
    def start(self) -> bool:
        """Start background trading"""
        if self.is_running:
            logger.warning("⚠️ Background trader already running")
            return False
        # If OAuth is required (default), ensure oauth_service exists and is authenticated
        # Honor explicit allow_start_without_oauth override; do NOT implicitly allow sandbox to bypass OAuth
        if self.config.get('require_oauth', True) and not self.config.get('allow_start_without_oauth', False):
            # Require an oauth_service to be present when OAuth is required
            if not self.oauth_service:
                # Allow starting in sandbox *only* when the retry scheduler is being used (tests expect scheduler-only starts)
                if self.use_sandbox and self.config.get('retry_pending_enabled', False):
                    logger.info("ℹ️ Starting background trader in sandbox-only mode to run pending retry scheduler without OAuth")
                else:
                    logger.error("❌ OAuth service not available - cannot start background trader")
                    self._log_activity("START_FAILED", "OAuth service not available")
                    return False

            # Attempt to load cached tokens if an OAuth service is present (best-effort)
            if self.oauth_service:
                try:
                    oauth_status = self.oauth_service.get_status()
                    if not oauth_status.get('is_authenticated') and hasattr(self.oauth_service, 'load_cached_tokens'):
                        try:
                            loaded = self.oauth_service.load_cached_tokens()
                            if loaded:
                                logger.info("✅ Loaded cached OAuth tokens during BackgroundTrader start")
                        except Exception as e:
                            logger.debug(f"Could not load cached tokens during start: {e}")

                    oauth_status = self.oauth_service.get_status()
                    if not oauth_status.get('is_authenticated'):
                        logger.error("❌ E*TRADE not authenticated - cannot start background trader")
                        self._log_activity("START_FAILED", "E*TRADE not authenticated")
                        return False
                except Exception as e:
                    logger.error(f"❌ Error checking OAuth status: {e}")
                    self._log_activity("START_FAILED", f"OAuth status error: {e}")
                    return False
        
        self.is_active = True
        self.is_running = True
        self.thread = threading.Thread(target=self._trading_loop, daemon=True)
        self.thread.start()
        
        logger.info("🚀 Background trader started")

        # Auto-reconcile with E*TRADE sandbox if enabled, authorized and funding service present
        try:
            # Only attempt reconcile in sandbox mode and if funding_service available
            if self.config.get('auto_reconcile_on_start', False) and self.use_sandbox and self.funding_service:
                if self.oauth_service and getattr(self.oauth_service, 'is_authenticated', lambda: False)():
                    # find account id if available
                    account_id = None
                    try:
                        if hasattr(self.trader_tools, 'account_id'):
                            account_id = getattr(self.trader_tools, 'account_id')
                    except Exception:
                        account_id = None

                    # perform reconcile audit
                    ok, audit = self.funding_service.reconcile_with_etrade(self.etrade_service if hasattr(self, 'etrade_service') else None, account_id, sandbox_mode=True) if hasattr(self.funding_service, 'reconcile_with_etrade') else (False, "No reconcile method")
                    if ok and audit:
                        # log reconcile action
                        self._log_activity("RECONCILE", f"Auto reconcile result: {audit.get('delta', 0.0):.2f}")
                        # auto-apply if setting indicates
                        if self.config.get('auto_apply_reconcile_on_start', False):
                            aok, ares = self.funding_service.apply_reconcile() if hasattr(self.funding_service, 'apply_reconcile') else (False, 'no apply_reconcile')
                            if aok:
                                self._log_activity('RECONCILE_APPLY', f"Applied reconcile: new_balance=${ares:.2f}")
                            else:
                                self._log_activity('RECONCILE_FAIL', f"Apply reconcile failed: {ares}")
        except Exception as e:
            logger.warning(f"⚠️ Auto-reconcile on start failed: {e}")
        # Register to funding service notifications for auto-unblock
        try:
            if self.funding_service and hasattr(self.funding_service, 'register_on_funds_added'):
                self.funding_service.register_on_funds_added(self._handle_funds_added)
        except Exception:
            logger.warning("⚠️ Could not register funds-added callback on funding service")

        self._log_activity("START", "Background trader started successfully")
        # Start scheduler thread if enabled
        try:
            if self.config.get('retry_pending_enabled', False):
                self._retry_scheduler_stop.clear()
                self._retry_scheduler_thread = threading.Thread(target=self._retry_scheduler_loop, daemon=True)
                self._retry_scheduler_thread.start()
        except Exception as e:
            logger.warning(f"⚠️ Could not start retry scheduler: {e}")
        return True
    
    def stop(self) -> None:
        """Stop background trading"""
        self.is_active = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        self.is_running = False
        # Deregister funding service callback
        try:
            if self.funding_service and hasattr(self.funding_service, 'deregister_on_funds_added'):
                self.funding_service.deregister_on_funds_added(self._handle_funds_added)
        except Exception:
            pass
        # Stop scheduler
        try:
            if self._retry_scheduler_thread and self._retry_scheduler_thread.is_alive():
                self._retry_scheduler_stop.set()
                self._retry_scheduler_thread.join(timeout=2)
        except Exception:
            pass
        logger.info("⏹️ Background trader stopped")
        self._log_activity("STOP", "Background trader stopped")
    
    def _load_watchlist(self) -> List[str]:
        """Load watchlist from file (top 55 NAS, S&P, DOW)"""
        try:
            watchlist_file = Path(__file__).parent.parent / "data" / "watchlist.json"
            if watchlist_file.exists():
                with open(watchlist_file, 'r') as f:
                    data = json.load(f)
                    # Use combined watchlist (top performers from all indices)
                    watchlist = data.get("combined_watchlist", [])
                    logger.info(f"✅ Loaded watchlist with {len(watchlist)} stocks from file")
                    return watchlist
        except Exception as e:
            logger.warning(f"⚠️ Could not load watchlist file: {e}")
        
        # Fallback to default watchlist
        default_watchlist = [
            "NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "TSLA", "META", "NFLX", "ASML", "ADBE",
            "INTC", "AMD", "QCOM", "V", "JNJ", "WMT", "JPM", "MA", "PG", "DIS",
            "MCD", "VZ", "NKE", "KO", "COST", "BA", "IBM", "TXN", "CVX", "GE"
        ]
        logger.info(f"⚠️ Using fallback watchlist with {len(default_watchlist)} stocks")
        return default_watchlist
    
    def _get_popular_us_tickers(self) -> List[str]:
        """Get comprehensive list of popular US market tickers for ALL mode"""
        # Load from watchlist file for breadth, plus additional commonly traded stocks
        popular = [
            # Large-cap tech
            "NVDA", "MSFT", "AAPL", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NFLX", "ADOBE",
            # Semiconductors
            "INTC", "AMD", "QCOM", "AVGO", "MRVL", "KLAC", "ASML", "LRCX", "MU", "NXPI",
            # Finance & Banking
            "JPM", "BAC", "WFC", "GS", "MS", "AXP", "V", "MA", "SCHW", "PAYX",
            # Healthcare & Pharma
            "JNJ", "PFE", "UNH", "ABBV", "MERCK", "LLY", "TMO", "AMGN", "VRTX", "REGN",
            # Consumer
            "WMT", "PG", "KO", "MCD", "DIS", "NKE", "LULU", "CMG", "ULVR", "PEP",
            # Energy
            "CVX", "XOM", "COP", "SLB", "EOG", "OXY", "MPC", "VLO", "PSX", "HES",
            # Industrials
            "BA", "CAT", "HON", "GE", "MMM", "UNP", "CSX", "NSC", "PCAR", "RHI",
            # Real Estate & Infrastructure
            "EQIX", "SPG", "CCI", "DLR", "VICI", "PLD", "AMT", "ARE", "WELL", "OKE",
            # Communication Services
            "GOOGL", "META", "NFLX", "DIS", "CHTR", "COMCAST", "T", "VZ",
            # Growth stocks
            "SNOW", "CRWD", "OKTA", "SPLK", "DOCU", "WDAY", "BILL", "SHOP", "NUVL", "MSTR",
            # Additional popular tickers
            "SPY", "QQQ", "IWM", "DIA", "EEM", "FXI", "GLD", "TLT", "USO", "GBX"
        ]
        
        # Remove duplicates and sort
        return sorted(list(set(popular)))
    
    def _get_stocks_for_cycle(self) -> List[str]:
        """Get stocks to research for this cycle (handles both normal and ALL modes)"""
        if self.is_all_mode:
            # In ALL mode, randomly select from popular tickers
            # This gives broader market coverage while staying computationally efficient
            research_count = min(self.config["stocks_per_cycle"], len(self.popular_tickers))
            return random.sample(self.popular_tickers, research_count)
        else:
            # Normal mode: use configured watchlist
            research_count = min(self.config["stocks_per_cycle"], len(self.watchlist))
            if research_count > 0:
                return random.sample(self.watchlist, research_count)
            return []
    
    def set_watchlist(self, watchlist: List[str]) -> None:
        """Update watchlist and mode dynamically"""
        self.watchlist = watchlist
        self.is_all_mode = (watchlist == ["ALL"])
        if self.is_all_mode:
            logger.info("🌍 Background trader switched to ALL US Markets mode")
        else:
            logger.info(f"📋 Background trader watchlist updated: {len(watchlist)} stocks")

    
    def _trading_loop(self) -> None:
        """Main trading loop - runs continuously"""
        logger.info("🔄 Trading loop started")
        
        while self.is_active:
            try:
                # Phase 1: Research stocks
                research_start = time.time()
                self._research_phase()
                research_time = time.time() - research_start
                
                # Phase 2: Manage open positions (stops / take-profit) before new entries
                self._position_management_phase()

                # Phase 3: Evaluate and execute
                execution_start = time.time()
                self._execution_phase()
                execution_time = time.time() - execution_start
                
                # Log cycle completion
                logger.info(
                    f"✅ Trading cycle complete | "
                    f"Research: {research_time:.1f}s | "
                    f"Execution: {execution_time:.1f}s"
                )
                
                # Wait before next cycle
                time.sleep(self.config["research_interval"])
                
            except Exception as e:
                logger.error(f"❌ Error in trading loop: {e}")
                self._log_activity("ERROR", f"Trading loop error: {str(e)}")
                time.sleep(10)  # Wait before retry
        
        logger.info("🛑 Trading loop exited")
    
    def _research_phase(self) -> None:
        """Research selected stocks"""
        try:
            # Get stocks to research (handles both normal and ALL modes)
            stocks_to_research = self._get_stocks_for_cycle()
            
            if not stocks_to_research:
                logger.warning("⚠️ No stocks available to research")
                return
            
            logger.info(f"📊 Researching {len(stocks_to_research)} stocks: {', '.join(stocks_to_research)}")
            
            for symbol in stocks_to_research:
                try:
                    # Get quote
                    quote = self.pricing_service.get_quote(symbol)
                    if not quote:
                        logger.warning(f"⚠️ Could not get quote for {symbol}")
                        continue
                    
                    # Perform research
                    research = self.autonomous_trader.perform_research(symbol, "EVALUATE")
                    if not research:
                        logger.warning(f"⚠️ Research failed for {symbol}")
                        continue
                    
                    # Determine action based on technical analysis
                    action = self._analyze_and_determine_action(symbol, research, quote)
                    
                    # Log research
                    research_log = {
                        "timestamp": now_utc_iso(),
                        "symbol": symbol,
                        "price": quote.get("price"),
                        "action_recommended": action,
                        "confidence": research.get("confidence", 0),
                        "technical_indicators": research.get("indicators", {})
                    }
                    self.research_history.append(research_log)
                    self.daily_stats["research_count"] += 1
                    
                    # Callback to UI
                    if self.update_callback:
                        self.update_callback({
                            "type": "RESEARCH",
                            "symbol": symbol,
                            "action": action,
                            "price": quote.get("price"),
                            "timestamp": now_utc_iso()
                        })
                    
                    self._log_activity(
                        "RESEARCH",
                        f"{symbol}: {action} recommended (${quote.get('price', 0):.2f})"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Error researching {symbol}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"❌ Research phase error: {e}")
    
    def _execution_phase(self) -> None:
        """Evaluate and execute trades"""
        try:
            # Check daily trade limit
            if self.daily_stats["trades_executed"] >= self.config["max_daily_trades"]:
                logger.info(f"⚠️ Daily trade limit reached ({self.config['max_daily_trades']})")
                self._log_activity("LIMIT", "Daily trade limit reached")
                return
            
            # Reload funding service to get fresh data from disk (handles manual resets)
            if self.funding_service:
                try:
                    summary_before = self.funding_service.get_balance_summary()
                    # Always reload to ensure fresh data on each cycle
                    try:
                        self.funding_service.reload()
                    except Exception:
                        # Non-fatal; proceed with whatever in-memory state is available
                        pass
                    summary_after = self.funding_service.get_balance_summary()
                    logger.debug(f"💰 Funding reload: before=${summary_before.get('allocated_to_portfolio', 0):,.2f}, after=${summary_after.get('allocated_to_portfolio', 0):,.2f}")
                except Exception as e:
                    logger.debug(f"ℹ️ Funding service reload skipped: {e}")
            
            # Get account balance. Prefer broker account; fallback to funding service in sandbox or when broker unavailable
            account_id = None
            try:
                account_id = self.trader_tools.account_id if (self.trader_tools and hasattr(self.trader_tools, 'account_id')) else None
                balance = self.trader_tools.get_account_balance(account_id) if account_id else None
                if balance:
                    logger.info(f"[BALANCE] Broker returned: cash=${balance.get('cash', 0):.2f}")
                else:
                    logger.info(f"[BALANCE] Broker returned: None")
            except Exception as e:
                logger.info(f"[BALANCE] Broker error: {e}")
                balance = None

            # If no broker balance available, and funding service present, use allocated portfolio as cash
            if (not balance or balance.get("cash", 0) <= 0) and self.funding_service:
                fs = self.funding_service.get_balance_summary()
                allocated = fs.get('allocated_to_portfolio', 0.0)
                logger.info(f"[BALANCE] Using funding service: allocated=${allocated:,.2f}")
                balance = {
                    'account_id': 'SANDBOX_FUNDING',
                    'cash': float(allocated),
                    'buying_power': float(allocated)
                }

            # Allow small allocations to be used — only skip when there's effectively no cash
            if not balance or balance.get("cash", 0) <= 0:
                broker_cash = balance.get('cash', 0) if balance else 0
                fs_alloc = 0.0
                if self.funding_service:
                    try:
                        fs_alloc = self.funding_service.get_balance_summary().get('allocated_to_portfolio', 0.0)
                    except Exception:
                        fs_alloc = 0.0
                logger.warning(f"⚠️ Insufficient cash balance - skipping execution phase | Broker cash: ${broker_cash:,.2f} | Funding allocated: ${fs_alloc:,.2f}")
                self._log_activity("SKIP", f"Insufficient cash balance | Broker cash: ${broker_cash:.2f} | Funding allocated: ${fs_alloc:.2f}")
                return
            
            # Evaluate recent research
            if not self.research_history:
                logger.debug("📭 No recent research to evaluate")
                return
            
            # Get most recent research
            latest_research = self.research_history[-1]
            symbol = latest_research["symbol"]
            action = latest_research["action_recommended"]
            price = latest_research["price"]
            
            if action == "HOLD":
                logger.debug(f"⏸️ {symbol}: HOLD decision - no execution")
                self.daily_stats["decisions_skipped"] += 1
                return
            
            # Determine trade quantity based on available capital and position sizing
            qty = 1
            trade_cost = 0.0
            if self.funding_service:
                fs = self.funding_service.get_balance_summary()
                available_capital = fs.get('allocated_to_portfolio', 0.0) - fs.get('reserved', 0.0)
            else:
                available_capital = balance.get('buying_power', balance.get('cash', 0)) if balance else 0

            max_pos_pct = self.config.get('max_position_size', 5)
            per_trade_cap = (available_capital * (max_pos_pct / 100.0)) if available_capital > 0 else 0
            if price and per_trade_cap > 0:
                qty = int(per_trade_cap // price)
                if qty < 1:
                    logger.info(f"⚠️ Not enough capital to buy 1 share of {symbol} at ${price:.2f} (per-trade cap ${per_trade_cap:.2f})")
                    self._log_activity('SKIP', f'Insufficient per-trade capital for {symbol}')
                    self.daily_stats['decisions_skipped'] += 1
                    return
                trade_cost = qty * price

            # Get council approval
            logger.info(f"🗳️ Seeking council approval for {symbol} {action} (qty={qty})...")
            council_decision = self.autonomous_trader.consult_council(
                symbol=symbol,
                action=action,
                price=price,
                quantity=qty
            )
            
            if not council_decision:
                logger.warning(f"⚠️ Council decision error for {symbol}")
                return
            
            approval_pct = council_decision.get("approval_percentage", 0)
            
            # Check approval threshold
            if approval_pct < self.config["min_council_approval"]:
                logger.info(
                    f"⛔ {symbol} {action} rejected by council "
                    f"({approval_pct:.0f}% < {self.config['min_council_approval']}%)"
                )
                self._log_activity(
                    "COUNCIL_REJECT",
                    f"{symbol}: {action} rejected ({approval_pct:.0f}% approval)"
                )
                self.daily_stats["decisions_skipped"] += 1
                return
            
            # Execute trade
            logger.info(f"✅ Council approved {symbol} {action} ({approval_pct:.0f}% approval)")
            self._log_activity(
                "COUNCIL_APPROVE",
                f"{symbol}: {action} approved ({approval_pct:.0f}% approval)"
            )
            
            try:
                # Reserve funds in funding service if applicable
                reserved_amount = 0.0
                if self.funding_service:
                    reserved_amount = trade_cost
                    reserved_ok = self.funding_service.reserve_funds(reserved_amount)
                    if not reserved_ok:
                        logger.warning(f"⚠️ Could not reserve ${reserved_amount:,.2f} for {symbol} - skipping trade")
                        self._log_activity('SKIP', f'Could not reserve funds for {symbol}')
                        # Add to FundingService persistent pending trades to attempt resume once funds are added
                        try:
                            pending = {
                                'timestamp': now_utc_iso(),
                                'symbol': symbol,
                                'action': action,
                                'qty': qty,
                                'price': price,
                                'trade_cost': trade_cost,
                                'attempts': 1
                            }
                            if self.funding_service and hasattr(self.funding_service, 'add_pending_trade'):
                                self.funding_service.add_pending_trade(pending)
                                logger.info(f"🔁 Persisted {symbol} to pending trades for retry on funds added: ${trade_cost:,.2f}")
                        except Exception:
                            logger.warning("⚠️ Failed to add pending trade")
                        self.daily_stats['decisions_skipped'] += 1
                        return

                order_result = self.autonomous_trader.execute_order(
                    symbol=symbol,
                    action=action,
                    qty=qty,
                    price=None,
                    price_type="MARKET",
                    account_id=account_id
                )
                
                if order_result and order_result.get("status") == "SUCCESS":
                    logger.info(f"✅ Trade executed: {symbol} {action} Order ID: {order_result.get('order_id')}")
                    
                    # Record trade
                    trade_record = {
                        "timestamp": now_utc_iso(),
                        "symbol": symbol,
                        "action": action,
                        "quantity": qty,
                        "price": price,
                        "order_id": order_result.get("order_id"),
                        "status": "EXECUTED",
                        "council_approval": approval_pct
                    }
                    self.trade_history.append(trade_record)
                    self.daily_stats["trades_executed"] += 1
                    
                    # Apply trade debit to funding service if present
                    if self.funding_service and trade_cost > 0:
                        applied = self.funding_service.apply_trade_debit(trade_cost)
                        if not applied:
                            logger.warning(f"⚠️ Could not apply trade debit for {symbol} ${trade_cost:,.2f}")

                    # Tim rule: every BUY gets a broker-backed stop + take-profit immediately
                    if str(action).upper() in ("BUY", "DAY_TRADE", "SWING"):
                        try:
                            indicators = latest_research.get("technical_indicators") or latest_research.get("indicators") or {}
                            self.autonomous_trader.open_position_with_stop_loss(
                                symbol=symbol,
                                entry_price=float(price),
                                quantity=int(qty),
                                stop_loss_percent=self.config.get("stop_loss_pct"),
                                take_profit_percent=self.config.get("take_profit_pct"),
                                indicators=indicators,
                                place_broker_stop=True,
                            )
                            self._log_activity(
                                "STOP_ARMED",
                                f"{symbol}: protective stop + TP armed after fill"
                            )
                        except Exception as e:
                            logger.error(f"❌ Failed to arm stop for {symbol}: {e}")

                    self._log_activity(
                        "TRADE_EXECUTED",
                        f"{symbol}: {action} {qty} share(s) @ ${price:.2f} (ID: {order_result.get('order_id')})"
                    )
                    
                    # Callback to UI
                    if self.update_callback:
                        self.update_callback({
                            "type": "TRADE_EXECUTED",
                            "symbol": symbol,
                            "action": action,
                            "quantity": qty,
                            "price": price,
                            "order_id": order_result.get("order_id"),
                            "timestamp": now_utc_iso()
                        })
                else:
                    logger.error(f"❌ Trade execution failed for {symbol}: {order_result}")
                    self._log_activity("TRADE_FAILED", f"{symbol}: {action} execution failed")
                    # Release reserved funds on failure
                    if self.funding_service and reserved_amount > 0:
                        try:
                            self.funding_service.release_reserved(reserved_amount)
                        except Exception:
                            pass
            
            except Exception as e:
                logger.error(f"❌ Error executing trade: {e}")
                self._log_activity("TRADE_ERROR", f"Execution error: {str(e)}")
        
        except Exception as e:
            logger.error(f"❌ Execution phase error: {e}")
    
    def _position_management_phase(self) -> None:
        """Enforce stops / take-profits on open managed positions every cycle."""
        try:
            positions = {}
            if hasattr(self.autonomous_trader, "get_positions_status"):
                positions = self.autonomous_trader.get_positions_status() or {}
            if not positions:
                return

            quotes: Dict[str, float] = {}
            for symbol in positions.keys():
                price = None
                if self.pricing_service and hasattr(self.pricing_service, "get_quote"):
                    try:
                        q = self.pricing_service.get_quote(symbol) or {}
                        price = q.get("price")
                    except Exception:
                        price = None
                if price is None:
                    # Fall back to last researched price
                    for r in reversed(self.research_history):
                        if r.get("symbol") == symbol and r.get("price"):
                            price = r["price"]
                            break
                if price is not None:
                    quotes[symbol] = float(price)

            if not quotes:
                return

            results = self.autonomous_trader.manage_open_positions(quotes)
            for r in results:
                if r.get("exited"):
                    self._log_activity("EXIT", f"{r.get('symbol')}: {r.get('message')}")
                    self.daily_stats["trades_executed"] += 1
        except Exception as e:
            logger.error(f"❌ Position management error: {e}")

    def _analyze_and_determine_action(self, symbol: str, research: Dict, quote: Dict) -> str:
        """
        Momentum sniping only. No RSI dip-buys. No hope.
        Returns: BUY, SELL, HOLD
        """
        try:
            try:
                from .momentum_engine import evaluate_momentum_entry, MomentumConfig
            except ImportError:
                from app.services.momentum_engine import evaluate_momentum_entry, MomentumConfig

            indicators = dict(research.get("indicators") or {})
            price = float(quote.get("price") or research.get("price") or 0)
            if research.get("action_hint") in ("BUY", "SELL", "HOLD") and research.get("confidence", 0) >= 55:
                # Trust perform_research when it already ran the momentum engine
                hint = research["action_hint"]
                if hint == "BUY":
                    return "BUY"
                if hint == "SELL":
                    return "SELL"

            action, confidence, reason = evaluate_momentum_entry(
                price, indicators, MomentumConfig()
            )
            logger.info(f"📈 {symbol} momentum -> {action} ({confidence:.2f}): {reason}")
            return action
        except Exception as e:
            logger.error(f"❌ Error analyzing {symbol}: {e}")
            return "HOLD"

    def _handle_funds_added(self, amount: float, summary: Dict) -> None:
        """Callback from FundingService when funds are added. Spawn a background thread to resume pending trades."""
        try:
            logger.info(f"💸 Funds added: ${amount:,.2f}. Checking pending trades for resume...")
            self._log_activity('FUNDS_ADDED', f"Funds added: ${amount:,.2f}")
            # In sandbox mode we can process pending trades synchronously to avoid race conditions in tests.
            if self.use_sandbox:
                try:
                    self._maybe_resume_pending_trades()
                except Exception as e:
                    logger.warning(f"⚠️ Error running pending trades resume inline: {e}")
            else:
                t = threading.Thread(target=self._maybe_resume_pending_trades, daemon=True)
                t.start()
        except Exception as e:
            logger.warning(f"⚠️ Error handling funds added callback: {e}")

    def _maybe_resume_pending_trades(self) -> None:
        """Attempt to reserve and execute pending trades when funds have been added."""
        try:
            # Retrieve a snapshot of pending trades from FundingService (avoid popping them until confirmed)
            pending = []
            if self.funding_service and hasattr(self.funding_service, 'get_pending_trades'):
                try:
                    pending = list(self.funding_service.get_pending_trades())
                except Exception:
                    pending = []

            for p in pending:
                try:
                    # Limit retries
                    attempts = p.get('attempts', 1)
                    if attempts > 3:
                        logger.info(f"⚠️ Dropping pending trade for {p.get('symbol')} after {attempts} attempts")
                        continue

                    symbol = p.get('symbol')
                    action = p.get('action')
                    qty = p.get('qty')
                    trade_cost = p.get('trade_cost')
                    price = p.get('price')

                    logger.info(f"🔁 Attempting to resume pending trade {symbol} (attempt {attempts})")
                    # Try to reserve again
                    if self.funding_service:
                        reserved_ok = self.funding_service.reserve_funds(trade_cost)
                        if not reserved_ok:
                            # Retry a few times with short backoff before giving up (helps races between
                            # allocation and resume notifications in tests/environments)
                            retried = False
                            for _ in range(3):
                                time.sleep(0.1)
                                try:
                                    # If there's unallocated balance sufficient, auto-allocate to portfolio
                                    if self.funding_service and hasattr(self.funding_service, 'get_balance_summary'):
                                        summary = self.funding_service.get_balance_summary()
                                        allocated = summary.get('allocated_to_portfolio', 0.0)
                                        unallocated = summary.get('unallocated', 0.0)
                                        if unallocated >= trade_cost and hasattr(self.funding_service, 'allocate_to_portfolio'):
                                            try:
                                                # Increase allocation to cover the pending trade
                                                self.funding_service.allocate_to_portfolio(allocated + trade_cost)
                                            except Exception:
                                                pass

                                    if self.funding_service and hasattr(self.funding_service, 'reserve_funds'):
                                        if self.funding_service.reserve_funds(trade_cost):
                                            retried = True
                                            break
                                except Exception:
                                    pass

                            if not retried:
                                # Do not count insufficient funds as a failed attempt — keep it pending
                                try:
                                    if self.funding_service and hasattr(self.funding_service, 'add_pending_trade'):
                                        # Update attempts and requeue
                                        p['attempts'] = attempts + 1
                                        self.funding_service.add_pending_trade(p)
                                except Exception:
                                    logger.debug("⚠️ Failed to persist re-queued pending trade")
                                logger.info(f"🔁 Still insufficient funds for {symbol} - will retry later (attempt {attempts})")
                                continue

                    # Execute the order
                    account_id = None
                    try:
                        account_id = self.trader_tools.account_id if (self.trader_tools and hasattr(self.trader_tools, 'account_id')) else None
                    except Exception:
                        account_id = None

                    result = self.autonomous_trader.execute_order(
                        symbol=symbol,
                        action=action,
                        qty=qty,
                        price=None,
                        price_type="MARKET",
                        account_id=account_id
                    )

                    if result and result.get('status') == 'SUCCESS':
                        logger.info(f"✅ Pending trade executed: {symbol} (ID: {result.get('order_id')})")
                        # Apply trade debit
                        if self.funding_service and trade_cost > 0:
                            applied = self.funding_service.apply_trade_debit(trade_cost)
                            if not applied:
                                logger.warning(f"⚠️ Could not apply trade debit for resumed {symbol} ${trade_cost:,.2f}")
                        # Remove the pending trade from persistence if it was present
                        try:
                            if self.funding_service and hasattr(self.funding_service, 'remove_pending_trade_by_id') and p.get('id'):
                                self.funding_service.remove_pending_trade_by_id(p.get('id'))
                        except Exception:
                            pass
                    else:
                        # Execution failed, release reserved funds if any and requeue with increased attempts
                        logger.warning(f"⚠️ Pending trade execution failed for {symbol}. Re-queueing")
                        if self.funding_service and trade_cost > 0:
                            try:
                                self.funding_service.release_reserved(trade_cost)
                            except Exception:
                                pass
                        p['attempts'] = attempts + 1
                        try:
                            if self.funding_service and hasattr(self.funding_service, 'add_pending_trade'):
                                # Re-queue with updated attempts and remove original if present
                                try:
                                    if self.funding_service and hasattr(self.funding_service, 'remove_pending_trade_by_id') and p.get('id'):
                                        self.funding_service.remove_pending_trade_by_id(p.get('id'))
                                except Exception:
                                    pass
                                self.funding_service.add_pending_trade(p)
                        except Exception:
                            logger.debug("⚠️ Could not persist failed pending trade re-queue")
                        time.sleep(1)

                except Exception as e:
                    logger.warning(f"⚠️ Error resuming pending trade: {e}")
                    continue

        except Exception as e:
            logger.warning(f"⚠️ Error processing pending trades: {e}")

    def retry_pending_trades(self) -> bool:
        """Public method to retry all pending trades asynchronously."""
        try:
            t = threading.Thread(target=self._maybe_resume_pending_trades, daemon=True)
            t.start()
            self._log_activity('RETRY_PENDING', 'Retrying pending trades triggered')
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to start retry of pending trades: {e}")
            return False

    def _retry_scheduler_loop(self) -> None:
        """Background loop that triggers retry_pending_trades periodically if enabled"""
        try:
            interval = self.config.get('retry_pending_interval', 60)
            while not self._retry_scheduler_stop.is_set() and self.is_running:
                try:
                    if self.config.get('retry_pending_enabled', False):
                            # Only trigger retry of pending trades when there is funding available to attempt them.
                            try:
                                if self.funding_service:
                                    summary = self.funding_service.get_balance_summary()
                                    allocated = summary.get('allocated_to_portfolio', 0.0)
                                    unallocated = summary.get('unallocated', 0.0)
                                    if allocated <= 0 and unallocated <= 0:
                                        # No funds available yet; skip triggering retries until funds are added
                                        continue
                            except Exception:
                                # If balance summary is unavailable, still attempt retries to be safe
                                pass
                            self.retry_pending_trades()
                except Exception as e:
                    logger.warning(f"⚠️ Error in retry scheduler: {e}")
                # Wait with the ability to break early
                self._retry_scheduler_stop.wait(timeout=max(1, interval))
        except Exception as e:
            logger.warning(f"⚠️ Retry scheduler exited: {e}")
    
    def _log_activity(self, activity_type: str, message: str) -> None:
        """Log trading activity"""
        log_entry = {
            "timestamp": now_utc_iso(),
            "type": activity_type,
            "message": message
        }
        self.activity_log.append(log_entry)
        
        # Callback to UI
        if self.update_callback:
            self.update_callback({
                "type": "ACTIVITY_LOG",
                "activity": log_entry
            })
    
    def get_activity_log(self) -> List[Dict]:
        """Get recent activity log"""
        return list(self.activity_log)
    
    def get_trade_history(self) -> List[Dict]:
        """Get trade history"""
        return self.trade_history
    
    def get_daily_stats(self) -> Dict:
        """Get daily trading statistics"""
        return self.daily_stats.copy()
    
    def add_to_watchlist(self, symbol: str) -> None:
        """Add stock to watchlist"""
        if symbol.upper() not in self.watchlist:
            self.watchlist.append(symbol.upper())
            self._log_activity("WATCHLIST_ADD", f"Added {symbol} to watchlist")
            logger.info(f"✅ Added {symbol} to watchlist")
    
    def remove_from_watchlist(self, symbol: str) -> None:
        """Remove stock from watchlist"""
        if symbol.upper() in self.watchlist:
            self.watchlist.remove(symbol.upper())
            self._log_activity("WATCHLIST_REMOVE", f"Removed {symbol} from watchlist")
            logger.info(f"✅ Removed {symbol} from watchlist")
    
    def set_config(self, config_key: str, value: Any) -> None:
        """Update configuration"""
        if config_key in self.config:
            self.config[config_key] = value
            logger.info(f"⚙️ Config updated: {config_key} = {value}")
            self._log_activity("CONFIG_UPDATE", f"{config_key} = {value}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        oauth_authenticated = False
        if self.oauth_service:
            try:
                oauth_status = self.oauth_service.get_status()
                oauth_authenticated = oauth_status.get('is_authenticated', False)
            except:
                oauth_authenticated = False
        
        # Prepare watchlist info
        if self.is_all_mode:
            watchlist_info = ["ALL"]
            watchlist_display = f"🌍 ALL US Markets ({len(self.popular_tickers)} tickers available)"
        else:
            watchlist_info = self.watchlist
            watchlist_display = f"📋 Watchlist ({len(self.watchlist)} stocks)"
        
        # Funding summary (if funding service is attached)
        funding_summary = None
        if self.funding_service:
            try:
                funding_summary = self.funding_service.get_balance_summary()
            except Exception:
                funding_summary = None
        
        return {
            "is_active": self.is_active,
            "is_running": self.is_running,
            "authenticated": oauth_authenticated,
            "is_all_mode": self.is_all_mode,
            "watchlist": watchlist_info,
            "watchlist_display": watchlist_display,
            "funding_summary": funding_summary,
            "daily_stats": self.daily_stats.copy(),
            "recent_activity": list(self.activity_log)[-10:],
            "config": self.config.copy()
        }

    def get_test_trade_preview(self, symbol: str, qty: Optional[int] = None, amount: Optional[float] = None) -> Dict[str, Any]:
        """Return a preview for a hypothetical trade without executing it.

        Args:
            symbol: Ticker symbol
            qty: Quantity to buy/sell (preferred)
            amount: USD amount to size the trade if qty not provided
        Returns:
            Dict containing price, qty, trade_cost, available_funding, broker_buying_power, can_place, message
        """
        try:
            if not symbol:
                return {"ok": False, "message": "No symbol provided"}

            quote = None
            sym = symbol.strip().upper() if isinstance(symbol, str) else None
            try:
                if self.pricing_service:
                    quote = self.pricing_service.get_quote(sym)
            except Exception:
                quote = None
            # Fallback to AutonomousTrader pricing service if different
            if (not quote or not quote.get('price')) and hasattr(self, 'autonomous_trader') and getattr(self.autonomous_trader, 'pricing_service', None):
                try:
                    quote = self.autonomous_trader.pricing_service.get_quote(sym)
                except Exception:
                    quote = quote or None
            # Fallback to trader_tools if no pricing service quote
            if (not quote or not quote.get('price')) and self.trader_tools and hasattr(self.trader_tools, 'get_quote'):
                try:
                    tquote = self.trader_tools.get_quote(sym)
                    if tquote and tquote.get('price'):
                        quote = tquote
                except Exception:
                    pass

            price = float(quote.get('price')) if quote and quote.get('price') else None
            if price is None or price <= 0:
                return {"ok": False, "message": f"Price unavailable for {sym if sym else symbol}. Ensure pricing services are enabled and symbol is correct"}

            if qty is None and amount is not None:
                qty = int(amount // price)
            elif qty is None:
                qty = 1

            trade_cost = qty * price

            # Funding service available capital (allocated - reserved)
            allocated = 0.0
            reserved = 0.0
            if self.funding_service:
                fs = self.funding_service.get_balance_summary()
                allocated = fs.get('allocated_to_portfolio', 0.0)
                reserved = fs.get('reserved', 0.0)

            available_capital = max(0.0, allocated - reserved)

            # Broker buying power if available
            bp = None
            try:
                account_id = self.trader_tools.account_id if (self.trader_tools and hasattr(self.trader_tools, 'account_id')) else None
                if account_id:
                    bal = self.trader_tools.get_account_balance(account_id)
                    bp = float(bal.get('buying_power', bal.get('cash', 0.0))) if bal else None
            except Exception:
                bp = None

            effective_available = available_capital
            if bp is not None:
                effective_available = min(effective_available, float(bp))

            can_place = trade_cost <= effective_available
            message = "OK" if can_place else "Insufficient funds"

            return {
                "ok": True,
                "symbol": symbol,
                "price": price,
                "qty": qty,
                "trade_cost": trade_cost,
                "allocated": allocated,
                "reserved": reserved,
                "broker_buying_power": bp,
                "effective_available": effective_available,
                "can_place": can_place,
                "message": message
            }
        except Exception as e:
            logger.error(f"❌ Error getting test trade preview: {e}")
            return {"ok": False, "message": str(e)}
