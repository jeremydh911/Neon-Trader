"""
TLS helpers for AhanaFlow NDJSON TCP (Neon Trader / Tim memory).

Self-signed local certs are fine for loopback; for non-loopback / public bind,
TLS is mandatory (fail-closed) together with API-key auth.
"""

from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path
from typing import Optional, Tuple

from .ahanaflow_governance import env_truthy, is_public_bind

logger = logging.getLogger(__name__)


def tls_enabled(explicit: Optional[bool] = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return env_truthy("AHANAFLOW_TLS")


def tls_required_for_exposure(*, host: str, allow_remote: bool = False) -> bool:
    """Public bind or remote client target requires TLS."""
    if is_public_bind(host):
        return True
    h = (host or "").strip().lower()
    loopback = h in {"127.0.0.1", "localhost", "::1"} or h.startswith("127.")
    if loopback:
        return False
    if allow_remote or env_truthy("AHANAFLOW_ALLOW_REMOTE") or env_truthy("AHANAFLOW_ALLOW_PUBLIC"):
        return True
    return True  # any non-loopback host requires TLS


def resolve_cert_paths(
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
    cafile: Optional[str] = None,
) -> Tuple[Path, Path, Optional[Path]]:
    """
    Resolve cert/key/CA under AHANAFLOW_DATA_ROOT (default data/ahanaflow).
    Absolute paths must stay under the data root unless AHANAFLOW_TLS_ALLOW_ABS=1.
    """
    data_root = Path(os.getenv("AHANAFLOW_DATA_ROOT", "data/ahanaflow")).resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    def _place(p: Path) -> Path:
        if ".." in p.parts:
            raise PermissionError(f"TLS path {p} must not contain '..'")
        if env_truthy("AHANAFLOW_TLS_ALLOW_ABS") and p.is_absolute():
            return p.resolve()
        if p.is_absolute():
            try:
                p.resolve().relative_to(data_root)
                return p.resolve()
            except ValueError as e:
                raise PermissionError(
                    f"TLS path {p} escapes {data_root}; "
                    "set AHANAFLOW_TLS_ALLOW_ABS=1 for system certs"
                ) from e
        return (data_root / p).resolve()

    cert = Path(certfile or os.getenv("AHANAFLOW_TLS_CERT", "tls/server.crt"))
    key = Path(keyfile or os.getenv("AHANAFLOW_TLS_KEY", "tls/server.key"))
    ca_raw = cafile if cafile is not None else os.getenv("AHANAFLOW_TLS_CA", "")
    cert_p = _place(cert)
    key_p = _place(key)
    ca_p = _place(Path(ca_raw)) if ca_raw else None
    return cert_p, key_p, ca_p


def build_server_ssl_context(
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
) -> ssl.SSLContext:
    cert_p, key_p, _ = resolve_cert_paths(certfile, keyfile)
    if not cert_p.is_file() or not key_p.is_file():
        raise FileNotFoundError(
            f"TLS enabled but cert/key missing: cert={cert_p} key={key_p}. "
            "Run: ./scripts/generate_ahanaflow_tls.sh"
        )
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(cert_p), keyfile=str(key_p))
    ctx.verify_mode = ssl.CERT_NONE
    logger.info("AhanaFlow TLS server context loaded cert=%s", cert_p)
    return ctx


def build_client_ssl_context(
    *,
    cafile: Optional[str] = None,
    insecure: Optional[bool] = None,
) -> ssl.SSLContext:
    """
    Client TLS context.
    Default: verify against AHANAFLOW_TLS_CA (or server cert for self-signed).
    AHANAFLOW_TLS_INSECURE=1 disables verification (dev only).
    """
    if insecure is None:
        insecure = env_truthy("AHANAFLOW_TLS_INSECURE")
    cert_p, _, ca_p = resolve_cert_paths(cafile=cafile)
    trust = ca_p if ca_p and ca_p.is_file() else (cert_p if cert_p.is_file() else None)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        logger.warning("AhanaFlow TLS client INSECURE (verification disabled)")
        return ctx

    # Self-signed local certs usually don't match hostname; off by default
    ctx.check_hostname = env_truthy("AHANAFLOW_TLS_CHECK_HOSTNAME")
    ctx.verify_mode = ssl.CERT_REQUIRED
    if trust is None:
        raise FileNotFoundError(
            "TLS client needs AHANAFLOW_TLS_CA (or server cert at AHANAFLOW_TLS_CERT) "
            "unless AHANAFLOW_TLS_INSECURE=1"
        )
    ctx.load_verify_locations(cafile=str(trust))
    logger.info("AhanaFlow TLS client context loaded ca=%s", trust)
    return ctx


def wrap_vector_server_tls(server: object, ssl_ctx: ssl.SSLContext) -> None:
    """Patch VectorStateServerV2's inner ThreadingTCPServer to TLS-wrap accepts."""
    inner = getattr(server, "_srv", None)
    if inner is None:
        raise RuntimeError("VectorStateServerV2 has no _srv to wrap for TLS")

    def get_request():  # type: ignore[no-untyped-def]
        newsocket, fromaddr = inner.socket.accept()
        try:
            sslsock = ssl_ctx.wrap_socket(newsocket, server_side=True)
        except ssl.SSLError:
            newsocket.close()
            raise
        return sslsock, fromaddr

    inner.get_request = get_request  # type: ignore[method-assign]
    logger.info("AhanaFlow vector server TLS accept wrapper installed")
