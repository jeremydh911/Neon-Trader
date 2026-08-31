"""AhanaFlow store adapter (optional SDK + local gzip JSONL lookback).

The public SDK lives in AhanaAi-Company/AhanaFlow (`sdk/`). This public tree never vendors AhanaFlow source. When the `ahanaflow` package AND `AHANAFLOW_URL` are
present, records are duck-typed onto put/publish/store/get/query.

When the package is missing, lookback still works: gzip-compressed JSONL
under data/ahanaflow/ (gitignored). Never pickle.

License/token env (never logged): AHANAFLOW_LICENSE, AHANAFLOW_TOKEN.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

URL_ENV = "AHANAFLOW_URL"
LICENSE_ENVS = ("AHANAFLOW_LICENSE", "AHANAFLOW_TOKEN", "AHANAFLOW_API_KEY")
DATA_DIR_ENV = "AHANAFLOW_DATA_DIR"
RECORD_KINDS = (
    "plan",
    "alert",
    "fill",
    "quote",
    "council_note",
    "brain_note",
    "backtest",
    "session",
)

_mod = None
try:
    import ahanaflow as _mod  # type: ignore
    logger.info("AhanaFlow adapter: package present")
except ImportError:
    logger.info("AhanaFlow adapter: package not installed; using local gzip JSONL lookback")
    _mod = None


def available() -> bool:
    return _mod is not None


def enabled() -> bool:
    """Remote AhanaFlow is live only when the SDK is installed and a URL is set."""
    return bool((os.getenv(URL_ENV) or "").strip()) and available()


def data_dir() -> Path:
    raw = (os.getenv(DATA_DIR_ENV) or "").strip()
    if raw:
        path = Path(raw)
    else:
        root = Path(__file__).resolve().parents[3]
        path = root / "data" / "ahanaflow"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _records_path() -> Path:
    return data_dir() / "records.jsonl.gz"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _license() -> str:
    for key in LICENSE_ENVS:
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    return ""


def _normalize(record: Optional[Dict[str, Any]], kind: Optional[str] = None) -> Dict[str, Any]:
    rec = dict(record or {})
    rec_id = str(rec.get("id") or uuid.uuid4().hex[:16])
    rec_kind = str(kind or rec.get("kind") or rec.get("type") or "session").strip().lower()
    if rec_kind not in RECORD_KINDS:
        rec_kind = "session"
    payload = rec.get("payload")
    if payload is None:
        payload = {k: v for k, v in rec.items() if k not in {
            "id", "kind", "type", "ts", "timestamp", "symbol", "setup", "payload"
        }}
    return {
        "id": rec_id,
        "kind": rec_kind,
        "ts": str(rec.get("ts") or rec.get("timestamp") or _now_iso()),
        "symbol": str(rec.get("symbol") or "").upper(),
        "setup": str(rec.get("setup") or ""),
        "payload": payload if isinstance(payload, dict) else {"value": payload},
    }


def _local_append(rec: Dict[str, Any]) -> None:
    path = _records_path()
    line = json.dumps(rec, default=str) + "\n"
    with gzip.open(path, "at", encoding="utf-8") as handle:
        handle.write(line)


def _local_iter() -> Iterable[Dict[str, Any]]:
    path = _records_path()
    if not path.exists():
        return
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    yield rec
    except OSError:
        logger.warning("AhanaFlow local JSONL unreadable")
        return


def _duck(name: str, *alts: str):
    if _mod is None:
        return None
    for candidate in (name, *alts):
        fn = getattr(_mod, candidate, None)
        if callable(fn):
            return fn
        client = getattr(_mod, "client", None) or getattr(_mod, "Client", None)
        if client is not None:
            fn = getattr(client, candidate, None)
            if callable(fn):
                return fn
    return None


def _remote_put(rec: Dict[str, Any]) -> bool:
    if not enabled():
        return False
    try:
        from . import ahanazip
        blob = json.dumps(rec, default=str).encode("utf-8")
        packed = ahanazip.compress_blob(blob)
    except Exception:
        packed = None
    fn = _duck("put", "store", "publish", "upsert")
    if fn is None:
        logger.debug("AhanaFlow present but no put/store API; local only")
        return False
    try:
        kwargs = {"url": (os.getenv(URL_ENV) or "").strip()}
        license_key = _license()
        if license_key:
            kwargs["license"] = license_key
        try:
            fn(rec, **kwargs)
        except TypeError:
            try:
                fn(rec["id"], packed if packed is not None else rec)
            except TypeError:
                fn(rec)
        return True
    except Exception:
        logger.warning("AhanaFlow remote put failed; local lookback kept")
        return False


def put(record: Optional[Dict[str, Any]] = None, *, kind: Optional[str] = None) -> str:
    """Persist a record. Always writes local gzip JSONL; remotes if SDK+URL set."""
    rec = _normalize(record, kind=kind)
    _local_append(rec)
    _remote_put(rec)
    return rec["id"]


def get(record_id: str) -> Optional[Dict[str, Any]]:
    rid = str(record_id or "")
    if not rid:
        return None
    if enabled():
        fn = _duck("get", "fetch", "get_memory")
        if fn is not None:
            try:
                remote = fn(rid)
                if isinstance(remote, dict):
                    return remote
                if remote is not None:
                    try:
                        from . import ahanazip
                        raw = ahanazip.decompress_blob(remote if isinstance(remote, (bytes, bytearray)) else str(remote).encode("utf-8"))
                        parsed = json.loads(raw.decode("utf-8"))
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        pass
            except Exception:
                logger.warning("AhanaFlow remote get failed; trying local")
    for rec in _local_iter() or []:
        if rec.get("id") == rid:
            return rec
    return None


def query(
    *,
    kind: Optional[str] = None,
    symbol: Optional[str] = None,
    setup: Optional[str] = None,
    keyword: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Filter lookback records. Remote query if available, else local JSONL."""
    if enabled():
        fn = _duck("query", "search", "find")
        if fn is not None:
            try:
                remote = fn(
                    kind=kind, symbol=symbol, setup=setup,
                    keyword=keyword, since=since, until=until, limit=limit,
                )
                if isinstance(remote, list):
                    return [r for r in remote if isinstance(r, dict)][: max(int(limit), 0)]
            except TypeError:
                try:
                    remote = fn({"kind": kind, "symbol": symbol, "setup": setup})
                    if isinstance(remote, list):
                        return [r for r in remote if isinstance(r, dict)][: max(int(limit), 0)]
                except Exception:
                    logger.debug("AhanaFlow remote query signature mismatch")
            except Exception:
                logger.warning("AhanaFlow remote query failed; using local")
    needle = (keyword or "").strip().lower()
    sym = (symbol or "").strip().upper()
    kind_n = (kind or "").strip().lower()
    setup_n = (setup or "").strip()
    out: List[Dict[str, Any]] = []
    for rec in _local_iter() or []:
        if kind_n and str(rec.get("kind") or "") != kind_n:
            continue
        if sym and str(rec.get("symbol") or "").upper() != sym:
            continue
        if setup_n and str(rec.get("setup") or "") != setup_n:
            continue
        ts = str(rec.get("ts") or "")
        if since and ts < since:
            continue
        if until and ts > until:
            continue
        if needle:
            blob = json.dumps(rec, default=str).lower()
            if needle not in blob:
                continue
        out.append(rec)
    out.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    return out[: max(int(limit or 0), 0)]


def list_range(since: Optional[str] = None, until: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    return query(since=since, until=until, limit=limit)


def publish_session(topic: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Publish a session/memory event. Always stored locally for lookback."""
    rec_id = put({"kind": "session", "payload": {"topic": topic, **(payload or {})}})
    if not enabled():
        logger.debug("AhanaFlow stub: publish_session local-only topic=%s id=%s", topic, rec_id)
        return bool(rec_id)
    return True


def get_memory(key: str) -> Optional[Any]:
    hit = get(key)
    if hit is not None:
        return hit
    rows = query(keyword=key, limit=1)
    return rows[0] if rows else None
