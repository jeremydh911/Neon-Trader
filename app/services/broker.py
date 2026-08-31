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
    """E*TRADE execution path used by the Neon Trader day-trading desk.

    Preview is separate from place. Live (ETRADE_ENV=production) requires an
    explicit per-order confirm and will not one-shot preview+place.
    Credentials come from env / gitignored files only.
    """

    def __init__(self, use_sandbox: bool = None, risk_gate=None):
        super().__init__()
        from .etrade_config import (
            etrade_hosts,
            is_sandbox,
            load_credentials,
        )
        from .desk_risk import DeskRiskGate

        self.use_sandbox = is_sandbox() if use_sandbox is None else bool(use_sandbox)
        creds = load_credentials()
        self.consumer_key = creds.consumer_key
        self.consumer_secret = creds.consumer_secret
        self.access_token = creds.access_token
        self.access_token_secret = creds.access_token_secret
        hosts = etrade_hosts(sandbox=self.use_sandbox)
        self.base_url = hosts["host"]
        self.api_v1 = hosts["api_v1"]
        self.orders_log = "/app/data/etrade_orders.json"
        self.client = None
        self.order_client = None
        # After-hours is always in; market orders are never used.
        self.risk = risk_gate or DeskRiskGate(include_afterhours=True, allow_market=False)
        self._account_id_key = None

    def connect(self) -> bool:
        """Connect to E*TRADE API (sandbox by default)."""
        try:
            import pyetrade
        except ImportError:
            logger.error("pyetrade not installed")
            self.connected = False
            return False

        try:
            if not self.consumer_key or not self.consumer_secret:
                logger.warning(
                    "E*TRADE consumer credentials missing — set ETRADE_CONSUMER_KEY / "
                    "ETRADE_CONSUMER_SECRET (env or gitignored file)"
                )
                self.connected = False
                return False
            if not self.access_token or not self.access_token_secret:
                logger.warning(
                    "E*TRADE OAuth tokens empty — complete OAuth 1.0a (HMAC-SHA1). "
                    "Access tokens expire at midnight ET and go idle after ~2 hours."
                )
                self.connected = False
                return False

            self.client = pyetrade.ETradeAccounts(
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret,
                dev=self.use_sandbox,
            )
            self.order_client = pyetrade.ETradeOrder(
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret,
                dev=self.use_sandbox,
            )
            accounts = self._list_accounts()
            self.connected = True
            mode = "SANDBOX" if self.use_sandbox else "LIVE"
            n_accounts = len(accounts) if accounts else 0
            logger.info("Connected to E*TRADE %s (%s accounts) via %s", mode, n_accounts, self.base_url)
            return True
        except Exception as e:
            logger.error("E*TRADE connection issue (may need auth): %s", str(e)[:200])
            self.connected = False
            return False

    def disconnect(self) -> bool:
        self.connected = False
        return True

    def generate_client_order_id(self) -> str:
        """Unique clientOrderId, <= 20 alphanumeric characters."""
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(20))

    def preview_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "limit",
        limit_price: float = None,
        stop_price: float = None,
        estimated_price: float = None,
        account_id: str = None,
        client_order_id: str = None,
        is_new_entry: bool = None,
        skip_session_check: bool = False,
        now=None,
    ) -> Dict:
        """Preview only. Does not place."""
        if not self.connected:
            return {"status": "ERROR", "message": "Not connected"}
        try:
            prepared = self._prepare_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                estimated_price=estimated_price,
                is_new_entry=is_new_entry,
                skip_session_check=skip_session_check,
                now=now,
            )
            if prepared.get("status") == "ERROR":
                return prepared

            account_id_key = account_id or self._get_account_id_key()
            if not account_id_key:
                return {"status": "ERROR", "message": "No E*TRADE accountIdKey"}

            cid = client_order_id or self.generate_client_order_id()
            if not str(cid).isalnum() or len(str(cid)) > 20:
                return {"status": "ERROR", "message": "clientOrderId must be <=20 alphanumeric"}

            kwargs = self._pyetrade_kwargs(prepared, account_id_key, cid)
            preview = self.order_client.preview_equity_order(**kwargs)
            preview_id = self._extract_preview_id(preview)
            if not preview_id:
                return {
                    "status": "ERROR",
                    "message": "Preview failed (no previewId)",
                    "raw": preview,
                    "broker": "ETRADE",
                }
            logger.info("E*TRADE preview %s %s %s previewId=%s", prepared["side"], prepared["qty"], prepared["symbol"], preview_id)
            return {
                "status": "PREVIEW",
                "preview_id": preview_id,
                "client_order_id": cid,
                "symbol": prepared["symbol"],
                "qty": prepared["qty"],
                "side": prepared["side"],
                "type": prepared["order_type"],
                "limit_price": prepared.get("limit_price"),
                "stop_price": prepared.get("stop_price"),
                "account_id_key": account_id_key,
                "broker": "ETRADE",
                "environment": "sandbox" if self.use_sandbox else "production",
                "raw": preview,
                "timestamp": now_utc_iso(),
                "pdt_enforced": False,
            }
        except Exception as e:
            logger.error("E*TRADE preview failed: %s", e)
            return {"status": "ERROR", "message": str(e), "broker": "ETRADE"}

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "limit",
        limit_price: float = None,
        stop_price: float = None,
        preview_id: str = None,
        client_order_id: str = None,
        confirm_live: bool = False,
        estimated_price: float = None,
        account_id: str = None,
        is_new_entry: bool = None,
        skip_session_check: bool = False,
        now=None,
    ) -> Dict:
        """Place a previously previewed order. Live requires confirm_live=True.

        This method does NOT preview-then-place. Call preview_order first.
        """
        if not self.connected:
            return {"status": "ERROR", "message": "Not connected"}
        if not self.use_sandbox and not confirm_live:
            return {
                "status": "ERROR",
                "message": (
                    "LIVE place requires explicit per-order confirm "
                    "(confirm_live=True) and ETRADE_ENV=production"
                ),
                "broker": "ETRADE",
            }
        if not preview_id:
            return {
                "status": "ERROR",
                "message": (
                    "preview_id is required; preview and place are separate. "
                    "Live will not one-shot place."
                ),
                "broker": "ETRADE",
            }
        try:
            prepared = self._prepare_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                estimated_price=estimated_price,
                is_new_entry=is_new_entry,
                skip_session_check=skip_session_check,
                now=now,
            )
            if prepared.get("status") == "ERROR":
                return prepared

            account_id_key = account_id or self._get_account_id_key()
            if not account_id_key:
                return {"status": "ERROR", "message": "No E*TRADE accountIdKey"}

            cid = client_order_id or self.generate_client_order_id()
            if not str(cid).isalnum() or len(str(cid)) > 20:
                return {"status": "ERROR", "message": "clientOrderId must be <=20 alphanumeric"}

            kwargs = self._pyetrade_kwargs(prepared, account_id_key, cid)
            kwargs["previewId"] = preview_id
            order_result = self.order_client.place_equity_order(**kwargs)
            order_id = self._extract_order_id(order_result)
            order_dict = {
                "order_id": order_id,
                "preview_id": preview_id,
                "client_order_id": cid,
                "symbol": prepared["symbol"],
                "qty": prepared["qty"],
                "side": prepared["side"],
                "type": prepared["order_type"],
                "status": "PLACED",
                "broker": "ETRADE",
                "environment": "sandbox" if self.use_sandbox else "production",
                "timestamp": now_utc_iso(),
                "raw": order_result,
                "pdt_enforced": False,
            }
            self._log_order(order_dict)
            logger.info(
                "E*TRADE order placed: %s %s %s id=%s env=%s",
                prepared["side"],
                prepared["qty"],
                prepared["symbol"],
                order_id,
                order_dict["environment"],
            )
            return order_dict
        except Exception as e:
            # Surface brokerage rejections (including PDT) without client-side PDT logic.
            logger.error("Failed to place E*TRADE order: %s", e)
            return {"status": "ERROR", "message": str(e), "broker": "ETRADE", "pdt_enforced": False}

    def _prepare_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str,
        limit_price: float,
        stop_price: float,
        estimated_price: float,
        is_new_entry: bool,
        skip_session_check: bool,
        now,
    ) -> Dict:
        ticker = (symbol or "").strip().upper()
        action = (side or "").strip().upper()
        if action in ("BUY", "OPEN"):
            action = "BUY"
        elif action in ("SELL", "CLOSE"):
            action = "SELL"
        price_type = (order_type or "limit").strip().upper()
        if price_type in ("MKT",):
            price_type = "MARKET"
        px = limit_price if limit_price is not None else estimated_price
        if px is None:
            px = stop_price

        from .desk_risk import deployed_out_from_positions

        account = self.get_account() or {}
        equity = float(account.get("portfolio_value") or account.get("net_account_value") or 0)
        positions = self.get_positions() or {}
        deployed_out = deployed_out_from_positions(positions)
        open_orders = self.count_open_orders()

        gate = self.risk.evaluate(
            symbol=ticker,
            qty=int(qty),
            side=action,
            order_type=price_type,
            price=px,
            equity=equity,
            deployed_out=deployed_out,
            open_orders=open_orders,
            is_new_entry=is_new_entry,
            now=now,
            skip_session_check=skip_session_check,
        )
        if not gate.get("ok"):
            return {"status": "ERROR", "message": gate.get("message", "risk rejected"), "risk": gate}

        return {
            "status": "OK",
            "symbol": ticker,
            "qty": int(qty),
            "side": action,
            "order_type": price_type,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "price": px,
            "now": now,
        }

    def _pyetrade_kwargs(self, prepared: Dict, account_id_key: str, client_order_id: str) -> Dict:
        flags = self.risk.order_session_flags(now=prepared.get("now"))
        kwargs = {
            "accountIdKey": account_id_key,
            "symbol": prepared["symbol"],
            "orderAction": prepared["side"],
            "clientOrderId": client_order_id,
            "priceType": "LIMIT",
            "quantity": prepared["qty"],
            "orderTerm": flags["orderTerm"],
            "marketSession": flags["marketSession"],
        }
        if prepared.get("limit_price") is not None:
            kwargs["limitPrice"] = prepared["limit_price"]
        elif prepared.get("price") is not None:
            kwargs["limitPrice"] = prepared["price"]
        return kwargs

    def _list_accounts(self):
        if not self.client:
            return []
        if hasattr(self.client, "list_accounts"):
            data = self.client.list_accounts()
        elif hasattr(self.client, "get_account_list"):
            data = self.client.get_account_list()
        else:
            return []
        return self._normalize_accounts(data)

    def _normalize_accounts(self, data) -> list:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        accounts = (
            data.get("AccountListResponse", {})
            .get("Accounts", {})
            .get("Account")
        )
        if accounts is None:
            accounts = data.get("Accounts", data.get("Account", []))
        if isinstance(accounts, dict):
            return [accounts]
        return list(accounts or [])

    def _get_account_id_key(self) -> Optional[str]:
        if self._account_id_key:
            return self._account_id_key
        accounts = self._list_accounts()
        if not accounts:
            return None
        first = accounts[0]
        key = first.get("accountIdKey") or first.get("accountId") or first.get("account_id")
        self._account_id_key = str(key) if key else None
        return self._account_id_key

    @staticmethod
    def _extract_preview_id(preview) -> Optional[str]:
        if not isinstance(preview, dict):
            return None
        node = preview.get("PreviewOrderResponse", preview)
        ids = node.get("PreviewIds") or node.get("previewIds") or {}
        if isinstance(ids, list) and ids:
            ids = ids[0]
        if isinstance(ids, dict):
            pid = ids.get("previewId") or ids.get("preview_id")
            return str(pid) if pid is not None else None
        return None

    @staticmethod
    def _extract_order_id(result) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        node = result.get("PlaceOrderResponse", result)
        ids = node.get("OrderIds") or node.get("orderIds") or node.get("OrderId")
        if isinstance(ids, list) and ids:
            first = ids[0]
            if isinstance(first, dict):
                oid = first.get("orderId") or first.get("order_id")
                return str(oid) if oid is not None else None
            return str(first)
        if isinstance(ids, dict):
            oid = ids.get("orderId") or ids.get("order_id")
            return str(oid) if oid is not None else None
        return None

    def count_open_orders(self) -> int:
        try:
            if not self.order_client:
                return 0
            account_id_key = self._get_account_id_key()
            if not account_id_key:
                return 0
            data = self.order_client.list_orders(account_id_key, status="OPEN")
            orders = (
                (data or {}).get("OrdersResponse", {}).get("Order")
                if isinstance(data, dict)
                else data
            )
            if orders is None:
                return 0
            if isinstance(orders, dict):
                return 1
            return len(list(orders))
        except Exception as e:
            logger.warning("Could not list open E*TRADE orders: %s", e)
            return 0

    def list_open_orders(self) -> list:
        from .working_order_follower import normalize_open_orders

        if not self.order_client:
            return []
        account_id_key = self._get_account_id_key()
        if not account_id_key:
            return []
        try:
            data = self.order_client.list_orders(account_id_key, status="OPEN")
            return normalize_open_orders(data)
        except Exception as e:
            logger.warning("list_open_orders failed: %s", e)
            return []

    def cancel_order(self, order_id, confirm_live: bool = False) -> Dict:
        if not self.use_sandbox and not confirm_live:
            return {"status": "ERROR", "message": "LIVE cancel requires confirm_live=True"}
        if not self.order_client:
            return {"status": "ERROR", "message": "Not connected"}
        account_id_key = self._get_account_id_key()
        try:
            raw = self.order_client.cancel_order(account_id_key, int(order_id))
            return {"status": "CANCELLED", "order_id": order_id, "raw": raw}
        except Exception as e:
            return {"status": "ERROR", "message": str(e), "order_id": order_id}

    def cancel_premarket_before_roll(self, now=None, confirm_live: bool = False) -> Dict:
        """~9:28am ET: cancel EXTENDED working orders so they do not auto-roll."""
        if not self.risk.in_cancel_before_roll_window(now=now):
            clock = self.risk.hawaii_clock(now)
            return {
                "status": "SKIPPED",
                "message": "not in 09:28–09:30 ET cancel-before-roll window",
                "clock": clock,
            }
        cancelled = []
        errors = []
        for order in self.list_open_orders():
            if str(order.get("market_session") or "").upper() != "EXTENDED":
                continue
            result = self.cancel_order(order.get("order_id"), confirm_live=confirm_live)
            (cancelled if result.get("status") == "CANCELLED" else errors).append(
                {**result, "symbol": order.get("symbol")}
            )
        return {
            "status": "OK",
            "cancelled": cancelled,
            "errors": errors,
            "clock": self.risk.hawaii_clock(now),
        }

    def follow_afterhours_working_orders(
        self,
        quotes: Dict,
        now=None,
        confirm_live: bool = False,
        tick: float = 0.01,
    ) -> Dict:
        """Replace unfilled after-hours LIMITs as the tape moves (through 20:00 ET)."""
        from .working_order_follower import follow_instructions

        if self.risk.phase(now) != "afterhours":
            return {
                "status": "SKIPPED",
                "message": "after-hours follow only runs 16:00–20:00 ET",
                "clock": self.risk.hawaii_clock(now),
            }
        orders = self.list_open_orders()
        instructions = follow_instructions(orders, quotes or {}, tick=tick, extended_only=True)
        applied = []
        for inst in instructions:
            result = self.replace_working_limit(
                order_id=inst["order_id"],
                symbol=inst["symbol"],
                qty=inst["qty"],
                side=inst["side"],
                limit_price=inst["new_limit"],
                now=now,
                confirm_live=confirm_live,
            )
            applied.append({**inst, "result": result})
        return {
            "status": "OK",
            "followed": applied,
            "clock": self.risk.hawaii_clock(now),
        }

    def replace_working_limit(
        self,
        order_id,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        now=None,
        confirm_live: bool = False,
        client_order_id: str = None,
    ) -> Dict:
        """Cancel/replace a working LIMIT (preview change then place change). Live needs confirm."""
        if not self.use_sandbox and not confirm_live:
            return {"status": "ERROR", "message": "LIVE replace requires confirm_live=True"}
        if not self.order_client:
            return {"status": "ERROR", "message": "Not connected"}
        prepared = self._prepare_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="limit",
            limit_price=limit_price,
            stop_price=None,
            estimated_price=limit_price,
            is_new_entry=False,
            skip_session_check=False,
            now=now,
        )
        if prepared.get("status") == "ERROR":
            return prepared
        account_id_key = self._get_account_id_key()
        cid = client_order_id or self.generate_client_order_id()
        kwargs = self._pyetrade_kwargs(prepared, account_id_key, cid)
        try:
            if hasattr(self.order_client, "change_preview_equity_order"):
                preview = self.order_client.change_preview_equity_order(
                    account_id_key, str(order_id), **kwargs
                )
                preview_id = self._extract_preview_id(preview)
                if not preview_id:
                    return {"status": "ERROR", "message": "change preview failed", "raw": preview}
                kwargs["previewId"] = preview_id
                kwargs["orderId"] = order_id
                placed = self.order_client.place_changed_equity_order(**kwargs)
                return {
                    "status": "REPLACED",
                    "order_id": self._extract_order_id(placed) or order_id,
                    "preview_id": preview_id,
                    "limit_price": limit_price,
                    "raw": placed,
                }
            # Fallback: cancel then preview+place a new LIMIT.
            self.cancel_order(order_id, confirm_live=confirm_live)
            preview = self.preview_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type="limit",
                limit_price=limit_price,
                client_order_id=cid,
                now=now,
            )
            if preview.get("status") == "ERROR":
                return preview
            return self.place_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type="limit",
                limit_price=limit_price,
                preview_id=preview.get("preview_id"),
                client_order_id=preview.get("client_order_id"),
                confirm_live=confirm_live,
                now=now,
            )
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def _log_order(self, order: Dict):
        try:
            orders = []
            if os.path.exists(self.orders_log):
                with open(self.orders_log, "r") as f:
                    orders = json.load(f)
            orders.append(order)
            os.makedirs(os.path.dirname(self.orders_log) or ".", exist_ok=True)
            with open(self.orders_log, "w") as f:
                json.dump(orders, f, indent=2, default=str)
        except Exception as e:
            logger.error("Error logging order: %s", e)

    def get_positions(self) -> Dict[str, Dict]:
        if not self.connected:
            return {}
        try:
            account_id_key = self._get_account_id_key()
            if not account_id_key:
                return {}
            if hasattr(self.client, "get_account_portfolio"):
                portfolio = self.client.get_account_portfolio(account_id_key)
            else:
                portfolio = self.client.get_account(account_id_key, assetcat="CASH")
            positions_dict = {}
            node = portfolio.get("PortfolioResponse", portfolio) if isinstance(portfolio, dict) else {}
            raw_positions = node.get("AccountPortfolio", node)
            if isinstance(raw_positions, list):
                pos_list = []
                for item in raw_positions:
                    pos_list.extend(item.get("Position", []) if isinstance(item, dict) else [])
            elif isinstance(raw_positions, dict):
                pos_list = raw_positions.get("Position", [])
            else:
                pos_list = []
            if isinstance(pos_list, dict):
                pos_list = [pos_list]
            for position in pos_list or []:
                product = position.get("Product") or {}
                symbol = product.get("symbol") or position.get("symbol")
                if not symbol:
                    continue
                qty = float(position.get("quantity") or position.get("qty") or 0)
                price = float(position.get("Quick", {}).get("lastTrade") or position.get("lastPrice") or 0)
                positions_dict[symbol] = {
                    "symbol": symbol,
                    "qty": qty,
                    "price": price,
                    "market_value": float(position.get("marketValue") or qty * price),
                }
            return positions_dict
        except Exception as e:
            logger.error("Error getting E*TRADE positions: %s", e)
            return {}

    def get_account(self) -> Dict:
        if not self.connected:
            return {}
        try:
            account_id_key = self._get_account_id_key()
            if not account_id_key:
                return {}
            if hasattr(self.client, "get_account_balance"):
                account_data = self.client.get_account_balance(account_id_key)
            else:
                account_data = self.client.get_account(account_id_key, assetcat="CASH")
            node = account_data.get("BalanceResponse", account_data) if isinstance(account_data, dict) else {}
            computed = node.get("Computed") or node.get("Account") or node
            portfolio_value = _first_number(
                computed,
                ("RealTimeValues", "totalAccountValue"),
                ("totalAccountValue",),
                ("accountValue",),
                ("netAccountValue",),
            )
            cash = _first_number(
                computed,
                ("cashBuyingPower",),
                ("cashBalance",),
                ("cashAvailableForInvestment",),
            )
            buying_power = _first_number(
                computed,
                ("marginBuyingPower",),
                ("buyingPower",),
                ("cashBuyingPower",),
            )
            return {
                "account_number": account_id_key,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "buying_power": buying_power,
                "broker": "ETRADE",
                "environment": "sandbox" if self.use_sandbox else "production",
                "pdt_enforced": False,
            }
        except Exception as e:
            logger.error("Error getting E*TRADE account: %s", e)
            return {}


def _first_number(node: dict, *paths) -> float:
    if not isinstance(node, dict):
        return 0.0
    for path in paths:
        cur = node
        ok = True
        for part in path:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            try:
                return float(cur)
            except (TypeError, ValueError):
                continue
    return 0.0


_broker = None


def get_broker(broker_type: str = "etrade", use_sandbox: bool = None):
    """Get or create broker connection. Default is E*TRADE sandbox."""
    from .etrade_config import is_sandbox

    global _broker
    if _broker is None:
        sandbox = is_sandbox() if use_sandbox is None else bool(use_sandbox)
        if broker_type.lower() == "etrade":
            _broker = ETradeBroker(use_sandbox=sandbox)
        else:
            # Alpaca remains available but unused by the day-trading desk.
            _broker = AlpacaBroker(use_paper_trading=sandbox)
        _broker.connect()
    return _broker


def reset_broker_singleton() -> None:
    """Test helper to drop the cached broker."""
    global _broker
    _broker = None
