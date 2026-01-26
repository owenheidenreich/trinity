#!/bin/bash
# Trinity Akash Deployment Helper
# Usage: ./scripts/akash-deploy.sh [tier]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PROJECT_ROOT/deploy/akash"

TIER="${1:-1}"
case "$TIER" in
    1|test) YAML_FILE="$DEPLOY_DIR/deploy-tinyllama-prod.yaml"; echo "Tier 1: TinyLlama (\$0.05-0.15/hr)";;
    2|balanced) YAML_FILE="$DEPLOY_DIR/tier2-balanced.yaml"; echo "Tier 2: Llama 8B (\$0.15-0.25/hr)";;
    3|premium) YAML_FILE="$DEPLOY_DIR/deploy-qwen.yaml"; echo "Tier 3: Qwen 72B (\$0.50-0.80/hr)";;
    *) echo "Use: 1, 2, or 3"; exit 1;;
esac

echo ""
echo "CHOOSE: *.akash.pub, *.europlots.com, d3akash.cloud"
echo "AVOID:  *.leet.haus (broken)"
echo ""

cat "$YAML_FILE" | pbcopy && echo "YAML copied to clipboard!"
open "https://deploy.cloudmos.io/new-deployment"
echo "After deploy: ./scripts/switch-provider.sh <url>"

