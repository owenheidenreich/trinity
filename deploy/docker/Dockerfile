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
#   2. llama-server binary     (~500MB, pulled from official image — no compile)
#   3. System packages         (~200MB, rarely changes)
#   4. Python dependencies     (~1GB, changes with requirements.txt)
#   5. User + dirs             (~1KB, rarely changes)
#   6. Application code        (~2MB, changes every deploy) ← CACHEBUST here
#
# Models (~15GB) are NOT in the image — downloaded at startup by startup.sh.
# This keeps the image ~10GB, making pushes fast and reliable.
# On Akash, persistent storage caches models across container restarts.
# ============================================================================

# === LLAMA-SERVER SOURCE: Pre-built binary from official image ===
# Compiling llama.cpp from source with CUDA inside Docker fails on cross-platform
# builds (macOS ARM → linux/amd64) because nvcc can't run under QEMU emulation.
# Instead, we pull the official pre-built CUDA binary — fast, reliable, tested.
#
# This image is built natively on x86_64 with CUDA 12.4. The binary and its
# shared libs (libggml-cuda.so, libllama.so, etc.) are copied into our runtime.
# CUDA 12.4 libs are included alongside the binary; the NVIDIA driver on the
# Akash host provides libcuda.so.1 at runtime via nvidia-container-toolkit.
FROM --platform=linux/amd64 ghcr.io/ggml-org/llama.cpp:server-cuda-b8115 AS llama-bin

# === RUNTIME STAGE ===
FROM --platform=linux/amd64 ubuntu:22.04

# === STEP 2: Environment variables ===
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC
ENV MODEL_NAME=qwen3:32b
ENV PROVIDER_ID=akash-provider-1
ENV GPU_TYPE=auto
ENV MAX_QUEUE_SIZE=10
ENV MODEL_BACKEND=llama-server
ENV LLAMA_SERVER_CHAT_PORT=8081
ENV LLAMA_SERVER_INGEST_PORT=8082
ENV CHATS_DIR=/data/chats
# NVIDIA Container Toolkit: make GPUs visible inside the container
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# === STEP 3: System packages ===
# build-essential + libsqlcipher-dev needed for pysqlcipher3 native extension
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    curl \
    zstd \
    build-essential \
    libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

# === STEP 4: Install llama-server from official pre-built image ===
# Binary + all shared libs (libllama, libggml, libggml-cuda, libmtmd, CPU variants)
#
# IMPORTANT: llama.cpp b8115 loads backends (CPU, CUDA) as dynamic plugins via
# ggml_backend_load_all(). This searches:
#   1. The directory containing the llama-server binary (get_executable_path())
#   2. The process current working directory
# It does NOT use LD_LIBRARY_PATH or ld.so.conf for plugin discovery.
#
# On Linux, backend plugins are named libggml-<backend>.so (with lib prefix).
# They're included in lib*.so* but must also be copied NEXT TO the binary
# at /usr/local/bin/ — not just /usr/local/lib/ — or llama-server can't find them.
COPY --from=llama-bin /app/llama-server /usr/local/bin/llama-server
COPY --from=llama-bin /app/lib*.so* /usr/local/lib/
# Backend plugins must sit next to the binary for ggml_backend_load_all() discovery
COPY --from=llama-bin /app/libggml-*.so /usr/local/bin/
RUN chmod +x /usr/local/bin/llama-server && ldconfig

# CUDA 12.4 runtime libs from the official image (matches the binary's build)
# Only copy the specific libs the binary needs; the NVIDIA driver provides libcuda.so.1
COPY --from=llama-bin /usr/local/cuda/targets/x86_64-linux/lib/libcudart.so* /usr/local/lib/
COPY --from=llama-bin /usr/local/cuda/targets/x86_64-linux/lib/libcublas.so* /usr/local/lib/
COPY --from=llama-bin /usr/local/cuda/targets/x86_64-linux/lib/libcublasLt.so* /usr/local/lib/
RUN ldconfig

# huggingface-hub is installed via requirements.txt (fastembed dependency).
# startup.sh uses `python3 -c 'from huggingface_hub import hf_hub_download; ...'`
# instead of the `huggingface-cli` wrapper (entry point gets broken by pip upgrade).

# === STEP 5: Working directory ===
WORKDIR /app

# === STEP 6: Python dependencies (cached unless requirements.txt changes) ===
COPY backend/requirements.txt .
RUN pip3 install --upgrade pip setuptools wheel
RUN pip3 install --no-cache-dir -r requirements.txt

# === STEP 7: User, directories ===
# Models are NOT baked into the image — downloaded at container startup
# by startup.sh via huggingface-cli. On Akash, persistent storage caches
# models across container restarts.

# Create non-root user for security
RUN groupadd -r trinity && useradd -r -g trinity -d /app -s /sbin/nologin trinity

# Model directory (populated at runtime by startup.sh)
RUN mkdir -p /home/trinity/.models && chown -R trinity:trinity /home/trinity/.models

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
COPY backend/database.py .
COPY backend/encryption.py .
COPY backend/storage.py .
COPY backend/lighthouse.py .
COPY backend/validation.py .
COPY backend/middleware/ ./middleware/
COPY backend/services/ ./services/
COPY backend/routes/ ./routes/
COPY backend/models/ ./models/
COPY deploy/docker/startup.sh .
RUN chmod +x startup.sh

# Fix ownership of app directory (after code copy)
RUN chown -R trinity:trinity /app

# === STEP 9: Ports ===
EXPOSE 8000
EXPOSE 8081
EXPOSE 8082

# === STEP 10: Health check ===
HEALTHCHECK --interval=30s --timeout=10s --start-period=1200s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# === STEP 11: Start ===
# Runs as root so startup.sh can fix PersistentVolume permissions.
# PVs mount as root-owned; llama-server needs write access to model directory.
CMD ["/app/startup.sh"]
