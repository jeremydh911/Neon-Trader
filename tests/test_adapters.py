from pathlib import Path

from app.services.adapters import ahanaflow, ahanazip, chatwire


def test_adapters_noop_without_packages():
    assert ahanaflow.available() is False
    assert chatwire.available() is False
    assert ahanazip.available() is False
    assert ahanaflow.enabled() is False
    assert chatwire.enabled() is False
    assert ahanazip.enabled() is False
    assert ahanaflow.publish_session("topic", {"k": 1}) is False
    assert ahanaflow.get_memory("k") is None
    assert chatwire.send_message("topic", {"k": 1}) is False
    assert ahanazip.pack_artifact("/tmp/x") is None
    assert ahanazip.unpack_artifact("/tmp/x") is None


def test_adapters_still_noop_if_env_set_but_missing(monkeypatch):
    monkeypatch.setenv("AHANAFLOW_URL", "https://flow.example")
    monkeypatch.setenv("CHATWIRE_URL", "https://wire.example")
    monkeypatch.setenv("AHANAZIP_DIR", "/tmp/zip")
    assert ahanaflow.enabled() is False
    assert chatwire.enabled() is False
    assert ahanazip.enabled() is False
    assert ahanaflow.publish_session("t") is False
    assert chatwire.send_message("t") is False
    assert ahanazip.pack_artifact("x") is None


def test_no_vendored_private_sister_trees():
    root = Path(__file__).resolve().parents[1]
    banned = {"AhanaFlow", "AhanaZip", "Chatwire", "CloudWire", "aarmOS"}
    for path in root.rglob("*"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.is_dir() and path.name in banned:
            raise AssertionError(f"private sister tree vendored at {path}")
    assert not (root / ".gitmodules").exists()
