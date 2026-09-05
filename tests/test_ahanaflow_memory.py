"""AhanaFlow compressed RAG memory for Tim."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PAPER_MODE"] = "1"
os.environ["USE_MOCK_BROKER"] = "1"
os.environ["AHANAFLOW_MEMORY"] = "1"


def test_ahanaflow_vendor_present():
    root = (
        Path(__file__).parent.parent
        / "vendor"
        / "AhanaFlow"
        / "backend"
        / "vector_server"
        / "engine.py"
    )
    assert root.exists(), "vendor/AhanaFlow missing — run git submodule update --init"


def test_ahanaflow_remember_and_recall():
    from app.services.ahanaflow_memory import AhanaFlowMemory

    wal = Path(tempfile.mkdtemp()) / "tim_test.wal"
    mem = AhanaFlowMemory(wal_path=wal, collection="tim_test", dimensions=64)
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
    assert "AhanaFlow" in ctx
    assert "NVDA" in ctx

    stats = mem.stats()
    assert stats["backend"] == "ahanaflow"
    assert stats["vectors"] >= 2
    mem.close()


def test_get_memory_store_prefers_ahanaflow():
    from app.services import ahanaflow_memory as af

    af._STORE = None
    os.environ["AHANAFLOW_WAL"] = str(Path(tempfile.mkdtemp()) / "factory.wal")
    store = af.get_memory_store()
    assert type(store).__name__ == "AhanaFlowMemory"
    store.remember("paper snipe lesson: hard stop never softens", kind="note", tags=["tim"])
    summary = store.get_memory_summary()
    assert summary["backend"] == "ahanaflow"
    assert summary["total_memories"] >= 1


def test_tim_copilot_writes_memory():
    from app.services.ahanaflow_memory import AhanaFlowMemory
    from app.services.tim_copilot import TimCopilot

    wal = Path(tempfile.mkdtemp()) / "copilot.wal"
    mem = AhanaFlowMemory(wal_path=wal, collection="tim_copilot", dimensions=64)
    c = TimCopilot(paper_mode=True, memory=mem)
    d = c.analyze("NVDA")
    assert d["status"] == "success"
    hits = mem.search(f"{d.get('action')} NVDA", limit=5)
    assert hits
    strip = c.risk_strip()
    assert strip.get("memory_backend") == "ahanaflow"
    assert strip.get("memory_vectors", 0) >= 1
