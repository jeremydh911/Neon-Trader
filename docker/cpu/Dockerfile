FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install CPU-specific requirements
COPY ../docker/requirements.cpu.txt /tmp/requirements.cpu.txt
RUN pip install --no-cache-dir -r /tmp/requirements.cpu.txt || true

# Mount the repo at runtime via docker-compose volumes for easy development

CMD ["bash"]
