#!/bin/bash
set -e

MODEL=$1

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 Trinity - Production Deployment"
echo "==================================="
echo ""

if [ -z "$MODEL" ]; then
    echo "Usage: ./deploy.sh <model>"
    echo ""
    echo "Available models:"
    echo ""
    echo "  llama70b   - Llama3.1 70B (most powerful)"
    echo "             Hardware: 2x A100 80GB"
    echo "             Cost: ~\$150-200/month"
    echo "             Performance: 50-100 tokens/sec"
    echo ""
    echo "  mixtral    - Mixtral 8x22b (alternative large model)"
    echo "             Hardware: 2x A100 80GB"
    echo "             Cost: ~\$150-200/month"
    echo ""
    echo "  qwen       - Qwen2.5 72B (code-optimized)"
    echo "             Hardware: 2x A100 80GB"
    echo "             Cost: ~\$150-200/month"
    echo ""
    echo "  llama3     - Llama3.1 8B (balanced)"
    echo "             Hardware: 1x A100 80GB"
    echo "             Cost: ~\$80-100/month"
    echo ""
    echo "  phi3       - Phi3 3.8B (budget option)"
    echo "             Hardware: RTX 4090"
    echo "             Cost: ~\$30-40/month"
    echo ""
    echo "Example: ./deploy.sh llama70b"
    echo ""
    exit 1
fi

echo "Model: $MODEL"
echo ""

# Validate model choice and set YAML file
case $MODEL in
    llama70b)
        YAML_FILE="deploy-llama70.yaml"
        DESCRIPTION="Llama3.1 70B (most powerful)"
        ;;
    mixtral)
        YAML_FILE="deploy-mixtral.yaml"
        DESCRIPTION="Mixtral 8x22b (alternative large)"
        ;;
    qwen)
        YAML_FILE="deploy-qwen.yaml"
        DESCRIPTION="Qwen2.5 72B (code-optimized)"
        ;;
    llama3)
        YAML_FILE="deploy-llama3.yaml"
        DESCRIPTION="Llama3.1 8B (balanced)"
        ;;
    phi3)
        YAML_FILE="deploy-phi3.yaml"
        DESCRIPTION="Phi3 3.8B (budget)"
        ;;
    *)
        echo "❌ Unknown model: $MODEL"
        echo ""
        echo "Valid options: llama70b, mixtral, qwen, llama3, phi3"
        exit 1
        ;;
esac

echo "📋 Selected: $DESCRIPTION"
echo "📄 YAML: $YAML_FILE"
echo ""

# Build production image
echo "📦 Building Docker image..."
echo "   This will take 2-5 minutes..."
echo ""

cd "$PROJECT_ROOT/deploy/docker"
./build.sh

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Build failed"
    exit 1
fi

echo ""
echo "✅ Build successful!"
echo ""

# Get the image version that was just built
IMAGE_VERSION=$(grep 'image:' "$YAML_FILE" | awk '{print $2}')

echo "┌─────────────────────────────────────────────────────────┐"
echo "│  📝 NEXT STEPS - Deploy to Akash Network               │"
echo "├─────────────────────────────────────────────────────────┤"
echo "│                                                         │"
echo "│  1. Go to: https://console.akash.network               │"
echo "│                                                         │"
echo "│  2. Click 'Deploy' or update existing deployment       │"
echo "│                                                         │"
echo "│  3. Upload this file:                                  │"
echo "│     deploy/akash/$YAML_FILE"
echo "│                                                         │"
echo "│  4. Review and accept a bid                            │"
echo "│                                                         │"
echo "│  5. Wait 10-20 minutes for deployment                  │"
echo "│     (Model download: ~40GB for 70B)                    │"
echo "│                                                         │"
echo "│  6. Get the ingress URL from Akash Console             │"
echo "│                                                         │"
echo "│  7. Test health: https://<ingress-url>/health          │"
echo "│                                                         │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "📦 Docker Image: $IMAGE_VERSION"
echo "💰 Estimated Cost: See model details above"
echo "⚡ Performance: 50-100 tokens/sec (varies by model)"
echo ""
echo "🔧 Deployment File: $PROJECT_ROOT/deploy/akash/$YAML_FILE"
echo ""
echo "💡 TIP: Keep the local deployment running during this process"
echo "   so you can continue development while Akash deploys!"
echo ""
