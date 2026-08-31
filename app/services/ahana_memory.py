"""Thin RAG memory facade over the AhanaFlow store.

Ingests desk records (plans, alerts, fills, quotes, brain/council notes) and
retrieves top-k by symbol / setup / time / keyword. This is a lookback layer
only — not a second trading brain.

Hash-embed is used when sentence-transformers is unavailable. Persistence
goes through adapters.ahanaflow (remote SDK or local gzip JSONL).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EMBED_DIM = 64


def _tokens(text: str) -> List[str]:
    return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split() if t]


def hash_embed(text: str, dim: int = EMBED_DIM) -> List[float]:
    vec = [0.0] * dim
    toks = _tokens(text)
    if not toks:
        return vec
    for tok in toks:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dim
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
    mag = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / mag for v in vec]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def _record_text(rec: Dict[str, Any]) -> str:
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    parts = [
        rec.get("symbol") or "",
        rec.get("setup") or "",
        rec.get("kind") or "",
        payload.get("why") or payload.get("plan") or payload.get("note") or "",
        payload.get("side") or "",
        json.dumps(payload, default=str)[:800],
    ]
    return " ".join(str(p) for p in parts if p)


class AhanaMemory:
    """Memory layer for the desk and CoS. Does not place orders."""

    def ingest(self, record: Dict[str, Any], *, kind: Optional[str] = None) -> str:
        from .adapters import ahanaflow

        rec = dict(record or {})
        if kind:
            rec["kind"] = kind
        rec_id = ahanaflow.put(rec)
        logger.debug("AhanaMemory ingest %s kind=%s", rec_id, rec.get("kind"))
        return rec_id

    def retrieve(
        self,
        *,
        symbol: Optional[str] = None,
        setup: Optional[str] = None,
        keyword: Optional[str] = None,
        kind: Optional[str] = None,
        since: Optional[str] = None,
        k: int = 5,
        query_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from .adapters import ahanaflow

        rows = ahanaflow.query(
            kind=kind,
            symbol=symbol,
            setup=setup,
            keyword=keyword,
            since=since,
            limit=max(int(k) * 8, 20),
        )
        needle = query_text or " ".join(p for p in (symbol, setup, keyword) if p)
        if not needle:
            return rows[: max(int(k), 0)]
        qv = hash_embed(needle)
        scored = []
        for rec in rows:
            rec = dict(rec)
            rec["_score"] = cosine(qv, hash_embed(_record_text(rec)))
            scored.append(rec)
        scored.sort(key=lambda r: float(r.get("_score") or 0.0), reverse=True)
        return scored[: max(int(k), 0)]

    def similar_setups(self, symbol: str, setup: str, why: str = "", k: int = 3) -> List[Dict[str, Any]]:
        return self.retrieve(
            symbol=symbol,
            setup=setup,
            kind="plan",
            query_text=f"{symbol} {setup} {why}",
            k=k,
        )


_memory: Optional[AhanaMemory] = None


def get_ahana_memory() -> AhanaMemory:
    global _memory
    if _memory is None:
        _memory = AhanaMemory()
    return _memory
