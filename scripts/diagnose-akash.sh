#!/bin/bash
# ============================================================================
# Akash Marketplace Diagnostic Tool
# Checks what's actually available and working on Akash right now
# ============================================================================

WALLET_ADDRESS="akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp"
NODE_URL="https://rpc.akashnet.net:443"

echo "╔════════════════════════════════════════════════════════╗"
echo "║     Akash Marketplace Diagnostic Tool                 ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# Check 1: Network Connectivity
# ============================================================================
echo "[Check 1/6] Network connectivity to Akash RPC..."
if curl -s --max-time 5 "$NODE_URL/status" > /dev/null 2>&1; then
    echo "✓ Connected to Akash network"
else
    echo "✗ Cannot connect to Akash RPC"
    echo "  This might be a network issue"
    exit 1
fi
echo ""

# ============================================================================
# Check 2: Wallet Balance
# ============================================================================
echo "[Check 2/6] Checking wallet balance..."
BALANCE=$(akash query bank balances "$WALLET_ADDRESS" --node "$NODE_URL" 2>/dev/null | grep 'amount:' | head -1 | grep -o '[0-9]*')

if [[ -n "$BALANCE" ]]; then
    AKT_BALANCE=$(awk "BEGIN {printf \"%.2f\", $BALANCE/1000000}")
    echo "✓ Balance: $AKT_BALANCE AKT"
    
    if [[ $BALANCE -lt 5000000 ]]; then
        echo "⚠ Warning: Balance is low (need at least 5 AKT for deployment)"
    fi
else
    echo "✗ Could not check balance"
fi
echo ""

# ============================================================================
# Check 3: Active Providers
# ============================================================================
echo "[Check 3/6] Checking active providers on network..."
PROVIDER_COUNT=$(akash query provider list --node "$NODE_URL" 2>/dev/null | grep -c 'owner:')

echo "✓ Found $PROVIDER_COUNT providers on network"
echo ""

# ============================================================================
# Check 4: Current Market Activity
# ============================================================================
echo "[Check 4/6] Checking current marketplace activity..."

# Get recent deployments
RECENT_DEPLOYMENTS=$(akash query deployment list --node "$NODE_URL" 2>/dev/null | grep -c 'dseq:')
echo "  Active deployments on network: $RECENT_DEPLOYMENTS"

# Get open orders
OPEN_ORDERS=$(akash query market order list --node "$NODE_URL" 2>/dev/null | grep -c 'order_id:')
echo "  Open orders (waiting for bids): $OPEN_ORDERS"

# Get open bids
OPEN_BIDS=$(akash query market bid list --node "$NODE_URL" 2>/dev/null | grep -c 'bid_id:')
echo "  Open bids (providers bidding): $OPEN_BIDS"

# Get active leases
ACTIVE_LEASES=$(akash query market lease list --node "$NODE_URL" 2>/dev/null | grep 'state: active' | wc -l | tr -d ' ')
echo "  Active leases (running deployments): $ACTIVE_LEASES"
echo ""

# ============================================================================
# Check 5: Your Deployment History
# ============================================================================
echo "[Check 5/6] Checking your deployment history..."

YOUR_DEPLOYMENTS=$(akash query deployment list \
    --owner "$WALLET_ADDRESS" \
    --node "$NODE_URL" 2>/dev/null)

if echo "$YOUR_DEPLOYMENTS" | grep -q 'dseq:'; then
    echo "  Your active deployments:"
    echo "$YOUR_DEPLOYMENTS" | grep 'dseq:' | while read -r line; do
        DSEQ=$(echo "$line" | sed 's/.*dseq: "\([0-9]*\)".*/\1/')
        STATE=$(echo "$YOUR_DEPLOYMENTS" | grep -A 5 "dseq: \"$DSEQ\"" | grep 'state:' | head -1)
        echo "    DSEQ $DSEQ: $STATE"
    done
else
    echo "  No active deployments"
fi

YOUR_LEASES=$(akash query market lease list \
    --owner "$WALLET_ADDRESS" \
    --node "$NODE_URL" 2>/dev/null)

if echo "$YOUR_LEASES" | grep -q 'dseq:'; then
    echo "  Your leases:"
    echo "$YOUR_LEASES" | grep -E '(dseq:|state:|reason:)' | head -12
else
    echo "  No active leases"
fi
echo ""

# ============================================================================
# Check 6: GPU Availability (Sample Test)
# ============================================================================
echo "[Check 6/6] Testing GPU availability..."
echo "  Creating a minimal test deployment..."

# Create minimal test deployment manifest
cat > /tmp/test-deploy.yaml << 'EOF'
version: "2.0"
services:
  test:
    image: nginx:latest
    expose:
      - port: 80
        as: 80
        to:
          - global: true
profiles:
  compute:
    test:
      resources:
        cpu:
          units: 0.5
        memory:
          size: 512Mi
        storage:
          - size: 512Mi
  placement:
    akash:
      pricing:
        test:
          denom: uakt
          amount: 100
deployment:
  test:
    akash:
      profile: test
      count: 1
EOF

echo "  Testing basic deployment (no GPU)..."
TEST_OUTPUT=$(akash tx deployment create /tmp/test-deploy.yaml \
    --from trinity-wallet \
    --node "$NODE_URL" \
    --chain-id akashnet-2 \
    --gas-prices 0.025uakt \
    --gas auto \
    --gas-adjustment 1.5 \
    -y 2>&1)

if echo "$TEST_OUTPUT" | grep -q "code: 0"; then
    echo "✓ Test deployment created successfully"
    
    # Wait for DSEQ
    sleep 30
    TEST_DSEQ=$(akash query deployment list --owner "$WALLET_ADDRESS" --node "$NODE_URL" 2>/dev/null | grep 'dseq:' | head -1 | sed 's/.*dseq: "\([0-9]*\)".*/\1/')
    
    if [[ -n "$TEST_DSEQ" ]]; then
        echo "  Test DSEQ: $TEST_DSEQ"
        
        # Wait for bids
        echo "  Waiting 60s for bids..."
        sleep 60
        
        TEST_BIDS=$(akash query market bid list --owner "$WALLET_ADDRESS" --node "$NODE_URL" 2>/dev/null | grep -c "dseq: \"$TEST_DSEQ\"")
        
        if [[ $TEST_BIDS -gt 0 ]]; then
            echo "✓ Got $TEST_BIDS bid(s) for test deployment"
            echo "  ✓ Marketplace is working!"
        else
            echo "✗ No bids received for test deployment"
            echo "  ⚠ Marketplace might have issues"
        fi
        
        # Clean up
        echo "  Cleaning up test deployment..."
        akash tx deployment close --dseq "$TEST_DSEQ" --from trinity-wallet --node "$NODE_URL" --chain-id akashnet-2 -y &>/dev/null
    fi
else
    echo "✗ Test deployment failed"
    echo "  Error: $TEST_OUTPUT"
fi

rm -f /tmp/test-deploy.yaml
echo ""

# ============================================================================
# Summary and Recommendations
# ============================================================================
echo "╔════════════════════════════════════════════════════════╗"
echo "║                    DIAGNOSTIC SUMMARY                  ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

if [[ $BALANCE -lt 5000000 ]]; then
    echo "❌ BLOCKER: Insufficient balance"
    echo "   Action: Add more AKT to wallet"
    echo ""
fi

if [[ $ACTIVE_LEASES -eq 0 ]] && [[ $RECENT_DEPLOYMENTS -lt 100 ]]; then
    echo "⚠️  WARNING: Very low marketplace activity"
    echo "   This might indicate network issues"
    echo ""
fi

if [[ $OPEN_BIDS -lt 10 ]]; then
    echo "⚠️  WARNING: Very few open bids"
    echo "   Providers might not be actively bidding"
    echo ""
fi

echo "Recommendations:"
echo "1. If test deployment got bids → Marketplace works, issue is with GPU manifest"
echo "2. If no bids on test → Network-wide issue, try again later"
echo "3. Check Akash Discord/Status page for network issues"
echo "4. Try Akash Console (console.akash.network) for visual deployment"
echo ""

echo "Useful links:"
echo "  Akash Console: https://console.akash.network"
echo "  Akash Stats: https://stats.akash.network"
echo "  Provider Status: https://akashnet.net/providers"
echo "  Discord: https://discord.akash.network"
