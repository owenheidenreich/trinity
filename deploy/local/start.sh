#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "🔧 Trinity Local Backend - Starting..."
echo "======================================"
echo ""

# Check Ollama installation
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not installed"
    echo ""
    echo "Install with: curl -fsSL https://ollama.com/install.sh | sh"
    echo "Or download from: https://ollama.com"
    exit 1
fi

echo "✅ Ollama installed"

# Start Ollama service if not running
if ! pgrep -x "ollama" > /dev/null; then
    echo "▶️  Starting Ollama service..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    echo "✅ Ollama service started"
else
    echo "✅ Ollama service already running"
fi

# Pull TinyLlama model
echo ""
echo "📥 Ensuring TinyLlama 1.1B model is available..."
if ollama list | grep -q "tinyllama:1.1b"; then
    echo "✅ TinyLlama already downloaded"
else
    echo "📥 Downloading TinyLlama (~637MB, ~30 seconds)..."
    ollama pull tinyllama:1.1b
    echo "✅ TinyLlama downloaded"
fi

# Set environment variables
export FILECOIN_API_KEY="$(cat ~/.pinata_jwt 2>/dev/null || echo '')"
export CHATS_DIR="$HOME/.trinity/chats"
export PROVIDER_ID="local-mac"
export MODEL_NAME="tinyllama:1.1b"
export OLLAMA_HOST="http://localhost:11434"
export MODEL_BACKEND="ollama"

# Create chats directory
mkdir -p "$CHATS_DIR"

# Check if backend already running
if lsof -i :8000 > /dev/null 2>&1; then
    echo ""
    echo "⚠️  Port 8000 already in use!"
    PID=$(lsof -t -i :8000)
    echo "   Process PID: $PID"
    echo ""
    echo "Stop it with: kill $PID"
    echo "Or run: ./stop.sh"
    exit 1
fi

# Start Flask backend
echo ""
echo "🐍 Starting Python Flask backend..."
cd ../../backend
python3 inference_server.py > /tmp/trinity_backend.log 2>&1 &
BACKEND_PID=$!

# Save PID for stop script
echo $BACKEND_PID > /tmp/trinity_backend.pid

echo "✅ Backend started (PID: $BACKEND_PID)"
echo ""

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
for i in {1..15}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend is healthy!"
        break
    fi
    if [ $i -eq 15 ]; then
        echo "❌ Backend failed to start (timeout after 15 seconds)"
        echo "   Check logs: tail -f /tmp/trinity_backend.log"
        exit 1
    fi
    sleep 1
    echo "   Attempt $i/15..."
done

echo ""
echo "🎉 Local backend ready!"
echo ""
echo "📍 Backend URL: http://localhost:8000"
echo "🏥 Health check: http://localhost:8000/health"
echo "📁 Chats stored: $CHATS_DIR"
echo ""
echo "📝 View logs:"
echo "   tail -f /tmp/trinity_backend.log   # Backend"
echo "   tail -f /tmp/ollama.log            # Ollama"
echo ""
echo "🛑 Stop backend:"
echo "   ./stop.sh"
echo ""
echo "📊 Check status:"
echo "   ./status.sh"
