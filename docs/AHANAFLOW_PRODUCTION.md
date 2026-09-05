# AhanaFlow Production — Neon Trader

Self-hosted AhanaFlow is the **preferred** memory backend for Neon Trader.
Trade decisions stay on your box; Grok’s cloud API can plug in later as `AHANAFLOW_MODE=remote`.

## Quick start (prod-shaped)

```bash
git submodule update --init --recursive vendor/AhanaFlow
cp .env.ahanaflow.example .env.ahanaflow
# edit secrets if enabling auth

# Terminal A — vector server (127.0.0.1 only by default)
./scripts/run_ahanaflow_selfhost.sh

# Terminal B — health + smoke
export $(grep -v '^#' .env.ahanaflow | xargs)
python3 scripts/ahanaflow_healthcheck.py
python3 scripts/smoke_ahanaflow_prod.py

# Terminal B — Tim UI
streamlit run app/main.py
```

## Modes

| `AHANAFLOW_MODE` | Behavior |
|------------------|----------|
| `selfhosted` | TCP → local `VectorStateServerV2` (recommended) |
| `embedded` | In-process engine (no daemon; fine for unit tests) |
| `auto` | Try selfhosted, fall back to embedded |
| `remote` | Reserved for cloud API |

## Hardening checklist

- [ ] Bind `127.0.0.1` (script refuses `0.0.0.0` unless `AHANAFLOW_ALLOW_PUBLIC=1`)
- [ ] Persist WAL on durable disk (`AHANAFLOW_WAL`)
- [ ] Enable API key auth if the host is shared: `AHANAFLOW_REQUIRE_AUTH=1` + `AHANAFLOW_API_KEY`
- [ ] Run `python3 scripts/ahanaflow_healthcheck.py` from process supervisor / k8s probe
- [ ] Run `python3 scripts/smoke_ahanaflow_prod.py` after deploys
- [ ] Keep `AHANAFLOW_EMBED_DIM` and collection name stable across upgrades
- [ ] Paper/mock only until broker path is separately signed off (`PAPER_MODE=1`)

## Ops commands

```bash
# Start
./scripts/run_ahanaflow_selfhost.sh

# Readiness (exit 0 = healthy)
AHANAFLOW_HOST=127.0.0.1 AHANAFLOW_PORT=9634 python3 scripts/ahanaflow_healthcheck.py

# Full smoke (spins ephemeral server if none listening)
python3 scripts/smoke_ahanaflow_prod.py

# Unit / integration
PYTHONPATH=. AHANAFLOW_MODE=embedded pytest tests/test_ahanaflow_memory.py -q
```

## Failure behavior

- **Search soft-fails** to `[]` on transport errors so Tim keeps trading
- **Writes** raise (better to know memory is down than silently drop decisions)
- **`auto` mode** falls back to embedded if selfhost is unreachable at boot

## Auth (optional)

```bash
export AHANAFLOW_REQUIRE_AUTH=1
export AHANAFLOW_API_KEY="$(openssl rand -hex 32)"
./scripts/run_ahanaflow_selfhost.sh
# client side: same AHANAFLOW_API_KEY in Tim / Streamlit env
```

## Not production-ready yet (trading)

AhanaFlow memory can be production-hardened for **desk memory**. Live capital still requires separate broker/fill/risk sign-off beyond this doc.
