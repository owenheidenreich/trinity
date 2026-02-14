#!/bin/bash
# ============================================================================
# Trinity Inference Server - Startup Script
# ============================================================================
#
# WHAT THIS SCRIPT DOES:
# This script runs when the Docker container starts. It handles the startup
# sequence for both Ollama and the Flask inference server.
#
# WHY WE NEED THIS:
# - Ollama needs to start before Flask (Flask depends on it)
# - We need to download the AI model (first time)
# - We need to verify everything is working
# - If either service crashes, the whole container should stop
#
# STARTUP SEQUENCE:
# 1. Start Ollama service in background
# 2. Wait for Ollama to be ready (can take 30-60 seconds)
# 3. Download/pull the AI model (e.g., qwen2.5-coder:32b)
# 4. Start Flask inference server
# 5. Monitor both processes
# ============================================================================

# Exit immediately if any command fails
# This is important - we don't want to continue if something breaks
set -e

# ============================================================================
# STEP 0: Fix PersistentVolume Permissions
# ============================================================================
# When Akash mounts a PersistentVolume at /home/trinity/.ollama, it's
# root-owned. Fix ownership so Ollama (and the trinity user) can write
# models to it. This is a no-op if no PV is mounted.
if [ -d "/home/trinity/.ollama" ]; then
    chown -R trinity:trinity /home/trinity/.ollama 2>/dev/null || true
    echo "✓ Fixed model directory permissions"
fi
if [ -d "/data/chats" ]; then
    chown -R trinity:trinity /data/chats 2>/dev/null || true
fi

# ============================================================================
# STARTUP BANNER
# ============================================================================
# Display configuration information for debugging
echo "=========================================="
echo "Trinity Inference Server - Starting..."
echo "Provider: $PROVIDER_ID"
echo "Model: $MODEL_NAME"
echo "GPU: $GPU_TYPE"
echo "Max Queue: $MAX_QUEUE_SIZE"
echo "=========================================="

# ============================================================================
# STEP 1: Start Ollama Service
# ============================================================================
# Start Ollama in the background so we can continue with the script
# The & at the end means "run this in the background"
echo "Starting Ollama server..."
ollama serve &

# Save Ollama's process ID so we can check if it's still running
OLLAMA_PID=$!
echo "Ollama started with PID: $OLLAMA_PID"

# ============================================================================
# STEP 2: Wait for Ollama to be Ready
# ============================================================================
# Ollama takes time to start up. We need to wait until it's ready to accept
# requests before we try to pull the model or start Flask.
#
# We do this by repeatedly checking if Ollama responds to HTTP requests.
# We try for 60 attempts (120 seconds total).

echo "Waiting for Ollama to start..."
for i in {1..60}; do
    # Try to connect to Ollama's API endpoint
    # -s: silent (don't show progress)
    # > /dev/null: discard the output
    # 2>&1: also discard error messages
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✓ Ollama is ready (attempt $i/60)"
        break
    fi
    
    echo "Waiting for Ollama... (attempt $i/60)"
    sleep 2  # Wait 2 seconds before trying again
    
    # If we've tried 60 times and it's still not ready, something is wrong
    if [ $i -eq 60 ]; then
        echo "ERROR: Ollama failed to start after 120 seconds"
        echo "Checking if Ollama process is running..."
        ps aux | grep ollama || true
        exit 1
    fi
done

# ============================================================================
# STEP 3: Pull/Download the AI Model
# ============================================================================
# Download the AI model specified in MODEL_NAME environment variable
# This might take a while on first run (models are several GB)
# - Qwen2.5-Coder 32B (Q4_K_M): ~20GB, takes 10-20 minutes
# - Llama3.1 8B: ~5GB, takes 5-10 minutes
# On subsequent runs, if the model is already downloaded, this is fast

echo "Pulling primary model: $MODEL_NAME"
echo "⚠️  WARNING: Large models (70B+) can take 10-20 minutes to download"
echo "Please be patient..."
echo ""

# Show disk space before download
echo "Available disk space:"
df -h / || true
echo ""

# Pull the primary model
echo "Starting model download at $(date)"
if ! timeout 1800 ollama pull "$MODEL_NAME"; then
    echo "ERROR: Model pull timed out or failed after 30 minutes"
    echo "Model: $MODEL_NAME"
    echo "This could mean:"
    echo "1. Model name is incorrect"
    echo "2. Network connection issues"
    echo "3. Insufficient disk space"
    echo "4. Model is too large for available resources"
    df -h / || true
    exit 1
fi
echo "Primary model download completed at $(date)"
echo ""

echo ""

# Verify the primary model was downloaded successfully
echo "Verifying model..."
if ollama list | grep -q "$MODEL_NAME"; then
    echo "✓ Model $MODEL_NAME is available"
else
    echo "ERROR: Model $MODEL_NAME not found after pull"
    exit 1
fi

# Show all available models
echo "Available models:"
ollama list

# ============================================================================
# STEP 4: Start Flask Inference Server
# ============================================================================
# Now that Ollama is running and the model is loaded, start Flask
echo "Starting Flask inference server on port 8000..."

# Start Flask in the background
python3 inference_server.py &

# Save Flask's process ID
SERVER_PID=$!
echo "Flask started with PID: $SERVER_PID"

# ============================================================================
# STEP 5: Monitor Both Processes
# ============================================================================
# We need to keep the script running and monitor both processes.
# If either Ollama or Flask crashes, we should exit the container.
#
# The "wait" command waits for any background process to exit.
# The "-n" flag means "wait for the NEXT process to exit"

echo ""
echo "=========================================="
echo "✓ All services started successfully!"
echo "Ollama PID: $OLLAMA_PID"
echo "Flask PID: $SERVER_PID"
echo "Server ready at http://0.0.0.0:8000"
echo "=========================================="
echo ""

# Wait for either process to exit
# If this command returns, it means one of our processes died
wait -n $OLLAMA_PID $SERVER_PID

# If we get here, something stopped. Kill both processes.
echo ""
echo "WARNING: One of the services stopped!"
echo "Shutting down container..."

# Kill both processes (ignore errors if already dead)
# 2>/dev/null means "don't show error messages"
kill $OLLAMA_PID $SERVER_PID 2>/dev/null || true

echo "Container stopped"
exit 1

# ============================================================================
# SCRIPT EXPLANATION FOR DOCKER BEGINNERS
# ============================================================================
#
# WHY USE A STARTUP SCRIPT?
# Docker containers need a "main process" that keeps running. When that
# process stops, the container stops. In our case, we have TWO processes
# (Ollama and Flask) that both need to keep running. This script:
# 1. Starts both processes in the background
# 2. Monitors them
# 3. If either dies, shut down the container gracefully
#
# WHAT HAPPENS IF THE MODEL IS ALREADY DOWNLOADED?
# The "ollama pull" command checks if the model exists. If it does,
# it returns immediately. So subsequent container starts are fast.
#
# WHAT IF OLLAMA CRASHES?
# The "wait" command will detect it, and we'll kill Flask and exit.
# Docker/Kubernetes/Akash will see the container exited and can restart it.
#
# CAN I DEBUG THIS SCRIPT?
# Yes! If you run the container with "docker run -it", you can see all
# the echo statements and understand what's happening at each step.
# ============================================================================
