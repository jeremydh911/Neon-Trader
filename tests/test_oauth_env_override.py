from unittest.mock import Mock

from app.services.etrade_oauth_service import ETradeOAuthService


def test_initiate_oauth_flow_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "CK_TEST")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "CS_TEST")
    monkeypatch.setenv("ETRADE_OAUTH_STATE_FILE", str(tmp_path / "request.json"))
    monkeypatch.setenv("ETRADE_ACCESS_TOKEN_FILE", str(tmp_path / "access.json"))
    monkeypatch.delenv("ETRADE_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("ETRADE_ENV", raising=False)
    monkeypatch.delenv("ETRADE_SANDBOX", raising=False)

    def fake_post(self, url, **kwargs):
        resp = Mock()
        resp.status_code = 200
        resp.text = "oauth_token=FAKE_TOKEN_123&oauth_token_secret=FAKE_SECRET_123"
        return resp

    monkeypatch.setattr("requests.sessions.Session.post", fake_post)

    svc = ETradeOAuthService()
    auth_url = svc.initiate_oauth_flow()
    assert "key=" in auth_url and "token=" in auth_url, "Auth URL should include key and token"
    assert "CK_TEST" in auth_url
    assert "FAKE_TOKEN_123" in auth_url
