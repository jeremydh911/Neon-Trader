# Neon Trader 2.0 - Multi-Agent Trading Platform

A sophisticated multi-agent trading system with democratic council voting, per-agent learning, persistent leaderboard scoring, and end-to-end observability via OpenTelemetry tracing.

## Features

- **Multi-Agent Orchestration**: 5 named specialist traders (Tina, Eddie, Gloria, Victor, Riley) with unique personalities and domain expertise
- **Democratic Council**: Voting mechanism where agents debate and decide trades by majority with confidence weighting
- **Persistent Learning**: Per-agent RAG memory + online learners (sklearn) enable continuous improvement
- **Leaderboard Scoring**: +1 per $ won, -1.3 per $ lost; persistent SQLite database
- **Trade Reconciliation**: Pending trades tracked and resolved when broker confirms closures
- **Full Observability**: OpenTelemetry tracing of research → deliberation → execution → learning
- **Docker Ready**: CPU/GPU containers with MCP microservices for ticker and charting

## Architecture Overview

```text
Streamlit UI (Trading Page)
    ↓
CouncilOrchestrator
├─ Agent Research Phase (all agents propose)
├─ Council Deliberation (5 members vote)
└─ Backend Execution (approved trades)
    ├─ AutonomousTrader places order
    └─ Agents learn from outcome
        ├─ RAG memory updated
        └─ Online learner trained
```

## Test Today (Paper / Mock)

One command — no live capital:

```bash
./scripts/run_paper_test_today.sh
```

See [docs/TEST_TODAY.md](docs/TEST_TODAY.md). Keep `PAPER_MODE=1` and `USE_MOCK_BROKER=1`.

## Quick Start

### Local Setup (No Docker)

```bash
cd /home/jeremiah/Desktop/neon-trader-gpu
pip install -r docker/requirements.cpu.txt
export OTLP_ENABLED=false
streamlit run app/app.py
```

Then open `http://localhost:8501`.

### With Docker

```bash
cd docker
docker compose up --build
```

Access at `http://localhost:8501`.

### With Tracing (Jaeger)

Start Jaeger:

```bash
docker run -d --name jaeger -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one:latest
```

Run app with tracing:

```bash
export OTLP_ENABLED=true
export OTLP_ENDPOINT=http://localhost:4317
streamlit run app/app.py
```

View traces at `http://localhost:16686`.

## Key Components

| File | Purpose |
|------|---------|
| `agent_framework.py` | Core orchestration, base agent classes, RewardManager |
| `specialist_agents.py` | 8 specialist agents + 5 named team members |
| `trading_council.py` | Council voting logic (Tech, Sentiment, Risk, Memory, LLM) |
| `autonomous_trader.py` | Backend trader with broker interface and council approval |
| `rag_memory.py` | Per-agent RAG memory with embeddings and semantic search |
| `leaderboard.py` | SQLite-backed scoring and pending trade tracking |
| `reconciliation.py` | Worker to resolve pending trades and apply PnL |
| `tracing_config.py` | OpenTelemetry initialization and span creation |
| `app/app.py` | Streamlit UI with orchestrator integration |

## Usage

### Run a Trading Cycle

1. Open `http://localhost:8501`
2. Go to Trading page
3. Click "Run Single Research Cycle"
4. View:
   - Agent proposals
   - Council decision
   - Execution result
   - Updated leaderboard

### View Leaderboard

Persistent scores updated on every trade.

```bash
sqlite3 ./data/leaderboard.db "SELECT agent, score FROM agents ORDER BY score DESC;"
```

### Monitor Traces

- Jaeger UI: `http://localhost:16686`
- Filter by trace name: `orchestrator_cycle_AAPL`
- Inspect agent research, council voting, and execution spans

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `OTLP_ENABLED` | `true` | Disable if no collector available |
| `OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry collector address |
| `ALLOW_EARLY_START` | `true` | Start UI before LLM ready |
| `OLLAMA_BASE_URL` | `http://ollama-gpu:11434` | LLM endpoint |

## Project Structure

```text
neon-trader-gpu/
├── app/
│   ├── app.py                       # Streamlit UI
│   ├── api.py                       # FastAPI backend
│   ├── services/
│   │   ├── agent_framework.py       # Orchestration core
│   │   ├── specialist_agents.py     # Agent implementations
│   │   ├── trading_council.py       # Council voting
│   │   ├── autonomous_trader.py     # Backend trader
│   │   ├── leaderboard.py           # SQLite DB
│   │   ├── reconciliation.py        # Trade reconciliation
│   │   ├── tracing_config.py        # OpenTelemetry setup
│   │   └── [other services...]
│   ├── mcp/
│   │   ├── ticker_service.py        # Ticker endpoint
│   │   └── chart_service.py         # Chart endpoint
│   └── pages/                       # Streamlit pages
├── docker/
│   ├── docker-compose.yml           # Main compose file
│   ├── docker-compose-tracing.yml   # Jaeger stack
│   ├── cpu/Dockerfile               # CPU worker
│   ├── gpu/Dockerfile               # GPU worker
│   └── requirements.cpu.txt         # CPU deps
├── data/                            # Persistent storage
│   ├── leaderboard.db               # Agent scores
│   └── memory/                      # Per-agent memories
├── TRACING.md                       # Tracing guide
└── README.md                        # This file
```

## Testing

Verify installation:

```bash
python -c "from app.services.agent_framework import CouncilOrchestrator; print('✓')"
python -c "from app.services.leaderboard import get_leaderboard_db; print('✓')"
python -c "from app.services.tracing_config import setup_tracing; print('✓')"
```

Run test suites:

```bash
python app/services/test_leaderboard.py
python app/services/test_reconciliation.py
python app/services/tracing_example.py
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

### Agent not learning

- Verify trade result from execution
- Check memory directory: `ls -la ./data/memory/agents/`

## Next Steps

- **Broker Integration**: Wire eTrade or live broker APIs
- **LLM Setup**: Install Ollama/Mistral in GPU container
- **Production**: Kubernetes manifests, persistent volumes, monitoring
- **Advanced Learning**: Weekly champions, streaks, federated learning

## References

- [OpenTelemetry](https://opentelemetry.io/)
- [Streamlit Docs](https://streamlit.io/)
- [Jaeger Tracing](https://www.jaegertracing.io/)
- [Docker Compose](https://docs.docker.com/compose/)

## License

This is a demonstration project. Use responsibly and never enable autonomous trading with real capital without extensive testing.

---

**Status**: Beta (Dec 2025). All core features implemented. Ready for testing and integration with live brokers.

### AhanaVoice (Tim narration)

Tim speaks through Jeremiah’s vendored AhanaVoice pack. See `docs/AHANAVOICE_TIM.md`.
