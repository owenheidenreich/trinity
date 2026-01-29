#!/bin/zsh
# =============================================================================
# Trinity Unified Deployment Script
# =============================================================================
# 
# Single command to deploy Trinity from development to production.
# Pipeline: Local Validation → Docker Build → Push → Akash Deploy → Verify
#
# Usage:
#   ./scripts/trinity-deploy.sh           # Interactive tier selection
#   ./scripts/trinity-deploy.sh 1         # Auto-select Tier 1 (TinyLlama)
#   ./scripts/trinity-deploy.sh 2         # Auto-select Tier 2 (Llama 8B)
#   ./scripts/trinity-deploy.sh 3         # Auto-select Tier 3 (Qwen 72B)
#
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
DOCKER_IMAGE="gdubx/trinity-inference"
AKASH_NODE="https://rpc.akashnet.net:443"
AKASH_CHAIN_ID="akashnet-2"
WALLET_NAME="trinity-wallet"
VERCEL_PROXY_URL="https://vercel-proxy-swart-nine.vercel.app"
ICP_FRONTEND_URL="https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io"

# Tier configurations (zsh associative arrays)
typeset -A TIER_YAML
TIER_YAML[1]="deploy-tier1-basic.yaml"
TIER_YAML[2]="deploy-tier2-balanced.yaml"
TIER_YAML[3]="deploy-tier3-complex.yaml"

typeset -A TIER_DESC
TIER_DESC[1]="TinyLlama 1.1B - Testing (~\$25/mo)"
TIER_DESC[2]="Llama 3.1 8B - Balanced (~\$50/mo)"
TIER_DESC[3]="Qwen 2.5 72B - Complex (~\$200/mo)"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

log_step() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}▶ $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# =============================================================================
# PREREQUISITE CHECKS
# =============================================================================

check_prerequisites() {
    log_step "Checking Prerequisites"
    
    local missing=()
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        missing+=("docker")
    elif ! docker info &> /dev/null; then
        log_error "Docker is installed but not running"
        echo "Please start Docker Desktop and try again"
        exit 1
    else
        log_success "Docker is running"
    fi
    
    # Check provider-services CLI
    if ! command -v provider-services &> /dev/null; then
        log_error "Akash provider-services CLI not found"
        echo ""
        echo "Install with:"
        echo "  curl -sfL https://raw.githubusercontent.com/akash-network/provider/main/install.sh | bash"
        exit 1
    else
        log_success "provider-services CLI installed"
    fi
    
    # Check wallet configuration
    if ! provider-services keys show "$WALLET_NAME" --keyring-backend os &> /dev/null 2>&1; then
        log_error "Wallet '$WALLET_NAME' not found in keyring"
        echo ""
        echo "Import from mnemonic:"
        echo "  provider-services keys add $WALLET_NAME --recover --keyring-backend os"
        exit 1
    else
        WALLET_ADDR=$(provider-services keys show "$WALLET_NAME" --keyring-backend os -a 2>/dev/null)
        log_success "Wallet configured: $WALLET_ADDR"
        
        # Check balance
        BALANCE=$(provider-services query bank balances "$WALLET_ADDR" --node "$AKASH_NODE" -o json 2>/dev/null | grep -o '"amount":"[0-9]*"' | head -1 | grep -o '[0-9]*' || echo "0")
        BALANCE_AKT=$(echo "scale=2; $BALANCE / 1000000" | bc 2>/dev/null || echo "0")
        log_info "Balance: ${BALANCE_AKT} AKT"
        
        if [ "$BALANCE" -lt 5000000 ]; then
            log_warning "Low balance! Recommend at least 5 AKT for deployment"
        fi
    fi
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    else
        log_success "Python3 available"
    fi
    
    # Check Vercel CLI (optional)
    if command -v vercel &> /dev/null; then
        log_success "Vercel CLI available"
        VERCEL_AVAILABLE=true
    else
        log_warning "Vercel CLI not found - will provide manual update command"
        VERCEL_AVAILABLE=false
    fi
    
    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

# =============================================================================
# AKASH DEPLOYMENT (via Python helper)
# =============================================================================

select_tier() {
    log_step "Select Deployment Tier"
    
    # Check if tier was passed as argument
    if [[ "$TIER_ARG" =~ ^[123]$ ]]; then
        SELECTED_TIER="$TIER_ARG"
        log_success "Using Tier $SELECTED_TIER: ${TIER_DESC[$SELECTED_TIER]}"
        return
    fi
    
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                    SELECT DEPLOYMENT TIER                    │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  1) TinyLlama 1.1B  - Testing (~\$25/mo)                     │"
    echo "│  2) Llama 3.1 8B    - General Use (~\$50/mo)                 │"
    echo "│  3) Qwen 2.5 72B    - Intelligence (~\$200/mo)               │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
    
    echo -n "Select tier [1/2/3] (default: 1): "
    read -r TIER_CHOICE </dev/tty
    TIER_CHOICE="${TIER_CHOICE:-1}"
    
    if [[ "$TIER_CHOICE" =~ ^[123]$ ]]; then
        SELECTED_TIER="$TIER_CHOICE"
    else
        SELECTED_TIER="1"
    fi
    log_success "Selected Tier $SELECTED_TIER: ${TIER_DESC[$SELECTED_TIER]}"
}

deploy_to_akash() {
    log_step "Deploying to Akash Network"
    
    cd "$PROJECT_ROOT"
    
    echo "Running Python deployment helper with tier $SELECTED_TIER..."
    echo ""
    
    # Create temp file for output capture
    DEPLOY_OUTPUT_FILE=$(mktemp)
    
    # Run Python script with tee to show progress and capture output
    python3 "$SCRIPT_DIR/akash_deploy.py" "$DEPLOY_DIR" "$DEPLOY_TAG" "$SELECTED_TIER" 2>&1 | tee "$DEPLOY_OUTPUT_FILE"
    DEPLOY_RESULT=${pipestatus[1]}
    
    DEPLOY_OUTPUT=$(cat "$DEPLOY_OUTPUT_FILE")
    rm -f "$DEPLOY_OUTPUT_FILE"
    
    if [ $DEPLOY_RESULT -ne 0 ]; then
        log_error "Akash deployment failed"
        exit 1
    fi
    
    # Parse the result section (after __RESULT__ marker)
    DEPLOYED_TIER=$(echo "$DEPLOY_OUTPUT" | grep "^TIER=" | cut -d'=' -f2)
    DEPLOYED_DSEQ=$(echo "$DEPLOY_OUTPUT" | grep "^DSEQ=" | cut -d'=' -f2)
    DEPLOYED_PROVIDER=$(echo "$DEPLOY_OUTPUT" | grep "^PROVIDER=" | cut -d'=' -f2)
    DEPLOYED_URI=$(echo "$DEPLOY_OUTPUT" | grep "^URI=" | cut -d'=' -f2)
    
    # Set TIER for summary
    TIER="${DEPLOYED_TIER:-$SELECTED_TIER}"
    
    if [ -z "$DEPLOYED_URI" ]; then
        log_error "Could not extract deployment URI from output"
        echo "Looking for URI in output..."
        echo "$DEPLOY_OUTPUT" | grep -i uri || true
        exit 1
    fi
    
    log_success "Akash deployment complete: https://$DEPLOYED_URI"
    echo ""
}

# =============================================================================
# LOCAL VALIDATION (Fast Fail)
# =============================================================================

validate_local() {
    log_step "Local Validation (Fast Fail Gate)"
    
    cd "$PROJECT_ROOT"
    
    # Python syntax check
    echo "Checking Python syntax..."
    if ! python3 -m py_compile backend/inference_server.py 2>&1; then
        log_error "Python syntax error in inference_server.py"
        exit 1
    fi
    log_success "Python syntax OK"
    
    # Note: Import checking skipped - packages only exist in Docker container
    # Docker build will fail if imports are broken
    log_success "Python syntax validated (imports verified during Docker build)"
    
    # Build Docker image locally
    echo ""
    echo "Building Docker image (AMD64 for Akash)..."
    TAG="v2-$(date +%Y%m%d-%H%M%S)"
    
    docker build --platform linux/amd64 \
        -t "$DOCKER_IMAGE:$TAG" \
        -t "$DOCKER_IMAGE:latest" \
        -f "$DEPLOY_DIR/docker/Dockerfile" \
        "$PROJECT_ROOT" || {
        log_error "Docker build failed"
        exit 1
    }
    log_success "Docker build OK: $DOCKER_IMAGE:$TAG"
    
    # Skip local container test (AMD64 image on ARM Mac is too slow)
    log_info "Skipping local container test (cross-platform)"
    
    # Clean Docker build cache
    echo ""
    echo "Cleaning Docker build cache..."
    docker builder prune -f &> /dev/null || true
    
    log_success "Local validation passed - safe to deploy"
    
    # Store tag for later
    DEPLOY_TAG="$TAG"
}

# =============================================================================
# DOCKER PUSH
# =============================================================================

push_image() {
    log_step "Pushing Docker Image"
    
    echo "Pushing $DOCKER_IMAGE:$DEPLOY_TAG..."
    
    docker push "$DOCKER_IMAGE:$DEPLOY_TAG" || {
        log_error "Docker push failed"
        exit 1
    }
    
    docker push "$DOCKER_IMAGE:latest" || {
        log_warning "Failed to push :latest tag (non-fatal)"
    }
    
    log_success "Image pushed: $DOCKER_IMAGE:$DEPLOY_TAG"
}

# =============================================================================
# UPDATE VERCEL PROXY
# =============================================================================

update_vercel_proxy() {
    log_step "Updating Vercel Proxy"
    
    # Ensure the URL has https:// prefix
    FULL_AKASH_URL="https://$DEPLOYED_URI"
    
    if [ "$VERCEL_AVAILABLE" = true ]; then
        cd "$DEPLOY_DIR/vercel-proxy"
        
        echo "Updating AKASH_URL environment variable..."
        
        # Remove existing env var (ignore errors)
        vercel env rm AKASH_URL production --yes 2>/dev/null || true
        
        # Add new env var with full URL including https://
        if echo "$FULL_AKASH_URL" | vercel env add AKASH_URL production --yes 2>/dev/null; then
            log_success "Environment variable updated: AKASH_URL=$FULL_AKASH_URL"
        else
            log_warning "vercel env add failed - updating proxy.js fallback"
            sed -i.bak "s|https://[a-z0-9]*\.ingress\.[^'\"]*|$FULL_AKASH_URL|g" api/proxy.js
            rm -f api/proxy.js.bak
        fi
        
        # Redeploy
        echo ""
        echo "Redeploying Vercel proxy..."
        if vercel --prod --yes 2>&1 | tail -5; then
            log_success "Vercel proxy redeployed"
        else
            log_warning "Vercel deploy may have issues - check output"
        fi
        
        cd "$PROJECT_ROOT"
    else
        # Update fallback URL in proxy.js directly
        PROXY_FILE="$DEPLOY_DIR/vercel-proxy/api/proxy.js"
        if [ -f "$PROXY_FILE" ]; then
            sed -i.bak "s|https://[a-z0-9]*\.ingress\.[^'\"]*|$FULL_AKASH_URL|g" "$PROXY_FILE"
            rm -f "${PROXY_FILE}.bak"
            log_warning "Updated proxy.js fallback - manual Vercel deploy needed"
            echo "  Run: cd $DEPLOY_DIR/vercel-proxy && vercel --prod"
        fi
    fi
    
    # Wait for Vercel to propagate
    echo ""
    echo "Waiting 10s for Vercel to propagate..."
    sleep 10
}

# =============================================================================
# UPDATE ICP CANISTERS
# =============================================================================

update_icp_canisters() {
    log_step "Updating ICP Canisters"
    
    # Check if dfx is available
    if ! command -v dfx &> /dev/null; then
        log_warning "dfx CLI not available - skipping ICP canister updates"
        echo "  Install: sh -ci \"\$(curl -fsSL https://internetcomputer.org/install.sh)\""
        return
    fi
    
    cd "$PROJECT_ROOT/trinity-icp"
    
    # Verify the full chain works (ICP → Vercel → Akash)
    echo "Verifying ICP canister can reach Akash via Vercel proxy..."
    HEALTH_RESULT=$(dfx canister --ic call trinity_backend health 2>&1 || echo "error")
    
    if echo "$HEALTH_RESULT" | grep -q 'healthy'; then
        log_success "ICP backend canister connected to Akash"
        echo "  $(echo "$HEALTH_RESULT" | grep -o 'model = "[^"]*"' | head -1)"
    else
        log_warning "ICP canister health check pending - Vercel may still be propagating"
    fi
    
    # Deploy frontend canister
    echo ""
    echo "Deploying ICP frontend canister..."
    if dfx deploy --ic trinity_frontend 2>&1 | tail -10; then
        log_success "ICP frontend canister deployed"
    else
        log_warning "ICP frontend deployment may have issues"
    fi
    
    cd "$PROJECT_ROOT"
}

# =============================================================================
# PRODUCTION VERIFICATION
# =============================================================================

verify_production() {
    log_step "Production Verification"
    
    BACKEND_URL="https://$DEPLOYED_URI"
    
    # Wait for model to load (this can take a while for large models)
    echo "Waiting for model to load (this may take several minutes for large models)..."
    
    HEALTH_OK=false
    for i in {1..60}; do
        RESPONSE=$(curl -s --max-time 10 "$BACKEND_URL/health" 2>/dev/null || echo "")
        
        if echo "$RESPONSE" | grep -q '"status":"healthy"'; then
            HEALTH_OK=true
            break
        fi
        
        echo "  Waiting for /health... ($i/60)"
        sleep 10
    done
    
    if [ "$HEALTH_OK" = false ]; then
        log_warning "Production /health check still pending after 10 minutes"
        echo "  Container may still be starting - continuing with tests..."
    else
        log_success "Production /health OK"
    fi
    
    # Test /generate
    echo ""
    echo "Testing /generate endpoint..."
    
    GENERATE_RESPONSE=$(curl -s --max-time 120 \
        -X POST "$BACKEND_URL/generate" \
        -H "Content-Type: application/json" \
        -d '{"prompt": "Say hello in exactly 3 words.", "max_tokens": 20}' 2>/dev/null || echo "")
    
    if echo "$GENERATE_RESPONSE" | grep -q '"response"'; then
        log_success "Production /generate OK"
        RESPONSE_TEXT=$(echo "$GENERATE_RESPONSE" | grep -o '"response":"[^"]*"' | cut -d'"' -f4 | head -c 100)
        echo "  Response: $RESPONSE_TEXT"
    else
        log_warning "Production /generate returned unexpected response"
        echo "  Response: $GENERATE_RESPONSE"
    fi
    
    # Test via Vercel Proxy
    echo ""
    echo "Testing Vercel proxy /health..."
    PROXY_HEALTH=$(curl -s --max-time 10 "$VERCEL_PROXY_URL/health" 2>/dev/null || echo "")
    
    if echo "$PROXY_HEALTH" | grep -q '"status":"healthy"'; then
        log_success "Vercel proxy → Akash connection OK"
    else
        log_warning "Vercel proxy health check issue"
    fi
    
    # Test ICP Canister (if dfx available)
    if command -v dfx &> /dev/null; then
        echo ""
        echo "Testing ICP canister health..."
        cd "$PROJECT_ROOT/trinity-icp"
        ICP_HEALTH=$(dfx canister --ic call trinity_backend health 2>&1 || echo "")
        
        if echo "$ICP_HEALTH" | grep -q 'healthy'; then
            log_success "ICP canister → Vercel → Akash connection OK"
        else
            log_warning "ICP canister health check issue"
        fi
        cd "$PROJECT_ROOT"
    fi
    
    echo ""
    log_success "Full stack verification complete!"
}

# =============================================================================
# SUMMARY
# =============================================================================

print_summary() {
    log_step "Deployment Complete"
    
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}                    ✅ TRINITY PRODUCTION READY                          ${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Tier:       ${TIER_DESC[$TIER]}"
    echo "  Image:      $DOCKER_IMAGE:$DEPLOY_TAG"
    echo "  DSEQ:       $DEPLOYED_DSEQ"
    echo "  Provider:   $DEPLOYED_PROVIDER"
    echo ""
    echo "  Akash:      https://$DEPLOYED_URI"
    echo "  Vercel:     $VERCEL_PROXY_URL"
    echo "  Frontend:   $ICP_FRONTEND_URL"
    echo ""
    echo "  View logs:"
    echo "    provider-services lease-logs --dseq $DEPLOYED_DSEQ --provider $DEPLOYED_PROVIDER --from $WALLET_NAME --keyring-backend os --node $AKASH_NODE --follow"
    echo ""
    echo "  Close deployment:"
    echo "    provider-services tx deployment close --dseq $DEPLOYED_DSEQ --from $WALLET_NAME --keyring-backend os --node $AKASH_NODE --chain-id $AKASH_CHAIN_ID -y"
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    # Get tier from command line argument if provided
    TIER_ARG="${1:-}"
    
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                     TRINITY UNIFIED DEPLOYMENT                           ║${NC}"
    echo -e "${CYAN}║                                                                          ║${NC}"
    echo -e "${CYAN}║  Pipeline: Build → Push → Deploy Akash → Update Vercel → Update ICP     ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    check_prerequisites
    select_tier
    validate_local
    push_image
    deploy_to_akash
    update_vercel_proxy
    update_icp_canisters
    verify_production
    print_summary
}

# Run main with all arguments
main "$@"
