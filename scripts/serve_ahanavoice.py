#!/usr/bin/env python3
"""
Minimal AhanaVoice-compatible mouth for Neon / Tim.

Loads Jeremiah's vendored .aarm pack + roster, exposes:
  POST /v1/audio/speech   (OpenAI-style)
  POST /api/say           (AhanaVoice talk.js shape)
  GET  /health
  GET  /v1/voices

Prefer pointing AHANAVOICE_URL at a real serve_aarm. This process will
try cloud when AHANAVOICE_ALLOW_CLOUD=1, else desk-preview.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ahanavoice_client import AhanaVoiceClient  # noqa: E402
from app.services.ahanavoice_pack import seats_from_roster  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    client: AhanaVoiceClient = None  # type: ignore

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("ahanavoice-serve: " + (fmt % args) + "\n")

    def _json(self, code: int, obj: Dict[str, Any]) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _audio(self, result) -> None:
        self.send_response(200)
        self.send_header("Content-Type", result.content_type or "audio/wav")
        self.send_header("Content-Length", str(len(result.audio)))
        self.send_header("X-Ahana-Mode", result.mode)
        self.send_header("X-Ahana-Slot", result.slot)
        self.send_header("X-Ahana-Pack-Bytes", str(result.pack_bytes))
        self.end_headers()
        self.wfile.write(result.audio)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/v1/health"):
            self._json(200, {"ok": True, **self.client.status()})
            return
        if path in ("/v1/voices", "/voices"):
            seats = [s.as_dict() for s in seats_from_roster()]
            self._json(200, {"object": "list", "data": seats, "brand": "AhanaVoice"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        body = self._read_json()
        try:
            if path in ("/v1/audio/speech", "/audio/speech"):
                text = str(body.get("input") or body.get("text") or "")
                slot = str(body.get("voice") or body.get("slot") or "") or None
                result = self.client.speak(text, slot=slot)
                self._audio(result)
                return
            if path in ("/api/say", "/say"):
                text = str(body.get("text") or body.get("input") or "")
                slot = str(body.get("slot") or body.get("voice") or "") or None
                result = self.client.speak(text, slot=slot)
                self._audio(result)
                return
            self._json(404, {"error": "not found"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description="AhanaVoice desk serve (Jeremiah pack)")
    parser.add_argument("--host", default=os.getenv("AHANAVOICE_SERVE_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("AHANAVOICE_SERVE_PORT", "9635"))
    )
    parser.add_argument("--slot", default=os.getenv("AHANAVOICE_VOICE", "drew-three-am"))
    args = parser.parse_args()

    os.environ.pop("AHANAVOICE_URL", None)
    client = AhanaVoiceClient(slot=args.slot, base_url="")
    Handler.client = client
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    status = client.status()
    print(
        json.dumps(
            {
                "listening": f"http://{args.host}:{args.port}",
                "pack_bytes": status.get("pack", {}).get("pack_bytes"),
                "slot": status.get("slot"),
                "routes": ["/v1/audio/speech", "/api/say", "/v1/voices", "/health"],
            }
        ),
        flush=True,
    )
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
