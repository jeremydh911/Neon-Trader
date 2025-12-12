import sys
from pathlib import Path
import time

# Add parent directory to path so imports like 'app.services' resolve during pytest
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.funding_service import FundingService
from app.services.autonomous_trader import AutonomousTrader
from app.services.background_trader import BackgroundTraderService
from app.services.mock_broker import MockBroker


class DummyCouncil:
    def discuss_trade(self, symbol, action, current_price, indicators, available_capital, market_sentiment):
        class Decision:
            approval_percentage = 100.0
            final_confidence = 1.0

        return Decision(), True


def test_end_to_end_autonomous_trade(tmp_path):
    # Setup funding service with an initial balance and allocate to portfolio
    data_file = tmp_path / "funding.json"
    fs = FundingService(data_file=data_file)
    fs.add_funds(1000.0)
    fs.allocate_to_portfolio(500.0)

    # Setup autonomous trader with mock broker and dummy council
    mock_broker = MockBroker()
    trader = AutonomousTrader(memory_service=None, llm_service=None, council=DummyCouncil(), use_sandbox=True)
    # Inject mock broker directly
    trader.broker = mock_broker

    # Create a background trader and inject services
    bg = BackgroundTraderService(autonomous_trader=trader, oauth_service=None, pricing_service=None, trader_tools=None, funding_service=fs, use_sandbox=True)
    # Adjust configs for test: low approval threshold and allow starting without oauth
    bg.config['min_council_approval'] = 50
    bg.config['require_oauth'] = False
    bg.config['allow_start_without_oauth'] = True

    # Inject research result that recommends BUY
    bg.research_history.append({
        'symbol': 'TEST',
        'action_recommended': 'BUY',
        'price': 10.0,
        'indicators': {},
        'confidence': 90
    })

    # Execute the execution phase to process the queued decision
    # Show that a manual reload (UI action) does not crash and returns summary
    summary_before = fs.get_balance_summary()
    assert 'last_update' in summary_before
    fs.reload()

    bg._execution_phase()

    # Verify a trade was executed and recorded
    trades = bg.get_trade_history()
    assert len(trades) >= 1
    t = trades[-1]
    assert t['symbol'] == 'TEST'
    assert t['action'] == 'BUY'

    # Verify mock broker recorded the trade
    mb_trades = mock_broker.get_trades()
    assert len(mb_trades) == 1
