# Trinity Codebase Reference

> **Purpose:** Comprehensive documentation for AI assistants to quickly understand the Trinity project  
> **Last Updated:** January 29, 2026  
> **Last Verified:** January 29, 2026 - Backend temporarily down for maintenance  
> **Status:** Development - Streaming + UI Improvements Complete  
> **Version:** v3.3.0 (Streaming Responses + Compact UI)

---

## ⚡ Quick Reference

| Component | Value |
|-----------|-------|
| **ICP Frontend Canister** | `zc67k-kiaaa-aaaal-qtmiq-cai` |
| **ICP Backend Canister** | `au5zq-2qaaa-aaaal-qtowa-cai` |
| **Primary URL** | https://trinityai.cc |
| **Canister URL** | https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io |
| **Vercel Proxy** | https://vercel-proxy-swart-nine.vercel.app |
| **Docker Image** | `gdubx/trinity-inference:v10-streaming` |
| **Akash Wallet** | `akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp` |

---

## 🚀 Deployment (Single Command)

```bash
./scripts/trinity-deploy-production.sh [tier]

# Examples:
./scripts/trinity-deploy-production.sh      # Interactive tier selection
./scripts/trinity-deploy-production.sh 1    # TinyLlama 1.1B (~$25/mo)
./scripts/trinity-deploy-production.sh 2    # Llama 3.1 8B (~$50/mo)
./scripts/trinity-deploy-production.sh 3    # Qwen 2.5 72B (~$200/mo)
```

**The script handles EVERYTHING:**
1. Prerequisites check (Docker, provider-services CLI, wallet)
2. Local validation (Python syntax, Docker build)
3. Docker push to Docker Hub
4. Akash deployment via CLI (closes old deployments, creates new)
5. Vercel proxy URL update
6. ICP frontend canister deployment
7. Production verification (/health, /generate tests)

---

## 📁 Project Structure

```
Trinity/
├── dev                          # → scripts/dev.sh (local development)
├── test-prod                    # → scripts/test-prod.sh (production testing)
├── icp-deploy                   # → ICP canister deployment
├── README.md                    # Project overview
│
├── backend/                     # 🖥️ FLASK BACKEND
│   ├── inference_server.py      # Main server (endpoints, auth, encryption)
│   ├── icp_auth.py              # Ed25519 signature verification
│   └── requirements.txt         # Python dependencies
│
├── deploy/                      # 🚀 DEPLOYMENT CONFIGS
│   ├── akash/                   # Akash SDL manifests
│   │   ├── deploy-tier1-basic.yaml      # TinyLlama 1.1B
│   │   ├── deploy-tier2-balanced.yaml   # Llama 3.1 8B
│   │   └── deploy-tier3-complex.yaml    # Qwen 2.5 72B
│   ├── docker/                  # Docker build files
│   │   ├── Dockerfile           # Container definition
│   │   ├── build.sh             # Build script
│   │   └── startup.sh           # Container entrypoint
│   ├── local/                   # Local development
│   │   ├── start.sh             # Start TinyLlama locally
│   │   ├── stop.sh              # Stop local backend
│   │   └── status.sh            # Check local status
│   └── vercel-proxy/            # SSL termination proxy
│       ├── api/proxy.js         # Node.js proxy (http/https support)
│       ├── vercel.json          # Routing config
│       └── package.json         # Dependencies
│
├── scripts/                     # 📜 AUTOMATION SCRIPTS
│   ├── trinity-deploy-production.sh  # ⭐ MAIN DEPLOYMENT SCRIPT
│   ├── akash_deploy.py          # Akash CLI helper (Python)
│   ├── dev.sh                   # Start local development
│   ├── test-prod.sh             # Test production backend
│   ├── switch-provider.sh       # Update Vercel proxy URL
│   ├── trinity-test-local.sh    # Local testing script
│   └── docker-cleanup.sh        # Clean Docker cache
│
├── trinity-icp/                 # 🎨 FRONTEND (ICP)
│   ├── dfx.json                 # ICP canister config
│   ├── canister_ids.json        # Production canister IDs
│   ├── package.json             # npm dependencies
│   ├── vite.config.js           # Vite bundler config
│   └── src/                     # Source code
│       ├── app.js               # Main application
│       ├── config.js            # Environment config
│       ├── index.html           # HTML template
│       ├── styles.css           # CSS styling
│       ├── tools.js             # Tools dropdown
│       ├── api/
│       │   └── canister-client.js  # ICP backend client
│       ├── auth/
│       │   ├── authManager.js   # Ed25519 keypair management
│       │   ├── keyExportModal.js # Key display modal
│       │   ├── auth-client.js   # Auth utilities
│       │   ├── auth-entry.js    # Auth entry point
│       │   └── icp-auth.js      # ICP auth library
│       ├── state/
│       │   ├── store.js         # Zustand state management
│       │   └── contextMemory.js # Conversation compression
│       ├── storage/
│       │   ├── autosave.js      # Debounced persistence
│       │   ├── lighthouse.js    # Filecoin/IPFS uploads
│       │   └── mock.js          # Test mode storage
│       ├── ui/
│       │   ├── index.js         # UI module aggregator
│       │   ├── domCache.js      # DOM element caching
│       │   ├── messages.js      # Message rendering
│       │   ├── sidebar.js       # Chat list
│       │   ├── modals.js        # Dialog boxes
│       │   ├── notifications.js # Toast notifications
│       │   └── rainbowBorder.js # Rainbow effects
│       ├── modules/
│       │   ├── archive.js       # Filecoin archival
│       │   └── funding.js       # Funding transparency panel
│       ├── utils/
│       │   └── validation.js    # Input validation
│       └── backend_canister/    # ICP Backend (Rust)
│           ├── src/lib.rs       # HTTPS Outcalls canister
│           ├── Cargo.toml       # Rust dependencies
│           └── trinity_backend.did  # Candid interface
│
├── test/                        # 🧪 TESTING
│   ├── integration/             # Integration tests
│   │   ├── test_filecoin_integration.py
│   │   ├── test_auth_backend.py
│   │   ├── test_autosave_integration.py
│   │   ├── test_context_memory.py
│   │   ├── test_llm_response.py
│   │   ├── test_signature_verification.py
│   │   └── benchmark_models.py
│   └── local/                   # Local test configs
│       ├── docker-compose.local.yml
│       └── start-local.sh
│
└── docs/                        # 📚 DOCUMENTATION
    ├── CLAUDE.md                # This file
    ├── diagrams/
    │   └── trinity-storage-architecture.md
    └── user/
        └── quickstart.md
```

---

## 🏗️ Architecture

```
User Browser
    ↓ HTTPS
ICP Frontend Canister (zc67k-kiaaa-aaaal-qtmiq-cai)
    │
    ├─→ Direct API calls (most endpoints)
    │       ↓
    │   Vercel Proxy (SSL termination)
    │       ↓
    │   Akash Backend (Flask + Ollama)
    │
    └─→ ICP Backend Canister (au5zq-2qaaa-aaaal-qtowa-cai)
            ↓ HTTPS Outcalls (for ICP consensus)
        Vercel Proxy → Akash Backend
```

### Why Vercel Proxy?
- Akash providers have invalid/self-signed SSL certificates
- ICP HTTPS Outcalls require valid SSL
- Vercel provides valid SSL and forwards requests with certificate bypass

---

## 🔧 Akash CLI Reference

### Prerequisites
```bash
# Install provider-services CLI
curl -sfL https://raw.githubusercontent.com/akash-network/provider/main/install.sh | bash

# Import wallet
provider-services keys add trinity-wallet --recover --keyring-backend os

# Verify wallet
provider-services keys show trinity-wallet --keyring-backend os -a
```

### Key Commands
```bash
# Check balance
provider-services query bank balances akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --node https://rpc.akashnet.net:443 -o json

# List active deployments
provider-services query deployment list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --state active --node https://rpc.akashnet.net:443 -o json

# Close deployment
provider-services tx deployment close --dseq <DSEQ> \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Create deployment
provider-services tx deployment create deploy.yaml \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Get bids
provider-services query market bid list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --dseq <DSEQ> --node https://rpc.akashnet.net:443 -o json

# Create lease
provider-services tx market lease create \
  --dseq <DSEQ> --gseq 1 --oseq 1 --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Send manifest
provider-services send-manifest deploy.yaml \
  --dseq <DSEQ> --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# Get lease status (includes URI)
provider-services query provider lease-status \
  --dseq <DSEQ> --gseq 1 --oseq 1 --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# View logs
provider-services lease-logs \
  --dseq <DSEQ> --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443 --follow
```

### Provider Selection
**GOOD (Reliable):**
- `*.pcgameservers.com` - Fast image caching, reliable ingress
- `*.akash.pub` domains (e.g., `hurricane.akash.pub`, `europlots.akash.pub`)

**AVOID (Unreliable):**
- `*.leet.haus` domains - ingress networking often broken
- `quanglong.org` - Very slow image pulls (26+ minutes)
- `digitalfrontier` providers - Intermittent 502 errors

---

## 📊 Model Tiers

| Tier | Model | GPU | Memory | Cost | Use Case |
|------|-------|-----|--------|------|----------|
| 1 | TinyLlama 1.1B | T4/RTX3090/4090 | 16GB | ~$25/mo | Testing |
| 2 | Llama 3.1 8B | RTX4090/A10 | 32GB | ~$50/mo | Balanced |
| 3 | Qwen 2.5 72B | A100 80GB | 180GB | ~$200/mo | Complex |

---

## 🔐 Authentication

### Ed25519 Self-Custody
- Keypairs generated in browser
- Principal ID derived from public key
- Private key stored in localStorage (user's responsibility)
- All `/chat/*` endpoints require signature

### Signature Verification
```python
# Backend decorator
@require_auth
def protected_endpoint():
    principal = request.principal  # Set by decorator
    # Access user-specific data
```

### Headers Required
```
ICP-Principal: <principal-id>
ICP-Timestamp: <unix-timestamp>
ICP-Signature: <base64-signature>
ICP-PublicKey: <hex-public-key>
```

---

## 💾 Storage Architecture

### Two-Tier System
1. **Active Storage (Akash):** Encrypted JSON files on deployment disk
2. **Archive Storage (Filecoin):** Permanent storage via Lighthouse SDK

### Encryption
- AES-256-GCM with PBKDF2 key derivation
- Principal ID used as encryption password
- 100k PBKDF2 iterations, random salt + nonce

### Autosave
- 2-second debounce after each message
- Exponential backoff retry (5 attempts max)
- Rainbow wave animation during save

---

## ⚠️ Critical Conventions

### Zustand State Management
**CRITICAL:** Direct assignments fail silently!

```javascript
// ❌ WRONG - Fails silently
State.isAuthenticated = true;
State.chatHistory = [...messages];

// ✅ CORRECT - Use setter methods
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

### Docker Build (Apple Silicon)
```bash
# ✅ CORRECT - AMD64 for Akash
docker build --platform linux/amd64 -t image:tag .

# ❌ WRONG - ARM64 won't work on Akash
docker build -t image:tag .
```

### Environment Differences
| Feature | Local (TinyLlama) | Production (Akash) |
|---------|-------------------|-------------------|
| AI Inference | ✅ | ✅ |
| Autosave | ❌ No storage | ✅ Encrypted disk |
| Filecoin Archive | ❌ No Lighthouse | ✅ Full archival |
| Context Memory | ⚠️ Not persisted | ✅ Persisted |

---

## 🛠️ Common Tasks

### Deploy Everything
```bash
./scripts/trinity-deploy-production.sh 1  # Tier 1
./scripts/trinity-deploy-production.sh 2  # Tier 2
./scripts/trinity-deploy-production.sh 3  # Tier 3
```

### Frontend Only
```bash
cd trinity-icp && npm run build && dfx deploy --ic trinity_frontend
```

### Switch Akash Provider
```bash
./scripts/switch-provider.sh https://new-url.ingress.akash.pub
```

### Clean Docker
```bash
./scripts/docker-cleanup.sh
```

### Local Development
```bash
./dev  # or ./scripts/dev.sh
```

### Test Production
```bash
./test-prod  # or ./scripts/test-prod.sh
```

---

## 🧪 Testing

```bash
# Integration tests
python3 test/integration/test_filecoin_integration.py

# Health check
curl https://vercel-proxy-swart-nine.vercel.app/health

# ICP canister health
dfx canister --network ic call au5zq-2qaaa-aaaal-qtowa-cai health
```

---

## 📋 API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | No | Health check |
| `/health/icp` | GET | No | ICP consensus health |
| `/generate` | POST | No | LLM generation |
| `/stats` | GET | No | Performance stats |
| `/funding/status` | GET | No | Escrow balance + time remaining |
| `/chat/autosave` | POST | ✅ | Save encrypted chat |
| `/chat/list` | GET | ✅ | List user's chats |
| `/chat/<id>` | GET | ✅ | Load specific chat |
| `/chat/<id>` | DELETE | ✅ | Delete chat |
| `/chat/<id>/archive` | POST | ✅ | Archive to Filecoin |
| `/chat/recover-archives` | GET | ✅ | Recover archives |
| `/chat/archive/<cid>` | GET | No | Download by CID |
| `/user/memory` | GET/POST | ✅ | User memory CRUD |

---

## 🐛 Troubleshooting

### Cold Start (20-30s first request)
**Expected behavior.** LLM loads into GPU memory on first request.

### No Consensus Error (ICP)
```
❌ No consensus could be reached. Replicas had different responses.
```
**Solution:** Use `/health/icp` endpoint. Backend strips non-deterministic fields for ICP requests with `X-Request-ID` header.

### Docker Disk Full
```bash
docker system prune -a --volumes -f
docker builder prune -a -f
```

### Git Slow
Delete build artifacts:
```bash
rm -rf trinity-icp/target trinity-icp/node_modules
```

### Browser Cache
Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows/Linux)

---

## 📚 Key Files Reference

| Need to... | Edit this file |
|------------|----------------|
| Change backend logic | `backend/inference_server.py` |
| Change auth verification | `backend/icp_auth.py` |
| Change frontend UI | `trinity-icp/src/ui/*.js` |
| Change state management | `trinity-icp/src/state/store.js` |
| Change context memory | `trinity-icp/src/state/contextMemory.js` |
| Change auth flow | `trinity-icp/src/auth/authManager.js` |
| Change autosave | `trinity-icp/src/storage/autosave.js` |
| Change Filecoin archive | `trinity-icp/src/modules/archive.js` |
| Change funding panel | `trinity-icp/src/modules/funding.js` |
| Change environment config | `trinity-icp/src/config.js` |
| Change Vercel proxy | `deploy/vercel-proxy/api/proxy.js` |
| Change Akash deployment | `deploy/akash/deploy-tier*.yaml` |
| Change Docker build | `deploy/docker/Dockerfile` |
| Change deployment script | `scripts/trinity-deploy-production.sh` |
| Change ICP canister | `trinity-icp/src/backend_canister/src/lib.rs` |

---

## 🎯 Feature Status

### ✅ Complete
- Self-custody Ed25519 authentication
- Encrypted autosave (AES-256-GCM)
- Filecoin archive via Lighthouse SDK
- Context memory (6-message window + summarization)
- Modular frontend architecture (Zustand)
- ICP backend canister (HTTPS Outcalls)
- Vercel SSL proxy
- Unified CLI deployment pipeline (`trinity-deploy-production.sh`)
- Custom domain (trinityai.cc)
- Funding transparency (Akash escrow balance + ICP cycles)

### ⏳ Planned
- Lightweight RAG (FastEmbed + BM25)
- Audio transcription (Groq Whisper API)
- Document attachments (browser-side PDF parsing)

---

## 🎨 UI/UX Design System

### Theme
- **Background:** `#1a1a1a` (main), `#2d2d2d` (surfaces)
- **Text:** `#ffffff` (primary), `#bbb` (secondary)
- **Borders:** `#3d3d3d`
- **Interactive Hover:** Rainbow gradient borders
- **Archive Indicator:** Purple `#9c27b0`

### Typography
- Font: System fonts (`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif`)
- Weights: 400, 500, 600
- Size range: 11px-18px

### Spacing
- Border radius: 6px (buttons), 8px (modals)
- Grid: 8px system

---

## 🔗 Quick Links

- **Production:** https://trinityai.cc
- **ICP Direct:** https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io
- **Vercel Proxy:** https://vercel-proxy-swart-nine.vercel.app
- **Docker Hub:** https://hub.docker.com/r/gdubx/trinity-inference
- **Akash Console:** https://console.akash.network

---

*This document is maintained for AI assistants to quickly understand Trinity without re-exploring files. Last updated January 30, 2026.*
