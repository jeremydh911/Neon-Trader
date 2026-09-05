"""
Thin TCP client for a self-hosted AhanaFlow VectorStateServerV2.

Protocol: newline-delimited JSON over TCP (default 127.0.0.1:9634).
Commands: PING, VECTOR_CREATE, VECTOR_UPSERT, VECTOR_QUERY, VECTOR_SCAN, VECTOR_STATS, …

This is the preferred Neon Trader path — memory stays on your box, not a vendor cloud.
Grok's remote API backend can still be plugged in later via AHANAFLOW_MODE=remote.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_HOST = os.getenv("AHANAFLOW_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("AHANAFLOW_PORT", "9634"))
DEFAULT_TIMEOUT = float(os.getenv("AHANAFLOW_TIMEOUT", "5.0"))


class AhanaFlowVectorClient:
    """Synchronous NDJSON TCP client for AhanaFlow vector server."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        api_key: Optional[str] = None,
        auto_reconnect: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.api_key = api_key or os.getenv("AHANAFLOW_API_KEY")
        self.auto_reconnect = auto_reconnect
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._connect()

    def _connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self._sock = sock
        logger.info("AhanaFlow vector client connected %s:%s", self.host, self.port)

    def _ensure(self) -> socket.socket:
        if self._sock is None:
            if not self.auto_reconnect:
                raise ConnectionError("AhanaFlow vector client not connected")
            self._connect()
        assert self._sock is not None
        return self._sock

    def close(self) -> None:
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    def request(self, cmd: str, **fields: Any) -> Any:
        payload: Dict[str, Any] = {"cmd": cmd, **fields}
        if self.api_key:
            payload["api_key"] = self.api_key
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            sock = self._ensure()
            try:
                sock.sendall(line)
                buf = b""
                while b"\n" not in buf:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("AhanaFlow vector server closed connection")
                    buf += chunk
            except OSError:
                self._sock = None
                if self.auto_reconnect:
                    sock = self._ensure()
                    sock.sendall(line)
                    buf = b""
                    while b"\n" not in buf:
                        chunk = sock.recv(65536)
                        if not chunk:
                            raise ConnectionError("AhanaFlow vector server closed connection")
                        buf += chunk
                else:
                    raise
        raw = buf.split(b"\n", 1)[0]
        try:
            resp = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"invalid AhanaFlow response: {raw[:200]!r}") from e
        if not resp.get("ok", False):
            raise RuntimeError(resp.get("error") or f"AhanaFlow {cmd} failed: {resp}")
        return resp.get("result")

    # --- vector ops ---

    def ping(self) -> str:
        return str(self.request("PING"))

    def create_collection(
        self,
        collection: str,
        dimensions: int,
        *,
        metric: str = "cosine",
        modality: str = "vector",
    ) -> None:
        self.request(
            "VECTOR_CREATE",
            collection=collection,
            dimensions=dimensions,
            metric=metric,
            modality=modality,
        )

    def upsert(
        self,
        collection: str,
        item_id: str,
        vector: List[float],
        *,
        metadata: Optional[Dict[str, Any]] = None,
        payload: Any = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        fields: Dict[str, Any] = {
            "collection": collection,
            "id": item_id,
            "vector": vector,
        }
        if metadata is not None:
            fields["metadata"] = metadata
        if payload is not None:
            fields["payload"] = payload
        if ttl_seconds is not None:
            fields["ttl_seconds"] = ttl_seconds
        self.request("VECTOR_UPSERT", **fields)

    def query(
        self,
        collection: str,
        vector: List[float],
        *,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        compress_results: bool = True,
        strategy: str = "exact",
    ) -> Any:
        fields: Dict[str, Any] = {
            "collection": collection,
            "vector": vector,
            "top_k": top_k,
            "compress_results": compress_results,
            "strategy": strategy,
        }
        if filters:
            fields["filters"] = filters
        return self.request("VECTOR_QUERY", **fields)

    def scan(
        self,
        collection: str,
        *,
        limit: int = 1000,
        include_vectors: bool = False,
    ) -> List[Dict[str, Any]]:
        result = self.request(
            "VECTOR_SCAN",
            collection=collection,
            limit=limit,
            include_vectors=include_vectors,
        )
        return list(result or [])

    def stats(self) -> Dict[str, Any]:
        result = self.request("VECTOR_STATS")
        return dict(result or {})
