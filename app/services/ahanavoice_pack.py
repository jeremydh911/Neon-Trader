"""
AhanaVoice .aarm pack loader — Jeremiah's tiny mastered seats.

Public contract (ahanavoice.com):
  Magic AARMv1 · ~50,950 B pack · 100 × f16×256 (512 B) voice profiles
  Roster: individuals.json · OpenAI-style voice=<slot>

Vendored: vendor/ahanavoice/jeremiah-av-experts-cpu.aarm
Neural decode via AHANAVOICE_URL / serve_aarm or cloud /api/say.
"""

from __future__ import annotations

import json
import logging
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAGIC = b"AARMv1"
PROFILE_BYTES = 512  # 256 × f16
DEFAULT_PACK = "jeremiah-av-experts-cpu.aarm"
DEFAULT_ROSTER = "individuals.json"
TIM_DEFAULT_SLOT = "drew-three-am"


def _repo_vendor() -> Path:
    return Path(__file__).resolve().parents[2] / "vendor" / "ahanavoice"


def pack_search_paths(explicit: Optional[str] = None) -> List[Path]:
    env = (explicit or os.getenv("AHANAVOICE_PACK") or "").strip()
    roots = [
        Path(env) if env else None,
        Path(os.getenv("AHANAVOICE_DATA_ROOT", "./data/ahanavoice")) / DEFAULT_PACK,
        _repo_vendor() / DEFAULT_PACK,
        Path("./vendor/ahanavoice") / DEFAULT_PACK,
    ]
    return [p for p in roots if p is not None]


def roster_search_paths(explicit: Optional[str] = None) -> List[Path]:
    env = (explicit or os.getenv("AHANAVOICE_ROSTER") or "").strip()
    roots = [
        Path(env) if env else None,
        Path(os.getenv("AHANAVOICE_DATA_ROOT", "./data/ahanavoice")) / DEFAULT_ROSTER,
        _repo_vendor() / DEFAULT_ROSTER,
        Path("./vendor/ahanavoice") / DEFAULT_ROSTER,
    ]
    return [p for p in roots if p is not None]


@dataclass(frozen=True)
class VoiceSeat:
    slot: str
    name: str
    gender: str
    pitch: float
    rate: float
    bio: str = ""
    line: str = ""
    face: str = ""
    profile_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "name": self.name,
            "gender": self.gender,
            "pitch": self.pitch,
            "rate": self.rate,
            "bio": self.bio,
            "line": self.line,
            "face": self.face,
            "profile_id": self.profile_id,
        }


@dataclass
class AarmPack:
    path: Path
    raw: bytes
    meta: Dict[str, Any]
    profile_ids: List[str]
    pack_bytes: int

    @property
    def seat_count(self) -> int:
        return len(self.profile_ids)


def _decompress_payload(raw: bytes) -> bytes:
    if len(raw) < 32 or raw[:6] != MAGIC:
        raise ValueError("Not an AARMv1 pack (missing magic)")
    try:
        import zstandard as zstd
    except ImportError as exc:
        raise RuntimeError("zstandard required to read .aarm packs") from exc
    uncompressed = struct.unpack_from("<I", raw, 12)[0]
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(raw[28:], max_output_size=max(uncompressed, 1_000_000))


def _profile_ids_from_meta(meta: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for group in meta.get("groups") or []:
        key = str(group.get("key") or "")
        if "voice_profiles." not in key:
            continue
        part = key.split("voice_profiles.", 1)[-1]
        pid = part.split(".", 1)[0]
        if pid and pid not in ids:
            ids.append(pid)
    return ids


def load_pack(path: Optional[str | Path] = None) -> AarmPack:
    last_err: Optional[Exception] = None
    candidates = [Path(path)] if path else pack_search_paths()
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            raw = cand.read_bytes()
            payload = _decompress_payload(raw)
            meta = json.loads(payload.decode("utf-8"))
            ids = _profile_ids_from_meta(meta)
            logger.info(
                "AhanaVoice pack loaded path=%s bytes=%s seats=%s",
                cand,
                len(raw),
                len(ids),
            )
            return AarmPack(
                path=cand.resolve(),
                raw=raw,
                meta=meta,
                profile_ids=ids,
                pack_bytes=len(raw),
            )
        except Exception as exc:
            last_err = exc
            continue
    raise FileNotFoundError(
        f"AhanaVoice .aarm pack not found. Tried {[str(p) for p in candidates]}. Last error: {last_err}"
    )


def load_roster(path: Optional[str | Path] = None) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    candidates = [Path(path)] if path else roster_search_paths()
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            return json.loads(cand.read_text(encoding="utf-8"))
        except Exception as exc:
            last_err = exc
            continue
    raise FileNotFoundError(
        f"AhanaVoice roster not found. Tried {[str(p) for p in candidates]}. Last error: {last_err}"
    )


def seats_from_roster(roster: Optional[Dict[str, Any]] = None) -> List[VoiceSeat]:
    data = roster or load_roster()
    out: List[VoiceSeat] = []
    for row in data.get("individuals") or []:
        slot = str(row.get("slot") or "").strip()
        if not slot:
            continue
        out.append(
            VoiceSeat(
                slot=slot,
                name=str(row.get("name") or "").strip(),
                gender=str(row.get("gender") or "").strip().lower(),
                pitch=float(row.get("pitch") or 1.0),
                rate=float(row.get("rate") or 1.0),
                bio=str(row.get("bio") or ""),
                line=str(row.get("line") or ""),
                face=str(row.get("face") or ""),
            )
        )
    return out


def resolve_seat(slot: Optional[str] = None) -> VoiceSeat:
    wanted = (
        slot
        or os.getenv("AHANAVOICE_VOICE")
        or os.getenv("AHANAVOICE_SLOT")
        or TIM_DEFAULT_SLOT
    ).strip()
    aliases = {
        "tim": TIM_DEFAULT_SLOT,
        "tim-momentum": TIM_DEFAULT_SLOT,
        "jeremiah": TIM_DEFAULT_SLOT,
        "jeremiah-mastered": TIM_DEFAULT_SLOT,
    }
    wanted = aliases.get(wanted.lower(), wanted)
    seats = {s.slot: s for s in seats_from_roster()}
    if wanted in seats:
        return seats[wanted]
    for s in seats.values():
        if s.gender == "male":
            return s
    if seats:
        return next(iter(seats.values()))
    raise KeyError(f"No AhanaVoice seat for slot={wanted!r}")


def pack_fingerprint(pack: Optional[AarmPack] = None) -> Dict[str, Any]:
    p = pack or load_pack()
    return {
        "brand": "AhanaVoice",
        "pack_path": str(p.path),
        "pack_bytes": p.pack_bytes,
        "profile_bytes": PROFILE_BYTES,
        "seat_profiles": p.seat_count,
        "seat_count": p.seat_count,
        "default_slot": TIM_DEFAULT_SLOT,
        "magic": MAGIC.decode("ascii"),
    }
