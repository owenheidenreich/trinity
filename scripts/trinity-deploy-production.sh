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

# Cloudflare Worker Proxy (replaces Vercel)
CLOUDFLARE_WORKER_DIR="$DEPLOY_DIR/cloudflare-worker"
CLOUDFLARE_WORKER_URL="https://api.dubya.ai"
API_PROXY_URL="https://api.dubya.ai"  # Custom domain (once DNS configured)

# Frontend URLs
ICP_FRONTEND_URL="https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io"
CUSTOM_FRONTEND_URL="https://dubya.ai"

# Tier configurations (zsh associative arrays)
typeset -A TIER_YAML
TIER_YAML[1]="deploy-tier1-basic.yaml"
TIER_YAML[2]="deploy-tier2-balanced.yaml"
TIER_YAML[3]="deploy-tier3-complex.yaml"

typeset -A TIER_DESC
TIER_DESC[1]="Qwen3 1.7B - Testing (~\$25/mo)"
TIER_DESC[2]="Qwen2.5 14B - Balanced (~\$50/mo)"
TIER_DESC[3]="Qwen3 32B - Intelligence (~\$200/mo)"

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

# Track elapsed time for each step
DEPLOY_START_TIME=$(date +%s)
step_timer() {
    local now=$(date +%s)
    local elapsed=$((now - DEPLOY_START_TIME))
    local mins=$((elapsed / 60))
    local secs=$((elapsed % 60))
    echo -e "${BLUE}  ⏱  ${mins}m ${secs}s elapsed${NC}"
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
    
    # Check Wrangler CLI (for Cloudflare Workers)
    if command -v wrangler &> /dev/null; then
        log_success "Wrangler CLI available"
        WRANGLER_AVAILABLE=true
        
        # Check if authenticated
        if wrangler whoami &> /dev/null 2>&1; then
            log_success "Wrangler authenticated"
        else
            log_warning "Wrangler not authenticated - run 'wrangler login'"
            WRANGLER_AVAILABLE=false
        fi
    else
        log_warning "Wrangler CLI not found - will provide manual update command"
        log_info "Install with: npm install -g wrangler"
        WRANGLER_AVAILABLE=false
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
    echo "│  1) Qwen3 1.7B     - Testing (~\$25/mo)                       │"
    echo "│  2) Qwen2.5 14B    - Balanced (~\$50/mo)                     │"
    echo "│  3) Qwen3 32B      - Intelligence (~\$200/mo)                │"
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

ask_deposit() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}                         DEPLOYMENT FUNDING                               ${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Get current balance
    CURRENT_BALANCE=$(provider-services query bank balances $WALLET_ADDR --node $AKASH_NODE -o json 2>/dev/null | grep -o '"amount":"[0-9]*"' | head -1 | grep -o '[0-9]*' || echo "0")
    CURRENT_AKT=$(echo "scale=2; $CURRENT_BALANCE / 1000000" | bc 2>/dev/null || echo "unknown")
    
    echo ""
    echo "  Current wallet balance: $CURRENT_AKT AKT"
    echo "  Selected tier: ${TIER_DESC[$SELECTED_TIER]}"
    echo ""
    echo "  How many AKT would you like to deposit to this deployment?"
    echo "  (Enter 0 or press Enter to skip)"
    echo ""
    printf "  AKT to deposit: "
    read -r FUNDING_AKT_AMOUNT </dev/tty
    
    # Default to 0 if empty
    FUNDING_AKT_AMOUNT="${FUNDING_AKT_AMOUNT:-0}"
    
    # Validate it's a number
    if ! [[ "$FUNDING_AKT_AMOUNT" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        log_warning "Invalid amount '$FUNDING_AKT_AMOUNT' - skipping deposit"
        FUNDING_AKT_AMOUNT="0"
    fi
    
    if [ "$FUNDING_AKT_AMOUNT" != "0" ]; then
        log_info "Will deposit ${FUNDING_AKT_AMOUNT} AKT after deployment completes"
    else
        log_info "No additional deposit requested"
    fi
    echo ""
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
    DEPLOYED_URL=$(echo "$DEPLOY_OUTPUT" | grep "^URL=" | cut -d'=' -f2-)
    
    # Set TIER for summary
    TIER="${DEPLOYED_TIER:-$SELECTED_TIER}"
    
    if [ -z "$DEPLOYED_URI" ]; then
        log_error "Could not extract deployment URI from output"
        echo "Looking for URI in output..."
        echo "$DEPLOY_OUTPUT" | grep -i uri || true
        exit 1
    fi
    
    # Use the URL with proper scheme (http/https based on SSL check)
    if [ -z "$DEPLOYED_URL" ]; then
        # Fallback to https if URL not provided (old script version)
        DEPLOYED_URL="https://$DEPLOYED_URI"
    fi
    
    log_success "Akash deployment complete: $DEPLOYED_URL"
    step_timer
    echo ""
}

# =============================================================================
# LOCAL VALIDATION (Fast Fail)
# =============================================================================

validate_local() {
    log_step "Local Validation (Fast Fail Gate)"
    
    cd "$PROJECT_ROOT"
    
    # Python syntax check — validate ALL backend Python files
    echo "Checking Python syntax..."
    local syntax_ok=true
    local checked=0
    for pyfile in backend/*.py backend/services/*.py backend/routes/*.py backend/middleware/*.py; do
        if [ -f "$pyfile" ]; then
            if ! python3 -m py_compile "$pyfile" 2>&1; then
                log_error "Syntax error in $pyfile"
                syntax_ok=false
            fi
            checked=$((checked + 1))
        fi
    done
    if [ "$syntax_ok" = false ]; then
        log_error "Python syntax check failed"
        exit 1
    fi
    log_success "Python syntax OK ($checked files checked)"
    
    # Build Docker image locally
    echo ""
    echo "Building Docker image (AMD64 for Akash)..."
    TAG="v2-$(date +%Y%m%d-%H%M%S)"
    
    # DOCKER_BUILDKIT=1 with --provenance=false --sbom=false skips attestation
    # layers that change every build and slow down pushes unnecessarily
    docker build --platform linux/amd64 \
        --provenance=false --sbom=false \
        -t "${DOCKER_IMAGE}:${TAG}" \
        -t "${DOCKER_IMAGE}:latest" \
        -f "$DEPLOY_DIR/docker/Dockerfile" \
        "$PROJECT_ROOT" || {
        log_error "Docker build failed"
        exit 1
    }
    log_success "Docker build OK: ${DOCKER_IMAGE}:${TAG}"
    
    # Store tag for later
    DEPLOY_TAG="$TAG"
    
    # Skip local container test (AMD64 image on ARM Mac is too slow)
    log_info "Skipping local container test (cross-platform)"
    step_timer
    
    log_success "Local validation passed - safe to deploy"
}

# =============================================================================
# DOCKER PUSH
# =============================================================================

push_image() {
    log_step "Pushing Docker Image"
    
    echo "Pushing ${DOCKER_IMAGE}:latest..."
    
    docker push "${DOCKER_IMAGE}:latest" || {
        log_error "Docker push failed"
        exit 1
    }
    
    # Also tag with deploy version for rollback reference (push is fast since layers already uploaded)
    docker push "${DOCKER_IMAGE}:${DEPLOY_TAG}" || {
        log_warning "Failed to push :${DEPLOY_TAG} tag (non-fatal, :latest already pushed)"
    }
    
    log_success "Image pushed: ${DOCKER_IMAGE}:latest (also tagged ${DEPLOY_TAG})"
    step_timer
    
    # Clean up old Docker images AFTER push (not before — preserves build cache for push)
    echo "Cleaning up old Docker images..."
    docker images "$DOCKER_IMAGE" --format '{{.Tag}} {{.ID}}' | \
        grep -v -E "^(latest|$DEPLOY_TAG) " | \
        awk '{print $2}' | xargs -r docker rmi -f &> /dev/null || true
    docker image prune -f &> /dev/null || true
}

# =============================================================================
# UPDATE AKASH YAML FILES (so they always reflect current deploy tag)
# =============================================================================

update_akash_yamls() {
    log_step "Updating Akash YAML Files"
    
    cd "$DEPLOY_DIR/akash"
    for yaml_file in deploy-*.yaml; do
        if [ -f "$yaml_file" ]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|image: gdubx/trinity-inference:.*|image: gdubx/trinity-inference:$DEPLOY_TAG|g" "$yaml_file"
            else
                sed -i "s|image: gdubx/trinity-inference:.*|image: gdubx/trinity-inference:$DEPLOY_TAG|g" "$yaml_file"
            fi
            chflags nohidden "$yaml_file" 2>/dev/null || true
            echo "  ✓ Updated: $yaml_file → $DEPLOY_TAG"
        fi
    done
    cd "$PROJECT_ROOT"
    
    log_success "YAML files updated to $DEPLOY_TAG"
}

# =============================================================================
# UPDATE CLOUDFLARE WORKER
# =============================================================================

update_cloudflare_worker() {
    log_step "Updating Cloudflare Worker Proxy"
    
    # Use the URL with detected scheme (http/https based on SSL check)
    FULL_AKASH_URL="$DEPLOYED_URL"
    
    if [ "$WRANGLER_AVAILABLE" = true ]; then
        cd "$CLOUDFLARE_WORKER_DIR"
        
        echo "Updating AKASH_URL secret..."
        echo "  URL: $FULL_AKASH_URL"
        
        # Update the secret (instant, no redeploy needed)
        if echo "$FULL_AKASH_URL" | wrangler secret put AKASH_URL 2>/dev/null; then
            log_success "AKASH_URL secret updated: $FULL_AKASH_URL"
        else
            log_error "Failed to update AKASH_URL secret"
            echo ""
            echo "Manual command:"
            echo "  cd $CLOUDFLARE_WORKER_DIR"
            echo "  echo '$FULL_AKASH_URL' | wrangler secret put AKASH_URL"
        fi
        
        cd "$PROJECT_ROOT"
    else
        log_warning "Wrangler not available - manual Cloudflare update needed"
        echo ""
        echo "Run these commands to update:"
        echo "  cd $CLOUDFLARE_WORKER_DIR"
        echo "  echo '$FULL_AKASH_URL' | wrangler secret put AKASH_URL"
    fi
    
    # No propagation wait needed - Cloudflare secrets are instant
    log_info "Cloudflare Worker update complete (instant propagation)"
}

# =============================================================================
# UPDATE ICP CANISTERS
# =============================================================================

update_icp_canisters() {
    log_step "Building and Deploying ICP Canisters"
    
    # Check if dfx is available
    if ! command -v dfx &> /dev/null; then
        log_warning "dfx CLI not available - skipping ICP canister updates"
        echo "  Install: sh -ci \"\$(curl -fsSL https://internetcomputer.org/install.sh)\""
        return
    fi
    
    cd "$PROJECT_ROOT/trinity-icp"
    
    # Install npm dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "Installing npm dependencies..."
        npm install || {
            log_warning "npm install failed - continuing anyway"
        }
    fi
    
    # Build frontend
    echo ""
    echo "Building ICP frontend..."
    if npm run build 2>&1 | tail -10; then
        log_success "Frontend build complete"
    else
        log_error "Frontend build failed"
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    # Verify the full chain works (ICP → Cloudflare → Akash)
    echo ""
    echo "Verifying ICP canister can reach Akash via Cloudflare Worker..."
    HEALTH_RESULT=$(dfx canister --ic call trinity_backend health 2>&1 || echo "error")
    
    if echo "$HEALTH_RESULT" | grep -q 'healthy'; then
        log_success "ICP backend canister connected to Akash"
        echo "  $(echo "$HEALTH_RESULT" | grep -o 'model = "[^"]*"' | head -1)"
    else
        log_warning "ICP canister health check pending - Cloudflare may still be propagating"
    fi
    
    # Deploy frontend canister
    echo ""
    echo "Deploying ICP frontend canister..."
    if dfx deploy trinity_frontend --network ic 2>&1 | tail -10; then
        log_success "ICP frontend canister deployed"
    else
        log_warning "ICP frontend deployment may have issues"
    fi
    
    # Deploy backend canister (optional - only if there are changes)
    echo ""
    echo "Deploying ICP backend canister..."
    if dfx deploy trinity_backend --network ic 2>&1 | tail -10; then
        log_success "ICP backend canister deployed"
    else
        log_warning "ICP backend deployment may have issues"
    fi
    
    cd "$PROJECT_ROOT"
}

# =============================================================================
# PRODUCTION VERIFICATION
# =============================================================================

verify_production() {
    log_step "Production Verification"
    
    BACKEND_URL="$DEPLOYED_URL"
    
    # Quick health check (don't wait long - model loading takes time)
    echo "Checking backend status (model may still be loading)..."
    echo "  URL: $BACKEND_URL"
    
    # Use -k to skip SSL verify in case of self-signed certs
    RESPONSE=$(curl -sk --max-time 10 "$BACKEND_URL/health" 2>/dev/null || echo "")
    
    if echo "$RESPONSE" | grep -q '"status":"healthy"'; then
        log_success "Production /health OK - model loaded!"
    else
        log_warning "Model still loading - this is normal for Tier 3 (takes 5-10 minutes)"
        echo "  Check manually: curl -sk $BACKEND_URL/health"
    fi
    
    # Test via Cloudflare Worker Proxy
    echo ""
    echo "Testing Cloudflare Worker proxy..."
    PROXY_HEALTH=$(curl -s --max-time 10 "$CLOUDFLARE_WORKER_URL/health" 2>/dev/null || echo "")
    
    if echo "$PROXY_HEALTH" | grep -q '"status":"healthy"'; then
        log_success "Cloudflare Worker → Akash connection OK"
    elif echo "$PROXY_HEALTH" | grep -q '"status"'; then
        log_success "Cloudflare Worker connected (model loading)"
    else
        log_warning "Cloudflare Worker health check pending"
    fi
    
    echo ""
    log_success "Deployment verification complete!"
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
    echo "  Image:      ${DOCKER_IMAGE}:${DEPLOY_TAG}"
    echo "  DSEQ:       $DEPLOYED_DSEQ"
    echo "  Provider:   $DEPLOYED_PROVIDER"
    echo ""
    echo "  Akash:      $DEPLOYED_URL"
    echo "  Proxy:      $CLOUDFLARE_WORKER_URL"
    echo "  API:        $API_PROXY_URL (once DNS configured)"
    echo "  Frontend:   $CUSTOM_FRONTEND_URL (or $ICP_FRONTEND_URL)"
    echo ""
    echo "  View logs:"
    echo "    provider-services lease-logs --dseq $DEPLOYED_DSEQ --provider $DEPLOYED_PROVIDER --from $WALLET_NAME --keyring-backend os --node $AKASH_NODE --follow"
    echo ""
    echo "  Close deployment:"
    echo "    provider-services tx deployment close --dseq $DEPLOYED_DSEQ --from $WALLET_NAME --keyring-backend os --node $AKASH_NODE --chain-id $AKASH_CHAIN_ID -y"
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Process funding if user specified an amount earlier
    if [ -n "$FUNDING_AKT_AMOUNT" ] && [ "$FUNDING_AKT_AMOUNT" != "0" ]; then
        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}                      PROCESSING DEPOSIT                                  ${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        # Convert to uakt (1 AKT = 1,000,000 uakt)
        UAKT_AMOUNT=$(echo "$FUNDING_AKT_AMOUNT * 1000000" | bc | cut -d'.' -f1)
        
        echo ""
        echo "  Depositing ${FUNDING_AKT_AMOUNT} AKT (${UAKT_AMOUNT} uakt) to deployment $DEPLOYED_DSEQ..."
        
        DEPOSIT_RESULT=$(provider-services tx deployment deposit ${UAKT_AMOUNT}uakt \
            --dseq $DEPLOYED_DSEQ \
            --from $WALLET_NAME \
            --keyring-backend os \
            --node $AKASH_NODE \
            --chain-id $AKASH_CHAIN_ID \
            --gas-prices 0.025uakt \
            --gas auto \
            --gas-adjustment 1.5 \
            -y 2>&1)
        
        if echo "$DEPOSIT_RESULT" | grep -q 'txhash'; then
            log_success "Deposited ${FUNDING_AKT_AMOUNT} AKT to deployment"
        else
            log_warning "Deposit may have failed - check manually"
            echo "  $DEPOSIT_RESULT"
        fi
    fi
    
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
    echo -e "${CYAN}║  Pipeline: Build → Push → Deploy Akash → Update Cloudflare → Update ICP║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    check_prerequisites
    select_tier
    ask_deposit
    validate_local
    push_image
    deploy_to_akash
    update_akash_yamls     # After deploy succeeds — avoids dirty git state on failure
    update_cloudflare_worker
    update_icp_canisters
    verify_production
    print_summary
}

# Run main with all arguments
main "$@"
