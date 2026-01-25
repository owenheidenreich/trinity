#!/bin/bash

echo "📊 Trinity Local Backend - Status Check"
echo "========================================"
echo ""

# Check backend
if lsof -i :8000 > /dev/null 2>&1; then
    PID=$(lsof -t -i :8000)
    echo "✅ Backend: RUNNING (PID: $PID)"
    echo "   URL: http://localhost:8000"
    echo ""
    
    # Test health endpoint
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        HEALTH=$(curl -s http://localhost:8000/health)
        echo "   🏥 Health: HEALTHY"
        
        # Parse health response (requires jq, but gracefully handle if not installed)
        if command -v jq &> /dev/null; then
            PROVIDER=$(echo "$HEALTH" | jq -r '.provider_id // "unknown"')
            MODEL=$(echo "$HEALTH" | jq -r '.model // "unknown"')
            STATUS=$(echo "$HEALTH" | jq -r '.status // "unknown"')
            echo "   📍 Provider: $PROVIDER"
            echo "   🤖 Model: $MODEL"
            echo "   ✅ Status: $STATUS"
        else
            echo "   Response: $HEALTH"
            echo "   (Install jq for formatted output: brew install jq)"
        fi
    else
        echo "   ⚠️  Health: UNHEALTHY (endpoint not responding)"
        echo "   Check logs: tail -f /tmp/trinity_backend.log"
    fi
else
    echo "❌ Backend: NOT RUNNING"
    echo "   Start with: ./start.sh"
fi

echo ""

# Check Ollama
if pgrep -x "ollama" > /dev/null; then
    OLLAMA_PID=$(pgrep -x "ollama")
    echo "✅ Ollama: RUNNING (PID: $OLLAMA_PID)"
    echo "   URL: http://localhost:11434"
    
    # List models
    if ollama list > /dev/null 2>&1; then
        echo ""
        echo "   📦 Available models:"
        ollama list | tail -n +2 | awk '{printf "      - %s (size: %s)\n", $1, $2}'
    fi
else
    echo "❌ Ollama: NOT RUNNING"
    echo "   Start with: ollama serve"
fi

echo ""
echo "📝 Logs:"
echo "   Backend: tail -f /tmp/trinity_backend.log"
echo "   Ollama:  tail -f /tmp/ollama.log"
echo ""
echo "🛠️  Commands:"
echo "   Start:  ./start.sh"
echo "   Stop:   ./stop.sh"
echo "   Status: ./status.sh"
