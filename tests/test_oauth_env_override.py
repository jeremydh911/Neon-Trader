import os
import importlib

from app.services.etrade_oauth_service import ETradeOAuthService

class FakeETradeOAuth:
    def __init__(self, consumer_key=None, consumer_secret=None, callback_url=None):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.callback_url = callback_url
        self.auth_token_url = 'https://us.etrade.com/e/t/etws/authorize'
        self.access_token_url = None
        self.resource_owner_key = None
    def get_request_token(self):
        # Simulate obtaining a request token; store raw token
        self.resource_owner_key = 'FAKE_TOKEN_123'
        return 'fake_request_token_value'

def test_initiate_oauth_flow_env_override(monkeypatch, tmp_path):
    # Ensure env vars override credentials
    monkeypatch.setenv('ETRADE_CONSUMER_KEY', 'CK_TEST')
    monkeypatch.setenv('ETRADE_CONSUMER_SECRET', 'CS_TEST')
    monkeypatch.delenv('ETRADE_CREDENTIALS_FILE', raising=False)

    # Mock the ETradeOAuth class used in the service
    import app.services.etrade_oauth_service as svc_mod
    monkeypatch.setattr(svc_mod, 'ETradeOAuth', FakeETradeOAuth)

    svc = ETradeOAuthService()
    auth_url = svc.initiate_oauth_flow()
    assert 'key=' in auth_url and 'token=' in auth_url, 'Auth URL should include key and token'
