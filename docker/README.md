# Neon Trader Docker Setup

This folder contains scaffolding to run Neon Trader components with Docker and Docker Compose.

## Services

The compose file defines the following services:

- `web`: The main web/backend container (binds to ports 8000/8501).
- `worker_cpu`: CPU-only worker for background tasks and orchestrator simulations.
- `llm_gpu`: GPU-enabled container intended to host LLMs (Ollama-like endpoints) and heavy ML workloads.

## Notes

- The GPU Dockerfile uses the `nvidia/cuda` base image and expects the host to have NVIDIA Container Toolkit installed.
- The `requirements.gpu.txt` lists common LLM packages; choose the correct `torch` wheel compatible with your GPU and CUDA version.
- The `llm_gpu` service exposes ports `11434-11436` to be compatible with existing `app/services/council_llm.py` expectations.

## Quick Start (Development)

1. Install Docker and Docker Compose on your machine.
2. Install NVIDIA Container Toolkit if you plan to run the `llm_gpu` service with GPUs.
3. From the `docker` directory run:

```bash
docker compose up --build
```

## Security / Safety

- The orchestrator and worker scripts are for simulation and demonstration. They will not place live trades unless you wire a real broker and enable autonomous trading.
