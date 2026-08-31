import io
import json
from urllib.error import HTTPError

import pytest

from app.services import brain_plugin as bp


class _Resp:
    def __init__(self, payload, status=200):
        if isinstance(payload, (dict, list)):
            raw = json.dumps(payload).encode("utf-8")
        else:
            raw = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        self._raw = raw
        self.status = status

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_unset_env_keeps_council(monkeypatch):
    monkeypatch.delenv("AHANA_BRAIN_URL", raising=False)
    monkeypatch.delenv("AHANA_BRAIN_TOKEN", raising=False)
    assert bp.brain_configured() is False
    assert bp.active_brain() == "council"
    assert bp.plugin_proposal("AAPL", 100.0, {}) is None
    assert bp.COUNCIL_NAMES == ("Tina", "Eddie", "Gloria", "Victor", "Riley")


def test_webhook_brain(monkeypatch):
    monkeypatch.setenv("AHANA_BRAIN_URL", "https://brain.example/decide")
    monkeypatch.setenv("AHANA_BRAIN_TOKEN", "secret-token")

    captured = {}

    def fake_urlopen(req, timeout=20.0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items()) if hasattr(req, "header_items") else {}
        captured["auth"] = req.get_header("Authorization")
        body = json.loads(req.data.decode("utf-8"))
        captured["body"] = body
        assert body["symbol"] == "AAPL"
        return _Resp({"action": "BUY", "confidence": 0.8, "plan": "breakout"})

    monkeypatch.setattr(bp.urllib.request, "urlopen", fake_urlopen)
    proposal = bp.plugin_proposal("AAPL", 101.5, {"rsi": 40})
    assert proposal is not None
    assert proposal["action"] == "BUY"
    assert proposal["confidence"] == 0.8
    assert proposal["brain"] == "plugin"
    assert captured["auth"] == "Bearer secret-token"
    # Token must not leak into the normalized proposal keys as a secret field.
    dumped = json.dumps(proposal)
    assert "secret-token" not in dumped


def test_openai_compatible_brain(monkeypatch):
    monkeypatch.setenv("AHANA_BRAIN_URL", "https://api.x.ai/v1/chat/completions")
    monkeypatch.delenv("AHANA_BRAIN_TOKEN", raising=False)

    def fake_urlopen(req, timeout=20.0):
        body = json.loads(req.data.decode("utf-8"))
        assert "messages" in body
        inner = {"action": "HOLD", "confidence": 0.1, "plan": "wait"}
        return _Resp({"choices": [{"message": {"content": json.dumps(inner)}}]})

    monkeypatch.setattr(bp.urllib.request, "urlopen", fake_urlopen)
    proposal = bp.consult_brain("MSFT", 400.0)
    assert proposal["action"] == "HOLD"
    assert proposal["approved"] is False


def test_brain_http_error_falls_back(monkeypatch):
    monkeypatch.setenv("AHANA_BRAIN_URL", "https://brain.example/decide")

    def fake_urlopen(req, timeout=20.0):
        raise HTTPError("https://brain.example/decide", 503, "unavailable", hdrs=None, fp=io.BytesIO())

    monkeypatch.setattr(bp.urllib.request, "urlopen", fake_urlopen)
    assert bp.plugin_proposal("AAPL", 10.0) is None
