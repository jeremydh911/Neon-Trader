# AhanaTrade

Retail day-trading desk for E*TRADE: limit-only, 7:00am–8:00pm ET, $10k deployed-out cap, plug-and-play agent brain.

The GitHub repository is still named Neon-Trader.

This is not investment advice and nothing here is a guaranteed return.

## Product

AhanaTrade is the Streamlit desk. A dark premium splash is the landing page; **Enter the desk** opens the existing E*TRADE workspace.

- **Session**: 7:00am–8:00pm ET (Hawaii UI is ET-6 in August)
- **Orders**: LIMIT + GOOD_FOR_DAY only (EXTENDED premarket / after-hours)
- **Risk**: $10,000 aggregate deployed-out; max 3 open orders; overnight flat after 8:00pm ET
- **Brain**: Plug in a Grok Bot or any OpenAI-compatible / webhook agent via `AHANA_BRAIN_URL`. If unset, the Tina / Eddie / Gloria / Victor / Riley council stays in charge.
- **Broker**: E*TRADE sandbox first. Live requires `ETRADE_ENV=production` **and** per-order `confirm_live=True`.

Sister products (AhanaFlow, AhanaZip, Chatwire / Cloud Wire, aarmOS) are private. This public tree only ships env-gated import-or-stub adapters — it does not vendor their source.

## Features

- **Splash / landing**: AhanaTrade hero, session rules, CTA into the desk. No live balances or quotes on the splash.
- **Multi-agent council** (default brain): Tina, Eddie, Gloria, Victor, Riley
- **Plug-in brain**: `AHANA_BRAIN_URL` + optional `AHANA_BRAIN_TOKEN`
- **Private-stack adapters** (no-op if the package is missing): AhanaFlow session/memory bus, Chatwire transport, AhanaZip pack
- **Persistent learning**: per-agent RAG + online learners
- **Leaderboard**: +1 per $ won, -1.3 per $ lost
- **Observability**: OpenTelemetry tracing
- **Docker**: CPU/GPU containers with MCP ticker/chart services

## Architecture Overview

```text
Splash (AhanaTrade) → Enter the desk
    ↓
Streamlit UI (E*TRADE Dashboard / Trading)
    ↓
CouncilOrchestrator
├─ Plug-in brain (AHANA_BRAIN_URL)  OR  Tina/Eddie/Gloria/Victor/Riley
└─ Backend execution (approved LIMIT orders)
    └─ ETradeBroker  (sandbox default; live gated)
```

## Quick Start

### Local Setup (No Docker)

```bash
pip install -r docker/requirements.cpu.txt
export OTLP_ENABLED=false
streamlit run app/app.py
```

Then open `http://localhost:8501`. The splash is Home; **Enter the desk** goes to Trading.

### With Docker

```bash
cd docker
docker compose up --build
```

Access at `http://localhost:8501`.

### With Tracing (Jaeger)

```bash
docker run -d --name jaeger -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one:latest
export OTLP_ENABLED=true
export OTLP_ENDPOINT=http://localhost:4317
streamlit run app/app.py
```

View traces at `http://localhost:16686`.

## Plug-in agent brain

Set these in the environment (never commit tokens):

| Variable | Default | Notes |
|----------|---------|-------|
| `AHANA_BRAIN_URL` | _(unset)_ | Webhook JSON endpoint **or** OpenAI-compatible `/v1/chat/completions` URL |
| `AHANA_BRAIN_TOKEN` | _(unset)_ | Optional bearer token |
| `AHANA_BRAIN_MODEL` | `grok` | Model id when the URL is OpenAI-compatible |

If `AHANA_BRAIN_URL` is unset, the desk uses the existing council. If the plugin call fails, it falls back to the council.

See `app/services/brain_plugin.py`.

## Private-stack adapters

Optional, env-gated, import-or-stub. Missing packages log and no-op.

| Adapter | Env | Role |
|---------|-----|------|
| AhanaFlow | `AHANAFLOW_URL` | Session / memory bus |
| Chatwire / Cloud Wire | `CHATWIRE_URL` or `CLOUDWIRE_URL` | Compressed agent message transport |
| AhanaZip | `AHANAZIP_DIR` | Artifact compress / pack |

Do not clone or copy `jeremydh911/AhanaFlow`, `jeremydh911/AhanaZip`, `jeremydh911/Chatwire`, or aarmOS into this public tree.

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

All orders are LIMIT. Crypto is not sent on the REST Order API (account entitlement
does not override that). PDT / $25k is **not** enforced in-app; if E*TRADE rejects a
day trade, the error is surfaced.

### Risk caps

- Max **$10,000 deployed-out aggregate** across positions
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
| `AHANA_BRAIN_URL` | _(unset)_ | Plug-in brain; council used if empty |
| `AHANA_BRAIN_TOKEN` | _(unset)_ | Optional bearer auth for the brain |
| `AHANAFLOW_URL` | _(unset)_ | Enable AhanaFlow adapter if the package is installed |
| `CHATWIRE_URL` | _(unset)_ | Enable Chatwire adapter if the package is installed |
| `AHANAZIP_DIR` | _(unset)_ | Enable AhanaZip adapter if the package is installed |
| `OTLP_ENABLED` | `true` | Disable if no collector available |
| `OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry collector address |
| `ALLOW_EARLY_START` | `true` | Start UI before LLM ready |
| `OLLAMA_BASE_URL` | `http://ollama-gpu:11434` | LLM endpoint for the local council |

## Key Components

| File | Purpose |
|------|---------|
| `app/components/splash.py` | Retail splash / landing page |
| `app/services/brain_plugin.py` | Plug-in brain (Grok / OpenAI-compatible / webhook) |
| `app/services/adapters/` | AhanaFlow, Chatwire, AhanaZip stubs |
| `agent_framework.py` | Orchestration; honors plugin brain when configured |
| `specialist_agents.py` | Named team: Tina, Eddie, Gloria, Victor, Riley |
| `trading_council.py` | Council voting (used when no plugin brain) |
| `autonomous_trader.py` | Backend trader with broker interface |
| `broker.py` | E*TRADE execution path |
| `desk_risk.py` | Session, LIMIT-only, $10k-out |
| `app/app.py` | Streamlit UI (splash + desk) |

## Testing

```bash
pytest
```

## Troubleshooting

### App won't start

- Check Python 3.11+: `python --version`
- Install deps: `pip install -r docker/requirements.cpu.txt`

### No traces appearing

- Verify Jaeger: `docker ps | grep jaeger`
- Set `OTLP_ENDPOINT=http://localhost:4317`

### Database errors

- Remove stale DB: `rm ./data/leaderboard.db`

## License

Demonstration project. Use responsibly. Never enable live trading without sandbox testing, OAuth, and `confirm_live`.
