# ============================================================================
# Trinity Inference Server - Dockerfile
# ============================================================================
#
# LAYER ORDERING STRATEGY (critical for fast deploys):
# Heavy, rarely-changing layers FIRST → cached across code deploys
# Lightweight, frequently-changing code LAST → only ~2MB rebuilt per deploy
#
# Layer cache flow:
#   1. CUDA base image        (~4GB, never changes)
#   2. System packages         (~200MB, rarely changes)
#   3. Ollama install          (~500MB, rarely changes)
#   4. Python dependencies     (~1GB, changes with requirements.txt)
#   5. User + dirs             (~1KB, rarely changes)
#   6. Application code        (~2MB, changes every deploy) ← CACHEBUST here
#
# Models (~15GB) are NOT in the image — pulled at startup by startup.sh.
# This keeps the image ~10GB, making pushes fast and reliable.
# On Akash, persistent storage caches models across container restarts.
# ============================================================================

# === STEP 1: Base image (CUDA + Ubuntu) ===
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# === STEP 2: Environment variables ===
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV OLLAMA_HOST=http://localhost:11434
ENV MODEL_NAME=qwen2.5-coder:32b
ENV PROVIDER_ID=akash-provider-1
ENV GPU_TYPE=NVIDIA-A100
ENV MAX_QUEUE_SIZE=10

# === STEP 3: System packages ===
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    curl \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# === STEP 4: Install Ollama ===
RUN curl -fsSL https://ollama.ai/install.sh | sh

# === STEP 5: Working directory ===
WORKDIR /app

# === STEP 6: Python dependencies (cached unless requirements.txt changes) ===
COPY backend/requirements.txt .
RUN pip3 install --upgrade pip setuptools wheel
RUN pip3 install --no-cache-dir -r requirements.txt

# === STEP 7: User, directories ===
# Models are NOT baked into the image — they're pulled at container startup
# by startup.sh. This keeps the image ~10GB instead of ~25GB, making pushes
# fast and reliable. On Akash, persistent storage caches models across restarts.

# Create non-root user for security
RUN groupadd -r trinity && useradd -r -g trinity -d /app -s /sbin/nologin trinity

# Ollama model directory (populated at runtime by startup.sh)
RUN mkdir -p /home/trinity/.ollama && chown -R trinity:trinity /home/trinity/.ollama
ENV OLLAMA_MODELS=/home/trinity/.ollama

# Chat storage directory
RUN mkdir -p /data/chats && chown -R trinity:trinity /data/chats
VOLUME ["/data/chats"]

# === STEP 8: Application code (changes every deploy — kept LAST) ===
# CACHEBUST invalidates cache from this point forward on every build.
# Everything above stays cached. Only ~2MB of code is rebuilt per deploy.
ARG CACHEBUST=1

COPY backend/inference_server.py .
COPY backend/icp_auth.py .
COPY backend/config.py .
COPY backend/encryption.py .
COPY backend/storage.py .
COPY backend/lighthouse.py .
COPY backend/validation.py .
COPY backend/middleware/ ./middleware/
COPY backend/services/ ./services/
COPY backend/routes/ ./routes/
COPY deploy/docker/startup.sh .
RUN chmod +x startup.sh

# Fix ownership of app directory (after code copy)
RUN chown -R trinity:trinity /app

# === STEP 9: Ports ===
EXPOSE 8000
EXPOSE 11434

# === STEP 10: Health check ===
HEALTHCHECK --interval=30s --timeout=10s --start-period=1200s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# === STEP 11: Start ===
# Runs as root so startup.sh can fix PersistentVolume permissions.
# PVs mount as root-owned; Ollama needs write access to model directory.
CMD ["/app/startup.sh"]
