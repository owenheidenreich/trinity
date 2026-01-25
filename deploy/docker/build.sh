#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project root is two levels up from deploy/docker/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Generate version based on date and time
VERSION="v2-$(date +%Y%m%d-%H%M%S)"

echo "🔨 Building Trinity Inference Docker Image"
echo "📦 Version: $VERSION"
echo ""

# Change to the project root for build context
# This allows Docker to access backend/ and deploy/ directories
cd "$PROJECT_ROOT"

echo "📂 Build context: $(pwd)"
echo ""

# Build and push with version tag
# -f specifies Dockerfile location in deploy/docker/
# Build context is the project root (contains backend/ and deploy/)
docker buildx build --platform linux/amd64 \
  -f deploy/docker/Dockerfile \
  -t gdubx/trinity-inference:$VERSION \
  --push .

if [ $? -ne 0 ]; then
    echo "❌ Build failed"
    exit 1
fi

echo ""
echo "✅ Successfully pushed: gdubx/trinity-inference:$VERSION"
echo ""

# Update all YAML files in the akash directory
echo "📝 Updating YAML deployment files..."
cd "$SCRIPT_DIR/../akash"
for yaml_file in *.yaml; do
    if [ -f "$yaml_file" ] && [[ "$yaml_file" == deploy-*.yaml ]]; then
        # Use sed to replace the image line
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS version
            sed -i '' "s|image: gdubx/trinity-inference:.*|image: gdubx/trinity-inference:$VERSION|g" "$yaml_file"
        else
            # Linux version
            sed -i "s|image: gdubx/trinity-inference:.*|image: gdubx/trinity-inference:$VERSION|g" "$yaml_file"
        fi
        # Fix macOS hidden flag bug caused by sed -i
        chflags nohidden "$yaml_file" 2>/dev/null || true
        echo "   ✓ Updated: $(basename $yaml_file)"
    fi
done

echo ""
echo "🚀 Ready to deploy!"
echo "   1. Go to Akash Console"
echo "   2. Click 'Update Deployment'"
echo "   3. Upload your updated YAML file from deploy/akash/"
echo ""
echo "📋 Image: gdubx/trinity-inference:$VERSION"
echo ""