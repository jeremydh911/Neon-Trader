#!/usr/bin/env python3
"""
Production self-hosted AhanaFlow vector server for Neon Trader.

Governance:
- Default bind 127.0.0.1
- Public bind (0.0.0.0) REQUIRES auth + API key material + TLS
- Optional TLS on loopback (AHANAFLOW_TLS=1)
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
    from app.services.ahanaflow_tls import (
        build_server_ssl_context,
        tls_enabled,
        tls_required_for_exposure,
        wrap_vector_server_tls,
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
    parser.add_argument(
        "--tls",
        action="store_true",
        default=tls_enabled(),
        help="Enable TLS (also set via AHANAFLOW_TLS=1)",
    )
    parser.add_argument(
        "--tls-cert",
        default=os.getenv("AHANAFLOW_TLS_CERT", "tls/server.crt"),
        help="TLS certificate path under AHANAFLOW_DATA_ROOT",
    )
    parser.add_argument(
        "--tls-key",
        default=os.getenv("AHANAFLOW_TLS_KEY", "tls/server.key"),
        help="TLS private key path under AHANAFLOW_DATA_ROOT",
    )
    args = parser.parse_args()

    host = args.host
    allow_public = env_truthy("AHANAFLOW_ALLOW_PUBLIC")
    public = is_public_bind(host)
    use_tls = bool(args.tls) or tls_required_for_exposure(host=host)

    if public and not allow_public:
        raise SystemExit(
            f"Refusing to bind {host} without AHANAFLOW_ALLOW_PUBLIC=1 "
            "(trade memory must not be exposed accidentally)."
        )

    api_key = os.getenv("AHANAFLOW_API_KEY", "").strip()
    keys_file = (args.api_keys_file or "").strip()
    require_auth = bool(args.require_auth or api_key or keys_file or public)

    # Fail closed: public bind always needs real key material + TLS
    if public and not (api_key or keys_file):
        raise SystemExit(
            "Public bind requires AHANAFLOW_API_KEY or --api-keys-file "
            "(auth is mandatory when exposing the vector API)."
        )
    if public and not use_tls:
        raise SystemExit(
            "Public bind requires TLS. Set AHANAFLOW_TLS=1 and generate certs "
            "(./scripts/generate_ahanaflow_tls.sh)."
        )
    if require_auth and not (api_key or keys_file):
        raise SystemExit(
            "AHANAFLOW_REQUIRE_AUTH=1 but no AHANAFLOW_API_KEY / --api-keys-file provided."
        )

    data_root = Path(os.getenv("AHANAFLOW_DATA_ROOT", str(ROOT / "data" / "ahanaflow")))
    os.environ.setdefault("AHANAFLOW_DATA_ROOT", str(data_root))
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

    ssl_ctx = None
    if use_tls:
        try:
            ssl_ctx = build_server_ssl_context(args.tls_cert, args.tls_key)
        except FileNotFoundError as e:
            raise SystemExit(str(e)) from e

    server = VectorStateServerV2(
        wal_path=wal,
        host=host,
        port=int(args.port),
        security_config=security_config,
    )
    if ssl_ctx is not None:
        wrap_vector_server_tls(server, ssl_ctx)
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
        f"TLS: {'ON' if use_tls else 'off'} | "
        f"Auth: {'REQUIRED' if security_config else 'off (loopback only)'} | "
        f"export AHANAFLOW_MODE=selfhosted AHANAFLOW_HOST={bound_host} "
        f"AHANAFLOW_PORT={bound_port}"
        f"{' AHANAFLOW_TLS=1' if use_tls else ''}\n"
    )
    print(msg, flush=True)
    log.info(
        "serving host=%s port=%s wal=%s auth=%s public=%s tls=%s",
        bound_host,
        bound_port,
        wal,
        bool(security_config),
        public,
        use_tls,
    )
    try:
        server.serve_forever()
    finally:
        server.shutdown()
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
