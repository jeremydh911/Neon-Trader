"""
AhanaFlow compressed RAG memory for Neon Trader / Tim.

Modes (AHANAFLOW_MODE):
  selfhosted  — TCP client → local VectorStateServerV2 (preferred for Neon Trader)
  embedded    — in-process VectorStateEngineV2 from vendor/AhanaFlow
  auto        — try selfhosted, fall back to embedded (default)

Remote cloud API (Grok build) can plug in later as AHANAFLOW_MODE=remote.

Docs: https://www.ahanaflow.com  ·  https://github.com/AhanaAi-Company/AhanaFlow
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

TIM_COLLECTION = os.getenv("AHANAFLOW_COLLECTION", "tim_memory")
TIM_DIM = int(os.getenv("AHANAFLOW_EMBED_DIM", "128"))
AHANAFLOW_ROOT = Path(__file__).resolve().parents[2] / "vendor" / "AhanaFlow"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_embed(text: str, dim: int = TIM_DIM) -> List[float]:
    """Deterministic bag-of-tokens embedding (no external model required)."""
    tokens = (text or "").lower().split()
    if not tokens:
        tokens = ["_empty_"]
    vec = [0.0] * dim
    for i, tok in enumerate(tokens):
        digest = hashlib.sha256(f"{i}:{tok}".encode()).digest()
        for j in range(dim):
            b = digest[j % len(digest)]
            vec[j] += ((b / 255.0) * 2 - 1) / (1.0 + i * 0.15)
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _ensure_ahanaflow_path() -> bool:
    root = str(AHANAFLOW_ROOT)
    if AHANAFLOW_ROOT.is_dir() and root not in sys.path:
        sys.path.insert(0, root)
    return AHANAFLOW_ROOT.is_dir()


def _decode_payload(payload: Any) -> Any:
    """Expand AhanaFlow compress_results blobs back to original payload."""
    if not isinstance(payload, dict):
        return payload
    if not payload.get("compressed"):
        return payload.get("payload", payload)
    data_b64 = payload.get("data")
    if not data_b64:
        return payload
    try:
        _ensure_ahanaflow_path()
        from backend.vector_server.codec import decompress  # type: ignore

        raw = decompress(base64.b64decode(data_b64))
        try:
            return json.loads(raw)
        except Exception:
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("payload decompress failed: %s", e)
        return payload


def _payload_text(payload: Any) -> str:
    decoded = _decode_payload(payload)
    if isinstance(decoded, dict):
        return str(decoded.get("text") or decoded.get("content") or decoded)
    return str(decoded or "")


def _resolve_mode() -> str:
    mode = (os.getenv("AHANAFLOW_MODE") or "auto").strip().lower()
    if mode in ("server", "local", "self-hosted", "self_hosted"):
        return "selfhosted"
    if mode in ("inprocess", "in-process", "embed"):
        return "embedded"
    if mode in ("cloud", "api"):
        return "remote"
    return mode if mode in ("selfhosted", "embedded", "auto", "remote") else "auto"


class AhanaFlowMemory:
    """
    Compression-native RAG memory.

    Preferred: self-hosted AhanaFlow vector server (data stays on your box).
    Fallback: embedded VectorStateEngineV2 from vendor/.
    """

    def __init__(
        self,
        wal_path: Optional[Union[str, Path]] = None,
        collection: str = TIM_COLLECTION,
        dimensions: int = TIM_DIM,
        mode: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self.collection = collection
        self.dimensions = dimensions
        self.engine = None
        self.client = None
        self._backend = "ahanaflow"

        chosen = (mode or _resolve_mode()).lower()
        if chosen in ("server", "local", "self-hosted", "self_hosted"):
            chosen = "selfhosted"
        if chosen in ("inprocess", "embed"):
            chosen = "embedded"

        errors: List[str] = []

        if chosen in ("selfhosted", "auto"):
            try:
                self._init_selfhosted(host=host, port=port)
                return
            except Exception as e:
                errors.append(f"selfhosted: {e}")
                if chosen == "selfhosted":
                    raise
                logger.info("AhanaFlow selfhosted unavailable (%s) — trying embedded", e)

        if chosen in ("embedded", "auto"):
            try:
                self._init_embedded(wal_path=wal_path)
                return
            except Exception as e:
                errors.append(f"embedded: {e}")
                if chosen == "embedded":
                    raise

        if chosen == "remote":
            raise NotImplementedError(
                "AHANAFLOW_MODE=remote awaits the cloud API backend. "
                "Use selfhosted or embedded until then."
            )

        raise ImportError(
            "AhanaFlow memory could not start. Tried: " + "; ".join(errors)
        )

    def _init_selfhosted(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        from .ahanaflow_vector_client import AhanaFlowVectorClient

        self.client = AhanaFlowVectorClient(
            host=host or os.getenv("AHANAFLOW_HOST", "127.0.0.1"),
            port=int(port or os.getenv("AHANAFLOW_PORT", "9634")),
        )
        self.client.ping()
        try:
            self.client.create_collection(self.collection, self.dimensions, metric="cosine")
        except Exception:
            # collection may already exist
            pass
        self._backend = "ahanaflow-selfhosted"
        logger.info(
            "AhanaFlow memory ready mode=selfhosted collection=%s dim=%s %s:%s",
            self.collection,
            self.dimensions,
            self.client.host,
            self.client.port,
        )

    def _init_embedded(self, wal_path: Optional[Union[str, Path]] = None) -> None:
        if not _ensure_ahanaflow_path():
            raise ImportError(
                f"AhanaFlow vendor missing at {AHANAFLOW_ROOT}. "
                "Run: git submodule update --init vendor/AhanaFlow"
            )
        from backend.vector_server.engine import VectorStateEngineV2  # type: ignore

        root = Path(wal_path or os.getenv("AHANAFLOW_WAL", "./data/ahanaflow/tim_memory.wal"))
        root.parent.mkdir(parents=True, exist_ok=True)
        self.engine = VectorStateEngineV2(root)
        try:
            self.engine.create_collection(self.collection, self.dimensions, metric="cosine")
        except ValueError:
            pass
        self._backend = "ahanaflow-embedded"
        logger.info(
            "AhanaFlow memory ready mode=embedded collection=%s dim=%s wal=%s",
            self.collection,
            self.dimensions,
            root,
        )

    # --- backend ops ---

    def _upsert(
        self,
        mid: str,
        vector: List[float],
        meta: Dict[str, Any],
        payload: Dict[str, Any],
        ttl_seconds: Optional[int],
    ) -> None:
        if self.client is not None:
            self.client.upsert(
                self.collection,
                mid,
                vector,
                metadata=meta,
                payload=payload,
                ttl_seconds=ttl_seconds,
            )
            return
        assert self.engine is not None
        self.engine.upsert(
            self.collection,
            mid,
            vector,
            metadata=meta,
            payload=payload,
            ttl_seconds=ttl_seconds,
        )

    def _query(
        self,
        vector: List[float],
        top_k: int,
        compress: bool,
    ) -> List[Dict[str, Any]]:
        if self.client is not None:
            raw = self.client.query(
                self.collection,
                vector,
                top_k=top_k,
                compress_results=compress,
                strategy="exact",
            )
        else:
            assert self.engine is not None
            raw = self.engine.query(
                self.collection,
                vector,
                top_k=top_k,
                filters=None,
                compress_results=compress,
                strategy="exact",
            )
        if isinstance(raw, dict):
            return list(raw.get("hits") or raw.get("results") or [])
        return list(raw or [])

    def _scan(self, limit: int) -> List[Dict[str, Any]]:
        if self.client is not None:
            return self.client.scan(self.collection, limit=limit)
        assert self.engine is not None
        return self.engine.scan(self.collection, limit=limit)

    def _stats_raw(self) -> Dict[str, Any]:
        if self.client is not None:
            return self.client.stats()
        assert self.engine is not None
        s = self.engine.stats()
        return {
            "collections": getattr(s, "collections", None),
            "vectors": getattr(s, "vectors", None),
            "wal_size_bytes": getattr(s, "wal_size_bytes", None),
            "records_replayed": getattr(s, "records_replayed", None),
        }

    # --- write ---

    def remember(
        self,
        content: str,
        *,
        kind: str = "note",
        symbol: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        council_votes: Optional[Dict[str, Any]] = None,
        outcome: Optional[str] = None,
    ) -> str:
        mid = memory_id or f"m_{uuid.uuid4().hex[:12]}"
        meta: Dict[str, Any] = {
            "kind": kind,
            "type": kind,
            "symbol": (symbol or "").upper() or None,
            "tags": tags or [],
            "timestamp": _utc_now(),
            "outcome": outcome,
            **(metadata or {}),
        }
        if council_votes is not None:
            meta["council_votes"] = council_votes
        meta = {k: v for k, v in meta.items() if v is not None}
        vector = _hash_embed(content, self.dimensions)
        self._upsert(mid, vector, meta, {"text": content, "kind": kind}, ttl_seconds)
        return mid

    def add_discussion(
        self,
        content: str,
        council_votes: Optional[Dict[str, str]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        return self.remember(
            content, kind="discussion", tags=tags, council_votes=council_votes
        )

    def add_decision(
        self,
        content: str,
        outcome: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        decision: Optional[Dict[str, Any]] = None,
    ) -> str:
        decision = decision or {}
        meta = {
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
            "reason": decision.get("reason"),
            **(metadata or {}),
        }
        return self.remember(
            content,
            kind="decision",
            symbol=decision.get("symbol"),
            tags=tags,
            outcome=outcome,
            metadata=meta,
        )

    def add_trade_result(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        exit_price: Optional[float],
        outcome: str,
        pnl: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        content = (
            f"{action} {symbol} entry={entry_price} exit={exit_price} "
            f"outcome={outcome} pnl={pnl}"
        )
        return self.remember(
            content,
            kind="trade_result",
            symbol=symbol,
            tags=tags or [symbol, action, outcome],
            outcome=outcome,
            metadata={
                "action": action,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "symbol": symbol.upper(),
                **(metadata or {}),
            },
        )

    # --- read ---

    def _hit_to_entry(self, h: Dict[str, Any], score: Optional[float] = None):
        from .rag_memory import MemoryEntry

        meta = h.get("metadata") or {}
        text = _payload_text(h.get("payload"))
        kind = meta.get("kind") or meta.get("type") or "note"
        return MemoryEntry(
            id=str(h.get("id") or ""),
            timestamp=str(meta.get("timestamp") or _utc_now()),
            type=kind,
            content=text,
            metadata=meta,
            council_votes=meta.get("council_votes"),
            outcome=meta.get("outcome"),
            relevance_score=float(score if score is not None else h.get("score") or 0.0),
            tags=list(meta.get("tags") or []),
        )

    def search(
        self,
        query: str,
        limit: int = 5,
        time_limit: Optional[int] = None,
        memory_type: Optional[str] = None,
        *,
        top_k: Optional[int] = None,
        symbol: Optional[str] = None,
        kind: Optional[str] = None,
        compress: bool = True,
    ) -> List[Any]:
        k = int(top_k or limit or 5)
        mt = kind or memory_type
        vector = _hash_embed(query, self.dimensions)
        hits = self._query(
            vector,
            top_k=max(k * 3, k) if time_limit or symbol or mt else k,
            compress=compress,
        )
        cutoff = None
        if time_limit:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=time_limit)).isoformat()

        out = []
        for h in hits or []:
            meta = h.get("metadata") or {}
            if symbol and (meta.get("symbol") or "").upper() != symbol.upper():
                continue
            if mt and meta.get("kind") != mt and meta.get("type") != mt:
                continue
            ts = meta.get("timestamp") or ""
            if cutoff and ts and ts < cutoff:
                continue
            out.append(self._hit_to_entry(h))
            if len(out) >= k:
                break
        return out

    def search_by_tags(self, tags: List[str], limit: int = 20) -> List[Any]:
        rows = self._scan(max(limit * 5, 50))
        tagset = set(tags or [])
        matched = []
        for row in rows:
            meta = row.get("metadata") or {}
            row_tags = set(meta.get("tags") or [])
            if tagset & row_tags:
                matched.append(self._hit_to_entry(row, score=1.0))
            if len(matched) >= limit:
                break
        return matched

    def get_recent_decisions(self, limit: int = 5) -> List[Any]:
        rows = self._scan(max(limit * 10, 50))
        decisions = [
            self._hit_to_entry(r, score=1.0)
            for r in rows
            if (r.get("metadata") or {}).get("kind") == "decision"
        ]
        decisions.sort(key=lambda m: m.timestamp, reverse=True)
        return decisions[:limit]

    def get_successful_trades(self, symbol: Optional[str] = None) -> List[Any]:
        rows = self._scan(500)
        out = []
        for r in rows:
            meta = r.get("metadata") or {}
            if meta.get("kind") != "trade_result" or meta.get("outcome") != "WIN":
                continue
            if symbol and meta.get("symbol") != symbol.upper():
                continue
            out.append(self._hit_to_entry(r, score=1.0))
        return out

    def get_failed_trades(self, symbol: Optional[str] = None) -> List[Any]:
        rows = self._scan(500)
        out = []
        for r in rows:
            meta = r.get("metadata") or {}
            if meta.get("kind") != "trade_result" or meta.get("outcome") != "LOSS":
                continue
            if symbol and meta.get("symbol") != symbol.upper():
                continue
            out.append(self._hit_to_entry(r, score=1.0))
        return out

    def get_symbol_history(self, symbol: str) -> Dict[str, Any]:
        rows = self._scan(500)
        trades = []
        for r in rows:
            meta = r.get("metadata") or {}
            if meta.get("kind") == "trade_result" and meta.get("symbol") == symbol.upper():
                trades.append(self._hit_to_entry(r, score=1.0))
        wins = len([t for t in trades if t.outcome == "WIN"])
        losses = len([t for t in trades if t.outcome == "LOSS"])
        total_pnl = sum(float((t.metadata or {}).get("pnl") or 0) for t in trades)
        return {
            "symbol": symbol.upper(),
            "total_trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(trades) if trades else 0,
            "total_pnl": total_pnl,
            "trades": trades,
        }

    def recall_context(self, query: str, top_k: int = 4, symbol: Optional[str] = None) -> str:
        hits = self.search(query, limit=top_k, symbol=symbol, compress=True)
        if not hits:
            return ""
        lines = ["[AhanaFlow compressed memory]"]
        for h in hits:
            sym = (h.metadata or {}).get("symbol") or "—"
            lines.append(f"- ({h.type}|{sym}|score={h.relevance_score:.3f}) {h.content}")
        return "\n".join(lines)

    def get_memory_summary(self) -> Dict[str, Any]:
        s = self.stats()
        rows = self._scan(2000)
        kinds = {"discussion": 0, "decision": 0, "trade_result": 0, "note": 0}
        stamps = []
        for r in rows:
            meta = r.get("metadata") or {}
            k = meta.get("kind") or "note"
            kinds[k] = kinds.get(k, 0) + 1
            if meta.get("timestamp"):
                stamps.append(meta["timestamp"])
        return {
            "total_memories": len(rows),
            "discussions": kinds.get("discussion", 0),
            "decisions": kinds.get("decision", 0),
            "trades": kinds.get("trade_result", 0),
            "oldest_memory": min(stamps) if stamps else None,
            "newest_memory": max(stamps) if stamps else None,
            "backend": self._backend,
            "vectors": s.get("vectors"),
            "wal_size_bytes": s.get("wal_size_bytes"),
        }

    def stats(self) -> Dict[str, Any]:
        try:
            data = dict(self._stats_raw())
        except Exception as e:
            data = {"error": str(e)}
        data["backend"] = self._backend
        data["collection"] = self.collection
        data["dimensions"] = self.dimensions
        data["mode"] = "selfhosted" if self.client else "embedded"
        return data

    def get_memory_stats(self) -> Dict[str, Any]:
        return self.stats()

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        if self.engine is not None:
            try:
                self.engine.flush()
                self.engine.close()
            except Exception:
                pass


_STORE: Optional[Any] = None


def get_ahanaflow_memory(force_new: bool = False, **kwargs) -> AhanaFlowMemory:
    global _STORE
    if _STORE is not None and not force_new and not kwargs:
        return _STORE
    store = AhanaFlowMemory(**kwargs)
    if not kwargs:
        _STORE = store
    return store


def get_memory_store():
    """Preferred memory factory — AhanaFlow first, legacy fallback."""
    prefer = os.getenv("AHANAFLOW_MEMORY", "1").lower() not in ("0", "false", "no", "off")
    if prefer:
        try:
            return get_ahanaflow_memory()
        except Exception as e:
            logger.warning("AhanaFlow memory unavailable (%s) — using legacy RAG store", e)
    from .rag_memory import RAGMemoryStore

    return RAGMemoryStore()
