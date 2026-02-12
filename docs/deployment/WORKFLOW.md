# Trinity Deployment Workflow

> **Last Updated:** February 10, 2026  
> **Scripts:** [scripts/](../../scripts/)  
> **Configs:** [deploy/](../../deploy/)

---

## Overview

Trinity deploys to a fully decentralized stack:

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEPLOYMENT PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│  Local Code  →  Docker Build  →  Docker Hub  →  Akash Deploy   │
│                                                                  │
│  Frontend: ICP Canister (dfx deploy)                            │
│  Backend:  Akash + Cloudflare Worker (SSL proxy)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### One-Command Deploy

```bash
# Interactive tier selection
./scripts/trinity-deploy-production.sh

# Auto-select specific tier
./scripts/trinity-deploy-production.sh 2   # Tier 2 (Qwen 14B, ~$180/mo)
```

This script handles everything:
1. ✅ Check prerequisites (Docker, Akash CLI, etc.)
2. ✅ Run Python syntax validation
3. ✅ Build Docker image (linux/amd64)
4. ✅ Push to Docker Hub
5. ✅ Deploy to Akash Network
6. ✅ Update Cloudflare Worker URL
7. ✅ Deploy ICP frontend
8. ✅ Verify health endpoint

---

## Deployment Tiers

| Tier | Model | GPU | Monthly Cost | Use Case |
|------|-------|-----|--------------|----------|
| 1 | TinyLlama 1.1B | Any NVIDIA | ~$65 | Development/Testing |
| 2 | Qwen 2.5 14B | P40/RTX 3090 | ~$180 | **Production (recommended)** |
| 3 | Qwen 2.5 72B | A100 80GB | ~$2,800 | Premium/Enterprise |

**Current Production:** Tier 2 (qwen2.5:14b)

---

## Component Deployment

### 1. Backend (Akash)

**Files:**
```
deploy/
├── docker/
│   ├── Dockerfile           # Multi-stage build
│   └── startup.sh           # Model download, server start
└── akash/
    ├── deploy-tier1-basic.yaml
    ├── deploy-tier2-balanced.yaml
    ├── deploy-tier3-complex.yaml
    └── kings/               # Large model configs
```

**Manual Deploy Steps:**

```bash
# 1. Build Docker image
docker build --platform linux/amd64 \
  -t gdubx/trinity-inference:$(date +%Y%m%d-%H%M%S) \
  -f deploy/docker/Dockerfile .

# 2. Push to Docker Hub
docker push gdubx/trinity-inference:TAG

# 3. Update YAML with new image tag
# Edit deploy/akash/deploy-tier2-balanced.yaml

# 4. Deploy to Akash
provider-services tx deployment create deploy/akash/deploy-tier2-balanced.yaml \
  --from trinity-wallet \
  --node https://rpc.akashnet.net:443 \
  --chain-id akashnet-2 \
  --gas-prices 0.025uakt \
  --gas auto \
  --gas-adjustment 1.5

# 5. Accept bid
provider-services tx market lease create \
  --dseq DSEQ --gseq 1 --oseq 1 \
  --provider PROVIDER_ADDRESS \
  --from trinity-wallet

# 6. Send manifest
provider-services send-manifest deploy/akash/deploy-tier2-balanced.yaml \
  --dseq DSEQ --provider PROVIDER_ADDRESS \
  --from trinity-wallet
```

**Get Lease URL:**
```bash
provider-services query market lease list \
  --owner $(provider-services keys show trinity-wallet -a)
```

---

### 2. SSL Proxy (Cloudflare Worker)

**Location:** [deploy/cloudflare-worker/](../../deploy/cloudflare-worker/)

**Purpose:** SSL termination for Akash backend (Akash only provides HTTP)

**Deploy:**
```bash
cd deploy/cloudflare-worker
wrangler deploy
```

**Update Backend URL:**
```bash
# Edit wrangler.toml
[vars]
BACKEND_URL = "http://NEW_AKASH_URL:8000"

# Or use script
./scripts/switch-provider.sh http://NEW_AKASH_URL:8000
```

**Custom Domain:** `api.dubya.ai` → Cloudflare Worker → Akash Backend

---

### 3. Frontend (ICP)

**Location:** [trinity-icp/](../../trinity-icp/)

**Deploy:**
```bash
cd trinity-icp
dfx deploy --network ic
```

**Canister IDs:**
- Frontend: `au5zq-2qaaa-aaaal-qtowa-cai`
- Backend: (disabled)

**Custom Domain:** `dubya.ai` → ICP Canister

---

## Environment Variables

### Backend (set in Akash YAML)

```yaml
env:
  - name: MODEL_NAME
    value: "qwen2.5:14b"
  - name: OLLAMA_HOST
    value: "http://localhost:11434"
  - name: DEPLOYMENT_TIER
    value: "2"
  - name: BRAVE_SEARCH_API_KEY
    value: "BSA..."
  - name: LIGHTHOUSE_API_KEY
    value: "..."
  - name: AUTH_TIMESTAMP_WINDOW
    value: "60"
```

### Cloudflare Worker (set in wrangler.toml)

```toml
[vars]
BACKEND_URL = "http://akash-provider-url:8000"
```

---

## Verification

### Health Check

```bash
# Backend
curl https://api.dubya.ai/health

# Expected response:
{
  "status": "healthy",
  "version": "4.0.2",
  "model": "qwen2.5:14b",
  "tier": 2
}
```

### Inference Test

```bash
curl -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, how are you?"}'
```

### Frontend

- Production: https://dubya.ai
- ICP direct: https://au5zq-2qaaa-aaaal-qtowa-cai.icp0.io

---

## Troubleshooting

### Cold Start (20-30 seconds)

**Symptom:** First request after deployment times out or takes 30+ seconds.

**Cause:** Ollama loading model into GPU memory.

**Solution:** This is expected. Subsequent requests are fast (1-10 seconds).

---

### Bid Not Accepted

**Symptom:** `provider-services tx market lease create` fails.

**Cause:** Bid expired or provider went offline.

**Solution:**
```bash
# List available bids
provider-services query market bid list --dseq DSEQ

# Accept a different provider
provider-services tx market lease create --provider DIFFERENT_PROVIDER
```

---

### Container Crash Loop

**Symptom:** Deployment keeps restarting.

**Diagnosis:**
```bash
# Check logs
provider-services lease-logs --dseq DSEQ --provider PROVIDER
```

**Common Causes:**
1. Out of memory — model too large for GPU
2. Missing environment variable
3. Docker image pull failure

---

### CORS Errors

**Symptom:** Frontend can't reach backend.

**Check:** Cloudflare Worker CORS headers in [worker.js](../../deploy/cloudflare-worker/worker.js)

**Fix:** Ensure origin is in allowed list:
```javascript
const ALLOWED_ORIGINS = [
  'https://dubya.ai',
  'https://au5zq-2qaaa-aaaal-qtowa-cai.icp0.io',
  'http://localhost:5173'
];
```

---

### Akash Provider Offline

**Symptom:** Backend becomes unreachable.

**Solution:**
1. Check provider status: `provider-services query provider list`
2. Close old lease: `provider-services tx market lease close --dseq DSEQ`
3. Create new deployment with different provider
4. Update Cloudflare Worker URL

---

## Monitoring

### Prometheus Metrics

**Endpoint:** `https://api.dubya.ai/metrics`

**Key Metrics:**
- `trinity_http_requests_total` — Request count
- `trinity_inference_duration_seconds` — Latency
- `trinity_errors_total` — Error count
- `trinity_tokens_generated_total` — Token usage

### Grafana Dashboard

**Location:** [deploy/grafana/](../../deploy/grafana/)

**Setup:**
```bash
# Start local Grafana
docker-compose -f deploy/grafana/docker-compose.yml up -d

# Access: http://localhost:3000
```

---

## Cost Management

### Check Escrow Balance

```bash
provider-services query bank balances $(provider-services keys show trinity-wallet -a)
```

### Estimate Monthly Cost

```bash
# Get current lease price (uakt/block)
provider-services query market lease list --owner WALLET

# Calculate: price_uakt * 6 * 60 * 24 * 30 / 1_000_000 = AKT/month
```

### Close Deployment (Stop Billing)

```bash
provider-services tx deployment close --dseq DSEQ --from trinity-wallet
```

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `trinity-deploy-production.sh` | Full deployment pipeline |
| `switch-provider.sh` | Update Cloudflare Worker backend URL |
| `docker-cleanup.sh` | Remove old Docker images |
| `stress-test.py` | Load testing |
| `throughput-test.py` | Benchmark inference speed |
| `war-commander.sh` | Model comparison testing |
| `akash_deploy.py` | Python Akash deployment helper |

---

## Rollback Procedure

### Backend Rollback

1. Find previous Docker image tag:
   ```bash
   docker images gdubx/trinity-inference --format "{{.Tag}}"
   ```

2. Update Akash YAML with previous tag

3. Redeploy:
   ```bash
   ./scripts/trinity-deploy-production.sh 2
   ```

### Frontend Rollback

1. Check previous deployments:
   ```bash
   dfx canister --network ic info au5zq-2qaaa-aaaal-qtowa-cai
   ```

2. ICP doesn't have easy rollback — redeploy previous version from git:
   ```bash
   git checkout PREVIOUS_COMMIT
   cd trinity-icp && dfx deploy --network ic
   ```

---

## Checklist

### Pre-Deployment

- [ ] All tests pass: `pytest backend/tests/ -v`
- [ ] Docker builds successfully: `docker build -f deploy/docker/Dockerfile .`
- [ ] Environment variables set in YAML
- [ ] Akash wallet funded (check balance)

### Post-Deployment

- [ ] Health check returns 200: `curl https://api.dubya.ai/health`
- [ ] Inference works: test with sample prompt
- [ ] Frontend loads: https://dubya.ai
- [ ] Autosave works: send message, check saves
- [ ] Metrics endpoint accessible: `/metrics`
