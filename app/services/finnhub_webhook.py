"""
Finnhub Webhook Handler - Receives and processes Finnhub trade events
"""

import json
import logging
from typing import Dict, Optional
from datetime import datetime
import hashlib
import hmac

logger = logging.getLogger(__name__)


class FinnhubWebhookHandler:
    """Handles incoming Finnhub webhook events"""

    # Event types
    EVENT_TRADE = "trade"
    EVENT_COMPANY_UPDATE = "company_update"

    def __init__(self, webhook_secret: str):
        """
        Initialize webhook handler
        
        Args:
            webhook_secret: Secret key for webhook validation
        """
        self.webhook_secret = webhook_secret
        self.events_received = 0
        self.events_processed = 0
        self.last_event = None

    def validate_webhook(self, body: str, signature: str) -> bool:
        """
        Validate webhook signature
        
        Args:
            body: Raw request body
            signature: Signature from X-Finnhub-Secret header
            
        Returns:
            True if signature is valid
        """
        try:
            # Compute expected signature
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                body.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures (timing-safe)
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Webhook validation error: {e}")
            return False

    def process_webhook(self, body: str, secret_header: str) -> Dict:
        """
        Process incoming webhook
        
        Args:
            body: Raw request body
            secret_header: Value from X-Finnhub-Secret header
            
        Returns:
            Response with status: {
                'success': bool,
                'acknowledged': bool,
                'message': str,
                'status_code': int
            }
        """
        self.events_received += 1

        # Validate secret
        if secret_header != self.webhook_secret:
            logger.warning("Webhook validation failed - invalid secret")
            return {
                'success': False,
                'acknowledged': False,
                'message': 'Invalid secret',
                'status_code': 401
            }

        try:
            # Parse JSON
            event = json.loads(body)
            
            # Process event
            result = self._process_event(event)
            
            self.events_processed += 1
            self.last_event = {
                'timestamp': datetime.now().isoformat(),
                'event': event,
                'result': result
            }
            
            logger.info(f"Webhook processed successfully: {result['message']}")
            
            return {
                'success': True,
                'acknowledged': True,
                'message': result['message'],
                'status_code': 200
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook JSON: {e}")
            return {
                'success': False,
                'acknowledged': False,
                'message': 'Invalid JSON',
                'status_code': 400
            }
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            return {
                'success': False,
                'acknowledged': False,
                'message': str(e),
                'status_code': 500
            }

    def _process_event(self, event: Dict) -> Dict:
        """
        Process specific event type
        
        Args:
            event: Event data
            
        Returns:
            Processing result
        """
        event_type = event.get('type')
        
        if event_type == self.EVENT_TRADE:
            return self._process_trade_event(event)
        elif event_type == self.EVENT_COMPANY_UPDATE:
            return self._process_company_update(event)
        else:
            logger.warning(f"Unknown event type: {event_type}")
            return {
                'message': f'Unknown event type: {event_type}'
            }

    def _process_trade_event(self, event: Dict) -> Dict:
        """
        Process trade event
        
        Format:
        {
            "type": "trade",
            "data": [
                {
                    "s": "AAPL",
                    "p": 150.25,
                    "t": 1633024800000,
                    "v": 100,
                    "c": ["a"]
                }
            ]
        }
        """
        try:
            trades = event.get('data', [])
            
            if not trades:
                return {'message': 'Trade event with no data'}
            
            # Process trades
            processed_trades = []
            for trade in trades:
                processed_trades.append({
                    'symbol': trade.get('s'),
                    'price': trade.get('p'),
                    'timestamp': trade.get('t'),
                    'volume': trade.get('v'),
                    'conditions': trade.get('c', [])
                })
            
            logger.info(f"Processed {len(processed_trades)} trades")
            
            return {
                'message': f'Processed {len(processed_trades)} trades',
                'trades': processed_trades
            }

        except Exception as e:
            logger.error(f"Trade event processing error: {e}")
            raise

    def _process_company_update(self, event: Dict) -> Dict:
        """
        Process company update event
        
        Format:
        {
            "type": "company_update",
            "symbol": "AAPL",
            "data": { ... }
        }
        """
        try:
            symbol = event.get('symbol')
            update_data = event.get('data', {})
            
            logger.info(f"Company update for {symbol}")
            
            return {
                'message': f'Processed company update for {symbol}',
                'symbol': symbol,
                'update_keys': list(update_data.keys())
            }

        except Exception as e:
            logger.error(f"Company update processing error: {e}")
            raise

    def get_stats(self) -> Dict:
        """
        Get webhook handler statistics
        
        Returns:
            Stats including events received/processed
        """
        return {
            'events_received': self.events_received,
            'events_processed': self.events_processed,
            'success_rate': (
                self.events_processed / self.events_received
                if self.events_received > 0
                else 0
            ),
            'last_event_time': (
                self.last_event['timestamp']
                if self.last_event
                else None
            )
        }


def get_webhook_handler(webhook_secret: str) -> FinnhubWebhookHandler:
    """
    Factory function to create webhook handler
    
    Args:
        webhook_secret: Finnhub webhook secret
        
    Returns:
        FinnhubWebhookHandler instance
    """
    return FinnhubWebhookHandler(webhook_secret)
