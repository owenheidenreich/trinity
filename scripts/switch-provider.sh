#!/bin/bash
# ============================================================================
# Trinity Provider Switch Script
# ============================================================================
#
# Usage: ./scripts/switch-provider.sh <akash-url>
#
# Examples:
#   ./scripts/switch-provider.sh http://xyz.ingress.akash.pub
#   ./scripts/switch-provider.sh http://abc.ingress.hurricane.akash.pub
#
# This script:
# 1. Updates the AKASH_URL secret in Cloudflare Worker
#
# IMPORTANT: Use HTTP (not HTTPS) - Akash providers have invalid SSL certs
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
    echo "  ./scripts/switch-provider.sh http://xyz.ingress.akash.pub"
    echo "  ./scripts/switch-provider.sh http://abc.ingress.hurricane.akash.pub"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Use http:// (not https://) - Akash providers have invalid SSL certs${NC}"
    exit 1
fi

AKASH_URL="$1"

# Validate URL format
if [[ ! "$AKASH_URL" =~ ^https?:// ]]; then
    echo -e "${RED}Error: URL must start with http:// or https://${NC}"
    exit 1
fi

# Warn about HTTPS
if [[ "$AKASH_URL" == https://* ]]; then
    echo ""
    echo -e "${YELLOW}⚠️  WARNING: You specified HTTPS but Akash providers have invalid SSL certs!${NC}"
    echo -e "${YELLOW}   This will cause Cloudflare 526 errors.${NC}"
    echo -e "${YELLOW}   Consider using http:// instead.${NC}"
    echo ""
    read -p "Continue with HTTPS anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted. Rerun with http:// URL"
        exit 1
    fi
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
CLOUDFLARE_DIR="$PROJECT_ROOT/deploy/cloudflare-worker"

echo ""
echo "=========================================="
echo "Trinity Provider Switch"
echo "=========================================="
echo ""
echo -e "New URL: ${GREEN}$AKASH_URL${NC}"
echo ""

# Check if npx is available
if ! command -v npx &> /dev/null; then
    echo -e "${RED}Error: npx not found${NC}"
    echo "Install Node.js first"
    exit 1
fi

# Navigate to cloudflare worker directory
cd "$CLOUDFLARE_DIR"

echo "Updating AKASH_URL secret in Cloudflare Worker..."
echo "$AKASH_URL" | npx wrangler secret put AKASH_URL

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Provider switch complete!${NC}"
echo "=========================================="
echo ""
echo "Cloudflare Worker now points to: $AKASH_URL"
echo ""
echo "Test with:"
echo "  curl https://api.dubya.ai/health"
echo ""
