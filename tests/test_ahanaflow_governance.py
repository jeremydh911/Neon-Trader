"""Governance / security regression tests for AhanaFlow integration."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
ROOT = Path(__file__).parent.parent


def test_reject_evil_collection_names():
    from app.services.ahanaflow_governance import validate_collection_name

    for bad in ("../evil", "evil;rm", "a/b", "", "1bad", "has space", "x" * 80):
        try:
            validate_collection_name(bad)
            assert False, f"expected reject {bad!r}"
        except ValueError:
            pass
    assert validate_collection_name("tim_memory") == "tim_memory"


def test_client_refuses_non_loopback_by_default():
    from app.services.ahanaflow_vector_client import AhanaFlowVectorClient

    os.environ.pop("AHANAFLOW_ALLOW_REMOTE", None)
    os.environ.pop("AHANAFLOW_ALLOW_PUBLIC", None)
    try:
        AhanaFlowVectorClient(host="8.8.8.8", port=9634, connect_eager=False)
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_wal_jail_blocks_escape():
    from app.services.ahanaflow_governance import jail_wal_path

    root = Path(tempfile.mkdtemp())
    try:
        jail_wal_path("../../etc/passwd", root=root)
        assert False, "expected PermissionError"
    except PermissionError:
        pass
    try:
        jail_wal_path(Path("/tmp/outside.wal"), root=root)
        assert False, "expected PermissionError for absolute escape"
    except PermissionError:
        pass
    ok = jail_wal_path("tim_memory.wal", root=root)
    assert ok.parent == root.resolve()
    assert ok.name == "tim_memory.wal"


def test_chat_ttl_default_applied():
    from app.services.ahanaflow_governance import default_ttl_seconds

    os.environ.pop("AHANAFLOW_DEFAULT_TTL_SECONDS", None)
    os.environ["AHANAFLOW_CHAT_TTL_SECONDS"] = "3600"
    assert default_ttl_seconds("discussion") == 3600
    assert default_ttl_seconds("decision") is None


def test_clamp_caps():
    from app.services.ahanaflow_governance import clamp_scan_limit, clamp_top_k

    os.environ["AHANAFLOW_MAX_TOP_K"] = "50"
    os.environ["AHANAFLOW_MAX_SCAN"] = "1000"
    assert clamp_top_k(9999) == 50
    assert clamp_scan_limit(99999) == 1000


def test_public_bind_without_key_exits():
    env = os.environ.copy()
    env["AHANAFLOW_ALLOW_PUBLIC"] = "1"
    env.pop("AHANAFLOW_API_KEY", None)
    env.pop("AHANAFLOW_API_KEYS_FILE", None)
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ahanaflow_selfhost_server.py"),
            "--host",
            "0.0.0.0",
            "--port",
            "19699",
            "--wal",
            "gov_public.wal",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "Public bind requires" in combined or "API_KEY" in combined


def test_auth_error_not_soft_failed_on_search():
    vendor = ROOT / "vendor" / "AhanaFlow"
    sys.path.insert(0, str(vendor))
    from backend.universal_server.security import SecurityConfig, hash_api_key
    from backend.vector_server.server import VectorStateServerV2
    from app.services.ahanaflow_memory import AhanaFlowMemory
    from app.services.ahanaflow_vector_client import (
        AhanaFlowAuthError,
        AhanaFlowVectorClient,
    )

    wal = Path(tempfile.mkdtemp()) / "auth_search.wal"
    key = "gov-test-key"
    cfg = SecurityConfig(enabled=True, require_auth=True)
    srv = VectorStateServerV2(wal, host="127.0.0.1", port=19638, security_config=cfg)
    srv._security._api_keys.add(hash_api_key(key))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.25)
    prev = os.environ.get("AHANAFLOW_API_KEY")
    os.environ["AHANAFLOW_API_KEY"] = key
    try:
        mem = AhanaFlowMemory(
            collection="govauth",
            dimensions=32,
            mode="selfhosted",
            host="127.0.0.1",
            port=19638,
        )
        mem.client.close()
        mem.client = AhanaFlowVectorClient(
            host="127.0.0.1", port=19638, api_key=None, retries=1
        )
        try:
            mem.search("anything", limit=2)
            assert False, "auth failure must not soft-fail to []"
        except AhanaFlowAuthError:
            pass
    finally:
        if prev is None:
            os.environ.pop("AHANAFLOW_API_KEY", None)
        else:
            os.environ["AHANAFLOW_API_KEY"] = prev
        srv.shutdown()


def test_tls_required_for_non_loopback():
    from app.services.ahanaflow_tls import tls_required_for_exposure
    from app.services.ahanaflow_vector_client import AhanaFlowVectorClient

    assert tls_required_for_exposure(host="10.0.0.5") is True
    assert tls_required_for_exposure(host="127.0.0.1") is False
    os.environ["AHANAFLOW_ALLOW_REMOTE"] = "1"
    os.environ.pop("AHANAFLOW_TLS", None)
    try:
        AhanaFlowVectorClient(host="10.0.0.5", port=9634, connect_eager=False, use_tls=False)
        assert False, "expected PermissionError without TLS"
    except PermissionError:
        pass
    finally:
        os.environ.pop("AHANAFLOW_ALLOW_REMOTE", None)


def test_tls_roundtrip_selfhosted():
    """Self-signed TLS encrypts the NDJSON wire end-to-end."""
    import subprocess

    vendor = ROOT / "vendor" / "AhanaFlow"
    sys.path.insert(0, str(vendor))
    from backend.vector_server.server import VectorStateServerV2
    from app.services.ahanaflow_tls import (
        build_client_ssl_context,
        build_server_ssl_context,
        wrap_vector_server_tls,
    )
    from app.services.ahanaflow_vector_client import AhanaFlowVectorClient

    data_root = Path(tempfile.mkdtemp())
    os.environ["AHANAFLOW_DATA_ROOT"] = str(data_root)
    os.environ["AHANAFLOW_TLS_CERT"] = "tls/server.crt"
    os.environ["AHANAFLOW_TLS_KEY"] = "tls/server.key"
    os.environ["AHANAFLOW_TLS_CA"] = "tls/server.crt"
    os.environ.pop("AHANAFLOW_TLS_INSECURE", None)

    proc = subprocess.run(
        [str(ROOT / "scripts" / "generate_ahanaflow_tls.sh")],
        env={**os.environ, "AHANAFLOW_DATA_ROOT": str(data_root)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (data_root / "tls" / "server.crt").is_file()

    wal = data_root / "tls_roundtrip.wal"
    srv = VectorStateServerV2(wal, host="127.0.0.1", port=19640)
    wrap_vector_server_tls(srv, build_server_ssl_context())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    try:
        # Plain client must fail against TLS server
        try:
            AhanaFlowVectorClient(
                host="127.0.0.1", port=19640, retries=1, use_tls=False
            ).ping()
            assert False, "plaintext client should fail against TLS server"
        except Exception:
            pass

        client = AhanaFlowVectorClient(
            host="127.0.0.1",
            port=19640,
            retries=1,
            use_tls=True,
            ssl_context=build_client_ssl_context(),
        )
        assert client.ping()
        h = client.health()
        assert h.get("ok") is True
        assert h.get("tls") is True
        client.create_collection("tls_test", 32)
        client.upsert("tls_test", "m1", [0.1] * 32, payload={"text": "BUY NVDA TLS"})
        hits = client.query("tls_test", [0.1] * 32, top_k=2)
        assert hits
        client.close()
    finally:
        srv.shutdown()


def test_public_bind_without_tls_exits_when_key_present():
    env = os.environ.copy()
    env["AHANAFLOW_ALLOW_PUBLIC"] = "1"
    env["AHANAFLOW_API_KEY"] = "public-needs-tls-too"
    env.pop("AHANAFLOW_TLS", None)
    env["PYTHONPATH"] = str(ROOT)
    env["AHANAFLOW_DATA_ROOT"] = tempfile.mkdtemp()
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ahanaflow_selfhost_server.py"),
            "--host",
            "0.0.0.0",
            "--port",
            "19698",
            "--wal",
            "gov_public_tls.wal",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "TLS" in combined
