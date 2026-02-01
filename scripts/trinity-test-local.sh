#!/bin/bash
# Trinity Local Test Environment
# Runs the full backend (Docker) locally with test mode enabled
# Allows testing autosave, memory, and storage features without production deployment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_ROOT/deploy/docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  🧪 Trinity Local Test Environment${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is required but not installed${NC}"
    exit 1
fi

# Ensure Docker is running
if ! docker info &> /dev/null; then
    echo -e "${YELLOW}⏳ Starting Docker...${NC}"
    open -a Docker 2>/dev/null || true
    sleep 10
    if ! docker info &> /dev/null; then
        echo -e "${RED}❌ Docker is not running. Please start Docker Desktop.${NC}"
        exit 1
    fi
fi

# Stop any existing container
EXISTING=$(docker ps -q -f "name=trinity-test" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo -e "${YELLOW}🛑 Stopping existing test container...${NC}"
    docker stop trinity-test &>/dev/null || true
    docker rm trinity-test &>/dev/null || true
fi

# Build options
echo ""
echo -e "${YELLOW}Build options:${NC}"
echo "  1) Use production image (gdubx/trinity-inference:v3-fresh)"
echo "  2) Build fresh local image"
echo ""
read -p "Choice [1]: " BUILD_CHOICE
BUILD_CHOICE=${BUILD_CHOICE:-1}

if [ "$BUILD_CHOICE" = "2" ]; then
    echo -e "${BLUE}🔨 Building local Docker image...${NC}"
    cd "$DOCKER_DIR"
    docker build -t trinity-test:local -f Dockerfile ../..
    IMAGE="trinity-test:local"
else
    IMAGE="gdubx/trinity-inference:v3-fresh"
    echo -e "${BLUE}📦 Pulling production image...${NC}"
    docker pull "$IMAGE"
fi

# Create local storage directory
STORAGE_DIR="$PROJECT_ROOT/.trinity-test-data"
mkdir -p "$STORAGE_DIR/chats"
mkdir -p "$STORAGE_DIR/memory"

echo ""
echo -e "${GREEN}🚀 Starting Trinity test container...${NC}"
echo -e "${YELLOW}   Model: TinyLlama 1.1B (fast, for testing)${NC}"
echo -e "${YELLOW}   Data:  ${STORAGE_DIR}${NC}"
echo ""

# Run container
docker run -d \
    --name trinity-test \
    -p 8000:8000 \
    -e MODEL_NAME=tinyllama \
    -e OLLAMA_HOST=http://localhost:11434 \
    -e CHATS_DIR=/var/lib/trinity/chats \
    -v "$STORAGE_DIR/chats:/var/lib/trinity/chats" \
    "$IMAGE"

# Wait for startup
echo -e "${YELLOW}⏳ Waiting for container to start...${NC}"
sleep 5

# Check container is running
if ! docker ps -q -f "name=trinity-test" &>/dev/null; then
    echo -e "${RED}❌ Container failed to start. Logs:${NC}"
    docker logs trinity-test 2>&1 | tail -20
    exit 1
fi

# Wait for health endpoint
echo -e "${YELLOW}⏳ Waiting for backend to be ready (pulling model on first run)...${NC}"
for i in {1..60}; do
    if curl -s http://localhost:8000/health &>/dev/null; then
        break
    fi
    sleep 2
    echo -n "."
done
echo ""

# Final check
if curl -s http://localhost:8000/health | grep -q "ok"; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✅ Trinity Test Environment Ready!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  ${BLUE}Backend:${NC}     http://localhost:8000"
    echo -e "  ${BLUE}Health:${NC}      http://localhost:8000/health"
    echo -e "  ${BLUE}Test Data:${NC}   $STORAGE_DIR"
    echo ""
    echo -e "  ${YELLOW}Testing Tips:${NC}"
    echo -e "    • No signature verification in test mode"
    echo -e "    • Send ICP-Principal header for user isolation"
    echo -e "    • Chats saved to local disk (not Filecoin)"
    echo ""
    echo -e "  ${YELLOW}Commands:${NC}"
    echo -e "    docker logs -f trinity-test    # View logs"
    echo -e "    docker stop trinity-test       # Stop container"
    echo -e "    docker rm trinity-test         # Remove container"
    echo ""
    echo -e "  ${YELLOW}Quick Test:${NC}"
    echo -e "    curl http://localhost:8000/health"
    echo -e "    curl -X POST http://localhost:8000/generate \\"
    echo -e "      -H 'Content-Type: application/json' \\"
    echo -e "      -d '{\"prompt\": \"Hello!\", \"context\": []}'"
    echo ""
else
    echo -e "${RED}❌ Backend failed to start. Check logs:${NC}"
    docker logs trinity-test 2>&1 | tail -30
    exit 1
fi
