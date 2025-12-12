# Tracing Setup Guide for Neon Trader 2.0

## Overview

OpenTelemetry tracing has been integrated into Neon Trader for end-to-end observability of:

- Agent research and decision making
- Council deliberation and voting
- Backend trade execution and learning
- Pending trade reconciliation

Traces can be exported to any OpenTelemetry-compatible backend (Jaeger, Tempo, Honeycomb, Datadog, etc.).

## Quick Start: Local Tracing with Jaeger

### 1. Start Jaeger (OpenTelemetry Collector + UI)

```bash
docker run -d \
  --name jaeger \
  -p 4317:4317 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

This exposes:

- **OTLP gRPC endpoint**: `http://localhost:4317` (where apps send traces)
- **Jaeger UI**: `http://localhost:16686` (where you view traces)

### 2. Configure Tracing

Set environment variables in your shell or `.env` file:

```bash
export OTLP_ENABLED=true
export OTLP_ENDPOINT=http://localhost:4317
export ENABLE_SENSITIVE_DATA=true
```

### 3. Run Your Application

```bash
python app/app.py
```

or

```bash
streamlit run app/app.py
```

Tracing is initialized automatically at startup via `app/services/tracing_config.py`.

### 4. View Traces

Open Jaeger UI in your browser at `http://localhost:16686`.

Select "Neon Trader" (or your service name) from the dropdown to see traces.

---

## Trace Structure

Each `orchestrator.run_cycle()` produces a top-level span containing:

```text
orchestrator_cycle_AAPL
├── gather_proposals
│   ├── agent_research_TurboTrade Tina
│   ├── agent_research_EcoEdge Eddie
│   └── agent_research_GlobalGains Gloria
├── council_deliberation
│   └── (council voting logic)
└── backend_execution
    └── (trade execution and reward application)
```

### Key Attributes Captured

- **Symbol, price, sentiment**: Market context
- **Agent name, specialty, action, confidence**: Agent decisions
- **Approval percentage**: Council voting result
- **Execution status**: Trade success/failure
- **PnL and rewards**: Financial outcomes

---

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTLP_ENABLED` | `true` | Enable/disable tracing |
| `OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry collector gRPC endpoint |
| `ENABLE_SENSITIVE_DATA` | `true` | Capture prompts/completions in traces |

### Code-Level Setup

```python
from app.services.tracing_config import setup_tracing, get_tracer

# Initialize tracing (done automatically in app.py)
setup_tracing(
    endpoint="http://localhost:4317",
    enable_sensitive=True
)

# Use tracer in custom code
tracer = get_tracer("my_module")
with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("key", "value")
    span.add_event("important_event")
    # ... your code ...
```

---

## Production Deployment

### Using Jaeger in Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jaeger
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: jaeger
        image: jaegertracing/all-in-one:latest
        ports:
        - name: otlp-grpc
          containerPort: 4317
        - name: ui
          containerPort: 16686
```

### Using Tempo (Grafana)

Export to Grafana Tempo by setting:

```bash
OTLP_ENDPOINT=http://tempo-distributor.tempo:4317
```

### Using Datadog

Use the Datadog Python APM library:

```bash
pip install dd-trace
```

In your code:

```python
from ddtrace import tracer
```

### Using Honeycomb

```bash
OTLP_ENDPOINT=https://api.honeycomb.io:443
```

Also set Honeycomb API key.

---

## Troubleshooting

### Traces Not Appearing

1. **Check OTLP_ENABLED**: `echo $OTLP_ENABLED` should be `true`
2. **Check endpoint connectivity**: `telnet localhost 4317`
3. **Check logs**: Look for "OpenTelemetry tracing initialized" in app logs
4. **Verify Jaeger is running**: `docker ps | grep jaeger`

### Performance Impact

- Tracing adds minimal overhead (< 1% in most cases)
- Batch processing reduces network calls
- Sensitive data capture is optional (disable with `ENABLE_SENSITIVE_DATA=false`)

### Memory Usage

- Each span is ~1-2 KB in memory
- Batch processor flushes periodically
- If memory is an issue, reduce `BATCH_SIZE` in `tracing_config.py`

---

## Example: Viewing a Trade Cycle

1. Open Jaeger UI: `http://localhost:16686`
2. Select "neon-trader" from Service dropdown
3. Click on a trace to see the full decision flow
4. Example trace name: `orchestrator_cycle_AAPL`
5. Expand sections to see:
   - Which agents proposed which actions
   - Council voting outcomes
   - Final execution and PnL

---

## Next Steps

- **Integration**: Integrate tracing with your CI/CD pipeline
- **Alerts**: Set up alerts on slow spans or failed trades
- **Dashboards**: Create custom Grafana dashboards on top of Tempo
- **Analysis**: Use trace data to analyze agent performance and council effectiveness

For more details, see:

- [OpenTelemetry Documentation](https://opentelemetry.io/)
- [Jaeger Getting Started](https://www.jaegertracing.io/docs/getting-started/)
