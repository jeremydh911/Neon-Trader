"""AhanaVoice / Jeremiah tiny-pack integration for Tim."""

from __future__ import annotations

import os

os.environ["AHANAVOICE_ALLOW_CLOUD"] = "0"
os.environ["AHANAVOICE_ALLOW_PREVIEW"] = "1"
os.environ["AHANAVOICE_ENGINE"] = "preview"
os.environ.pop("AHANAVOICE_URL", None)


def test_load_jeremiah_pack():
    from app.services.ahanavoice_pack import MAGIC, load_pack, pack_fingerprint

    pack = load_pack()
    assert pack.raw[:6] == MAGIC
    assert pack.pack_bytes == 50950
    assert pack.seat_count >= 12
    fp = pack_fingerprint(pack)
    assert fp["pack_bytes"] == 50950
    assert fp["profile_bytes"] == 512


def test_roster_and_tim_alias():
    from app.services.ahanavoice_pack import TIM_DEFAULT_SLOT, resolve_seat, seats_from_roster

    seats = seats_from_roster()
    assert len(seats) == 12
    assert "drew-three-am" in {s.slot for s in seats}
    assert resolve_seat("tim").slot == TIM_DEFAULT_SLOT
    assert resolve_seat("jeremiah").slot == TIM_DEFAULT_SLOT


def test_desk_preview_speech():
    from app.services.ahanavoice_client import AhanaVoiceClient

    client = AhanaVoiceClient(base_url="")
    result = client.speak("Engines decide. Hard stops. I narrate.")
    assert result.mode == "desk-preview"
    assert result.slot == "drew-three-am"
    assert result.pack_bytes == 50950
    assert result.audio[:4] == b"RIFF"
    assert len(result.audio) > 1000


def test_engine_mode_borrow_default():
    from app.services import ahanavoice_client as av

    os.environ.pop("AHANAVOICE_ENGINE", None)
    assert av._engine_mode() == "borrow"
    os.environ["AHANAVOICE_ENGINE"] = "local"
    assert av._engine_mode() == "local"
    os.environ["AHANAVOICE_ENGINE"] = "preview"
    assert av._engine_mode() == "preview"
    os.environ.pop("AHANAVOICE_ENGINE", None)


def test_tim_copilot_speak():
    from app.services.tim_copilot import TimCopilot

    copilot = TimCopilot(paper_mode=True)
    out = copilot.speak("Paper snipe armed.")
    assert out["status"] == "success"
    assert out["mode"] == "desk-preview"
    assert out["audio"][:4] == b"RIFF"
