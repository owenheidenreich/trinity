#!/bin/bash
# Trinity Frontend Deployment Script
# Builds and deploys the frontend to Internet Computer

set -e  # Exit on any error

echo "🚀 Starting Trinity Frontend Deployment..."
echo ""

# Navigate to trinity-icp directory
cd "$(dirname "$0")/trinity-icp"

echo "📦 Building frontend..."
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo ""
echo "✅ Build complete!"
echo ""
echo "🌐 Deploying to Internet Computer..."
dfx deploy --network ic trinity_frontend

if [ $? -ne 0 ]; then
    echo "❌ Deployment failed!"
    exit 1
fi

echo ""
echo "✅ Deployment successful!"
echo ""
echo "🔗 Your site is live at: https://trinityai.cc"
echo ""
echo "💡 Hard refresh your browser (Cmd+Shift+R) to see changes!"
echo ""
