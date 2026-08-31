"""AhanaFlow session/memory bus adapter (optional, private stack).

Import-or-stub: if the `ahanaflow` package is not installed, or AHANAFLOW_URL
is unset, log and no-op. This public tree never vendors AhanaFlow source.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

URL_ENV = "AHANAFLOW_URL"

_mod = None
try:
    import ahanaflow as _mod  # type: ignore
    logger.info("AhanaFlow adapter: package present")
except ImportError:
    logger.info("AhanaFlow adapter: package not installed; session/memory bus is a no-op stub")
    _mod = None


def available() -> bool:
    return _mod is not None


def enabled() -> bool:
    return bool((os.getenv(URL_ENV) or "").strip()) and available()


def publish_session(topic: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Publish a session/memory event. No-op when gated off or missing."""
    if not enabled():
        logger.debug("AhanaFlow stub: publish_session no-op topic=%s", topic)
        return False
    payload = payload or {}
    fn = getattr(_mod, "publish_session", None) or getattr(_mod, "publish", None)
    if fn is None:
        logger.debug("AhanaFlow present but no publish API; no-op")
        return False
    try:
        fn(topic, payload)
        return True
    except Exception:
        logger.warning("AhanaFlow publish_session failed; continuing")
        return False


def get_memory(key: str) -> Optional[Any]:
    if not enabled():
        logger.debug("AhanaFlow stub: get_memory no-op key=%s", key)
        return None
    fn = getattr(_mod, "get_memory", None) or getattr(_mod, "get", None)
    if fn is None:
        return None
    try:
        return fn(key)
    except Exception:
        logger.warning("AhanaFlow get_memory failed; continuing")
        return None
