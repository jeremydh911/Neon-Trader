"""Chatwire / Cloud Wire compressed agent message transport (optional).

Import-or-stub: tries `chatwire` then `cloudwire`. If neither package is
installed, or CHATWIRE_URL / CLOUDWIRE_URL is unset, log and no-op.
Do not vendor Chatwire source into this public tree.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

URL_ENVS = ("CHATWIRE_URL", "CLOUDWIRE_URL")

_mod = None
_name = None
for _pkg in ("chatwire", "cloudwire"):
    try:
        _mod = __import__(_pkg)
        _name = _pkg
        logger.info("Chatwire adapter: %s package present", _pkg)
        break
    except ImportError:
        continue
if _mod is None:
    logger.info("Chatwire adapter: package not installed; transport is a no-op stub")


def available() -> bool:
    return _mod is not None


def enabled() -> bool:
    if not available():
        return False
    return any((os.getenv(k) or "").strip() for k in URL_ENVS)


def send_message(topic: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Send a compressed agent message. No-op when gated off or missing."""
    if not enabled():
        logger.debug("Chatwire stub: send_message no-op topic=%s", topic)
        return False
    payload = payload or {}
    fn = (
        getattr(_mod, "send_message", None)
        or getattr(_mod, "send", None)
        or getattr(_mod, "publish", None)
    )
    if fn is None:
        logger.debug("Chatwire present but no send API; no-op")
        return False
    try:
        fn(topic, payload)
        return True
    except Exception:
        logger.warning("Chatwire send_message failed; continuing")
        return False
