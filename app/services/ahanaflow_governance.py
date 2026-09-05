"""
Shared governance helpers for AhanaFlow memory (Neon Trader).

Centralizes collection naming, host policy, WAL jailing, and query caps so
client + memory + selfhost server enforce the same rules.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

# Collection / id: no path separators, no shell metacharacters
_COLLECTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Hard caps (override via env, but never above absolute max)
ABS_MAX_TOP_K = 100
ABS_MAX_SCAN = 5000
ABS_MAX_DIM = 4096


def env_truthy(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def validate_collection_name(name: str) -> str:
    if not name or not _COLLECTION_RE.match(name):
        raise ValueError(
            f"invalid AhanaFlow collection name {name!r}; "
            "use 1-64 chars: letter then [A-Za-z0-9_-]"
        )
    return name


def validate_item_id(item_id: str) -> str:
    if not item_id or len(item_id) > 128 or "/" in item_id or "\\" in item_id or "\n" in item_id:
        raise ValueError(f"invalid AhanaFlow item id {item_id!r}")
    return item_id


def assert_safe_client_host(host: str) -> None:
    """Refuse non-loopback hosts unless AHANAFLOW_ALLOW_REMOTE=1."""
    h = (host or "").strip().lower()
    if h in _LOOPBACK or h.startswith("127."):
        return
    if env_truthy("AHANAFLOW_ALLOW_REMOTE") or env_truthy("AHANAFLOW_ALLOW_PUBLIC"):
        return
    raise PermissionError(
        f"AhanaFlow client refuses non-loopback host {host!r}. "
        "Set AHANAFLOW_ALLOW_REMOTE=1 only with TLS/auth on a trusted network."
    )


def is_public_bind(host: str) -> bool:
    return (host or "").strip().lower() in ("0.0.0.0", "::", "[::]", "*")


def jail_wal_path(wal: str | Path, *, root: Optional[Path] = None) -> Path:
    """
    Resolve WAL under an allowlisted data root.
    Prevents --wal ../../etc/passwd style escapes.
    Relative paths with '..' are rejected; other relatives are resolved from cwd
    if already under the data root, otherwise placed as basename under the root.
    """
    data_root = (root or Path(os.getenv("AHANAFLOW_DATA_ROOT", "data/ahanaflow"))).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    raw = Path(wal).expanduser()

    if ".." in raw.parts:
        raise PermissionError(
            f"AHANAFLOW_WAL {wal!r} must not contain '..' path segments."
        )

    if raw.is_absolute():
        target = raw.resolve()
    else:
        cwd_candidate = (Path.cwd() / raw).resolve()
        try:
            cwd_candidate.relative_to(data_root)
            target = cwd_candidate
        except ValueError:
            # Keep only the filename under the jail (no nested relative escapes)
            if not raw.name or raw.name in (".", ".."):
                raise PermissionError(f"AHANAFLOW_WAL {wal!r} has empty filename")
            target = (data_root / raw.name).resolve()

    try:
        target.relative_to(data_root)
    except ValueError as e:
        raise PermissionError(
            f"AHANAFLOW_WAL {wal!r} escapes data root {data_root}. "
            "Place WALs under data/ahanaflow/ (or AHANAFLOW_DATA_ROOT)."
        ) from e
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def clamp_top_k(n: int) -> int:
    env_cap = int(os.getenv("AHANAFLOW_MAX_TOP_K", "50"))
    cap = max(1, min(env_cap, ABS_MAX_TOP_K))
    return max(1, min(int(n or 1), cap))


def clamp_scan_limit(n: int) -> int:
    env_cap = int(os.getenv("AHANAFLOW_MAX_SCAN", "1000"))
    cap = max(1, min(env_cap, ABS_MAX_SCAN))
    return max(1, min(int(n or 1), cap))


def clamp_dimensions(n: int) -> int:
    return max(1, min(int(n or 1), ABS_MAX_DIM))


def default_ttl_seconds(kind: str) -> Optional[int]:
    """
    Retention defaults (governance).
    Discussions/chat expire; decisions/trades persist unless overridden.
    """
    raw = os.getenv("AHANAFLOW_DEFAULT_TTL_SECONDS", "").strip()
    if raw.isdigit():
        return int(raw) or None
    # kind-specific defaults (seconds); 0 / unset = no TTL for decisions
    if kind in ("discussion", "note", "chat"):
        chat_ttl = os.getenv("AHANAFLOW_CHAT_TTL_SECONDS", str(7 * 24 * 3600))
        return int(chat_ttl) if chat_ttl.isdigit() and int(chat_ttl) > 0 else None
    return None
