FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy GPU-specific requirements file
COPY ../docker/requirements.gpu.txt /tmp/requirements.gpu.txt

# Install python packages; in practice choose the right torch+cuda wheel for your GPU
RUN pip3 install --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir -r /tmp/requirements.gpu.txt || true

EXPOSE 11434 11435 11436

CMD ["bash"]
