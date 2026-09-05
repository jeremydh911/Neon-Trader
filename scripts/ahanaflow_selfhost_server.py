#!/usr/bin/env python3
"""
Production self-hosted AhanaFlow vector server for Neon Trader.

Governance:
- Default bind 127.0.0.1
- Public bind (0.0.0.0) REQUIRES auth + API key material
- WAL path jailed under data/ahanaflow (or AHANAFLOW_DATA_ROOT)
- Never logs API key material
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
sys.path.insert(0, str(ROOT))


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

    from app.services.ahanaflow_governance import (
        env_truthy,
        is_public_bind,
        jail_wal_path,
    )

    parser = argparse.ArgumentParser(description="Neon Trader AhanaFlow self-host server")
    parser.add_argument(
        "--wal",
        default=os.getenv("AHANAFLOW_WAL", "tim_memory.wal"),
        help="WAL filename or path under AHANAFLOW_DATA_ROOT",
    )
    parser.add_argument("--host", default=os.getenv("AHANAFLOW_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AHANAFLOW_PORT", "9634")))
    parser.add_argument(
        "--require-auth",
        action="store_true",
        default=env_truthy("AHANAFLOW_REQUIRE_AUTH"),
    )
    parser.add_argument(
        "--api-keys-file",
        default=os.getenv("AHANAFLOW_API_KEYS_FILE", ""),
        help="File of SHA-256 hex API key hashes (one per line)",
    )
    args = parser.parse_args()

    host = args.host
    allow_public = env_truthy("AHANAFLOW_ALLOW_PUBLIC")
    public = is_public_bind(host)

    if public and not allow_public:
        raise SystemExit(
            f"Refusing to bind {host} without AHANAFLOW_ALLOW_PUBLIC=1 "
            "(trade memory must not be exposed accidentally)."
        )

    api_key = os.getenv("AHANAFLOW_API_KEY", "").strip()
    keys_file = (args.api_keys_file or "").strip()
    require_auth = bool(args.require_auth or api_key or keys_file or public)

    # Fail closed: public bind always needs real key material
    if public and not (api_key or keys_file):
        raise SystemExit(
            "Public bind requires AHANAFLOW_API_KEY or --api-keys-file "
            "(auth is mandatory when exposing the vector API)."
        )
    if require_auth and not (api_key or keys_file):
        raise SystemExit(
            "AHANAFLOW_REQUIRE_AUTH=1 but no AHANAFLOW_API_KEY / --api-keys-file provided."
        )

    data_root = Path(os.getenv("AHANAFLOW_DATA_ROOT", str(ROOT / "data" / "ahanaflow")))
    try:
        wal = jail_wal_path(args.wal, root=data_root)
    except PermissionError as e:
        raise SystemExit(str(e)) from e

    security_config = None
    if require_auth:
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
        log.info("API key auth enabled (key loaded from env; value not logged)")

    def _shutdown(*_args: object) -> None:
        log.info("shutdown signal received")
        server.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    bound_host, bound_port = server.address
    msg = (
        f"AhanaFlow vector server listening on {bound_host}:{bound_port}\n"
        f"WAL: {wal}\n"
        f"Auth: {'REQUIRED' if security_config else 'off (loopback only)'} | "
        f"export AHANAFLOW_MODE=selfhosted AHANAFLOW_HOST={bound_host} AHANAFLOW_PORT={bound_port}\n"
    )
    print(msg, flush=True)
    log.info(
        "serving host=%s port=%s wal=%s auth=%s public=%s",
        bound_host,
        bound_port,
        wal,
        bool(security_config),
        public,
    )
    try:
        server.serve_forever()
    finally:
        server.shutdown()
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
