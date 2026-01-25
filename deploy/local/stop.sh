#!/bin/bash

echo "🛑 Trinity Local Backend - Stopping..."
echo "======================================"
echo ""

STOPPED_SOMETHING=false

# Stop backend server
if [ -f /tmp/trinity_backend.pid ]; then
    PID=$(cat /tmp/trinity_backend.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null && echo "✅ Backend stopped (PID: $PID)" || echo "⚠️  Could not stop PID $PID"
        STOPPED_SOMETHING=true
    else
        echo "ℹ️  Backend not running (stale PID file)"
    fi
    rm /tmp/trinity_backend.pid 2>/dev/null
elif lsof -i :8000 > /dev/null 2>&1; then
    PID=$(lsof -t -i :8000)
    kill $PID 2>/dev/null && echo "✅ Backend stopped (PID: $PID)" || echo "⚠️  Could not stop PID $PID"
    STOPPED_SOMETHING=true
else
    echo "ℹ️  Backend not running"
fi

# Ask about Ollama
if pgrep -x "ollama" > /dev/null; then
    echo ""
    read -p "Stop Ollama service too? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill ollama
        echo "✅ Ollama stopped"
        STOPPED_SOMETHING=true
    else
        echo "ℹ️  Ollama left running"
    fi
else
    echo "ℹ️  Ollama not running"
fi

echo ""
if [ "$STOPPED_SOMETHING" = true ]; then
    echo "🎉 Local backend stopped successfully"
else
    echo "ℹ️  Nothing to stop"
fi
