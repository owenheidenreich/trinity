#!/bin/bash
# ============================================================================
# Trinity v4.0 Feature Tests - Manual curl commands
# ============================================================================
#
# Run individual tests to verify v4.0 features work on production
#
# Usage: ./test/test_v4_curl.sh
# ============================================================================

set -e

# Configuration
PROD_URL="https://api.dubya.ai"
LOCAL_URL="http://localhost:8000"

# Use production by default, override with: URL=$LOCAL_URL ./test_v4_curl.sh
URL="${URL:-$PROD_URL}"

echo "============================================"
echo "Trinity v4.0 Feature Tests"
echo "Target: $URL"
echo "============================================"
echo ""

# --------------------------------------------
# Test 1: Health Check
# --------------------------------------------
echo "📋 Test 1: Health Check"
echo "curl -s $URL/health | jq '.status, .model, .ollama_connected'"
echo ""
curl -s "$URL/health" | jq -r '.status, .model, .ollama_connected' 2>/dev/null || echo "Failed or jq not installed"
echo ""

# --------------------------------------------
# Test 2: V4 Status (NEW ENDPOINT)
# --------------------------------------------
echo "📋 Test 2: V4 Status Endpoint"
echo "curl -s $URL/v4/status"
echo ""
response=$(curl -s "$URL/v4/status" 2>/dev/null)
if echo "$response" | jq . >/dev/null 2>&1; then
    echo "$response" | jq .
    echo ""
    echo "Feature breakdown:"
    echo "$response" | jq -r '.features | to_entries[] | "  \(.key): \(.value)"' 2>/dev/null
else
    echo "$response"
    echo "(Note: v4/status returns 404 if v4 features not deployed yet)"
fi
echo ""

# --------------------------------------------
# Test 3: Simple Generate (existing endpoint)
# --------------------------------------------
echo "📋 Test 3: Simple Generate"
echo 'curl -s -X POST $URL/generate -d {"prompt": "What is 2+2?"}'
echo ""
curl -s -X POST "$URL/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2? Reply with just the number.", "max_length": 20}' \
  | head -c 200
echo ""
echo ""

# --------------------------------------------
# Test 4: Agent Generate (tests complexity routing)
# --------------------------------------------
echo "📋 Test 4: Agent Generate (streaming)"
echo "This tests the agentic pipeline with complexity routing."
echo 'curl -s -X POST $URL/generate/agent -d {"prompt": "..."}'
echo ""
echo "Sending request (may take 10-30s for cold start)..."
curl -s -X POST "$URL/generate/agent" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?", "contextMemory": []}' \
  | head -c 500
echo ""
echo ""

# --------------------------------------------
# Test 5: Web Search Tool
# --------------------------------------------
echo "📋 Test 5: Web Search Tool"
echo 'curl -s -X POST $URL/tools/search -d {"query": "..."}'
echo ""
curl -s -X POST "$URL/tools/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "latest Bitcoin price", "count": 3}' \
  | jq '.results[:2]' 2>/dev/null || head -c 300
echo ""
echo ""

# --------------------------------------------
# Summary
# --------------------------------------------
echo "============================================"
echo "Tests Complete!"
echo ""
echo "Note: The following v4 endpoints require ICP authentication:"
echo "  - POST /v4/vector/index     (bulk index chat history)"
echo "  - POST /v4/vector/document  (embed documents for RAG)"
echo "  - POST /v4/vector/search    (semantic search)"
echo "  - POST /v4/vector/sync      (sync to IPFS)"
echo "  - POST /v4/tools/execute    (execute tools)"
echo ""
echo "To test authenticated endpoints, use the frontend UI."
echo "============================================"
