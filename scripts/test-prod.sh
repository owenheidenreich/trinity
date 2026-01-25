#!/bin/bash

echo "🧪 Trinity - Pre-Production Testing Workflow"
echo "============================================="
echo ""
echo "This will test against your Akash production backend:"
echo "  • Backend: Akash Network (decentralized)"
echo "  • Model: Llama3.1 70B (high quality)"
echo "  • Provider: trinity-llama70b [PROD]"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if local backend is running
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Local backend is running on port 8000"
    echo "   Auto-stopping for production testing..."
    echo ""
    cd "$PROJECT_ROOT/deploy/local"
    
    # Auto-stop backend (don't stop Ollama)
    if [ -f /tmp/trinity_backend.pid ]; then
        PID=$(cat /tmp/trinity_backend.pid)
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID 2>/dev/null && echo "✅ Backend stopped (PID: $PID)"
        fi
        rm /tmp/trinity_backend.pid 2>/dev/null
    elif lsof -i :8000 > /dev/null 2>&1; then
        PID=$(lsof -t -i :8000)
        kill $PID 2>/dev/null && echo "✅ Backend stopped (PID: $PID)"
    fi
    
    sleep 2
    cd "$PROJECT_ROOT"
    echo ""
fi

echo "✅ Local backend is stopped"
echo ""
echo "📍 Opening frontend in browser..."
echo ""
echo "⏱️  EXPECTED BEHAVIOR:"
echo "  1. Frontend tries localhost:8000 (2 second timeout)"
echo "  2. Switches to Akash production URL automatically"
echo "  3. Connects to Llama3.1 70B (10-20 seconds for cold start)"
echo ""
echo "📊 WHAT TO WATCH FOR:"
echo "  • Status should show 'Connecting...' for ~20 seconds"
echo "  • Then: 'Provider: trinity-llama70b [PROD]'"
echo "  • Model: 'llama3.1:70b'"
echo "  • Green status indicator"
echo ""
echo "🔍 Open browser console to see detailed connection logs"
echo ""

# Open frontend
cd "$PROJECT_ROOT"
open trinity-icp/dist/index.html

echo "✅ Frontend opened"
echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│  🧪 TESTING CHECKLIST                       │"
echo "├─────────────────────────────────────────────┤"
echo "│  ☐ Status shows 'Connecting...' initially  │"
echo "│  ☐ Wait 10-20 seconds                       │"
echo "│  ☐ Status changes to 'Connected'            │"
echo "│  ☐ Provider shows 'trinity-llama70b [PROD]' │"
echo "│  ☐ Model shows 'llama3.1:70b'               │"
echo "│  ☐ Send a test message                      │"
echo "│  ☐ Response is high quality (70B model)     │"
echo "└─────────────────────────────────────────────┘"
echo ""
echo "🔧 Debug Commands:"
echo "   lsof -i :8000                    # Verify no local backend"
echo "   ./deploy/local/status.sh     # Check local status"
echo ""
echo "💡 If stuck on 'Connecting...', check Akash deployment status"
echo ""
