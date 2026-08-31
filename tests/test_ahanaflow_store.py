import gzip
from pathlib import Path

from app.services.adapters import ahanaflow
from app.services.ahana_memory import AhanaMemory, hash_embed


def test_put_get_query_local_gzip(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AHANAFLOW_URL", raising=False)
    assert ahanaflow.enabled() is False

    rid = ahanaflow.put({
        "kind": "plan",
        "symbol": "AAPL",
        "setup": "A",
        "payload": {"why": "ORB break", "side": "BUY"},
    })
    ahanaflow.put({
        "kind": "alert",
        "symbol": "MSFT",
        "setup": "B",
        "payload": {"why": "VWAP reclaim"},
    })

    got = ahanaflow.get(rid)
    assert got is not None
    assert got["symbol"] == "AAPL"
    assert got["kind"] == "plan"
    assert got["payload"]["why"] == "ORB break"

    plans = ahanaflow.query(kind="plan", symbol="AAPL")
    assert len(plans) == 1
    ranged = ahanaflow.list_range(limit=10)
    assert len(ranged) >= 2

    gz = tmp_path / "records.jsonl.gz"
    assert gz.exists()
    with gzip.open(gz, "rt", encoding="utf-8") as handle:
        lines = [ln for ln in handle if ln.strip()]
    assert len(lines) >= 2
    assert not list(tmp_path.glob("*.pkl"))


def test_ahana_memory_retrieve_similar(tmp_path, monkeypatch):
    monkeypatch.setenv("AHANAFLOW_DATA_DIR", str(tmp_path))
    mem = AhanaMemory()
    mem.ingest({"kind": "plan", "symbol": "NVDA", "setup": "A", "payload": {"why": "opening range break long"}})
    mem.ingest({"kind": "plan", "symbol": "NVDA", "setup": "B", "payload": {"why": "vwap reject"}})
    hits = mem.similar_setups("NVDA", "A", "opening range", k=2)
    assert hits
    assert any(h.get("setup") == "A" for h in hits)
    assert hash_embed("aapl or break") != hash_embed("")
