#!/bin/bash
# =============================================================================
# Generate Console-Ready YAML
# =============================================================================
# Creates a temporary YAML file with API keys injected for Akash Console upload
# The generated file is in /tmp and NOT committed to git
#
# Usage: ./scripts/generate-console-yaml.sh [tier]
#   tier: 1, 2, or 3 (default: 3)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

# Load .env file
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found at $ENV_FILE"
    exit 1
fi

# Extract API keys
LIGHTHOUSE_API_KEY=$(grep "^LIGHTHOUSE_API_KEY=" "$ENV_FILE" | cut -d'=' -f2)
BRAVE_SEARCH_API_KEY=$(grep "^BRAVE_SEARCH_API_KEY=" "$ENV_FILE" | cut -d'=' -f2)

if [ -z "$LIGHTHOUSE_API_KEY" ] || [ -z "$BRAVE_SEARCH_API_KEY" ]; then
    echo "❌ API keys not found in .env file"
    exit 1
fi

# Select tier
TIER="${1:-3}"
case $TIER in
    1) YAML_FILE="$PROJECT_ROOT/deploy/akash/deploy-tier1-basic.yaml" ;;
    2) YAML_FILE="$PROJECT_ROOT/deploy/akash/deploy-tier2-balanced.yaml" ;;
    3) YAML_FILE="$PROJECT_ROOT/deploy/akash/deploy-tier3-complex.yaml" ;;
    *) echo "❌ Invalid tier: $TIER (use 1, 2, or 3)"; exit 1 ;;
esac

if [ ! -f "$YAML_FILE" ]; then
    echo "❌ YAML file not found: $YAML_FILE"
    exit 1
fi

# Generate output file
OUTPUT_FILE="/tmp/trinity-tier${TIER}-console.yaml"

# Replace placeholders with actual values
sed -e "s|\${LIGHTHOUSE_API_KEY}|${LIGHTHOUSE_API_KEY}|g" \
    -e "s|\${BRAVE_SEARCH_API_KEY}|${BRAVE_SEARCH_API_KEY}|g" \
    "$YAML_FILE" > "$OUTPUT_FILE"

echo "✅ Console-ready YAML generated: $OUTPUT_FILE"
echo ""
echo "📋 Copy this file to Akash Console:"
echo "   cat $OUTPUT_FILE | pbcopy"
echo ""
echo "Or open in Finder:"
echo "   open /tmp"
echo ""
echo "⚠️  WARNING: This file contains API keys - do NOT commit to git!"
