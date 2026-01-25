# ============================================================================
# Trinity Inference Server - Dockerfile (Phase 2)
# ============================================================================
# 
# WHAT IS A DOCKERFILE?
# A Dockerfile is like a recipe that tells Docker how to build a "container"
# Think of a container as a mini-computer that has everything needed to run
# your app: operating system, Python, libraries, and your code.
#
# WHY USE DOCKER?
# - Your app works the same on Mac, Linux, Windows, and Akash
# - All dependencies are included (no "works on my machine" problems)
# - Easy to deploy: just run one command
# - Isolated: doesn't interfere with other apps on the same machine
#
# WHAT THIS DOCKERFILE DOES:
# 1. Starts with Ubuntu + NVIDIA CUDA (for GPU support later)
# 2. Installs Python, pip, curl
# 3. Installs Ollama (the AI model runtime)
# 4. Copies your inference_server.py into the container
# 5. Installs Python dependencies (Flask, etc.)
# 6. Sets up the startup script
# 7. Exposes port 8000 (so we can access the server)
# 8. Defines what command runs when container starts
# ============================================================================

# ============================================================================
# STEP 1: Choose the "base image" (starting point)
# ============================================================================
# This is like choosing which operating system to install first.
# We use NVIDIA's CUDA image because:
# - It's Ubuntu 22.04 (popular Linux distribution)
# - It includes NVIDIA GPU drivers (needed for GPU inference on Akash)
# - It's the "runtime" version (smaller than the full development version)
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# ============================================================================
# STEP 2: Set environment variables
# ============================================================================
# Environment variables configure how the container behaves

# Prevent interactive prompts during package installation
# (normally Ubuntu asks questions during install, this skips them)
ENV DEBIAN_FRONTEND=noninteractive

# Make Python output appear immediately in logs (not buffered)
# Important for debugging - you see logs as they happen
ENV PYTHONUNBUFFERED=1

# Configure where Ollama runs (inside the container)
ENV OLLAMA_HOST=http://localhost:11434

# Default configuration (can be overridden when running the container)
ENV MODEL_NAME=phi3
ENV PROVIDER_ID=akash-provider-1
ENV GPU_TYPE=NVIDIA-A100
ENV MAX_QUEUE_SIZE=10

# ============================================================================
# STEP 3: Install system packages
# ============================================================================
# This installs the basic software needed to run everything

RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    curl \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# STEP 4: Install Ollama
# ============================================================================
# Ollama is the AI model runtime that runs Phi3, Llama, etc.
# This downloads and installs it automatically
RUN curl -fsSL https://ollama.ai/install.sh | sh

# ============================================================================
# STEP 5: Set up the working directory
# ============================================================================
# This is like "cd /app" - all future commands run from here
WORKDIR /app

# ============================================================================
# STEP 6: Install Python dependencies
# ============================================================================
# Copy requirements.txt first (Docker optimization trick)
# If requirements.txt doesn't change, Docker can cache this step
COPY backend/requirements.txt .

# Install Python packages
# --no-cache-dir: Don't save downloaded files (makes image smaller)
RUN pip3 install --no-cache-dir -r requirements.txt

# ============================================================================
# STEP 7: Copy application code
# ============================================================================
# Copy your inference server and startup script into the container
# Build context is project root, so we access backend/ and deploy/ from there
COPY backend/inference_server.py .
COPY backend/icp_auth.py .
COPY deploy/docker/startup.sh .

# Make startup script executable (give it permission to run)
RUN chmod +x startup.sh

# ============================================================================
# STEP 8: Create directory for Ollama models
# ============================================================================
# Ollama stores downloaded models here
RUN mkdir -p /root/.ollama

# ============================================================================
# STEP 8.5: Create directory for chat storage
# ============================================================================
# Create persistent storage directory for chat data
RUN mkdir -p /data/chats

# Declare volume for persistent storage
VOLUME ["/data/chats"]

# ============================================================================
# STEP 9: Expose the port
# ============================================================================
# This tells Docker that your app listens on port 8000
# It's like saying "this container has a door at port 8000"
EXPOSE 8000

# Also expose Ollama's port (used internally)
EXPOSE 11434

# ============================================================================
# STEP 10: Health check
# ============================================================================
# Docker will periodically check if your app is healthy
# --interval=30s: Check every 30 seconds
# --timeout=10s: If check takes >10s, consider it failed
# --start-period=1200s: Wait 20 minutes before first check (large models take time!)
# --retries=3: After 3 failed checks, mark container as unhealthy
# Note: Llama 70B download takes 10-20 minutes on first run
HEALTHCHECK --interval=30s --timeout=10s --start-period=1200s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ============================================================================
# STEP 11: Define the startup command
# ============================================================================
# When the container starts, run the startup.sh script
# This script will:
# 1. Start Ollama in the background
# 2. Wait for it to be ready
# 3. Pull the AI model
# 4. Start the Flask inference server
CMD ["/app/startup.sh"]

# ============================================================================
# DOCKER IMAGE BUILT!
# ============================================================================
# After running "docker build", you'll have a container image that:
# - Contains Ubuntu + CUDA + Python + Ollama + your code
# - Can run on any machine with Docker installed
# - Will automatically start both Ollama and your Flask server
# - Exposes port 8000 for HTTP requests
# - Includes health checks for monitoring
#
# Total image size: ~8-10GB (mostly CUDA drivers and AI model)
# ============================================================================
