"""Persist E*TRADE OAuth request/access material as JSON (mode 0600).

Never pickle a live OAuth1Session. After Streamlit reload / pickle, the
session has no _client and pyetrade get_access_token AttributeErrors.
JSON request-token fields are the source of truth for verifier exchange.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REQUEST_TOKEN_FIELDS = (
    "resource_owner_key",
    "resource_owner_secret",
    "authorize_url",
    "sandbox",
)


def secrets_dir() -> Path:
    override = os.getenv("ETRADE_SECRETS_DIR")
    if override:
        return Path(os.path.expanduser(override))
    return Path.home() / ".secrets"


def request_token_store_path() -> Path:
    override = os.getenv("ETRADE_OAUTH_STATE_FILE")
    if override:
        return Path(os.path.expanduser(override))
    return secrets_dir() / "etrade_oauth_request.json"


def access_token_store_path() -> Path:
    override = os.getenv("ETRADE_ACCESS_TOKEN_FILE")
    if override:
        return Path(os.path.expanduser(override))
    return secrets_dir() / "etrade_oauth_tokens.json"


def write_secret_json(path: Path, payload: dict) -> None:
    dest = Path(path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(dest.parent, 0o700)
    except OSError:
        pass
    data = json.dumps(payload, indent=2).encode("utf-8")
    fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def read_secret_json(path: Path) -> Optional[dict]:
    dest = Path(path).expanduser()
    if not dest.is_file():
        return None
    try:
        with open(dest, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read JSON %s: %s", dest, type(exc).__name__)
        return None
    return payload if isinstance(payload, dict) else None


def save_request_token_material(material: dict) -> Path:
    missing = [key for key in REQUEST_TOKEN_FIELDS if key not in material]
    if missing:
        raise ValueError("request token material missing: %s" % ", ".join(missing))
    path = request_token_store_path()
    write_secret_json(
        path,
        {
            "resource_owner_key": material["resource_owner_key"],
            "resource_owner_secret": material["resource_owner_secret"],
            "authorize_url": material["authorize_url"],
            "sandbox": bool(material["sandbox"]),
        },
    )
    logger.info("Saved E*TRADE request-token material to %s", path)
    return path


def load_request_token_material() -> Optional[dict]:
    data = read_secret_json(request_token_store_path())
    if not data:
        return None
    if not data.get("resource_owner_key") or not data.get("resource_owner_secret"):
        return None
    return data


def clear_request_token_material() -> None:
    path = request_token_store_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        logger.debug("Could not clear request-token file: %s", type(exc).__name__)


def save_access_token_material(access_token: str, access_token_secret: str) -> Path:
    path = access_token_store_path()
    write_secret_json(
        path,
        {
            "access_token": access_token,
            "access_token_secret": access_token_secret,
            "saved_time": datetime.now(timezone.utc).isoformat(),
        },
    )
    logger.info("Saved E*TRADE access tokens to %s", path)
    return path


def load_access_token_material() -> Optional[dict]:
    data = read_secret_json(access_token_store_path())
    if not data:
        return None
    if not data.get("access_token") or not data.get("access_token_secret"):
        return None
    return data
