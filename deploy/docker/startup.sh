#!/bin/bash
# ============================================================================
# Trinity Inference Server — startup.sh
# ============================================================================
#
# Runs as PID 1 inside the Docker container (started by CMD in Dockerfile).
# Responsibilities:
#   1. Fix Akash PersistentVolume permissions
#   2. Download GGUF models via huggingface-cli (cached across restarts)
#   3. Start llama-server instances (chat + ingest)
#   4. Wait for both servers to become healthy
#   5. Start Flask as foreground process (PID 1 for signal handling)
#
# Env vars consumed:
#   MODEL_NAME              — Model identifier, e.g. "qwen3:32b" (default: qwen3:32b)
#   CHAT_MODEL              — Chat model override (defaults to MODEL_NAME)
#   INGEST_MODEL            — Ingest model override (defaults to MODEL_NAME)
#   LLAMA_SERVER_CHAT_PORT  — Chat server port (default: 8081)
#   LLAMA_SERVER_INGEST_PORT — Ingest server port (default: 8082)
#   HF_TOKEN                — Optional HuggingFace auth token for gated models
# ============================================================================

set -euo pipefail

# ===== Ensure shared libs are found =====
export LD_LIBRARY_PATH="/usr/local/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# ===== Configuration =====
MODEL_DIR="/home/trinity/.models"
CHAT_PORT="${LLAMA_SERVER_CHAT_PORT:-8081}"
INGEST_PORT="${LLAMA_SERVER_INGEST_PORT:-8082}"
CHAT_CTX="${LLAMA_SERVER_CHAT_CTX:-40960}"
INGEST_CTX="${LLAMA_SERVER_INGEST_CTX:-8192}"

# PIDs for cleanup
CHAT_PID=""
INGEST_PID=""

# ===== Signal handling: clean shutdown on SIGTERM/SIGINT =====
cleanup() {
    echo "🛑 Shutting down..."
    [[ -n "$CHAT_PID" ]]   && kill "$CHAT_PID"   2>/dev/null && wait "$CHAT_PID"   2>/dev/null || true
    [[ -n "$INGEST_PID" ]] && kill "$INGEST_PID" 2>/dev/null && wait "$INGEST_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# ===== Model name mapping =====
# Converts model identifiers (qwen3:32b) to HuggingFace repo + filename.
# Add new models here as needed.
resolve_model() {
    local model_tag="$1"
    case "$model_tag" in
        qwen3:32b|qwen3-32b)
            echo "Qwen/Qwen3-32B-GGUF Qwen3-32B-Q4_K_M.gguf single"
            ;;
        qwen3:8b|qwen3-8b)
            echo "Qwen/Qwen3-8B-GGUF Qwen3-8B-Q4_K_M.gguf single"
            ;;
        qwen3:4b|qwen3-4b)
            echo "Qwen/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf single"
            ;;
        qwen3:1.7b|qwen3-1.7b)
            echo "Qwen/Qwen3-1.7B-GGUF Qwen3-1.7B-Q8_0.gguf single"
            ;;
        qwen3:0.6b|qwen3-0.6b)
            echo "Qwen/Qwen3-0.6B-GGUF Qwen3-0.6B-Q4_K_M.gguf single"
            ;;
        # Qwen2.5 alternatives (drop-in replacements for earlier model family)
        qwen2.5:1.5b|qwen2.5-1.5b)
            echo "Qwen/Qwen2.5-1.5B-Instruct-GGUF qwen2.5-1.5b-instruct-q4_k_m.gguf single"
            ;;
        qwen2.5:7b|qwen2.5-7b)
            echo "Qwen/Qwen2.5-7B-Instruct-GGUF qwen2.5-7b-instruct-q4_k_m.gguf single"
            ;;
        qwen3-coder-next|qwen3-coder-next:80b)
            # Split GGUF: 80B MoE model (3B activated), 4 shards (~48.4GB total)
            # llama-server loads shard 1 and auto-discovers shards 2-4
            echo "Qwen/Qwen3-Coder-Next-GGUF Qwen3-Coder-Next-Q4_K_M split"
            ;;
        *)
            echo "ERROR: Unknown model '$model_tag'. Add it to resolve_model() in startup.sh" >&2
            exit 1
            ;;
    esac
}

# ===== Download a model if not already cached =====
download_model() {
    local model_tag="$1"
    local resolved
    resolved=$(resolve_model "$model_tag")
    local hf_repo
    hf_repo=$(echo "$resolved" | awk '{print $1}')
    local gguf_file
    gguf_file=$(echo "$resolved" | awk '{print $2}')
    local gguf_type
    gguf_type=$(echo "$resolved" | awk '{print $3}')

    if [[ "$gguf_type" == "split" ]]; then
        # Split GGUF: download all shards via snapshot_download
        local subdir="${gguf_file}"
        local shard1_path="${MODEL_DIR}/${subdir}/${subdir}-00001-of-00004.gguf"

        if [[ -f "$shard1_path" ]]; then
            echo "✅ Model cached: ${subdir}/ (split GGUF, $(du -sh "${MODEL_DIR}/${subdir}" | cut -f1) total)"
            return 0
        fi

        echo "📥 Downloading ${subdir} (split GGUF, 4 shards) from ${hf_repo}..."
        echo "   This is ~48GB and may take 10-20 minutes. Progress logged every 30s."
        # Run download in background so we can print heartbeats
        python3 -u -c "
import sys, os
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'  # tqdm progress works better without hf_transfer
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='${hf_repo}',
    allow_patterns='${subdir}/*',
    local_dir='${MODEL_DIR}',
    token=os.environ.get('HF_TOKEN') or None,
)
print('Download complete', flush=True)
" &
        DL_PID=$!
        DL_ELAPSED=0
        while kill -0 "$DL_PID" 2>/dev/null; do
            sleep 30
            DL_ELAPSED=$((DL_ELAPSED + 30))
            # Show progress: how much has been downloaded so far
            if [[ -d "${MODEL_DIR}/${subdir}" ]]; then
                DL_SIZE=$(du -sh "${MODEL_DIR}/${subdir}" 2>/dev/null | cut -f1)
                echo "   ⏳ Downloading... ${DL_SIZE} so far (${DL_ELAPSED}s elapsed)"
            else
                echo "   ⏳ Downloading... (${DL_ELAPSED}s elapsed, initializing...)"
            fi
        done
        wait $DL_PID
        DL_EXIT=$?
        if [[ $DL_EXIT -ne 0 ]]; then
            echo "❌ Failed to download ${subdir} (exit code: ${DL_EXIT})" >&2
            exit 1
        fi
        echo "✅ Downloaded: ${subdir}/ ($(du -sh "${MODEL_DIR}/${subdir}" | cut -f1) total)"
    else
        # Single GGUF file
        local target_path="${MODEL_DIR}/${gguf_file}"

        if [[ -f "$target_path" ]]; then
            echo "✅ Model cached: ${gguf_file} ($(du -h "$target_path" | cut -f1))"
            return 0
        fi

        echo "📥 Downloading ${gguf_file} from ${hf_repo}..."
        if ! python3 -c "
from huggingface_hub import hf_hub_download
import os
hf_hub_download(
    repo_id='${hf_repo}',
    filename='${gguf_file}',
    local_dir='${MODEL_DIR}',
    token=os.environ.get('HF_TOKEN') or None,
)
print('Download complete')
"; then
            echo "❌ Failed to download ${gguf_file}" >&2
            exit 1
        fi
        echo "✅ Downloaded: ${gguf_file} ($(du -h "$target_path" | cut -f1))"
    fi
}

# ===== Get GGUF filepath for a model tag =====
model_path() {
    local model_tag="$1"
    local resolved
    resolved=$(resolve_model "$model_tag")
    local gguf_file
    gguf_file=$(echo "$resolved" | awk '{print $2}')
    local gguf_type
    gguf_type=$(echo "$resolved" | awk '{print $3}')

    if [[ "$gguf_type" == "split" ]]; then
        # Split GGUF: return path to first shard (llama-server auto-discovers the rest)
        echo "${MODEL_DIR}/${gguf_file}/${gguf_file}-00001-of-00004.gguf"
    else
        echo "${MODEL_DIR}/${gguf_file}"
    fi
}

# ===== Wait for a llama-server to become healthy =====
wait_for_health() {
    local port="$1"
    local name="$2"
    local max_wait="${3:-300}"  # 5 minutes default (model loading can be slow)
    local elapsed=0
    local heartbeat_interval=30  # Log every 30s so Akash logs don't go silent
    local last_heartbeat=0

    echo "⏳ Waiting for ${name} on port ${port} (timeout: ${max_wait}s)..."
    while (( elapsed < max_wait )); do
        if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo "✅ ${name} healthy (${elapsed}s)"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        # Heartbeat: print progress so Akash logs show the container is alive
        if (( elapsed - last_heartbeat >= heartbeat_interval )); then
            echo "   ⏳ ${name}: loading model... (${elapsed}s / ${max_wait}s)"
            last_heartbeat=$elapsed
        fi
    done

    echo "❌ ${name} failed to start within ${max_wait}s" >&2
    exit 1
}

# ============================================================================
# MAIN
# ============================================================================

echo "🚀 Trinity startup — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "   Chat model:    ${CHAT_MODEL:-${MODEL_NAME:-qwen3:32b}}"
echo "   Ingest model:  ${INGEST_MODEL:-${MODEL_NAME:-qwen3:32b}}"
echo "   Chat port:     ${CHAT_PORT}"
echo "   Ingest port:   ${INGEST_PORT}"

# --- Step 0: Auto-detect GPU type ---
# If GPU_TYPE is "auto" or unset, detect via nvidia-smi
if [[ "${GPU_TYPE:-auto}" == "auto" ]]; then
    if command -v nvidia-smi &>/dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | head -1 | xargs)
        export GPU_TYPE="${GPU_NAME:-unknown}"
        echo "   GPU detected: ${GPU_TYPE}"
    else
        export GPU_TYPE="CPU"
        echo "   GPU: none detected (CPU mode)"
    fi
else
    echo "   GPU type:     ${GPU_TYPE}"
fi

# --- Step 1: Fix Akash PersistentVolume permissions ---
# PVs mount as root-owned; our non-root user needs write access.
echo "🔧 Fixing directory permissions..."
chown -R trinity:trinity "$MODEL_DIR" || true
chown -R trinity:trinity /data || true

# --- Step 2: Download models ---
CHAT_MODEL="${CHAT_MODEL:-${OLLAMA_CHAT_MODEL:-${MODEL_NAME:-qwen3:32b}}}"
INGEST_MODEL="${INGEST_MODEL:-${OLLAMA_INGEST_MODEL:-${MODEL_NAME:-qwen3:32b}}}"

echo "📦 Ensuring models are available..."
download_model "$CHAT_MODEL"
if [[ "$INGEST_MODEL" != "$CHAT_MODEL" ]]; then
    download_model "$INGEST_MODEL"
fi

CHAT_MODEL_PATH=$(model_path "$CHAT_MODEL")
INGEST_MODEL_PATH=$(model_path "$INGEST_MODEL")

# --- Step 3: Start llama-server instances (background, tracked PIDs) ---

# CPU-aware GPU layers: skip GPU offload when no GPU available
if [[ "$GPU_TYPE" == "CPU" ]]; then
    GPU_LAYERS_FLAG="--n-gpu-layers 0"
    echo "   CPU mode: GPU offload disabled"
else
    GPU_LAYERS_FLAG="--n-gpu-layers -1"
fi

# Build extra flags for qwen3_next architecture models
CHAT_EXTRA_FLAGS=""
if [[ "$CHAT_MODEL" == qwen3-coder-next* ]]; then
    # --flash-attn on: flash attention (improves throughput with hybrid DeltaNet+Attention)
    # NOTE: b8115+ changed -fa from boolean to requiring on|off|auto
    # NOTE: --jinja removed — it enables server-side Jinja template rendering which
    # conflicts with Trinity's XML tool-call protocol (the model emits its native
    # JSON-in-XML format instead of Trinity's <tool_call name="..."> format).
    # Trinity controls tool-call formatting via system prompt, so --jinja is not needed.
    CHAT_EXTRA_FLAGS="--flash-attn on"
    echo "   Using qwen3_next flags: ${CHAT_EXTRA_FLAGS}"
fi

echo "🧠 Starting llama-server (chat) on port ${CHAT_PORT}..."
echo "   Model: ${CHAT_MODEL_PATH}"
echo "   Context: ${CHAT_CTX} tokens"
echo "   GPU layers: ${GPU_LAYERS_FLAG}"
su -s /bin/bash trinity -c "LD_LIBRARY_PATH=/usr/local/lib llama-server \
    --host 0.0.0.0 \
    --port ${CHAT_PORT} \
    --model ${CHAT_MODEL_PATH} \
    --ctx-size ${CHAT_CTX} \
    ${GPU_LAYERS_FLAG} \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --cont-batching \
    ${CHAT_EXTRA_FLAGS}" 2>&1 | sed 's/^/[chat-llama] /' &
CHAT_PID=$!

echo "🧠 Starting llama-server (ingest) on port ${INGEST_PORT}..."
echo "   Model: ${INGEST_MODEL_PATH}"
echo "   Context: ${INGEST_CTX} tokens"
su -s /bin/bash trinity -c "LD_LIBRARY_PATH=/usr/local/lib llama-server \
    --host 0.0.0.0 \
    --port ${INGEST_PORT} \
    --model ${INGEST_MODEL_PATH} \
    --ctx-size ${INGEST_CTX} \
    ${GPU_LAYERS_FLAG} \
    --cont-batching" 2>&1 | sed 's/^/[ingest-llama] /' &
INGEST_PID=$!

echo "   Chat PID:  ${CHAT_PID}"
echo "   Ingest PID: ${INGEST_PID}"

# --- Step 4: Wait for both servers to become healthy ---
# Larger MoE models (80B) need more time to load into VRAM than dense models (32B)
CHAT_HEALTH_TIMEOUT=600
if [[ "$CHAT_MODEL" == qwen3-coder-next* ]]; then
    CHAT_HEALTH_TIMEOUT=900
fi
wait_for_health "$CHAT_PORT" "chat llama-server" "$CHAT_HEALTH_TIMEOUT"
wait_for_health "$INGEST_PORT" "ingest llama-server" 300

# --- Step 5: Start Flask (foreground, stays as PID 1 child) ---
echo "🌐 Starting Flask inference server on port 8000..."
cd /app
su -s /bin/bash trinity -c "LD_LIBRARY_PATH=/usr/local/lib python3 inference_server.py" &
FLASK_PID=$!

# Wait for any child to exit — if Flask dies, we should exit so Docker restarts us
wait $FLASK_PID
EXIT_CODE=$?
echo "⚠️ Flask exited with code ${EXIT_CODE}"
cleanup
exit $EXIT_CODE
