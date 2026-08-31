"""E*TRADE environment, hosts, and credential loading.

Credentials come ONLY from the process environment or a gitignored file.
Never hardcode consumer keys/secrets. Never log secret values.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

SANDBOX_HOST = "https://apisb.etrade.com"
PRODUCTION_HOST = "https://api.etrade.com"
SANDBOX_API_V1 = "https://apisb.etrade.com/v1"
PRODUCTION_API_V1 = "https://api.etrade.com/v1"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"

# Filenames that MUST stay gitignored.
GITIGNORED_ENV_FILENAMES = (
    "etrade.env",
    ".secrets/etrade.env",
)

_DEFAULT_ENV_CANDIDATES = (
    os.getenv("ETRADE_ENV_FILE"),
    "/home/box/.secrets/etrade.env",
    str(Path.home() / ".secrets" / "etrade.env"),
    str(Path.cwd() / "etrade.env"),
    str(Path.cwd() / "config" / "etrade.env"),
    str(Path.cwd() / ".env"),
)


def _parse_env_file(path: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key.startswith("ETRADE_"):
                    parsed[key] = value
    except OSError as exc:
        logger.debug("Could not read env file %s: %s", path, type(exc).__name__)
    return parsed


def load_etrade_env(extra_paths: Optional[Iterable[str]] = None) -> None:
    """Load ETRADE_* keys from gitignored env files if they are not already set."""
    candidates = list(_DEFAULT_ENV_CANDIDATES)
    if extra_paths:
        candidates.extend(extra_paths)
    seen = set()
    for raw_path in candidates:
        if not raw_path:
            continue
        path = os.path.expanduser(raw_path)
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        parsed = _parse_env_file(path)
        loaded = 0
        for key, value in parsed.items():
            if key not in os.environ or os.environ.get(key, "") == "":
                os.environ[key] = value
                loaded += 1
        if loaded:
            logger.info("Loaded %s E*TRADE env key(s) from %s", loaded, path)


def is_sandbox() -> bool:
    """True unless ETRADE_ENV=production (or legacy ETRADE_SANDBOX=false)."""
    env = (os.getenv("ETRADE_ENV") or "").strip().lower()
    if env in ("production", "prod", "live"):
        return False
    if env in ("sandbox", "sb", "dev"):
        return True
    sandbox_flag = os.getenv("ETRADE_SANDBOX")
    if sandbox_flag is not None and sandbox_flag != "":
        return sandbox_flag.strip().lower() in ("1", "true", "yes", "on")
    return True


def etrade_hosts(sandbox: Optional[bool] = None) -> Dict[str, str]:
    sandbox = is_sandbox() if sandbox is None else sandbox
    host = SANDBOX_HOST if sandbox else PRODUCTION_HOST
    api_v1 = SANDBOX_API_V1 if sandbox else PRODUCTION_API_V1
    return {
        "host": host,
        "api_v1": api_v1,
        "request_token_url": f"{host}/oauth/request_token",
        "access_token_url": f"{host}/oauth/access_token",
        "authorize_url": AUTHORIZE_URL,
        "renew_token_url": f"{host}/oauth/renew_access_token",
        "revoke_token_url": f"{host}/oauth/revoke_access_token",
        "environment": "sandbox" if sandbox else "production",
    }


def extended_hours_opt_in() -> bool:
    """After-hours is part of the desk session (16:00–20:00 ET). Always on."""
    flag = (os.getenv("ETRADE_EXTENDED_HOURS") or "true").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return True


def allow_market_orders() -> bool:
    """Desk is LIMIT-only. Market orders are never enabled."""
    return False


@dataclass(frozen=True)
class ETradeCredentials:
    consumer_key: str
    consumer_secret: str
    access_token: str = ""
    access_token_secret: str = ""
    sandbox: bool = True

    @property
    def has_consumer(self) -> bool:
        return bool(self.consumer_key and self.consumer_secret)

    @property
    def has_access_tokens(self) -> bool:
        return bool(self.access_token and self.access_token_secret)


def load_credentials(load_files: bool = True) -> ETradeCredentials:
    """Read consumer + access tokens from env (and optional gitignored files)."""
    if load_files:
        load_etrade_env()
    return ETradeCredentials(
        consumer_key=os.getenv("ETRADE_CONSUMER_KEY", "") or "",
        consumer_secret=os.getenv("ETRADE_CONSUMER_SECRET", "") or "",
        access_token=os.getenv("ETRADE_ACCESS_TOKEN", "") or "",
        access_token_secret=os.getenv("ETRADE_ACCESS_TOKEN_SECRET", "") or "",
        sandbox=is_sandbox(),
    )


def credentials_from_json(payload: dict) -> Tuple[str, str]:
    """Extract consumer key/secret from a gitignored credentials JSON, if present."""
    oauth = (payload or {}).get("etrade", {}).get("oauth", {})
    return (
        str(oauth.get("consumer_key") or ""),
        str(oauth.get("consumer_secret") or ""),
    )
