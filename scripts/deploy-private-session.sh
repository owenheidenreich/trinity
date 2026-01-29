#!/bin/bash
# ============================================================================
# Trinity Private Session Deployment Script
# ============================================================================
# 
# Deploys a dedicated Akash instance for a private user session.
# Called after payment is detected. Creates isolated deployment with:
# - Unique session ID
# - Dedicated Vercel proxy endpoint (or shared with session routing)
# - Expiry timestamp based on payment amount
#
# Usage:
#   ./scripts/deploy-private-session.sh <tier> <payment_akt> <session_id>
#
# Example:
#   ./scripts/deploy-private-session.sh 1 0.16 sess_abc123
#
# Output: JSON with deployment details (URI, expiry, etc.)
# ============================================================================

set -e

# Arguments
TIER="${1:-1}"
PAYMENT_AKT="${2:-0}"
SESSION_ID="${3:-$(date +%s)}"

# Configuration
WALLET_NAME="trinity-wallet"
KEYRING="os"
CHAIN_ID="akashnet-2"
RPC_NODE="https://rpc.akashnet.net:443"
DOCKER_IMAGE="gdubx/trinity-inference:v4-funding"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PROJECT_ROOT/deploy/akash"

# Tier configuration
declare -A TIER_NAMES=([1]="Starter" [2]="Standard" [3]="Professional")
declare -A TIER_MODELS=([1]="tinyllama:1.1b" [2]="llama3.1:8b" [3]="qwen2.5:72b")
declare -A TIER_HOURLY_AKT=([1]="0.15" [2]="0.40" [3]="1.75")
declare -A TIER_YAMLS=([1]="deploy-tier1-basic.yaml" [2]="deploy-tier2-balanced.yaml" [3]="deploy-tier3-complex.yaml")

# Platform fee (5%)
PLATFORM_FEE_PERCENT=5

# Calculate session parameters
calculate_session() {
    local payment="$1"
    local hourly_rate="${TIER_HOURLY_AKT[$TIER]}"
    
    # 95% goes to hardware escrow
    local hardware_akt=$(echo "$payment * 0.95" | bc -l)
    local platform_akt=$(echo "$payment * 0.05" | bc -l)
    
    # Calculate hours from hardware budget
    local hours=$(echo "$hardware_akt / $hourly_rate" | bc -l)
    local hours_int=$(printf "%.0f" "$hours")
    
    # Calculate expiry timestamp
    local now=$(date +%s)
    local expiry_ts=$((now + hours_int * 3600))
    local expiry_iso=$(date -u -r "$expiry_ts" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "@$expiry_ts" +"%Y-%m-%dT%H:%M:%SZ")
    
    echo "$hardware_akt|$platform_akt|$hours_int|$expiry_iso"
}

# Create temporary SDL with session env vars
create_session_sdl() {
    local base_yaml="$1"
    local session_id="$2"
    local expiry="$3"
    local funded_akt="$4"
    
    local temp_yaml="/tmp/trinity-session-${session_id}.yaml"
    
    # Copy base YAML and inject session variables
    cp "$base_yaml" "$temp_yaml"
    
    # Replace SESSION_TYPE and add session-specific vars
    sed -i.bak "s/SESSION_TYPE=community/SESSION_TYPE=private/" "$temp_yaml"
    
    # Add session-specific environment variables after SESSION_TYPE line
    sed -i.bak "/SESSION_TYPE=private/a\\
      - SESSION_ID=${session_id}\\
      - SESSION_EXPIRY=${expiry}\\
      - SESSION_FUNDED_AKT=${funded_akt}
" "$temp_yaml"
    
    # Update provider ID to include session
    sed -i.bak "s/PROVIDER_ID=trinity-tier[0-9]-[a-z]*/PROVIDER_ID=trinity-session-${session_id}/" "$temp_yaml"
    
    rm -f "${temp_yaml}.bak"
    echo "$temp_yaml"
}

# Deploy to Akash
deploy_to_akash() {
    local yaml_file="$1"
    local hardware_akt="$2"
    
    echo "🚀 Creating Akash deployment..." >&2
    
    # Convert AKT to uAKT for deposit
    local deposit_uakt=$(echo "$hardware_akt * 1000000" | bc | cut -d. -f1)
    # Ensure minimum deposit of 500000 uAKT (0.5 AKT)
    if [ "$deposit_uakt" -lt 500000 ]; then
        deposit_uakt=500000
    fi
    
    # Create deployment
    local create_output=$(provider-services tx deployment create "$yaml_file" \
        --from "$WALLET_NAME" \
        --keyring-backend "$KEYRING" \
        --chain-id "$CHAIN_ID" \
        --node "$RPC_NODE" \
        --gas-prices 0.025uakt \
        --gas auto \
        --gas-adjustment 1.5 \
        --deposit "${deposit_uakt}uakt" \
        -y 2>&1)
    
    # Extract DSEQ from output
    local dseq=$(echo "$create_output" | grep -oP 'dseq:\s*\K\d+' | head -1)
    
    if [ -z "$dseq" ]; then
        echo "❌ Failed to create deployment" >&2
        echo "$create_output" >&2
        return 1
    fi
    
    echo "📦 Deployment created: DSEQ $dseq" >&2
    
    # Wait for bids
    sleep 30
    
    # Get bids
    local bids=$(provider-services query market bid list \
        --owner "$(provider-services keys show $WALLET_NAME -a --keyring-backend $KEYRING)" \
        --dseq "$dseq" \
        --state open \
        --node "$RPC_NODE" \
        -o json 2>/dev/null)
    
    local provider=$(echo "$bids" | jq -r '.bids[0].bid.bid_id.provider // empty')
    
    if [ -z "$provider" ]; then
        echo "❌ No bids received" >&2
        return 1
    fi
    
    echo "🤝 Accepting bid from: $provider" >&2
    
    # Accept bid
    provider-services tx market lease create \
        --dseq "$dseq" \
        --provider "$provider" \
        --from "$WALLET_NAME" \
        --keyring-backend "$KEYRING" \
        --chain-id "$CHAIN_ID" \
        --node "$RPC_NODE" \
        --gas-prices 0.025uakt \
        --gas auto \
        --gas-adjustment 1.5 \
        -y 2>&1 >/dev/null
    
    # Wait for lease
    sleep 10
    
    # Send manifest
    provider-services send-manifest "$yaml_file" \
        --dseq "$dseq" \
        --provider "$provider" \
        --from "$WALLET_NAME" \
        --keyring-backend "$KEYRING" \
        --chain-id "$CHAIN_ID" \
        --node "$RPC_NODE" 2>&1 >/dev/null
    
    # Wait for deployment
    sleep 20
    
    # Get lease status to extract URI
    local status=$(provider-services lease-status \
        --dseq "$dseq" \
        --provider "$provider" \
        --from "$WALLET_NAME" \
        --keyring-backend "$KEYRING" \
        --node "$RPC_NODE" 2>/dev/null)
    
    local uri=$(echo "$status" | jq -r '.services.trinity.uris[0] // empty')
    
    echo "$dseq|$provider|$uri"
}

# Close an existing deployment
close_deployment() {
    local dseq="$1"
    
    echo "🔒 Closing deployment DSEQ $dseq..." >&2
    
    provider-services tx deployment close \
        --dseq "$dseq" \
        --from "$WALLET_NAME" \
        --keyring-backend "$KEYRING" \
        --chain-id "$CHAIN_ID" \
        --node "$RPC_NODE" \
        --gas-prices 0.025uakt \
        --gas auto \
        --gas-adjustment 1.5 \
        -y 2>&1 >/dev/null
    
    echo "✅ Deployment closed" >&2
}

# Main execution
main() {
    # Validate tier
    if [[ ! "${TIER_MODELS[$TIER]+isset}" ]]; then
        echo '{"error": "Invalid tier. Use 1, 2, or 3"}' 
        exit 1
    fi
    
    # Validate payment
    if (( $(echo "$PAYMENT_AKT <= 0" | bc -l) )); then
        echo '{"error": "Invalid payment amount"}'
        exit 1
    fi
    
    # Calculate session parameters
    local result=$(calculate_session "$PAYMENT_AKT")
    IFS='|' read -r hardware_akt platform_akt hours expiry <<< "$result"
    
    if [ "$hours" -lt 1 ]; then
        echo "{\"error\": \"Payment too small. Minimum 1 hour. Received ${PAYMENT_AKT} AKT for tier ${TIER}\"}"
        exit 1
    fi
    
    # Get base YAML for tier
    local base_yaml="$DEPLOY_DIR/${TIER_YAMLS[$TIER]}"
    
    if [ ! -f "$base_yaml" ]; then
        echo "{\"error\": \"Missing deployment YAML: $base_yaml\"}"
        exit 1
    fi
    
    # Create session-specific SDL
    local session_yaml=$(create_session_sdl "$base_yaml" "$SESSION_ID" "$expiry" "$hardware_akt")
    
    # Deploy to Akash
    local deploy_result=$(deploy_to_akash "$session_yaml" "$hardware_akt")
    IFS='|' read -r dseq provider uri <<< "$deploy_result"
    
    # Cleanup temp file
    rm -f "$session_yaml"
    
    if [ -z "$uri" ]; then
        echo '{"error": "Deployment failed - no URI received"}'
        exit 1
    fi
    
    # Output result as JSON
    cat <<EOF
{
    "success": true,
    "session_id": "${SESSION_ID}",
    "tier": ${TIER},
    "tier_name": "${TIER_NAMES[$TIER]}",
    "model": "${TIER_MODELS[$TIER]}",
    "payment_akt": ${PAYMENT_AKT},
    "hardware_akt": ${hardware_akt},
    "platform_akt": ${platform_akt},
    "hours": ${hours},
    "expires_at": "${expiry}",
    "dseq": "${dseq}",
    "provider": "${provider}",
    "uri": "${uri}",
    "endpoint": "https://${uri}"
}
EOF
}

# Check if called with "close" command
if [ "$1" = "close" ] && [ -n "$2" ]; then
    close_deployment "$2"
    exit 0
fi

main
