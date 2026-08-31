"""E*TRADE OAuth reconstruct path — no pickled OAuth1Session."""

from unittest.mock import Mock
import json
import os
import stat

import pytest

import app.services.etrade_oauth_service as svc_mod
from app.services.etrade_oauth_service import ETradeOAuthService, reconstruct_oauth1_session
from app.services.etrade_config import etrade_hosts, is_sandbox


SANDBOX_ACCESS = "https://apisb.etrade.com/oauth/access_token"
SANDBOX_REQUEST = "https://apisb.etrade.com/oauth/request_token"
PROD_ACCESS = "https://api.etrade.com/oauth/access_token"


def _env(monkeypatch, tmp_path, etrade_env="sandbox"):
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "ck-test")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "cs-test")
    monkeypatch.setenv("ETRADE_ENV", etrade_env)
    monkeypatch.setenv("ETRADE_OAUTH_STATE_FILE", str(tmp_path / "request.json"))
    monkeypatch.setenv("ETRADE_ACCESS_TOKEN_FILE", str(tmp_path / "access.json"))
    monkeypatch.setenv("ETRADE_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("ETRADE_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("ETRADE_SANDBOX", raising=False)
    monkeypatch.delenv("ETRADE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ETRADE_ACCESS_TOKEN_SECRET", raising=False)


def _mock_http(monkeypatch, posted):
    def fake_post(self, url, **kwargs):
        posted.append(url)
        resp = Mock()
        resp.status_code = 200
        if url.endswith("/oauth/request_token"):
            resp.text = "oauth_token=req-key-1&oauth_token_secret=req-secret-1"
        elif url.endswith("/oauth/access_token"):
            resp.text = "oauth_token=acc-key-1&oauth_token_secret=acc-secret-1"
        else:
            resp.status_code = 404
            resp.text = "unexpected"
        return resp

    monkeypatch.setattr("requests.sessions.Session.post", fake_post)


def test_default_access_url_is_sandbox(monkeypatch):
    monkeypatch.delenv("ETRADE_ENV", raising=False)
    monkeypatch.delenv("ETRADE_SANDBOX", raising=False)
    assert is_sandbox() is True
    assert etrade_hosts()["access_token_url"] == SANDBOX_ACCESS
    assert etrade_hosts()["request_token_url"] == SANDBOX_REQUEST
    assert PROD_ACCESS != etrade_hosts()["access_token_url"]


def test_initiate_persists_json_not_session(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    posted = []
    _mock_http(monkeypatch, posted)

    svc = ETradeOAuthService()
    auth_url = svc.initiate_oauth_flow()
    assert "key=" in auth_url and "token=req-key-1" in auth_url
    assert svc.session is None
    assert svc.oauth is None

    store = tmp_path / "request.json"
    assert store.is_file()
    mode = stat.S_IMODE(os.stat(store).st_mode)
    assert mode == 0o600
    material = json.loads(store.read_text())
    assert set(material) >= {
        "resource_owner_key",
        "resource_owner_secret",
        "authorize_url",
        "sandbox",
    }
    assert material["resource_owner_key"] == "req-key-1"
    assert material["resource_owner_secret"] == "req-secret-1"
    assert material["sandbox"] is True
    assert SANDBOX_REQUEST in posted
    assert PROD_ACCESS not in posted


def test_reconstructed_session_path_used_after_dead_session(monkeypatch, tmp_path):
    """Verifier exchange must reconstruct OAuth1Session from JSON.

    pyetrade sets session._client.client.verifier; a pickled OAuth1Session
    has no _client (AttributeError). Poison any in-memory session and still
    succeed via the reconstruct path (mocked HTTP).
    """
    _env(monkeypatch, tmp_path)
    posted = []
    _mock_http(monkeypatch, posted)

    constructed = []
    Real = svc_mod.OAuth1Session

    class SpySession(Real):
        def __init__(self, *args, **kwargs):
            constructed.append({"args": args, "kwargs": kwargs})
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(svc_mod, "OAuth1Session", SpySession)

    svc = ETradeOAuthService()
    svc.initiate_oauth_flow()

    class DeadSession:
        """Stand-in for a pickled OAuth1Session missing _client."""

    class DeadOAuth:
        session = DeadSession()

        def get_access_token(self, verifier):
            # This is the pyetrade path that AttributeErrors after pickle.
            self.session._client.client.verifier = verifier

    dead = DeadOAuth()
    svc.oauth = dead
    svc.session = DeadSession()

    ok = svc.complete_oauth_flow("VERIFIER123")
    assert ok is True
    assert SANDBOX_ACCESS in posted
    assert PROD_ACCESS not in posted

    access_calls = [c for c in constructed if c["kwargs"].get("verifier") == "VERIFIER123"]
    assert access_calls, "reconstruct_oauth1_session path was not used"
    last = access_calls[-1]
    assert last["kwargs"]["resource_owner_key"] == "req-key-1"
    assert last["kwargs"]["resource_owner_secret"] == "req-secret-1"

    # Poisoned pyetrade object still AttributeErrors; app did not use it.
    with pytest.raises(AttributeError):
        dead.get_access_token("VERIFIER123")
    assert svc.oauth is None
    assert svc.session is None

    access = json.loads((tmp_path / "access.json").read_text())
    assert access["access_token"] == "acc-key-1"
    assert access["access_token_secret"] == "acc-secret-1"
    mode = stat.S_IMODE(os.stat(tmp_path / "access.json").st_mode)
    assert mode == 0o600
    assert not (tmp_path / "request.json").exists()


def test_complete_does_not_use_pyetrade_get_access_token(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    posted = []
    _mock_http(monkeypatch, posted)
    svc = ETradeOAuthService()
    svc.initiate_oauth_flow()
    svc.oauth = object()  # would fail if get_access_token were called
    assert svc.complete_oauth_flow("ABC") is True
    assert SANDBOX_ACCESS in posted


def test_production_access_url_only_when_env_set(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, etrade_env="production")
    posted = []
    _mock_http(monkeypatch, posted)
    svc = ETradeOAuthService()
    svc.initiate_oauth_flow()
    assert svc.complete_oauth_flow("ABC") is True
    assert PROD_ACCESS in posted
    assert SANDBOX_ACCESS not in posted


def test_mismatch_request_token_rejected(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    posted = []
    _mock_http(monkeypatch, posted)
    svc = ETradeOAuthService()
    svc.initiate_oauth_flow()
    with pytest.raises(Exception, match="different request token"):
        svc.complete_oauth_flow("ABC", request_token="other-key")
    assert SANDBOX_ACCESS not in posted


def test_reconstruct_helper_sets_verifier():
    session = reconstruct_oauth1_session(
        "ck-test", "cs-test", "req-key-1", "req-secret-1", "VERIFIER123"
    )
    assert session._client.client.verifier == "VERIFIER123"
    assert session._client.client.resource_owner_key == "req-key-1"
    session.close()


def test_oauth_service_has_no_pickle():
    src = open("app/services/etrade_oauth_service.py").read()
    store = open("app/services/etrade_oauth_store.py").read()
    assert "import pickle" not in src
    assert "pickle.dump" not in src and "pickle.load" not in src
    assert "import pickle" not in store
    assert "pickle.dump" not in store and "pickle.load" not in store
