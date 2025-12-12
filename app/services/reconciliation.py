"""Reconciliation worker to resolve pending trades and update leaderboard and agents.

This module provides a simple reconcile loop that looks for pending trades in the
leaderboard DB, attempts to match them with completed trades recorded in the
`AutonomousTrader` memory, and resolves them (apply PnL and notify agents).

The approach is conservative and does not assume any particular broker API.
It first attempts to match by `order_id` where available, then falls back to
matching recent completed trades by `symbol`, `qty` and `entry_price`.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Dict, Any

from .leaderboard import get_leaderboard_db, LeaderboardDB
from .autonomous_trader import AutonomousTrader
from .agent_framework import CouncilOrchestrator

logger = logging.getLogger(__name__)


class ReconciliationWorker:
    def __init__(self, orchestrator: CouncilOrchestrator, trader: AutonomousTrader, db_path: Optional[str] = None, poll_interval: float = 10.0):
        self.orchestrator = orchestrator
        self.trader = trader
        self.db = get_leaderboard_db(db_path) if db_path is not None else get_leaderboard_db()
        self.poll_interval = poll_interval
        self._running = False

    def _match_by_order_id(self, pending: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        order_id = pending.get('order_id') or pending.get('order')
        if not order_id:
            return None
        broker = getattr(self.trader, 'broker', None)
        if not broker:
            return None
        # Try common broker methods: get_orders, get_order
        try:
            if hasattr(broker, 'get_order'):
                info = broker.get_order(order_id)
                if info and info.get('status') in ('FILLED', 'filled', 'complete', 'COMPLETED'):
                    # compute pnl if available
                    executed_price = info.get('executed_price') or info.get('avg_price') or info.get('filled_price')
                    filled_qty = info.get('filled_qty') or info.get('filled_quantity') or info.get('quantity')
                    if executed_price is not None and filled_qty is not None:
                        entry = float(pending.get('entry_price', 0))
                        pnl = (float(executed_price) - float(entry)) * float(filled_qty)
                        return {'pnl': pnl, 'details': info}
            if hasattr(broker, 'get_orders'):
                # try to find order in list
                orders = broker.get_orders()
                for o in orders:
                    if str(o.get('order_id')) == str(order_id) or str(o.get('orderId')) == str(order_id):
                        if o.get('status') in ('FILLED', 'filled', 'complete', 'COMPLETED'):
                            executed_price = o.get('executed_price') or o.get('executedPrice') or o.get('avg_price')
                            qty = o.get('quantity') or o.get('qty') or 0
                            if executed_price is not None and qty:
                                entry = float(pending.get('entry_price', 0))
                                pnl = (float(executed_price) - float(entry)) * float(qty)
                                return {'pnl': pnl, 'details': o}
        except Exception as e:
            logger.debug(f"Broker order lookup failed for order_id={order_id}: {e}")
        return None

    def _match_by_memory(self, pending: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Try to find a completed trade in the trader memory with similar entry price/qty
        symbol = pending.get('symbol')
        entry_price = pending.get('entry_price')
        qty = pending.get('qty')
        try:
            recent = getattr(self.trader.memory, 'get_recent_trades')(limit=50, symbol=symbol)
            for t in recent:
                # Match if timestamps and qty and entry_price roughly match
                tp = float(t.get('entry_price', 0) or t.get('price', 0) or 0)
                tq = int(t.get('quantity', t.get('qty', 0) or 0))
                if tq == 0:
                    continue
                if qty and tq != int(qty):
                    continue
                # allow small rounding differences on price
                if abs(tp - float(entry_price or 0)) / (tp + 1e-9) < 0.02:
                    pnl = float(t.get('profit_loss') or t.get('profit') or 0)
                    return {'pnl': pnl, 'details': t}
        except Exception as e:
            logger.debug(f"Memory matching failed for pending trade {pending.get('trade_id')}: {e}")
        return None

    def reconcile_once(self):
        pending = self.db.get_pending_trades()
        if not pending:
            return 0
        resolved = 0
        for p in pending:
            trade_id = p.get('trade_id')
            agent = p.get('agent')
            # Try by order_id first
            matched = self._match_by_order_id(p)
            if not matched:
                matched = self._match_by_memory(p)

            if matched and 'pnl' in matched:
                pnl = float(matched['pnl'])
                new_score = None
                try:
                    new_score = self.orchestrator.reward_manager.resolve_trade(trade_id, pnl)
                except Exception as e:
                    logger.debug(f"Failed to resolve trade {trade_id} in reward manager: {e}")

                # Notify agent to learn from the closed trade
                try:
                    agent_obj = next((a for a in self.orchestrator.agents if a.name == agent), None)
                    if agent_obj:
                        # Build trade record for agent
                        trade_rec = {
                            'trade_id': trade_id,
                            'symbol': p.get('symbol'),
                            'qty': p.get('qty'),
                            'entry_price': p.get('entry_price'),
                            'pnl': pnl,
                            'details': matched.get('details')
                        }
                        agent_obj.on_trade_result(trade_rec)
                except Exception as e:
                    logger.debug(f"Failed to notify agent {agent} on trade result: {e}")

                logger.info(f"Resolved pending trade {trade_id} for agent {agent} with pnl={pnl:.2f}; new_score={new_score}")
                resolved += 1

        return resolved

    def start(self, interval: Optional[float] = None):
        self._running = True
        interval = interval or self.poll_interval
        logger.info("Starting reconciliation worker (interval=%.1fs)", interval)
        while self._running:
            try:
                count = self.reconcile_once()
                if count:
                    logger.info(f"Reconciled {count} trades this cycle")
            except Exception as e:
                logger.error(f"Reconciliation loop error: {e}")
            time.sleep(interval)

    def stop(self):
        self._running = False


__all__ = ["ReconciliationWorker"]
