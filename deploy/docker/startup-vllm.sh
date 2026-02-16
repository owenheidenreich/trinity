#!/bin/bash
# ============================================================================
# Trinity Inference Server — M2.5 vLLM Startup Script
# ============================================================================
#
# WHAT THIS SCRIPT DOES:
# This is the vLLM equivalent of startup.sh (which runs Ollama).
# It starts vLLM as the inference backend and Trinity Flask API on top.
#
# STARTUP SEQUENCE:
# 1. Fix PersistentVolume permissions
# 2. Start vLLM server in background (downloads model if not cached)
# 3. Wait for vLLM readiness — check /v1/models endpoint
#    (first start: 15-60 min for ~220GB weight download)
#    (subsequent starts: 2-5 min with cached weights)
# 4. Start Flask inference server
# 5. Monitor both processes
#
# ENVIRONMENT VARIABLES:
#   VLLM_MODEL_NAME    — HuggingFace model ID (default: MiniMaxAI/MiniMax-M2.5)
#   VLLM_PORT          — vLLM listen port (default: 8001)
#   TENSOR_PARALLEL_SIZE — Number of GPUs for tensor parallelism (default: 4)
#   GPU_TYPE           — GPU description for logging
#   VLLM_EXTRA_ARGS    — Additional vLLM CLI arguments
#   HUGGING_FACE_HUB_TOKEN — HF token for gated models (if needed)
# ============================================================================

set -e

# ============================================================================
# STEP 0a: Expand /dev/shm for vLLM multi-GPU IPC
# ============================================================================
# Akash containers default to 64MB /dev/shm. vLLM's multiprocess executor
# uses Python shared memory + PyTorch distributed IPC which need GBs.
# NCCL_SHM_DISABLE=1 only covers NCCL — not Python/PyTorch shared memory.
SHM_EXPANDED=false
if mount -t tmpfs -o size=16g tmpfs /dev/shm 2>/dev/null; then
    echo "✓ Expanded /dev/shm to 16GB"
    SHM_EXPANDED=true
else
    echo "⚠ Could not remount /dev/shm ($(df -h /dev/shm 2>/dev/null | tail -1 | awk '{print $2}'))"
    echo "  Will use Ray distributed executor as fallback."
fi

# ============================================================================
# STEP 0b: Fix PersistentVolume Permissions
# ============================================================================
# Akash PersistentVolumes mount as root-owned. Fix ownership so vLLM
# and the trinity user can write model weights and chat data.
if [ -d "/models" ]; then
    chown -R trinity:trinity /models 2>/dev/null || true
    echo "✓ Fixed model directory permissions"
fi
if [ -d "/data/chats" ]; then
    chown -R trinity:trinity /data/chats 2>/dev/null || true
fi

# ============================================================================
# STARTUP BANNER
# ============================================================================
echo "=========================================="
echo "Trinity Inference Server — Starting..."
echo "Backend: vLLM"
echo "Model: ${VLLM_MODEL_NAME:-MiniMaxAI/MiniMax-M2.5}"
echo "GPU: ${GPU_TYPE:-unknown}"
echo "Tensor Parallel: ${TENSOR_PARALLEL_SIZE:-4}"
echo "vLLM Port: ${VLLM_PORT:-8001}"
echo "Max Queue: ${MAX_QUEUE_SIZE:-5}"
echo "=========================================="

# ============================================================================
# STEP 1: Start vLLM Server
# ============================================================================
VLLM_PORT=${VLLM_PORT:-8001}
echo ""
echo "Starting vLLM server on port $VLLM_PORT..."
echo "Model weights will be cached in /models (HF_HOME=$HF_HOME)"
echo ""

# Show available disk space (important for 220GB model weights)
echo "Available disk space:"
df -h /models 2>/dev/null || df -h / || true
echo ""

# Show GPU topology
echo "GPU information:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "nvidia-smi not available"
echo ""

# CUDA driver info — compat libs removed at build time (Dockerfile STEP 3)
# so the container always uses the host-injected driver via nvidia-container-toolkit
echo "CUDA library check:"
ldconfig -p 2>/dev/null | grep libcuda | head -5 || echo "  (ldconfig not available)"
echo ""

# Start vLLM with MiniMax M2.5 optimized flags
# --trust-remote-code: Required for M2.5's custom attention implementation
# --tensor-parallel-size: Distribute model across 4 GPUs
# --enable-auto-tool-choice: Enable native tool/function calling
# --tool-call-parser minimax: MiniMax tool call format parser (v0.10.0 naming)
# NOTE: --reasoning-parser not available in v0.10.0; reasoning extraction
#       handled by the Flask layer instead.
echo "Starting vLLM at $(date)"

# ---- NCCL configuration ----
# v0.10.0 ships NCCL 2.26.2 (safe on CUDA 13.0 driver 580.x).
# P2P ENABLED — A100 SXM4 has NVLink, P2P is the primary inter-GPU transport.
# SHM disabled because Akash containers get only 64MB /dev/shm.
# v11 had P2P_DISABLE=1 which killed all transports → ncclCommInitRank failed.
# NCCL env vars — exported so Ray workers inherit them
export NCCL_NVLS_ENABLE=${NCCL_NVLS_ENABLE:-0}
export NCCL_CUMEM_ENABLE=${NCCL_CUMEM_ENABLE:-0}
export NCCL_SHM_DISABLE=${NCCL_SHM_DISABLE:-1}
export NCCL_P2P_DISABLE=${NCCL_P2P_DISABLE:-0}
export NCCL_DEBUG=${NCCL_DEBUG:-INFO}
echo "NCCL settings: NVLS=$NCCL_NVLS_ENABLE CUMEM=$NCCL_CUMEM_ENABLE SHM_DISABLE=$NCCL_SHM_DISABLE P2P_DISABLE=$NCCL_P2P_DISABLE"

# If /dev/shm expansion failed, use Ray executor (TCP-based IPC, no shm needed)
EXECUTOR_ARGS=""
if [ "$SHM_EXPANDED" != "true" ]; then
    echo "Using Ray distributed executor (bypasses /dev/shm limitation)"
    EXECUTOR_ARGS="--distributed-executor-backend ray"
fi

SAFETENSORS_FAST_GPU=1 python3 -m vllm.entrypoints.openai.api_server \
    --model "${VLLM_MODEL_NAME:-MiniMaxAI/MiniMax-M2.5}" \
    --trust-remote-code \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-4}" \
    --enable-auto-tool-choice \
    --tool-call-parser minimax \
    --port "$VLLM_PORT" \
    --host 0.0.0.0 \
    ${EXECUTOR_ARGS} \
    ${VLLM_EXTRA_ARGS:-} &
VLLM_PID=$!
echo "vLLM started with PID: $VLLM_PID"

# ============================================================================
# STEP 2: Wait for vLLM Readiness
# ============================================================================
# vLLM needs to:
# 1. Download model weights from HuggingFace (~220GB, first time only)
# 2. Load weights into GPU memory across 4 GPUs
# 3. Initialize tensor parallel communication (NCCL)
# This can take 15-60 minutes on first start, 2-5 minutes on subsequent starts.

echo ""
echo "Waiting for vLLM to load model weights..."
echo "⚠️  First start downloads ~220GB — this can take 15-60 minutes."
echo "    Subsequent starts use cached weights (2-5 minutes)."
echo ""

MAX_WAIT=5400   # 90 minutes max
WAIT_COUNT=0
INTERVAL=10

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # Check if vLLM's OpenAI-compatible API is responding
    if curl -sf "http://localhost:$VLLM_PORT/v1/models" > /dev/null 2>&1; then
        echo ""
        echo "✓ vLLM is ready! (waited ${WAIT_COUNT}s / $((WAIT_COUNT / 60)) min)"
        echo ""
        break
    fi

    # Check if vLLM process died
    if ! kill -0 $VLLM_PID 2>/dev/null; then
        echo ""
        echo "✗ vLLM process died during startup!"
        echo "Check GPU memory, model compatibility, or HuggingFace access."
        echo ""
        # Show last few lines of any error output
        echo "GPU memory status:"
        nvidia-smi 2>/dev/null || true
        exit 1
    fi

    sleep $INTERVAL
    WAIT_COUNT=$((WAIT_COUNT + INTERVAL))

    # Progress updates every 60 seconds
    if [ $((WAIT_COUNT % 60)) -eq 0 ]; then
        ELAPSED_MIN=$((WAIT_COUNT / 60))
        echo "... still loading (${ELAPSED_MIN} min elapsed, max $((MAX_WAIT / 60)) min)"
        # Show disk usage progress (helpful during weight download)
        du -sh /models 2>/dev/null || true
    fi
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo ""
    echo "✗ vLLM failed to start within $((MAX_WAIT / 60)) minutes"
    echo "Possible causes:"
    echo "  1. Insufficient GPU memory (need 4× A100 80GB)"
    echo "  2. Network issues downloading from HuggingFace"
    echo "  3. Insufficient disk space for model weights (~220GB)"
    echo ""
    echo "Disk usage:"
    df -h /models 2>/dev/null || df -h / || true
    echo ""
    echo "GPU status:"
    nvidia-smi 2>/dev/null || true
    kill $VLLM_PID 2>/dev/null || true
    exit 1
fi

# Verify vLLM is serving the expected model
echo "Verifying model..."
MODEL_LIST=$(curl -sf "http://localhost:$VLLM_PORT/v1/models" 2>/dev/null || echo "")
if [ -n "$MODEL_LIST" ]; then
    echo "Available models:"
    echo "$MODEL_LIST" | python3 -m json.tool 2>/dev/null || echo "$MODEL_LIST"
fi

# ============================================================================
# STEP 2b: Warmup Request
# ============================================================================
# First inference triggers CUDA kernel compilation and KV cache allocation.
# Run a short warmup so the first real user request isn't slow (20-30s).
echo ""
echo "Running warmup inference..."
WARMUP_RESP=$(curl -sf -m 120 "http://localhost:$VLLM_PORT/v1/completions" \
    -H "Content-Type: application/json" \
    -d '{"model": "'"${VLLM_MODEL_NAME:-MiniMaxAI/MiniMax-M2.5}"'", "prompt": "Hello", "max_tokens": 8}' 2>&1 || true)
if echo "$WARMUP_RESP" | grep -q '"choices"'; then
    echo "✓ Warmup complete"
else
    echo "⚠ Warmup request did not return expected response (non-fatal)"
fi

# ============================================================================
# STEP 3: Start Flask Inference Server
# ============================================================================
echo ""
echo "Starting Trinity Flask server on port 8000..."

# Ensure Flask knows we're using vLLM
export VLLM_HOST="http://localhost:$VLLM_PORT"
export MODEL_BACKEND=vllm

python3 inference_server.py &
FLASK_PID=$!
echo "Flask started with PID: $FLASK_PID"

# Wait a few seconds for Flask to initialize
sleep 3

# Verify Flask is responding
for i in {1..10}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Flask is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "⚠ Flask health check not responding yet (may still be initializing)"
    fi
    sleep 2
done

# ============================================================================
# STEP 4: All Systems Go
# ============================================================================
echo ""
echo "=========================================="
echo "✓ Trinity is ready!"
echo "  Backend: vLLM"
echo "  Model:   ${VLLM_MODEL_NAME:-MiniMaxAI/MiniMax-M2.5}"
echo "  vLLM:    http://localhost:$VLLM_PORT"
echo "  Flask:   http://localhost:8000"
echo "  vLLM PID:  $VLLM_PID"
echo "  Flask PID: $FLASK_PID"
echo "=========================================="
echo ""

# ============================================================================
# STEP 5: Monitor Both Processes
# ============================================================================
# Keep the script running and monitor both processes.
# If either vLLM or Flask crashes, exit the container so Akash restarts it.

wait -n $VLLM_PID $FLASK_PID

echo ""
echo "⚠ One of the services stopped!"
echo "Shutting down container..."

# Kill both processes (ignore errors if already dead)
kill $VLLM_PID $FLASK_PID 2>/dev/null || true

echo "Container stopped"
exit 1
