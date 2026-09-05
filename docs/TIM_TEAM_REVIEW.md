# Tim team review — keep the bot happy

Audience: desk eng + risk + product. Goal: Tim stays a **momentum sniper with hard exits**, remembers lessons, and never quietly fails closed into bad behavior.

## What just landed

- Self-hosted AhanaFlow memory (preferred over cloud)
- Governance: bind policy, WAL jail, collection validation, query caps, chat TTL
- Auth errors no longer soft-fail to empty memory
- **TLS on the NDJSON TCP wire** (`AHANAFLOW_TLS=1`, cert generator, mandatory for public/remote)

## Recommendations for the team

### P0 — do next

| # | Item | Why Tim cares |
|---|------|----------------|
| 1 | Default desk install to `AHANAFLOW_TLS=1` + self-signed certs on loopback | API keys and trade text no longer ride cleartext even on localhost shared boxes |
| 2 | Wire memory write failures into the Cockpit risk strip (red chip) | Tim already logs warnings; operators must *see* when memory is down mid-session |
| 3 | Persist broker stop IDs ↔ Tim decisions in AhanaFlow on every fill | Hard exits only stay hard if memory + broker agree after restart |
| 4 | Keep `PAPER_MODE=1` / mock broker until fill-polling + stop arming are signed off | Happy Tim ≠ live capital |

### P1 — quality of life

| # | Item | Why Tim cares |
|---|------|----------------|
| 5 | Structured Tim “mood”: engines green / memory green / risk green | One glance that Tim is allowed to snipe |
| 6 | Decision → outcome feedback loop (WIN/LOSS tags on exits) | Compressed RAG only helps if outcomes are written back |
| 7 | Cap concurrent AhanaFlow scans from UI pages | Avoid desk UI melting the vector server during “show me everything” |
| 8 | Rotate API keys via `AHANAFLOW_API_KEYS_FILE` (hashed) | Env single-key is fine for paper; not for shared hosts |

### P2 — later (still out of scope for this PR)

| # | Item | Why Tim cares |
|---|------|----------------|
| 9 | True intraday bars + fill polling | Momentum without fills is theater |
| 10 | Credible bar-replay backtest | Tim’s “I would have sniped” needs evidence |
| 11 | IPO scanner | Separate product surface; don’t pollute Tim’s momentum path |
| 12 | Mutual TLS / real CA for non-loopback | Self-signed is desk-OK; multi-host needs CA |

## Review checklist (for PR reviewers)

- [ ] Public bind without key **or** without TLS exits non-zero
- [ ] Non-loopback client without TLS raises `PermissionError`
- [ ] Search soft-fails transport only; auth raises
- [ ] TLS round-trip test passes (`test_tls_roundtrip_selfhosted`)
- [ ] Tim still refuses RSI dip-buy framing in UX copy
- [ ] Paper/mock flags remain default-on in examples

## Happy Tim definition (working)

Tim is happy when:

1. Momentum gates open only on strength (no dip-buy RSI stories)
2. Every paper fill arms a real broker stop
3. Memory remembers decisions + outcomes without silent empty recalls
4. Wire to memory is authenticated and (when exposed) encrypted
5. Risk strip tells the truth when anything above is broken

## How to exercise TLS locally

```bash
./scripts/generate_ahanaflow_tls.sh
AHANAFLOW_TLS=1 ./scripts/run_ahanaflow_selfhost.sh
export AHANAFLOW_TLS=1 AHANAFLOW_TLS_CA=tls/server.crt
python3 scripts/ahanaflow_healthcheck.py
PYTHONPATH=. pytest tests/test_ahanaflow_governance.py -q -k tls
```
