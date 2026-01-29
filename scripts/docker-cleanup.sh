#!/bin/bash
# Docker Cleanup Script with Progress
# Usage: ./scripts/docker-cleanup.sh

echo "🐳 Docker Cleanup Starting..."
echo "================================"

# Check if Docker is running
if ! docker info &>/dev/null; then
    echo "❌ Docker is not running. Starting Docker Desktop..."
    open -a Docker
    echo "⏳ Waiting for Docker to start (up to 60s)..."
    for i in {1..12}; do
        sleep 5
        if docker info &>/dev/null; then
            echo "✅ Docker is ready!"
            break
        fi
        echo "   Still waiting... ($((i*5))s)"
    done
    if ! docker info &>/dev/null; then
        echo "❌ Docker failed to start. Please start it manually."
        exit 1
    fi
fi

# Get initial disk usage
echo ""
echo "📊 Current Docker disk usage:"
docker system df
BEFORE=$(df -h / | tail -1 | awk '{print $4}')
echo ""
echo "💾 System free space before: $BEFORE"
echo ""

# Step 1: Remove stopped containers
echo "[1/5] 🗑️  Removing stopped containers..."
CONTAINERS=$(docker ps -aq 2>/dev/null | wc -l | tr -d ' ')
if [ "$CONTAINERS" -gt 0 ]; then
    docker rm $(docker ps -aq) 2>/dev/null
    echo "      Removed $CONTAINERS containers"
else
    echo "      No stopped containers"
fi

# Step 2: Remove dangling images
echo "[2/5] 🖼️  Removing dangling images..."
DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l | tr -d ' ')
if [ "$DANGLING" -gt 0 ]; then
    docker rmi $(docker images -f "dangling=true" -q) 2>/dev/null
    echo "      Removed $DANGLING dangling images"
else
    echo "      No dangling images"
fi

# Step 3: Remove ALL unused images (this is the big one)
echo "[3/5] 🖼️  Removing ALL unused images..."
docker image prune -a -f 2>/dev/null
echo "      Done"

# Step 4: Remove unused volumes
echo "[4/5] 💿 Removing unused volumes..."
VOLUMES=$(docker volume ls -q 2>/dev/null | wc -l | tr -d ' ')
docker volume prune -f 2>/dev/null
echo "      Pruned volumes (had $VOLUMES)"

# Step 5: Remove build cache
echo "[5/5] 🧹 Removing build cache..."
docker builder prune -a -f 2>/dev/null
echo "      Done"

# Final summary
echo ""
echo "================================"
echo "✅ Docker Cleanup Complete!"
echo ""
echo "📊 Docker disk usage after cleanup:"
docker system df
echo ""
AFTER=$(df -h / | tail -1 | awk '{print $4}')
echo "💾 System free space: $BEFORE → $AFTER"
echo "================================"
