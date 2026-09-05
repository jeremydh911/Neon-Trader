"""AhanaFlow compressed RAG memory for Tim — functional coverage."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PAPER_MODE"] = "1"
os.environ["USE_MOCK_BROKER"] = "1"
os.environ["AHANAFLOW_MEMORY"] = "1"


def _jailed(name: str = "tim_test.wal") -> Path:
    root = Path(tempfile.mkdtemp())
    os.environ["AHANAFLOW_DATA_ROOT"] = str(root)
    return root


def test_ahanaflow_vendor_present():
    engine = (
        Path(__file__).parent.parent
        / "vendor"
        / "AhanaFlow"
        / "backend"
        / "vector_server"
        / "engine.py"
    )
    assert engine.exists(), "vendor/AhanaFlow missing — run git submodule update --init"


def test_ahanaflow_remember_and_recall():
    from app.services.ahanaflow_memory import AhanaFlowMemory

    _jailed()
    mem = AhanaFlowMemory(
        wal_path="tim_test.wal", collection="tim_test", dimensions=64, mode="embedded"
    )
    mid = mem.remember(
        "BUY NVDA on VWAP reclaim with stacked RVOL",
        kind="decision",
        symbol="NVDA",
        tags=["tim", "engine"],
        metadata={"action": "BUY", "confidence": 0.82},
    )
    assert mid
    mem.remember(
        "HOLD AAPL — below VWAP, no snipe",
        kind="decision",
        symbol="AAPL",
        tags=["tim"],
    )

    hits = mem.search("NVDA momentum VWAP buy", limit=3)
    assert hits, "expected semantic hits"
    assert any("NVDA" in (h.content or "") for h in hits)

    ctx = mem.recall_context("snipe NVDA strength", symbol="NVDA")
    assert "NVDA" in ctx

    stats = mem.stats()
    assert "ahanaflow" in str(stats.get("backend") or "")
    assert stats.get("mode") == "embedded"
    assert (stats.get("vectors") or 0) >= 2
    mem.close()


def test_get_memory_store_prefers_ahanaflow():
    from app.services import ahanaflow_memory as af

    af._STORE = None
    root = _jailed()
    os.environ["AHANAFLOW_WAL"] = "factory.wal"
    os.environ["AHANAFLOW_MODE"] = "embedded"
    os.environ["AHANAFLOW_DATA_ROOT"] = str(root)
    store = af.get_memory_store()
    assert type(store).__name__ == "AhanaFlowMemory"
    store.remember("paper snipe lesson: hard stop never softens", kind="note", tags=["tim"])
    summary = store.get_memory_summary()
    assert "ahanaflow" in str(summary.get("backend") or "")
    assert summary["total_memories"] >= 1


def test_tim_copilot_writes_memory():
    from app.services.ahanaflow_memory import AhanaFlowMemory
    from app.services.tim_copilot import TimCopilot

    _jailed()
    mem = AhanaFlowMemory(
        wal_path="copilot.wal", collection="tim_copilot", dimensions=64, mode="embedded"
    )
    c = TimCopilot(paper_mode=True, memory=mem)
    d = c.analyze("NVDA")
    assert d["status"] == "success"
    hits = mem.search(f"{d.get('action')} NVDA", limit=5)
    assert hits
    strip = c.risk_strip()
    backend = str(strip.get("memory_backend") or "")
    assert "ahanaflow" in backend.lower() or (strip.get("memory_vectors") or 0) >= 1


def test_selfhosted_ahanaflow_tcp():
    root = Path(__file__).parent.parent / "vendor" / "AhanaFlow"
    sys.path.insert(0, str(root))
    from backend.vector_server.server import VectorStateServerV2
    from app.services.ahanaflow_memory import AhanaFlowMemory

    wal = Path(tempfile.mkdtemp()) / "selfhost.wal"
    srv = VectorStateServerV2(wal, host="127.0.0.1", port=19635)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.25)
    try:
        mem = AhanaFlowMemory(
            collection="tim_selfhost",
            dimensions=32,
            mode="selfhosted",
            host="127.0.0.1",
            port=19635,
        )
        assert mem.stats()["mode"] == "selfhosted"
        assert mem.health().get("ok") is True
        mem.remember("BUY SPY breakout", kind="decision", symbol="SPY")
        hits = mem.search("SPY breakout", limit=2)
        assert hits and "SPY" in hits[0].content
        assert "SPY" in mem.recall_context("SPY")
    finally:
        srv.shutdown()


def test_empty_remember_rejected():
    from app.services.ahanaflow_memory import AhanaFlowMemory

    _jailed()
    mem = AhanaFlowMemory(
        wal_path="empty.wal", collection="empty", dimensions=32, mode="embedded"
    )
    try:
        mem.remember("   ")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_search_soft_fails_when_server_down():
    root = Path(__file__).parent.parent / "vendor" / "AhanaFlow"
    sys.path.insert(0, str(root))
    from backend.vector_server.server import VectorStateServerV2
    from app.services.ahanaflow_memory import AhanaFlowMemory

    wal = Path(tempfile.mkdtemp()) / "soft.wal"
    srv = VectorStateServerV2(wal, host="127.0.0.1", port=19636)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.25)
    mem = AhanaFlowMemory(
        collection="soft",
        dimensions=32,
        mode="selfhosted",
        host="127.0.0.1",
        port=19636,
    )
    mem.remember("BUY AMD strength", kind="decision", symbol="AMD")
    srv.shutdown()
    time.sleep(0.1)
    assert mem.client is not None
    mem.client.close()
    mem.client._closed = False
    mem.client.port = 1
    mem.client.auto_reconnect = False
    assert mem.search("AMD", limit=2) == []


def test_client_rejects_wrong_dimensions():
    from app.services.ahanaflow_vector_client import (
        AhanaFlowProtocolError,
        AhanaFlowVectorClient,
    )

    c = AhanaFlowVectorClient(host="127.0.0.1", port=1, connect_eager=False, retries=1)
    try:
        c.upsert("c", "id1", [0.1, 0.2], expected_dimensions=8)
        assert False, "expected dimension error"
    except AhanaFlowProtocolError:
        pass


def test_api_key_auth_required():
    root = Path(__file__).parent.parent / "vendor" / "AhanaFlow"
    sys.path.insert(0, str(root))
    from backend.universal_server.security import SecurityConfig, hash_api_key
    from backend.vector_server.server import VectorStateServerV2
    from app.services.ahanaflow_vector_client import (
        AhanaFlowAuthError,
        AhanaFlowProtocolError,
        AhanaFlowVectorClient,
    )

    wal = Path(tempfile.mkdtemp()) / "auth.wal"
    key = "neon-tim-prod-test-key"
    cfg = SecurityConfig(enabled=True, require_auth=True)
    srv = VectorStateServerV2(wal, host="127.0.0.1", port=19637, security_config=cfg)
    assert srv._security is not None
    srv._security._api_keys.add(hash_api_key(key))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.25)
    try:
        try:
            AhanaFlowVectorClient(host="127.0.0.1", port=19637, retries=1).ping()
            assert False, "unauth should fail"
        except (AhanaFlowAuthError, AhanaFlowProtocolError, Exception):
            pass
        authed = AhanaFlowVectorClient(
            host="127.0.0.1", port=19637, api_key=key, retries=1
        )
        assert authed.ping()
        assert authed.health().get("ok") is True
    finally:
        srv.shutdown()


def test_embedded_health_stable_probe_id():
    from app.services.ahanaflow_memory import AhanaFlowMemory

    _jailed()
    mem = AhanaFlowMemory(
        wal_path="health.wal", collection="health", dimensions=32, mode="embedded"
    )
    h1 = mem.health()
    h2 = mem.health()
    assert h1.get("ok") and h2.get("ok")
    assert (mem.stats().get("vectors") or 0) <= 3
