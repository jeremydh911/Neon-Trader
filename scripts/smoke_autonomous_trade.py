"""Smoke script to demonstrate an autonomous trade in sandbox mode."""
from pathlib import Path
from app.services.funding_service import FundingService
from app.services.autonomous_trader import AutonomousTrader
from app.services.background_trader import BackgroundTraderService
from app.services.mock_broker import MockBroker


def main():
    tmp = Path('/tmp/neon_smoke_funding.json')
    if tmp.exists():
        tmp.unlink()

    fs = FundingService(data_file=tmp)
    fs.add_funds(2000.0)
    fs.allocate_to_portfolio(1000.0)

    broker = MockBroker()
    trader = AutonomousTrader(memory_service=None, llm_service=None, council=None, use_sandbox=True)
    trader.broker = broker

    bg = BackgroundTraderService(autonomous_trader=trader, oauth_service=None, pricing_service=None, trader_tools=None, funding_service=fs, use_sandbox=True)
    bg.config['require_oauth'] = False
    bg.config['allow_start_without_oauth'] = True
    bg.research_history.append({'symbol': 'SMOKE', 'action_recommended': 'BUY', 'price': 5.0, 'confidence': 95})

    print('Before execution: trades=', broker.get_trades())
    bg._execution_phase()
    print('After execution: trades=', broker.get_trades())
    print('Trade history:', bg.get_trade_history())


if __name__ == '__main__':
    main()
