# AhanaVoice for Tim

Tim narrates through **Jeremiah's AhanaVoice** tiny pack — not a cloud clone mill, not a 7B.

## What we borrowed

| Asset | Path / value |
|-------|----------------|
| Pack | `vendor/ahanavoice/jeremiah-av-experts-cpu.aarm` (50,950 B) |
| Roster | `vendor/ahanavoice/individuals.json` (12 seats) |
| Default Tim seat | `drew-three-am` (aliases: `tim`, `jeremiah`) |
| Profile size | 512 B / seat (256×f16) — the public ~16KB story is the seat SKU |

Public contract matches [ahanavoice.com](https://ahanavoice.com): plug `voice=<slot>` into OpenAI-style `/v1/audio/speech`.

## Speech path (priority)

1. **`AHANAVOICE_URL`** — real `serve_aarm` / desk mouth (`POST /v1/audio/speech`)
2. **Cloud** — `POST https://ahanavoice.com/api/say` when `AHANAVOICE_ALLOW_CLOUD=1`
3. **Desk-preview** — local WAV shaped by seat pitch/rate (honest fallback; **not** the neural decoder)

## Run desk mouth locally

```bash
pip install zstandard
python scripts/serve_ahanavoice.py --port 9635
export AHANAVOICE_URL=http://127.0.0.1:9635
```

Cockpit: **Speak (AhanaVoice)** plays Tim's last narration / decision line.

## Env

See `.env.ahanavoice.example`.

## Naming

Public brand: **AhanaVoice**. Do not ship “Aloha Voice” in UI or docs.
