"""AhanaZip artifact compress/pack adapter (optional, private stack).

Import-or-stub: if the `ahanazip` package is not installed, or AHANAZIP_DIR
is unset, log and no-op. This public tree never vendors AhanaZip source.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

DIR_ENV = "AHANAZIP_DIR"

_mod = None
try:
    import ahanazip as _mod  # type: ignore
    logger.info("AhanaZip adapter: package present")
except ImportError:
    logger.info("AhanaZip adapter: package not installed; compress/pack is a no-op stub")
    _mod = None


def available() -> bool:
    return _mod is not None


def enabled() -> bool:
    return bool((os.getenv(DIR_ENV) or "").strip()) and available()


def pack_artifact(path: str, dest: Optional[str] = None) -> Optional[str]:
    """Compress/pack an artifact. No-op when gated off or missing."""
    if not enabled():
        logger.debug("AhanaZip stub: pack_artifact no-op path=%s", path)
        return None
    fn = getattr(_mod, "pack_artifact", None) or getattr(_mod, "pack", None) or getattr(_mod, "compress", None)
    if fn is None:
        logger.debug("AhanaZip present but no pack API; no-op")
        return None
    try:
        if dest is not None:
            return fn(path, dest)
        return fn(path)
    except Exception:
        logger.warning("AhanaZip pack_artifact failed; continuing")
        return None


def unpack_artifact(path: str, dest: Optional[str] = None) -> Optional[Any]:
    if not enabled():
        logger.debug("AhanaZip stub: unpack_artifact no-op path=%s", path)
        return None
    fn = getattr(_mod, "unpack_artifact", None) or getattr(_mod, "unpack", None) or getattr(_mod, "decompress", None)
    if fn is None:
        return None
    try:
        if dest is not None:
            return fn(path, dest)
        return fn(path)
    except Exception:
        logger.warning("AhanaZip unpack_artifact failed; continuing")
        return None
