# AhanaTrade

Retail day-trading desk for E*TRADE: limit-only, 7:00am–8:00pm ET, $10k deployed-out cap, plug-and-play agent brain.

The GitHub repository is still named Neon-Trader.

This is not investment advice and nothing here is a guaranteed return.

## Product

AhanaTrade is the Streamlit desk. A dark premium splash is the landing page; **Enter the desk** opens a single workspace: chart with the levels the catcher is using, a plan-alert feed, remaining budget, and E*TRADE OAuth with preview-then-place.

- **Session**: 7:00am–8:00pm ET (Hawaii UI is ET-6 in August)
- **Orders**: LIMIT + GOOD_FOR_DAY only (EXTENDED premarket / after-hours)
- **Risk**: $10,000 aggregate deployed-out; $3.5k/name PM/AH, $5k RTH; max 2 names PM/AH, 3 RTH; overnight snipes flat 15:50 ET (20:00 if AH)
- **Catcher**: Mechanical setups A/B/C/D on OHLCV (public tape if broker quotes are missing). Each catch is a plan card sized under the remaining sleeve.
- **Brain**: Plug in a Grok Bot or any OpenAI-compatible / webhook agent via `AHANA_BRAIN_URL`. If unset, a local council stub annotates catches.
- **Memory**: AhanaFlow lookback (compressed KV + RAG). SDK is import-or-stub; local gzip JSONL fallback so history still accumulates.
- **Broker**: E*TRADE sandbox first. Live requires `ETRADE_ENV=production` **and** per-order `confirm_live=True`.

Sister products (AhanaZip, Chatwire / Cloud Wire, aarmOS) are private. Public AhanaFlow lives at [AhanaAi-Company/AhanaFlow](https://github.com/AhanaAi-Company/AhanaFlow) — this tree never vendors that `sdk/`.

## Features

- **Splash / landing**: AhanaTrade hero, session rules, CTA into the desk. No live balances or quotes on the splash.
- **Desk chart**: Candles plus VWAP, opening 15m range, PM 7:00–9:20 range, holdings peak/valley overlay, and the invalidation the catcher is using.
- **Strategy catch**: A Premarket gap 7:00–9:20 ET, B Open drive 9:30–10:15 (first 15m / opening range), C VWAP reclaim 10:00–15:45, D AH follow 16:00–20:00. Peak/valley (trim peaks, buy dips, leave a runner) is a holdings overlay, not letter D. Kona Latch experimental, default OFF.
- **Plan alerts**: Symbol, setup, side, limit zone, size $ and shares under remaining budget, invalidation, flatten time, why it fired, IRA-short note, similar past setups.
- **Budget**: Single book in `desk_risk.py` / `config.RISK` — not a second ledger.
- **E*TRADE ticket**: OAuth, preview, then place. Live will not one-shot.
- **Plug-in brain**: `AHANA_BRAIN_URL` + optional `AHANA_BRAIN_TOKEN` annotates catches when set.
- **AhanaFlow memory**: Compressed lookback of plans/alerts/fills. Local gzip JSONL if the SDK is not installed.
- **Private-stack adapters** (no-op if the package is missing): AhanaZip pack, Chatwire transport.

## Architecture Overview

```text
Splash (AhanaTrade) → Enter the desk
    ↓
Desk workspace
├─ Chart overlays (VWAP / OR / PM / invalidation)
├─ Strategy catcher A gap / B open drive / C VWAP / D AH follow → plan cards
├─ AhanaMemory RAG (similar past setups)
└─ E*TRADE preview → place
    └─ DeskRiskGate  (LIMIT, $10k-out, per-name, IRA shorts)
```

## Quick Start

### Local Setup (No Docker)

```bash
pip install -r docker/requirements.cpu.txt
export OTLP_ENABLED=false
streamlit run app/app.py
```

Then open `http://localhost:8501`. The splash is Home; **Enter the desk** opens the workspace.

`streamlit run app/main.py` is the same desk plus the OAuth sidebar.

### With Docker

```bash
cd docker
docker compose up --build
```

Access at `http://localhost:8501`.

## Plug-in agent brain

Set these in the environment (never commit tokens):

| Variable | Default | Notes |
|----------|---------|-------|
| `AHANA_BRAIN_URL` | _(unset)_ | Webhook JSON endpoint **or** OpenAI-compatible `/v1/chat/completions` URL |
| `AHANA_BRAIN_TOKEN` | _(unset)_ | Optional bearer token |
| `AHANA_BRAIN_MODEL` | `grok` | Model id when the URL is OpenAI-compatible |

If `AHANA_BRAIN_URL` is unset, the desk uses a local council stub to annotate catches. If the plugin call fails, it falls back to the stub.

See `app/services/brain_plugin.py`.

## AhanaFlow lookback + AhanaZip

Install the public SDK from [AhanaAi-Company/AhanaFlow](https://github.com/AhanaAi-Company/AhanaFlow) `sdk/` if you want the remote compressed KV + vector RAG. Do not copy that source into this repo.

| Variable | Default | Notes |
|----------|---------|-------|
| `AHANAFLOW_URL` | _(unset)_ | Remote AhanaFlow endpoint. Remote put/get/query only when the `ahanaflow` package is also installed. |
| `AHANAFLOW_LICENSE` / `AHANAFLOW_TOKEN` | _(unset)_ | Optional license/token (never logged, never committed) |
| `AHANAFLOW_DATA_DIR` | `data/ahanaflow/` | Local gzip JSONL lookback (gitignored) |
| `AHANAZIP_DIR` | _(unset)_ | Enable AhanaZip blob compress if the private package is installed; else stdlib gzip |
| `CHATWIRE_URL` | _(unset)_ | Chatwire transport if the package is installed |

Without the SDK, `put()` / `get()` / `query()` / `list_range()` still persist gzip-compressed JSONL under `data/ahanaflow/`. Never pickle. The desk RAG facade (`app/services/ahana_memory.py`) is a memory layer only — not a second trading brain.

## E*TRADE day-trading desk

AhanaTrade stays the Streamlit UI. Execution goes through the existing E*TRADE path (`etrade_service`, OAuth 1.0a HMAC-SHA1, `broker.ETradeBroker`). Alpaca may remain in the tree unused. There is no second bot.

### Sandbox vs live

| | Sandbox (default) | Live |
|---|---|---|
| Env | `ETRADE_ENV=sandbox` (or unset) | `ETRADE_ENV=production` **and** per-order `confirm_live=True` |
| Host | `https://apisb.etrade.com/v1` | `https://api.etrade.com/v1` |
| Place | Preview first, then place with `preview_id` | Same; one-shot preview+place is disabled |

OAuth tokens expire at midnight ET and go idle after ~2 hours. Re-auth via the OAuth page.

### Credentials (never commit)

Set `ETRADE_CONSUMER_KEY` and `ETRADE_CONSUMER_SECRET` in the environment or a
gitignored file (`etrade.env`, `.env`, or `ETRADE_ENV_FILE`). Optional access
tokens: `ETRADE_ACCESS_TOKEN`, `ETRADE_ACCESS_TOKEN_SECRET`. Copy `.env.example`.
Do not put keys in the repo, README, or logs.

### Session clock (America/New_York)

Hawaii UI is **ET-6 in August** (HST vs EDT).

| Window (ET) | Phase | Order flags |
|---|---|---|
| 04:00–07:00 | Blackout | No orders |
| 07:00–09:30 | Premarket | `EXTENDED` + `LIMIT` + `GOOD_FOR_DAY` |
| ~09:28 | Cancel-before-roll | Cancel remaining EXTENDED working orders so they do not auto-roll |
| 09:30–16:00 | Regular | `REGULAR` + `LIMIT` + `GOOD_FOR_DAY` |
| 16:00–20:00 | After-hours | `EXTENDED` + `LIMIT` + `GOOD_FOR_DAY`; unfilled working limits are repriced as the tape moves |
| 20:00–07:00 | Overnight out | No overnight risk |

All orders are LIMIT. Crypto is not sent on the REST Order API. PDT / $25k is **not** enforced in-app; if E*TRADE rejects a day trade, the error is surfaced.

Overnight snipes flatten at **15:50 ET** (20:00 if the desk is still in after-hours).

Shorts are allowed on cash/margin accounts. IRA accounts may not short.

### Risk caps

- Max **$10,000 deployed-out aggregate** across positions
- **$3,500 / name** premarket and after-hours; **$5,000 / name** RTH
- Max **2 names** PM/AH, **3 names** RTH
- Max 3 open orders
- Daily-loss halt for **new entries only**: min($250, 2.5% equity)
- Unique `clientOrderId` ≤ 20 alphanumeric

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `ETRADE_ENV` | `sandbox` | `production` required for live |
| `ETRADE_CONSUMER_KEY` | _(env / gitignored file)_ | OAuth consumer key |
| `ETRADE_CONSUMER_SECRET` | _(env / gitignored file)_ | OAuth consumer secret |
| `ETRADE_ACCESS_TOKEN` | _(after OAuth)_ | Expires midnight ET / idle ~2h |
| `ETRADE_ACCESS_TOKEN_SECRET` | _(after OAuth)_ | Pair with access token |
| `ETRADE_OAUTH_STATE_FILE` | `~/.secrets/etrade_oauth_request.json` | JSON request-token store (mode 0600) |
| `AHANA_BRAIN_URL` | _(unset)_ | Plug-in brain; council stub used if empty |
| `AHANA_BRAIN_TOKEN` | _(unset)_ | Optional bearer auth for the brain |
| `AHANAFLOW_URL` | _(unset)_ | Remote AhanaFlow; local gzip JSONL always on |
| `AHANAZIP_DIR` | _(unset)_ | Enable AhanaZip if the package is installed |
| `CHATWIRE_URL` | _(unset)_ | Enable Chatwire adapter if the package is installed |
| `AHANA_KONA_LATCH` | `0` | Experimental detector, default off |
| `OTLP_ENABLED` | `true` | Disable if no collector available |
| `OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry collector address |
| `ALLOW_EARLY_START` | `true` | Start UI before LLM ready |
| `OLLAMA_BASE_URL` | `http://ollama-gpu:11434` | LLM endpoint for the local council |

## Key Components

| File | Purpose |
|------|---------|
| `app/components/splash.py` | Retail splash / landing page |
| `app/components/desk.py` | Primary desk: chart, plans, budget, ticket |
| `app/services/strategy_catcher.py` | A Premarket gap / B Open drive / C VWAP reclaim / D AH follow → plan cards (peak/valley is a holdings overlay) |
| `app/services/desk_risk.py` | Session, LIMIT-only, $10k-out, per-name, IRA shorts |
| `app/services/ahana_memory.py` | Thin RAG over AhanaFlow / local gzip JSONL |
| `app/services/adapters/ahanaflow.py` | Store put/get/query (SDK or local fallback) |
| `app/services/brain_plugin.py` | Plug-in brain (Grok / OpenAI-compatible / webhook) |
| `app/services/broker.py` | E*TRADE execution path |
| `app/app.py` / `app/main.py` | Streamlit UI (splash + desk) |

## Testing

```bash
pytest
```

Tests never call `api.etrade.com`. Detectors run on synthetic OHLCV. AhanaFlow tests use the local gzip JSONL fallback.

## License

Demonstration project. Use responsibly. Never enable live trading without sandbox testing, OAuth, and `confirm_live`.
