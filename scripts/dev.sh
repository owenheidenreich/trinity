#!/bin/bash
set -e

echo "🚀 Trinity - Daily Development Workflow"
echo "======================================="
echo ""
echo "This will start your local test environment:"
echo "  • Backend: http://localhost:8000"
echo "  • Model: TinyLlama 1.1B (fast, free)"
echo "  • Provider: local-mac [LOCAL]"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if already running
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Backend already running on port 8000"
    echo ""
    read -p "Stop and restart? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 Stopping existing backend..."
        cd "$PROJECT_ROOT/deploy/local"
        ./stop.sh
        sleep 2
        echo ""
    else
        echo "✅ Using existing backend"
        echo ""
        echo "📍 Opening frontend..."
        open "$PROJECT_ROOT/trinity-icp/dist/index.html"
        echo ""
        echo "✅ Development environment ready!"
        echo ""
        echo "📊 Current status:"
        cd "$PROJECT_ROOT/deploy/local"
        ./status.sh
        exit 0
    fi
fi

# Start local backend
echo "🔧 Starting local backend..."
cd "$PROJECT_ROOT/deploy/local"
./start.sh

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Failed to start backend"
    echo "   Check logs: tail -f /tmp/trinity_backend.log"
    exit 1
fi

# Wait for health check
echo ""
echo "⏳ Verifying backend health..."
for i in {1..10}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend is healthy!"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "⚠️  Backend health check failed (timeout)"
        echo "   But it might still work - continuing anyway..."
    fi
    sleep 1
done

# Open frontend
cd "$PROJECT_ROOT"
echo ""
echo "📍 Opening frontend in browser..."
open trinity-icp/dist/index.html

echo ""
echo "🎉 Development environment ready!"
echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│  📊 STATUS                                  │"
echo "├─────────────────────────────────────────────┤"
echo "│  Backend:  http://localhost:8000            │"
echo "│  Provider: local-mac [LOCAL]                │"
echo "│  Model:    tinyllama:1.1b                   │"
echo "│  Frontend: index.html (opened in browser)   │"
echo "└─────────────────────────────────────────────┘"
echo ""
echo "📝 Useful Commands:"
echo "   ./deploy/local/status.sh    # Check status"
echo "   ./deploy/local/stop.sh      # Stop backend"
echo "   tail -f /tmp/trinity_backend.log # View logs"
echo ""
echo "💡 The frontend will auto-detect your local backend"
echo "   Look for: '✅ Local backend available' in browser console"
echo ""
