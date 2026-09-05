"""
Thin TCP client for a self-hosted AhanaFlow VectorStateServerV2.

Protocol: newline-delimited JSON over TCP (default 127.0.0.1:9634).
Production defaults: localhost-only, reconnect with backoff, optional API key.

Preferred Neon Trader path — trade memory stays on your box.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_HOST = os.getenv("AHANAFLOW_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("AHANAFLOW_PORT", "9634"))
DEFAULT_TIMEOUT = float(os.getenv("AHANAFLOW_TIMEOUT", "5.0"))
DEFAULT_RETRIES = int(os.getenv("AHANAFLOW_RETRIES", "3"))
MAX_LINE_BYTES = int(os.getenv("AHANAFLOW_MAX_LINE_BYTES", str(2 * 1024 * 1024)))


class AhanaFlowClientError(RuntimeError):
    """Base client error."""


class AhanaFlowConnectionError(AhanaFlowClientError):
    """Transport / connection failure."""


class AhanaFlowProtocolError(AhanaFlowClientError):
    """Bad response or command rejected by server."""


class AhanaFlowVectorClient:
    """Thread-safe NDJSON TCP client for AhanaFlow vector server."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        api_key: Optional[str] = None,
        auto_reconnect: bool = True,
        retries: int = DEFAULT_RETRIES,
        connect_eager: bool = True,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.api_key = api_key if api_key is not None else os.getenv("AHANAFLOW_API_KEY")
        self.auto_reconnect = auto_reconnect
        self.retries = max(1, int(retries))
        self._sock: Optional[socket.socket] = None
        self._lock = threading.RLock()
        self._closed = False
        if connect_eager:
            self._connect_with_retry()

    # --- transport ---

    def _connect(self) -> None:
        if self._closed:
            raise AhanaFlowConnectionError("client is closed")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as e:
            sock.close()
            raise AhanaFlowConnectionError(
                f"cannot connect to AhanaFlow at {self.host}:{self.port}: {e}"
            ) from e
        self._sock = sock
        logger.info("AhanaFlow vector client connected %s:%s", self.host, self.port)

    def _connect_with_retry(self) -> None:
        last: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                self._connect()
                return
            except AhanaFlowConnectionError as e:
                last = e
                self._sock = None
                if attempt >= self.retries:
                    break
                delay = min(2.0, 0.05 * (2 ** (attempt - 1)))
                logger.warning(
                    "AhanaFlow connect attempt %s/%s failed (%s); retry in %.2fs",
                    attempt,
                    self.retries,
                    e,
                    delay,
                )
                time.sleep(delay)
        raise AhanaFlowConnectionError(str(last) if last else "connect failed")

    def _drop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _ensure(self) -> socket.socket:
        if self._sock is None:
            if not self.auto_reconnect:
                raise AhanaFlowConnectionError("AhanaFlow vector client not connected")
            self._connect_with_retry()
        assert self._sock is not None
        return self._sock

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._drop()

    def __enter__(self) -> "AhanaFlowVectorClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _read_line(self, sock: socket.socket) -> bytes:
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                raise AhanaFlowConnectionError("AhanaFlow vector server closed connection")
            buf += chunk
            if len(buf) > MAX_LINE_BYTES:
                raise AhanaFlowProtocolError(
                    f"response exceeds AHANAFLOW_MAX_LINE_BYTES ({MAX_LINE_BYTES})"
                )
        return buf.split(b"\n", 1)[0]

    def request(self, cmd: str, **fields: Any) -> Any:
        if not cmd or not isinstance(cmd, str):
            raise AhanaFlowProtocolError("cmd must be a non-empty string")
        payload: Dict[str, Any] = {"cmd": cmd, **fields}
        if self.api_key:
            payload["api_key"] = self.api_key
        line = (json.dumps(payload, separators=(",", ":"), default=str) + "\n").encode("utf-8")
        if len(line) > MAX_LINE_BYTES:
            raise AhanaFlowProtocolError(
                f"request exceeds AHANAFLOW_MAX_LINE_BYTES ({MAX_LINE_BYTES})"
            )

        last: Optional[Exception] = None
        with self._lock:
            for attempt in range(1, self.retries + 1):
                try:
                    sock = self._ensure()
                    sock.sendall(line)
                    raw = self._read_line(sock)
                    try:
                        resp = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as e:
                        raise AhanaFlowProtocolError(
                            f"invalid AhanaFlow response: {raw[:200]!r}"
                        ) from e
                    if not isinstance(resp, dict):
                        raise AhanaFlowProtocolError(f"expected object response, got {type(resp)}")
                    ok = bool(resp.get("ok"))
                    if not ok:
                        err = resp.get("error") or resp.get("message") or resp
                        raise AhanaFlowProtocolError(f"AhanaFlow {cmd} failed: {err}")
                    return resp.get("result")
                except (AhanaFlowConnectionError, OSError, TimeoutError) as e:
                    last = e
                    self._drop()
                    if attempt >= self.retries or not self.auto_reconnect:
                        break
                    delay = min(2.0, 0.05 * (2 ** (attempt - 1)))
                    logger.warning(
                        "AhanaFlow %s attempt %s/%s failed (%s); retry in %.2fs",
                        cmd,
                        attempt,
                        self.retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                except AhanaFlowProtocolError:
                    raise
        raise AhanaFlowConnectionError(str(last) if last else f"{cmd} failed")

    # --- vector ops ---

    def ping(self) -> str:
        return str(self.request("PING"))

    def health(self) -> Dict[str, Any]:
        """Readiness probe used by smoke/prod checks."""
        t0 = time.perf_counter()
        try:
            pong = self.ping()
            stats = self.stats()
            return {
                "ok": True,
                "pong": pong,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "host": self.host,
                "port": self.port,
                "stats": stats,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "host": self.host,
                "port": self.port,
            }

    def create_collection(
        self,
        collection: str,
        dimensions: int,
        *,
        metric: str = "cosine",
        modality: str = "vector",
    ) -> None:
        if not collection or dimensions <= 0:
            raise AhanaFlowProtocolError("collection name and positive dimensions required")
        self.request(
            "VECTOR_CREATE",
            collection=collection,
            dimensions=int(dimensions),
            metric=metric,
            modality=modality,
        )

    def list_collections(self) -> Any:
        return self.request("VECTOR_LIST")

    def upsert(
        self,
        collection: str,
        item_id: str,
        vector: List[float],
        *,
        metadata: Optional[Dict[str, Any]] = None,
        payload: Any = None,
        ttl_seconds: Optional[int] = None,
        expected_dimensions: Optional[int] = None,
    ) -> None:
        if not item_id:
            raise AhanaFlowProtocolError("item id required")
        if not isinstance(vector, list) or not vector:
            raise AhanaFlowProtocolError("vector must be a non-empty float list")
        if expected_dimensions is not None and len(vector) != expected_dimensions:
            raise AhanaFlowProtocolError(
                f"vector length {len(vector)} != expected dimensions {expected_dimensions}"
            )
        fields: Dict[str, Any] = {
            "collection": collection,
            "id": item_id,
            "vector": [float(x) for x in vector],
        }
        if metadata is not None:
            fields["metadata"] = metadata
        if payload is not None:
            fields["payload"] = payload
        if ttl_seconds is not None:
            fields["ttl_seconds"] = int(ttl_seconds)
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
        expected_dimensions: Optional[int] = None,
    ) -> Any:
        if expected_dimensions is not None and len(vector) != expected_dimensions:
            raise AhanaFlowProtocolError(
                f"query vector length {len(vector)} != expected dimensions {expected_dimensions}"
            )
        fields: Dict[str, Any] = {
            "collection": collection,
            "vector": [float(x) for x in vector],
            "top_k": max(1, int(top_k)),
            "compress_results": bool(compress_results),
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
            limit=max(1, int(limit)),
            include_vectors=bool(include_vectors),
        )
        return list(result or [])

    def stats(self) -> Dict[str, Any]:
        result = self.request("VECTOR_STATS")
        return dict(result or {})
