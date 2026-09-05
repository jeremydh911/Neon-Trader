#!/usr/bin/env python3
"""
Production smoke for AhanaFlow memory (selfhosted if up, else embedded).

Covers: health, remember/search/recall, Tim analyze write-path, soft-fail.
Exit 0 on pass.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PAPER_MODE", "1")
os.environ.setdefault("USE_MOCK_BROKER", "1")


def _pass(msg: str) -> None:
    print(f"PASS  {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    raise SystemExit(1)


def main() -> int:
    from app.services.ahanaflow_memory import AhanaFlowMemory
    from app.services.ahanaflow_vector_client import AhanaFlowVectorClient
    from app.services.tim_copilot import TimCopilot

    host = os.getenv("AHANAFLOW_HOST", "127.0.0.1")
    port = int(os.getenv("AHANAFLOW_PORT", "9634"))
    mode = os.getenv("AHANAFLOW_MODE", "auto")

    # Prefer live selfhost; otherwise spin ephemeral server for smoke
    ephemeral = None
    try:
        c = AhanaFlowVectorClient(host=host, port=port, retries=1, connect_eager=True)
        if c.health().get("ok"):
            _pass(f"selfhost reachable {host}:{port}")
            mem = AhanaFlowMemory(
                collection="tim_smoke",
                dimensions=64,
                mode="selfhosted",
                host=host,
                port=port,
            )
        else:
            raise ConnectionError("unhealthy")
    except Exception:
        sys.path.insert(0, str(ROOT / "vendor" / "AhanaFlow"))
        from backend.vector_server.server import VectorStateServerV2

        wal = Path(tempfile.mkdtemp()) / "smoke.wal"
        ephemeral = VectorStateServerV2(wal, host="127.0.0.1", port=19650)
        threading.Thread(target=ephemeral.serve_forever, daemon=True).start()
        time.sleep(0.3)
        host, port = "127.0.0.1", 19650
        _pass(f"ephemeral selfhost on {host}:{port}")
        mem = AhanaFlowMemory(
            collection="tim_smoke",
            dimensions=64,
            mode="selfhosted",
            host=host,
            port=port,
        )

    h = mem.health()
    if not h.get("ok"):
        _fail(f"memory health: {h}")
    _pass(f"memory health ok mode={h.get('mode')} backend={h.get('backend')}")

    try:
        mem.remember("   ")
        _fail("empty remember should raise")
    except ValueError:
        _pass("empty remember rejected")

    mid = mem.remember(
        "BUY NVDA VWAP reclaim with stacked RVOL",
        kind="decision",
        symbol="NVDA",
        tags=["tim", "smoke"],
    )
    if not mid:
        _fail("remember returned empty id")
    _pass(f"remember id={mid}")

    hits = mem.search("NVDA buy momentum", limit=3)
    if not hits or "NVDA" not in (hits[0].content or ""):
        _fail(f"search miss: {hits}")
    _pass(f"search hit score={hits[0].relevance_score:.3f}")

    ctx = mem.recall_context("NVDA snipe", symbol="NVDA")
    if "NVDA" not in ctx:
        _fail(f"recall miss: {ctx!r}")
    _pass("recall_context ok")

    # soft-fail: close client then search should return [] not crash
    if mem.client is not None:
        mem.client.close()
        mem.client._closed = False  # allow reconnect attempts then fail soft
        # Force dead port to exercise soft-fail without reconnecting to live server
        mem.client.port = 1
        mem.client.auto_reconnect = False
        soft = mem.search("anything", limit=2)
        if soft != []:
            _fail(f"expected soft-fail [], got {soft}")
        _pass("search soft-fails on transport error")

    # Tim path (embedded memory injection)
    wal = Path(tempfile.mkdtemp()) / "tim.wal"
    emb = AhanaFlowMemory(wal_path=wal, collection="tim_copilot_smoke", dimensions=64, mode="embedded")
    tim = TimCopilot(paper_mode=True, memory=emb)
    decision = tim.analyze("NVDA")
    if decision.get("status") != "success":
        _fail(f"tim analyze: {decision}")
    strip = tim.risk_strip()
    if "ahanaflow" not in str(strip.get("memory_backend") or ""):
        _fail(f"tim strip backend: {strip.get('memory_backend')}")
    _pass(f"tim analyze action={decision.get('action')} vectors={strip.get('memory_vectors')}")

    if ephemeral is not None:
        ephemeral.shutdown()

    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
