#!/bin/bash
set -e

echo "🚀 Starting Trinity Local Native Environment (macOS)"
echo "===================================================="

cd "$(dirname "$0")"

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not found. Installing..."
    echo "📥 Downloading Ollama for macOS..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "✅ Ollama installed"
else
    echo "✅ Ollama already installed"
fi

# Start Ollama service (if not running)
if ! pgrep -x "ollama" > /dev/null; then
    echo "🔧 Starting Ollama service..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    echo "✅ Ollama service started"
else
    echo "✅ Ollama service already running"
fi

# Pull TinyLlama model (smallest model, fast download)
echo ""
echo "📥 Pulling TinyLlama 1.1B model (~637MB)..."
ollama pull tinyllama:1.1b

# Load environment variables
export FILECOIN_API_KEY="$(cat ~/.pinata_jwt)"
export CHATS_DIR="$HOME/.trinity/chats"
export PROVIDER_ID="local-mac"
export MODEL_NAME="tinyllama:1.1b"
export OLLAMA_HOST="http://localhost:11434"

# Create chats directory
mkdir -p "$CHATS_DIR"
echo "✅ Created chats directory: $CHATS_DIR"

# Start Python backend
echo ""
echo "🐍 Starting Python backend..."
cd ../../deployment/scripts
python3 inference_server.py > /tmp/trinity_backend.log 2>&1 &
BACKEND_PID=$!
echo "✅ Backend started (PID: $BACKEND_PID)"

# Wait for backend to be ready
echo ""
echo "⏳ Waiting for backend to be ready..."
sleep 5

# Test health endpoint
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Backend is healthy!"
else
    echo "⚠️  Backend may still be starting... check logs if issues persist"
fi

echo ""
echo "📍 Backend URL: http://localhost:8000"
echo "🏥 Health check: http://localhost:8000/health"
echo "📊 View logs: tail -f /tmp/trinity_backend.log"
echo "🛑 Stop: kill $BACKEND_PID"
echo ""
echo "🧪 Test at: https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io"
echo "   (Update frontend Config.API_URL to http://localhost:8000 for local testing)"
