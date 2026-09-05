# AhanaVoice for Tim

Tim narrates through **Jeremiah’s AhanaVoice** tiny pack — borrowed mouth, local 16KB-class seats.

## Borrow model

| Layer | What | Where |
|-------|------|--------|
| **Voices (16KB-class)** | `.aarm` pack + roster | `vendor/ahanavoice/` (synced from ahanavoice.com) |
| **Engine (mouth)** | Neural TTS | Borrowed: `POST https://ahanavoice.com/api/say` or `AHANAVOICE_URL` / `serve_aarm` |
| **Fallback** | Desk-preview WAV | Seat pitch/rate only — labeled `desk-preview`, not neural |

Default engine mode: **`AHANAVOICE_ENGINE=borrow`** (cloud mouth first, then local URL, then preview).

## Sync pack + roster

```bash
python scripts/sync_ahanavoice.py
# → vendor/ahanavoice/jeremiah-av-experts-cpu.aarm  (~50,950 B)
# → vendor/ahanavoice/individuals.json              (12 seats)
```

## Speak

```bash
# Borrow AhanaVoice cloud engine with our pack identity (default)
export AHANAVOICE_ENGINE=borrow
export AHANAVOICE_VOICE=drew-three-am   # aliases: tim, jeremiah

# Or point at a real serve_aarm
export AHANAVOICE_ENGINE=local
export AHANAVOICE_URL=http://127.0.0.1:9635
python scripts/serve_ahanavoice.py --port 9635
```

Cockpit: **Speak (AhanaVoice)** plays Tim’s last narration / decision line.

## Env

See `.env.ahanavoice.example`.

## Naming

Public brand: **AhanaVoice**. Do not ship “Aloha Voice” in UI or docs.
