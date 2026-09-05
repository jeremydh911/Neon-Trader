"""
AhanaVoice speech client for Tim.

Borrow Jeremiah's tiny mastered mouth:
  1) POST OpenAI-style /v1/audio/speech to AHANAVOICE_URL (serve_aarm / desk)
  2) POST https://ahanavoice.com/api/say (cloud mouth, pack-aware)
  3) Local desk-preview WAV shaped by seat pitch/rate + pack fingerprint
     (honest fallback — not the neural decoder; labeled desk-preview)
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .ahanavoice_pack import (
    TIM_DEFAULT_SLOT,
    VoiceSeat,
    load_pack,
    pack_fingerprint,
    resolve_seat,
)

logger = logging.getLogger(__name__)

DEFAULT_CLOUD = "https://ahanavoice.com"
DEFAULT_MODEL = "ahanavoice"


@dataclass
class SpeechResult:
    audio: bytes
    content_type: str
    mode: str  # serve_aarm | cloud | desk-preview
    slot: str
    pack_bytes: int
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "slot": self.slot,
            "pack_bytes": self.pack_bytes,
            "content_type": self.content_type,
            "bytes": len(self.audio),
            "detail": self.detail,
        }


def _env_url() -> str:
    return (os.getenv("AHANAVOICE_URL") or "").rstrip("/")


def _cloud_base() -> str:
    return (os.getenv("AHANAVOICE_CLOUD_URL") or DEFAULT_CLOUD).rstrip("/")


def _allow_cloud() -> bool:
    return os.getenv("AHANAVOICE_ALLOW_CLOUD", "1").lower() in ("1", "true", "yes")


def _allow_preview() -> bool:
    return os.getenv("AHANAVOICE_ALLOW_PREVIEW", "1").lower() in ("1", "true", "yes")


def _http_json(
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes, Dict[str, str]]:
    body = json.dumps(payload).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json",
        "Accept": "audio/*, application/json",
        "User-Agent": "NeonTrader-Tim/ahanavoice",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        data = exc.read() if hasattr(exc, "read") else b""
        hdr_map = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        return exc.code, data, hdr_map


def _pcm16_wav(samples: list[int], sample_rate: int = 22050) -> bytes:
    n = len(samples)
    data_size = n * 2
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(struct.pack("<" + "h" * n, *samples))
    return buf.getvalue()


def desk_preview_wav(text: str, seat: VoiceSeat, *, pack_bytes: int = 0) -> bytes:
    """
    Tiny local mouth when serve_aarm / cloud are quiet.

    Uses seat pitch/rate and a hash of the slot (and pack size) so each
    AhanaVoice individual has a distinct color — not Jeremiah's neural decode.
    """
    sr = 22050
    rate = max(0.7, min(1.25, float(seat.rate) or 1.0))
    pitch = max(0.5, min(1.8, float(seat.pitch) or 1.0))
    base_f0 = 175.0 if seat.gender == "female" else 108.0
    f0 = base_f0 * pitch
    seconds = max(0.55, min(8.0, 0.055 * max(1, len(text.strip())) / rate))
    n = int(sr * seconds)
    seed = (sum(ord(c) for c in seat.slot) + pack_bytes) % 997
    samples: list[int] = []
    words = max(1, len(text.split()))
    for i in range(n):
        t = i / sr
        syl = 0.5 + 0.5 * math.sin(2 * math.pi * (words * 1.35) * t * rate + seed)
        env = min(1.0, t * 8) * min(1.0, (seconds - t) * 6) * (0.55 + 0.45 * syl)
        f1 = f0
        f2 = f0 * (2.02 + (seed % 7) * 0.01)
        f3 = f0 * (3.1 + (seed % 5) * 0.02)
        vibr = 1.0 + 0.012 * math.sin(2 * math.pi * 5.2 * t)
        sig = (
            0.55 * math.sin(2 * math.pi * f1 * vibr * t)
            + 0.28 * math.sin(2 * math.pi * f2 * vibr * t)
            + 0.12 * math.sin(2 * math.pi * f3 * vibr * t)
        )
        if int(t * words / seconds) != int((t - 1 / sr) * words / seconds):
            sig += 0.15 * math.sin(2 * math.pi * (1200 + seed) * t)
        val = int(max(-1.0, min(1.0, sig * env * 0.55)) * 32767)
        samples.append(val)
    return _pcm16_wav(samples, sr)


class AhanaVoiceClient:
    """Tim's mouth — Jeremiah AhanaVoice pack + seats."""

    def __init__(
        self,
        *,
        slot: Optional[str] = None,
        base_url: Optional[str] = None,
        pack_path: Optional[str] = None,
    ):
        self.slot = slot or os.getenv("AHANAVOICE_VOICE") or TIM_DEFAULT_SLOT
        self.base_url = (base_url if base_url is not None else _env_url()).rstrip("/")
        self._pack = None
        self._fp: Dict[str, Any] = {}
        try:
            self._pack = load_pack(pack_path)
            self._fp = pack_fingerprint(self._pack)
        except Exception as exc:
            logger.warning("AhanaVoice pack not loaded: %s", exc)
            self._fp = {"pack_bytes": 0, "brand": "AhanaVoice"}

    @property
    def pack_bytes(self) -> int:
        return int(self._fp.get("pack_bytes") or 0)

    def seat(self, slot: Optional[str] = None) -> VoiceSeat:
        return resolve_seat(slot or self.slot)

    def status(self) -> Dict[str, Any]:
        seat = self.seat()
        return {
            "enabled": True,
            "brand": "AhanaVoice",
            "slot": seat.slot,
            "seat": seat.as_dict(),
            "pack": self._fp,
            "url": self.base_url or None,
            "cloud": _cloud_base() if _allow_cloud() else None,
            "preview_allowed": _allow_preview(),
        }

    def speak(self, text: str, *, slot: Optional[str] = None) -> SpeechResult:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty speech text")
        text = text[:1800]
        seat = self.seat(slot)
        pack_bytes = self.pack_bytes or 50950

        if self.base_url:
            try:
                result = self._speak_openai_style(text, seat)
                if result:
                    return result
            except Exception as exc:
                logger.warning("AhanaVoice serve_aarm path failed: %s", exc)

        if _allow_cloud():
            try:
                result = self._speak_cloud_say(text, seat, pack_bytes)
                if result:
                    return result
            except Exception as exc:
                logger.warning("AhanaVoice cloud say failed: %s", exc)

        if not _allow_preview():
            raise RuntimeError(
                "AhanaVoice speech unavailable (no serve_aarm, cloud quiet, preview disabled)"
            )
        wav = desk_preview_wav(text, seat, pack_bytes=pack_bytes)
        return SpeechResult(
            audio=wav,
            content_type="audio/wav",
            mode="desk-preview",
            slot=seat.slot,
            pack_bytes=pack_bytes,
            detail=(
                "Local preview shaped by AhanaVoice seat pitch/rate; "
                "neural decode needs serve_aarm or cloud."
            ),
        )

    def _speak_openai_style(self, text: str, seat: VoiceSeat) -> Optional[SpeechResult]:
        url = f"{self.base_url}/v1/audio/speech"
        payload = {
            "model": os.getenv("AHANAVOICE_MODEL", DEFAULT_MODEL),
            "voice": seat.slot,
            "input": text,
            "response_format": "wav",
        }
        api_key = (os.getenv("AHANAVOICE_API_KEY") or "").strip()
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        status, data, hdrs = _http_json(url, payload, headers=headers)
        if status >= 400 or not data:
            logger.info("serve_aarm speech HTTP %s: %s", status, data[:160])
            return None
        ctype = hdrs.get("content-type", "audio/wav")
        if "json" in ctype and data[:1] == b"{":
            return None
        return SpeechResult(
            audio=data,
            content_type=ctype.split(";")[0].strip() or "audio/wav",
            mode="serve_aarm",
            slot=seat.slot,
            pack_bytes=self.pack_bytes,
            detail=hdrs.get("x-ahana-pack-bytes") or "",
        )

    def _speak_cloud_say(
        self, text: str, seat: VoiceSeat, pack_bytes: int
    ) -> Optional[SpeechResult]:
        url = f"{_cloud_base()}/api/say"
        payload = {
            "text": text,
            "gender": seat.gender,
            "slot": seat.slot,
        }
        status, data, hdrs = _http_json(
            url,
            payload,
            headers={
                "Origin": _cloud_base(),
                "Referer": f"{_cloud_base()}/talk",
            },
        )
        if status >= 400 or not data:
            logger.info("cloud /api/say HTTP %s: %s", status, data[:200])
            return None
        ctype = hdrs.get("content-type", "")
        if "json" in ctype or data[:1] == b"{":
            logger.info("cloud /api/say non-audio: %s", data[:200])
            return None
        if data[:4] not in (b"RIFF", b"ID3", b"\xff\xfb", b"OggS"):
            if "audio" not in ctype:
                return None
        pb = int(hdrs.get("x-ahana-pack-bytes") or pack_bytes or 0)
        return SpeechResult(
            audio=data,
            content_type=(ctype.split(";")[0].strip() if ctype else "audio/wav"),
            mode="cloud",
            slot=seat.slot,
            pack_bytes=pb or pack_bytes,
            detail="Borrowed AhanaVoice cloud mouth with Jeremiah pack",
        )


_client: Optional[AhanaVoiceClient] = None


def get_ahanavoice_client() -> AhanaVoiceClient:
    global _client
    if _client is None:
        _client = AhanaVoiceClient()
    return _client


def speak_tim(text: str, *, slot: Optional[str] = None) -> SpeechResult:
    return get_ahanavoice_client().speak(text, slot=slot)
