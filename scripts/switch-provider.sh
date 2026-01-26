#!/bin/bash
# ============================================================================
# Trinity Provider Switch Script
# ============================================================================
#
# Usage: ./scripts/switch-provider.sh <akash-url>
#
# Examples:
#   ./scripts/switch-provider.sh https://xyz.ingress.akash.pub
#   ./scripts/switch-provider.sh http://abc.ingress.leet.haus
#
# This script:
# 1. Updates the AKASH_URL environment variable in Vercel
# 2. Redeploys the Vercel proxy
#
# The proxy auto-detects HTTP vs HTTPS from the URL scheme.
# ============================================================================

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if URL provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: No URL provided${NC}"
    echo ""
    echo "Usage: ./scripts/switch-provider.sh <akash-url>"
    echo ""
    echo "Examples:"
    echo "  ./scripts/switch-provider.sh https://xyz.ingress.akash.pub"
    echo "  ./scripts/switch-provider.sh http://abc.ingress.leet.haus"
    exit 1
fi

AKASH_URL="$1"

# Validate URL format
if [[ ! "$AKASH_URL" =~ ^https?:// ]]; then
    echo -e "${RED}Error: URL must start with http:// or https://${NC}"
    exit 1
fi

# Warn about problematic providers
if [[ "$AKASH_URL" == *"leet.haus"* ]]; then
    echo ""
    echo -e "${YELLOW}⚠️  WARNING: leet.haus providers have known ingress issues!${NC}"
    echo -e "${YELLOW}   These providers often have completely broken networking.${NC}"
    echo -e "${YELLOW}   Consider using a *.akash.pub provider instead.${NC}"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# Recommend good providers
echo ""
echo -e "${GREEN}Provider Selection Tips:${NC}"
echo "  ✓ GOOD: *.akash.pub domains (hurricane, europlots, a100.dsm.val)"
echo "  ✗ BAD:  *.leet.haus domains (broken ingress)"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERCEL_DIR="$PROJECT_ROOT/deploy/vercel-proxy"

echo ""
echo "=========================================="
echo "Trinity Provider Switch"
echo "=========================================="
echo ""
echo -e "New URL: ${GREEN}$AKASH_URL${NC}"
echo ""

# Check if vercel CLI is available
if ! command -v vercel &> /dev/null; then
    echo -e "${RED}Error: vercel CLI not found${NC}"
    echo "Install with: npm i -g vercel"
    exit 1
fi

# Navigate to vercel proxy directory
cd "$VERCEL_DIR"

# Remove existing env var (ignore errors if doesn't exist)
echo "Updating AKASH_URL environment variable..."
vercel env rm AKASH_URL production --yes 2>/dev/null || true

# Add new env var
echo "$AKASH_URL" | vercel env add AKASH_URL production

echo ""
echo "Deploying to Vercel..."
echo ""

# Deploy
npx vercel --yes --prod

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Provider switch complete!${NC}"
echo "=========================================="
echo ""
echo "Vercel proxy now points to: $AKASH_URL"
echo ""
echo "Test with:"
echo "  curl https://vercel-proxy-swart-nine.vercel.app/health"
echo ""
