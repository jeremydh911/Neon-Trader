#!/usr/bin/env python3
"""
Sync Jeremiah's AhanaVoice pack + roster from ahanavoice.com into vendor/.

This is how we "borrow" the public 16KB-class seats:
  - pack:   /pack/jeremiah-av-experts-cpu.aarm  (~50,950 B)
  - roster: /individuals.json

Engine (mouth) stays on AhanaVoice cloud or a local serve_aarm pointed
at AHANAVOICE_URL — see docs/AHANAVOICE_TIM.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "vendor" / "ahanavoice"
PACK_URL = "https://ahanavoice.com/pack/jeremiah-av-experts-cpu.aarm"
ROSTER_URL = "https://ahanavoice.com/individuals.json"
PACK_NAME = "jeremiah-av-experts-cpu.aarm"
ROSTER_NAME = "individuals.json"


def _fetch(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "NeonTrader-Tim/ahanavoice-sync",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sync(out_dir: Path, *, force: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_path = out_dir / PACK_NAME
    roster_path = out_dir / ROSTER_NAME

    pack = _fetch(PACK_URL)
    if not pack.startswith(b"AARMv1"):
        raise RuntimeError(f"unexpected pack magic: {pack[:8]!r}")
    if len(pack) < 10_000:
        raise RuntimeError(f"pack too small: {len(pack)} B")

    roster_raw = _fetch(ROSTER_URL)
    roster = json.loads(roster_raw.decode("utf-8"))
    if not roster.get("individuals"):
        raise RuntimeError("roster missing individuals")

    wrote_pack = force or (not pack_path.is_file()) or pack_path.read_bytes() != pack
    wrote_roster = (
        force
        or (not roster_path.is_file())
        or roster_path.read_bytes() != roster_raw
    )
    if wrote_pack:
        pack_path.write_bytes(pack)
    if wrote_roster:
        roster_path.write_bytes(roster_raw)

    digest = hashlib.sha256(pack).hexdigest()
    meta = {
        "source": "https://ahanavoice.com",
        "brand": "AhanaVoice",
        "pack": PACK_NAME,
        "pack_bytes": len(pack),
        "pack_sha256": digest,
        "roster": ROSTER_NAME,
        "seats": len(roster.get("individuals") or []),
        "wrote_pack": wrote_pack,
        "wrote_roster": wrote_roster,
        "engine": {
            "borrow": "POST https://ahanavoice.com/api/say",
            "openai_style": "POST {AHANAVOICE_URL}/v1/audio/speech",
            "note": "16KB-class seats live in the .aarm; mouth/engine is borrowed",
        },
    }
    (out_dir / "SYNC_META.json").write_text(json.dumps(meta, indent=2) + "\n")
    (out_dir / "README.md").write_text(
        "# AhanaVoice (borrowed for Tim)\n\n"
        "Public brand: **AhanaVoice** (not Aloha Voice).\n\n"
        f"- Pack: `{PACK_NAME}` ({len(pack)} B) from `{PACK_URL}`\n"
        f"- Roster: `{ROSTER_NAME}` ({len(roster.get('individuals') or [])} seats)\n"
        "- Default Tim seat: `drew-three-am`\n"
        "- Engine: borrow cloud `/api/say` or point `AHANAVOICE_URL` at `serve_aarm`\n"
        "- Resync: `python scripts/sync_ahanavoice.py`\n"
        "- Docs: `docs/AHANAVOICE_TIM.md`\n"
    )
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync AhanaVoice pack/roster for Tim")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        meta = sync(args.out, force=args.force)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **meta}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
