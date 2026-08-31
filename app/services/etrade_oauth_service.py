"""E*TRADE OAuth 1.0a (OOB) using JSON request-token state.

pyetrade.ETradeOAuth.get_access_token does:
    self.session._client.client.verifier = verifier
After pickle/reload, OAuth1Session has no _client (AttributeError).
This service never pickles the live session. Request-token material is JSON:
resource_owner_key, resource_owner_secret, authorize_url, sandbox.
Verifier exchange reconstructs OAuth1Session and POSTs the sandbox or
production access_token URL (production only when ETRADE_ENV=production).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from requests_oauthlib import OAuth1Session
except ImportError:  # pragma: no cover
    OAuth1Session = None  # type: ignore

try:
    from pyetrade import ETradeOAuth
except ImportError:  # pragma: no cover
    ETradeOAuth = None  # type: ignore

logger = logging.getLogger(__name__)


def _config():
    try:
        from .etrade_config import etrade_hosts, is_sandbox, load_credentials, load_etrade_env
    except ImportError:  # pragma: no cover
        from app.services.etrade_config import etrade_hosts, is_sandbox, load_credentials, load_etrade_env
    return etrade_hosts, is_sandbox, load_credentials, load_etrade_env


def _store():
    try:
        from .etrade_oauth_store import (
            access_token_store_path,
            clear_request_token_material,
            load_access_token_material,
            load_request_token_material,
            request_token_store_path,
            save_access_token_material,
            save_request_token_material,
        )
    except ImportError:  # pragma: no cover
        from app.services.etrade_oauth_store import (
            access_token_store_path,
            clear_request_token_material,
            load_access_token_material,
            load_request_token_material,
            request_token_store_path,
            save_access_token_material,
            save_request_token_material,
        )
    return (
        access_token_store_path,
        clear_request_token_material,
        load_access_token_material,
        load_request_token_material,
        request_token_store_path,
        save_access_token_material,
        save_request_token_material,
    )


def reconstruct_oauth1_session(
    consumer_key: str,
    consumer_secret: str,
    resource_owner_key: str,
    resource_owner_secret: str,
    verifier: str,
) -> "OAuth1Session":
    """Build a fresh OAuth1Session for access-token exchange. Never reuse a pickled session."""
    if OAuth1Session is None:
        raise RuntimeError("requests_oauthlib is required for E*TRADE OAuth")
    return OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
        signature_type="AUTH_HEADER",
    )


def access_token_url_for_sandbox(sandbox: bool) -> str:
    etrade_hosts, _, _, _ = _config()
    return etrade_hosts(sandbox=sandbox)["access_token_url"]


class ETradeOAuthService:
    """OAuth 1.0a OOB flow. JSON request-token store is the source of truth."""

    def __init__(self, credentials_file: str = None):
        etrade_hosts, is_sandbox, load_credentials, load_etrade_env = _config()
        (
            access_token_store_path,
            _,
            _,
            _,
            request_token_store_path,
            _,
            _,
        ) = _store()
        load_etrade_env()
        self.credentials_file = credentials_file or os.getenv("ETRADE_CREDENTIALS_FILE")
        if not self.credentials_file:
            possible_paths = [
                "/app/config/etrade-credentials.json",
                os.path.join(os.path.dirname(__file__), "..", "config", "etrade-credentials.json"),
                os.path.join(os.getcwd(), "app", "config", "etrade-credentials.json"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    self.credentials_file = path
                    break
            if not self.credentials_file:
                self.credentials_file = "/app/config/etrade-credentials.json"

        self.tokens_file = str(access_token_store_path())
        self.request_token_file = str(request_token_store_path())
        self.credentials = self._load_credentials()

        creds = load_credentials(load_files=False)
        if "etrade" not in self.credentials:
            self.credentials["etrade"] = {}
        if "oauth" not in self.credentials["etrade"]:
            self.credentials["etrade"]["oauth"] = {}
        if "api" not in self.credentials["etrade"]:
            self.credentials["etrade"]["api"] = {}
        if creds.consumer_key:
            self.credentials["etrade"]["oauth"]["consumer_key"] = creds.consumer_key
        if creds.consumer_secret:
            self.credentials["etrade"]["oauth"]["consumer_secret"] = creds.consumer_secret
        sandbox_mode = is_sandbox()
        self.credentials["etrade"]["oauth"]["sandbox_mode"] = sandbox_mode
        hosts = etrade_hosts(sandbox=sandbox_mode)
        env_base_url = os.getenv("ETRADE_BASE_URL")
        self.credentials["etrade"]["api"]["base_url"] = env_base_url or hosts["host"]
        self.credentials["etrade"]["oauth"]["request_token_url"] = hosts["request_token_url"]
        self.credentials["etrade"]["oauth"]["access_token_url"] = hosts["access_token_url"]
        self.credentials["etrade"]["oauth"]["authorize_url"] = hosts["authorize_url"]

        # Live OAuth1Session is never the source of truth.
        self.oauth = None
        self.session = None
        self.client = None
        self.is_authenticated = False
        self.last_auth_time = None
        self.token_expiry = None
        self.request_token = None
        logger.info("ETradeOAuthService initialized (JSON request-token store)")

    def _load_credentials(self) -> dict:
        import json

        try:
            with open(self.credentials_file, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in credentials file: %s", type(exc).__name__)
            return {}

    def _consumer(self):
        oauth_block = (self.credentials or {}).get("etrade", {}).get("oauth", {})
        key = oauth_block.get("consumer_key")
        secret = oauth_block.get("consumer_secret")
        if not key or not secret:
            raise Exception(
                "E*TRADE consumer key/secret missing (set ETRADE_CONSUMER_KEY / ETRADE_CONSUMER_SECRET)"
            )
        return key, secret

    def _sandbox_and_hosts(self, sandbox: Optional[bool] = None):
        etrade_hosts, is_sandbox, _, _ = _config()
        if sandbox is None:
            sandbox = is_sandbox()
        return bool(sandbox), etrade_hosts(sandbox=bool(sandbox))

    def initiate_oauth_flow(self) -> str:
        """Fetch a request token, persist JSON material, return the authorize URL."""
        if OAuth1Session is None:
            raise Exception("requests_oauthlib not installed")
        consumer_key, consumer_secret = self._consumer()
        sandbox, hosts = self._sandbox_and_hosts()
        (
            _,
            _,
            _,
            _,
            _,
            _,
            save_request_token_material,
        ) = _store()

        last_error = None
        retry_delay = 2
        for attempt in range(3):
            session = None
            try:
                logger.info("Initiating OAuth flow (attempt %s/3) sandbox=%s", attempt + 1, sandbox)
                session = OAuth1Session(
                    consumer_key,
                    client_secret=consumer_secret,
                    callback_uri="oob",
                    signature_type="AUTH_HEADER",
                )
                token = session.fetch_request_token(hosts["request_token_url"])
                resource_owner_key = token["oauth_token"]
                resource_owner_secret = token["oauth_token_secret"]
                authorize_url = "%s?key=%s&token=%s" % (
                    hosts["authorize_url"],
                    consumer_key,
                    resource_owner_key,
                )
                save_request_token_material(
                    {
                        "resource_owner_key": resource_owner_key,
                        "resource_owner_secret": resource_owner_secret,
                        "authorize_url": authorize_url,
                        "sandbox": sandbox,
                    }
                )
                self.request_token = resource_owner_key
                # Drop the live session so pickle/reload cannot become source of truth.
                try:
                    session.close()
                except Exception:
                    pass
                self.session = None
                self.oauth = None
                logger.info("Authorization URL generated")
                return authorize_url
            except Exception as exc:
                last_error = exc
                logger.warning("OAuth initiation failed (attempt %s): %s", attempt + 1, exc)
                if session is not None:
                    try:
                        session.close()
                    except Exception:
                        pass
                self.session = None
                self.oauth = None
                if attempt < 2:
                    time.sleep(retry_delay)
                    retry_delay *= 2
        raise Exception("Failed to initiate OAuth flow: %s" % last_error)

    def complete_oauth_flow(self, verification_code: str, request_token: Optional[str] = None) -> bool:
        """Exchange verifier using reconstructed OAuth1Session from JSON material."""
        (
            _,
            clear_request_token_material,
            _,
            load_request_token_material,
            _,
            save_access_token_material,
            _,
        ) = _store()
        material = load_request_token_material()
        if not material:
            raise Exception("Please start the OAuth flow first (no saved request token)")

        saved_key = material.get("resource_owner_key")
        if request_token and saved_key and request_token != saved_key:
            raise Exception(
                "Verifier belongs to a different request token than the one saved. "
                "Start a new OAuth flow and authorize the latest URL."
            )

        verifier = (verification_code or "").strip()
        if not verifier:
            raise Exception("Verification code is required")

        consumer_key, consumer_secret = self._consumer()
        saved_sandbox = bool(material.get("sandbox", True))
        _, hosts = self._sandbox_and_hosts(sandbox=saved_sandbox)
        token_url = hosts["access_token_url"]

        # Reconstruct — do not touch any pickled session._client.
        session = reconstruct_oauth1_session(
            consumer_key,
            consumer_secret,
            material["resource_owner_key"],
            material["resource_owner_secret"],
            verifier,
        )
        try:
            logger.info("Exchanging verification code for access tokens at %s", token_url)
            tokens = session.fetch_access_token(token_url)
        except AttributeError as exc:
            raise Exception(
                "OAuth session was not reconstructed (pickle _client bug). Re-initiate OAuth."
            ) from exc
        finally:
            try:
                session.close()
            except Exception:
                pass
            self.session = None
            self.oauth = None

        access_token = tokens.get("oauth_token") if isinstance(tokens, dict) else None
        access_token_secret = tokens.get("oauth_token_secret") if isinstance(tokens, dict) else None
        if not access_token or not access_token_secret:
            raise Exception("Access token response missing oauth_token fields")

        save_access_token_material(access_token, access_token_secret)
        os.environ["ETRADE_ACCESS_TOKEN"] = access_token
        os.environ["ETRADE_ACCESS_TOKEN_SECRET"] = access_token_secret
        clear_request_token_material()

        self.is_authenticated = True
        self.last_auth_time = datetime.now(timezone.utc)
        self.token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        self.request_token = None
        logger.info("OAuth flow completed successfully")
        return True

    def load_cached_tokens(self) -> bool:
        (
            _,
            _,
            load_access_token_material,
            _,
            _,
            _,
            _,
        ) = _store()
        tokens = load_access_token_material()
        if not tokens:
            logger.info("No cached access tokens found")
            return False
        os.environ["ETRADE_ACCESS_TOKEN"] = tokens["access_token"]
        os.environ["ETRADE_ACCESS_TOKEN_SECRET"] = tokens["access_token_secret"]
        self.is_authenticated = True
        saved = tokens.get("saved_time")
        self.last_auth_time = saved
        logger.info("Cached access tokens loaded")
        return True

    def get_status(self) -> dict:
        needs_refresh = False
        if self.token_expiry:
            needs_refresh = datetime.now(timezone.utc) > self.token_expiry
        return {
            "is_authenticated": self.is_authenticated,
            "auth_time": self.last_auth_time.isoformat() if hasattr(self.last_auth_time, "isoformat") else self.last_auth_time,
            "expiry_time": self.token_expiry.isoformat() if self.token_expiry else None,
            "needs_refresh": needs_refresh,
            "status": "authenticated" if self.is_authenticated else "unauthenticated",
        }
