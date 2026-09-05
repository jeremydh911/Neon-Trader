#!/usr/bin/env python3
"""
Production self-hosted AhanaFlow vector server for Neon Trader.

- Binds 127.0.0.1 by default (set AHANAFLOW_ALLOW_PUBLIC=1 for 0.0.0.0)
- Optional API-key auth via AHANAFLOW_API_KEY / AHANAFLOW_API_KEYS_FILE
- Clean SIGTERM/SIGINT shutdown (flushes WAL)

Usage:
  ./scripts/run_ahanaflow_selfhost.sh
  # or:
  PYTHONPATH=vendor/AhanaFlow python3 scripts/ahanaflow_selfhost_server.py
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AHANA = ROOT / "vendor" / "AhanaFlow"


def _setup_path() -> None:
    if not AHANA.is_dir():
        raise SystemExit(
            f"Missing {AHANA}. Run: git submodule update --init vendor/AhanaFlow"
        )
    p = str(AHANA)
    if p not in sys.path:
        sys.path.insert(0, p)


def main() -> int:
    _setup_path()

    from backend.universal_server.security import SecurityConfig, hash_api_key
    from backend.vector_server.server import VectorStateServerV2

    parser = argparse.ArgumentParser(description="Neon Trader AhanaFlow self-host server")
    parser.add_argument(
        "--wal",
        default=os.getenv("AHANAFLOW_WAL", str(ROOT / "data" / "ahanaflow" / "tim_memory.wal")),
    )
    parser.add_argument("--host", default=os.getenv("AHANAFLOW_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AHANAFLOW_PORT", "9634")))
    parser.add_argument(
        "--require-auth",
        action="store_true",
        default=os.getenv("AHANAFLOW_REQUIRE_AUTH", "").lower() in ("1", "true", "yes"),
    )
    parser.add_argument(
        "--api-keys-file",
        default=os.getenv("AHANAFLOW_API_KEYS_FILE", ""),
        help="File of SHA-256 hex API key hashes (one per line)",
    )
    args = parser.parse_args()

    host = args.host
    allow_public = os.getenv("AHANAFLOW_ALLOW_PUBLIC", "").lower() in ("1", "true", "yes")
    if host in ("0.0.0.0", "::", "[::]") and not allow_public:
        raise SystemExit(
            f"Refusing to bind {host} without AHANAFLOW_ALLOW_PUBLIC=1 "
            "(trade memory must not be exposed accidentally)."
        )

    wal = Path(args.wal)
    wal.parent.mkdir(parents=True, exist_ok=True)

    security_config = None
    api_key = os.getenv("AHANAFLOW_API_KEY", "").strip()
    keys_file = (args.api_keys_file or "").strip()
    if args.require_auth or api_key or keys_file:
        security_config = SecurityConfig(
            enabled=True,
            require_auth=True,
            api_keys_file=keys_file or None,
        )

    logging.basicConfig(
        level=os.getenv("AHANAFLOW_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("ahanaflow.selfhost")

    server = VectorStateServerV2(
        wal_path=wal,
        host=host,
        port=int(args.port),
        security_config=security_config,
    )
    if security_config and api_key and server._security is not None:
        server._security._api_keys.add(hash_api_key(api_key))
        log.info("API key auth enabled (AHANAFLOW_API_KEY loaded)")

    def _shutdown(*_args: object) -> None:
        log.info("shutdown signal received")
        server.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    bound_host, bound_port = server.address
    msg = (
        f"AhanaFlow vector server listening on {bound_host}:{bound_port}\n"
        f"WAL: {wal}\n"
        f"Auth: {'required' if security_config else 'off (localhost dev)'} | "
        f"export AHANAFLOW_MODE=selfhosted AHANAFLOW_HOST={bound_host} AHANAFLOW_PORT={bound_port}\n"
    )
    print(msg, flush=True)
    log.info("serving host=%s port=%s wal=%s", bound_host, bound_port, wal)
    try:
        server.serve_forever()
    finally:
        server.shutdown()
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
