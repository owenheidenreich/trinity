# Trinity Codebase Reference

> **Purpose:** Comprehensive documentation for AI assistants to quickly understand the Trinity project
> **Last Updated:** January 31, 2026
> **Last Verified:** January 31, 2026
> **Status:** Production - Security Hardened
> **Version:** v3.8.0 (Major Security Audit + XSS/CORS/CSP Hardening)

---

## ⚡ Quick Reference

| Component | Value |
|-----------|-------|
| **ICP Frontend Canister** | `zc67k-kiaaa-aaaal-qtmiq-cai` |
| **ICP Backend Canister** | `au5zq-2qaaa-aaaal-qtowa-cai` |
| **Primary URL** | https://trinityai.cc |
| **Canister URL** | https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io |
| **Vercel Proxy** | https://vercel-proxy-swart-nine.vercel.app |
| **Docker Image** | `gdubx/trinity-inference:v3-secure` |
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

**⚠️ IMPORTANT FOR AI ASSISTANTS:**
- **DO NOT run the deployment script and then run other commands** - this will interrupt/cancel the deployment
- If the user says they are running the deployment, **wait for them to report the result**
- The deployment script takes 5-10 minutes to complete - do not run `sleep` or other commands that would interrupt it
- Only check terminal output if the user asks or reports an issue

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
│   ├── inference_server.py      # Main server (endpoints, Flask app)
│   ├── icp_auth.py              # Ed25519 signature verification
│   ├── config.py                # Environment configuration
│   ├── encryption.py            # AES-256-GCM encryption
│   ├── storage.py               # File storage operations
│   ├── lighthouse.py            # IPFS/Filecoin uploads
│   ├── validation.py            # Input validation
│   ├── requirements.txt         # Python dependencies
│   ├── middleware/              # Request middleware
│   │   ├── __init__.py
│   │   ├── rate_limit.py        # Rate limiting
│   │   └── icp_cache.py         # ICP caching
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── prompts.py           # System prompts
│   │   ├── metrics.py           # Stats collection
│   │   ├── akash.py             # Akash blockchain API
│   │   ├── agent.py             # 🆕 Agentic pipeline orchestrator
│   │   ├── agent_prompts.py     # 🆕 Multi-pass prompts + XML parsing
│   │   ├── complexity.py        # 🆕 Question complexity classifier
│   │   ├── search.py            # 🆕 Brave web search integration
│   │   └── loading_messages.py  # 🆕 Whimsical loading phrases
│   └── routes/                  # (Reserved for future)
│       └── __init__.py
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
│       │   ├── rainbowBorder.js # Rainbow effects
│       │   └── loadingMessages.js # 🆕 Whimsical loading phrases
│       ├── modules/             # Feature modules (empty - archive/funding removed in v3.7)
│       ├── utils/
│       │   └── validation.js    # Input validation
│       └── backend_canister/    # ICP Backend (Rust)
│           ├── src/lib.rs       # HTTPS Outcalls canister
│           ├── Cargo.toml       # Rust dependencies
│           └── trinity_backend.did  # Candid interface
│
└── docs/                        # 📚 DOCUMENTATION
    ├── CLAUDE.md                # This file
    ├── diagrams/
    │   └── trinity-storage-architecture.md
    └── user/
        └── quickstart.md
```

---

## 🧠 Agentic Pipeline (v3.6.0)

Trinity uses a multi-pass reasoning pipeline that routes questions by complexity:

### Complexity Routing
| Complexity | Passes | Pipeline |
|------------|--------|----------|
| **Simple** | 1 | Direct answer |
| **Medium** | 3 | Understand → Execute → Critique |
| **Complex** | 5 | Understand → Plan → Execute → Critique → Refine |

### Automatic Detection
- **Complexity**: Word count, question marks, technical terms
- **Web Search**: Keywords like "current", "today", "price", "bitcoin", "latest"

### Pass Timeouts
| Pass | Timeout | Token Limit |
|------|---------|-------------|
| Understand | 120s | 1000 |
| Plan | 120s | 1000 |
| Execute | 300s (5 min) | 4000 |
| Critique | 120s | 1000 |
| Refine | 300s (5 min) | 4000 |
| Search | 30s | N/A |

### Data Persistence
| Data | Saved | Where |
|------|-------|-------|
| User messages | ✅ | Encrypted autosave |
| Final AI answer | ✅ | Encrypted autosave |
| Understanding | ❌ | Ephemeral (internal) |
| Planning | ❌ | Ephemeral (internal) |
| Critique | ❌ | Ephemeral (internal) |
| Search results | ❌ | Ephemeral (in prompt) |
| Phase messages | ❌ | UI only |

### Key Files
- `backend/services/agent.py` - Pipeline orchestrator
- `backend/services/agent_prompts.py` - Pass prompts + XML parsing
- `backend/services/complexity.py` - Question classifier
- `backend/services/search.py` - Brave web search
- `backend/services/loading_messages.py` - Whimsical phrases
- `trinity-icp/src/app.js` - `generateAgent()` function

### Tier Requirements
| Tier | Model | Agentic Support |
|------|-------|-----------------|
| 1 | TinyLlama 1.1B | ❌ Too small for XML parsing |
| 2 | Llama 8B | ✅ Works well |
| 3 | Qwen 32B | ✅ Best results |

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

### Persistent Cloud Storage (v3.4.0+)
**CRITICAL FIX:** All autosaves now sync to Lighthouse (IPFS + Filecoin) in addition to local disk.
This ensures user data survives Akash redeployments.

**Data Flow:**
```
User Message → Autosave (2s debounce)
    ├─→ Local Disk (fast, ephemeral on Akash)
    └─→ Lighthouse Upload (IPFS + Filecoin, permanent)

User Login (after redeploy):
    1. Check local disk (fast)
    2. If empty → Recover from Lighthouse (IPFS gateway)
    3. Cache recovered data locally
```

### Storage Layers
| Layer | Speed | Persistence | Purpose |
|-------|-------|-------------|---------|
| IPFS (Lighthouse) | Medium | Permanent | **Source of truth** - all chat data |
| Akash Disk | Fast | Lost on redeploy | Metadata cache only |
| Browser (IndexedDB) | Instant | Session only | UI responsiveness |

**Note:** Filecoin archive feature was removed in v3.7.0. IPFS is now the primary permanent storage.

### Encryption
- AES-256-GCM with PBKDF2 key derivation
- Principal ID used as encryption password
- 100k PBKDF2 iterations, random salt + nonce
- All data encrypted before upload to IPFS

### Autosave (v3.7.0)
- 2-second debounce after each message
- Direct upload to IPFS (Lighthouse)
- CID stored in metadata for recovery
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
# Health check
curl https://vercel-proxy-swart-nine.vercel.app/health

# Test LLM response
curl -X POST https://vercel-proxy-swart-nine.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?", "max_length": 50}'

# ICP canister health
dfx canister --network ic call au5zq-2qaaa-aaaal-qtowa-cai health

# Local development
./dev

# Test against production (stops local backend first)
./test-prod
```

---

## 📋 API Endpoints

**Security Features:**
- All `/chat/*` endpoints validate input parameters (chat_id, principal_id, CID format)
- All `/generate*` endpoints are rate-limited (30 requests/60 seconds per IP)
- All `/chat/*` endpoints are rate-limited (10 requests/minute per IP)
- Prompt length limited to 50KB max to prevent DoS
- CORS restricted to known origins only

| Endpoint | Method | Auth | Rate Limit | Purpose |
|----------|--------|------|------------|---------|
| `/health` | GET | No | None | Health check |
| `/health/icp` | GET | No | None | ICP consensus health |
| `/generate` | POST | No | 30/min | LLM generation |
| `/generate/agent` | POST | No | 30/min | Agentic pipeline |
| `/stats` | GET | No | None | Performance stats |
| `/chat/autosave` | POST | ✅ | 10/min | Save encrypted chat |
| `/chat/list` | GET | ✅ | 10/min | List user's chats |
| `/chat/<id>` | GET | ✅ | 10/min | Load specific chat |
| `/chat/<id>` | DELETE | ✅ | 10/min | Delete chat |
| `/user/memory` | GET/POST | ✅ | 10/min | User memory CRUD |
| `/tools/browse` | POST | No | 30/min | Web browsing (SSRF protected) |

---

## 🔒 Security Hardening (v3.8.0)

### v3.8.0 Security Audit Fixes (January 2026)
Major security audit identified 67 issues across the codebase. Key fixes implemented:

| Category | Fix | File |
|----------|-----|------|
| **API Key Exposure** | Removed hardcoded keys, now injected from `.env` at deploy time | `deploy/akash/deploy-tier*.yaml` |
| **XSS Prevention** | All innerHTML wrapped with DOMPurify sanitization | `trinity-icp/src/app.js` |
| **CORS Hardening** | Removed wildcard, restricted to known origins | `deploy/vercel-proxy/api/proxy.js` |
| **CSP Hardening** | Removed dangerous wildcard from connect-src | `trinity-icp/.ic-assets.json5` |
| **Docker Security** | Added non-root user (trinity) to prevent container escape | `deploy/docker/Dockerfile` |
| **Thread Safety** | Added locks to global state (document_store, funding_cache) | `backend/inference_server.py` |
| **Replay Attack** | Reduced auth timestamp window from 5min to 30s | `backend/icp_auth.py` |
| **DoS Prevention** | Added 5MB limit on document uploads | `backend/inference_server.py` |
| **Exception Handling** | Replaced bare `except:` with specific exception types | `backend/inference_server.py` |
| **Dependency Pinning** | Pinned exact versions (== instead of >=) | `backend/requirements.txt` |

### Backend Security
| Feature | Implementation | File |
|---------|----------------|------|
| Storage rate limiting | `@storage_rate_limit` decorator (10 req/min) | `middleware/rate_limit.py` |
| Prompt length validation | 50KB max, returns 400 if exceeded | `config.py`, `inference_server.py` |
| SSRF protection | `is_safe_url()` blocks private IPs, metadata endpoints | `validation.py` |
| CORS restriction | Whitelist of allowed origins | `inference_server.py` |
| Connection pooling | `requests.Session` with HTTPAdapter | `config.py` |
| Memory leak prevention | Auto-cleanup of stale rate limit IPs, document store TTL | `middleware/rate_limit.py` |
| Thread-safe globals | `threading.Lock()` on document_store and funding_cache | `inference_server.py` |
| Document size limit | 5MB max per upload, returns 413 if exceeded | `inference_server.py` |
| Auth timestamp validation | 30-second window prevents replay attacks | `icp_auth.py` |

### Frontend Security
| Feature | Implementation | File |
|---------|----------------|------|
| XSS prevention | DOMPurify sanitization on all dynamic HTML | `app.js` |
| Private key encryption | AES-GCM encryption in localStorage | `utils/crypto.js` |
| Content Security Policy | Hardened CSP without wildcards | `index.html`, `.ic-assets.json5` |
| Ed25519 signatures | Constant-time verification (cryptography lib) | `icp_auth.py` |
| Request cancellation | AbortController on all fetch calls | `app.js` |

### Proxy Security Headers
The Vercel proxy now includes:
```javascript
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### Dependencies (Pinned Versions)
```
flask==3.0.3
flask-cors==4.0.0
flask-compress==1.15
requests==2.31.0
urllib3==2.2.1
psutil==5.9.8
APScheduler==3.10.4
pycryptodome==3.20.0
python-dotenv==1.0.1
cryptography==42.0.5
yfinance==0.2.37
feedparser==6.0.11
beautifulsoup4==4.12.3
argon2-cffi==23.1.0
```

### API Key Management
**CRITICAL:** API keys are now managed via `.env` file and injected at deploy time:
```bash
# .env file (never commit to git!)
LIGHTHOUSE_API_KEY=your-key-here
BRAVE_SEARCH_API_KEY=your-key-here
```
The `scripts/akash_deploy.py` script reads `.env` and injects values into YAML before deployment.

### SSRF Protection
The `/tools/browse` endpoint blocks:
- Private IP ranges (10.x, 172.16-31.x, 192.168.x)
- Localhost (127.x, ::1)
- Link-local addresses (169.254.x)
- Cloud metadata endpoints (169.254.169.254)

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
| Change environment config | `trinity-icp/src/config.js` |
| Change Vercel proxy | `deploy/vercel-proxy/api/proxy.js` |
| Change Akash deployment | `deploy/akash/deploy-tier*.yaml` |
| Change Docker build | `deploy/docker/Dockerfile` |
| Change deployment script | `scripts/trinity-deploy-production.sh` |
| Change ICP canister | `trinity-icp/src/backend_canister/src/lib.rs` |

---

## 🔄 Workflow Checklists (CRITICAL)

> **AI ASSISTANT RULE:** Before making ANY change, identify which section(s) are affected and complete the FULL checklist for each. This prevents broken deployments and missed dependencies.

### Section Dependency Map

```
Frontend ←→ Config ←→ Backend ←→ Docker ←→ Akash
   ↓           ↓          ↓
  UI         ICP      Services
   ↓                     ↓
  CSS              Middleware
```

---

### 🐳 DOCKER Workflow Checklist

**When to use:** Any change to `backend/*.py`, `backend/**/`, or `deploy/docker/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ All Python files have valid syntax | `python3 -m py_compile backend/*.py` |
| 2 | ☐ All imports exist and are correct | Check `import` statements in changed files |
| 3 | ☐ Dockerfile COPY includes all needed files/dirs | `deploy/docker/Dockerfile` |
| 4 | ☐ requirements.txt includes all dependencies | `backend/requirements.txt` |
| 5 | ☐ Build passes locally | `docker build --platform linux/amd64 -t test .` |
| 6 | ☐ Container starts without import errors | Check startup logs |
| 7 | ☐ Push to Docker Hub | `docker push gdubx/trinity-inference:tag` |
| 8 | ☐ Update Akash YAML with new image tag | `deploy/akash/deploy-tier*.yaml` |

**Files that MUST be in Dockerfile COPY:**
```dockerfile
COPY backend/inference_server.py .
COPY backend/icp_auth.py .
COPY backend/config.py .
COPY backend/encryption.py .
COPY backend/storage.py .
COPY backend/lighthouse.py .
COPY backend/validation.py .
COPY backend/middleware/ ./middleware/
COPY backend/services/ ./services/
COPY backend/routes/ ./routes/
COPY deploy/docker/startup.sh .
```

**Common Docker Failures:**
- `ModuleNotFoundError` → Missing directory in COPY
- Container exits immediately → Check startup.sh permissions
- Port not accessible → EXPOSE 8000 missing

---

### 🖥️ BACKEND Workflow Checklist

**When to use:** Any change to `backend/inference_server.py` or `backend/services/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Python syntax valid | `python3 -m py_compile backend/inference_server.py` |
| 2 | ☐ All imports exist | Check import statements |
| 3 | ☐ All decorators applied correctly | `@require_auth`, `@rate_limit` |
| 4 | ☐ Route paths match frontend expectations | Compare with `trinity-icp/src/app.js` API calls |
| 5 | ☐ Request/response format matches frontend | JSON field names must match |
| 6 | ☐ Config variables used consistently | Check `backend/config.py` |
| 7 | ☐ Docker workflow completed | See Docker checklist above |

**Backend Module Structure:**
```
backend/
├── inference_server.py   # Main routes, Flask app
├── icp_auth.py           # Auth decorators, signature verification
├── config.py             # Environment config
├── encryption.py         # AES-256-GCM encryption
├── storage.py            # File storage operations
├── lighthouse.py         # IPFS/Filecoin uploads
├── validation.py         # Input validation functions
├── middleware/           # Rate limiting, caching
│   ├── __init__.py
│   ├── rate_limit.py
│   └── icp_cache.py
├── services/             # Business logic
│   ├── __init__.py
│   ├── prompts.py        # System prompts
│   ├── metrics.py        # Stats collection
│   └── akash.py          # Akash blockchain API
└── routes/               # (Reserved for future)
    └── __init__.py
```

---

### 🎨 FRONTEND Workflow Checklist

**When to use:** Any change to `trinity-icp/src/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ JavaScript syntax valid | Vite build will catch errors |
| 2 | ☐ All imports exist | Check import paths |
| 3 | ☐ API endpoints match backend | Compare with `backend/inference_server.py` |
| 4 | ☐ Zustand state uses setter methods | Never `State.prop = value` |
| 5 | ☐ Build succeeds | `cd trinity-icp && npm run build` |
| 6 | ☐ Test in browser | Check console for errors |
| 7 | ☐ Deploy to ICP | `dfx deploy --ic trinity_frontend` |

**Frontend Module Structure:**
```
trinity-icp/src/
├── app.js              # Main application entry
├── config.js           # Environment detection
├── index.html          # HTML template + CSP
├── styles.css          # All CSS
├── tools.js            # Tools dropdown
├── api/
│   └── canister-client.js  # ICP backend client
├── auth/
│   ├── authManager.js      # Keypair management (encrypts keys in localStorage)
│   └── keyExportModal.js   # Key display modal
├── state/
│   ├── store.js            # Zustand store
│   └── contextMemory.js    # Memory compression
├── storage/
│   ├── autosave.js         # Debounced save
│   └── lighthouse.js       # Filecoin client
├── ui/
│   ├── domCache.js         # DOM element refs
│   ├── messages.js         # Message rendering
│   ├── sidebar.js          # Chat list
│   ├── modals.js           # Dialog boxes
│   ├── notifications.js    # Toasts
│   └── rainbowBorder.js    # Effects
├── utils/
│   ├── validation.js       # Input validation
│   └── crypto.js           # AES-GCM encryption for localStorage
└── modules/                # Feature modules (empty - archive/funding removed in v3.7)
```

**UI Features:**
- **Live KaTeX Rendering:** Math formulas render with 300ms debounce for performance
- **Smooth Typing:** 3 chars per 15ms interval for natural feel
- **Rainbow Borders:** Hover effects on interactive elements
- **Dark Theme:** `#1a1a1a` background, `#ffffff` text
- **Request Cancellation:** AbortController allows stopping in-flight requests

---

### 🌐 AKASH Workflow Checklist

**When to use:** Deploying to Akash or changing `deploy/akash/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Docker image pushed to Docker Hub | `docker push gdubx/trinity-inference:tag` |
| 2 | ☐ YAML has correct image tag | `deploy/akash/deploy-tier*.yaml` |
| 3 | ☐ YAML has correct environment variables | Check `env:` section |
| 4 | ☐ Deployment created successfully | Check for DSEQ |
| 5 | ☐ Bid accepted from reliable provider | Avoid `*.leet.haus` |
| 6 | ☐ Lease status shows URI | Note the ingress URL |
| 7 | ☐ Logs show "Server ready" | `provider-services lease-logs ...` |
| 8 | ☐ Health endpoint responds | `curl https://<url>/health` |
| 9 | ☐ Vercel proxy updated with new URL | `./scripts/switch-provider.sh` |
| 10 | ☐ Frontend ICP canister redeployed | `dfx deploy --ic trinity_frontend` |

**Provider Reliability:**
- ✅ GOOD: `*.pcgameservers.com`, `*.akash.pub`
- ❌ AVOID: `*.leet.haus`, `*.quanglong.org`

---

### 🔵 ICP Workflow Checklist

**When to use:** Changes to ICP canisters or frontend deployment

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ dfx.json has correct canister IDs | `trinity-icp/dfx.json` |
| 2 | ☐ canister_ids.json matches | `trinity-icp/canister_ids.json` |
| 3 | ☐ Frontend builds successfully | `npm run build` |
| 4 | ☐ For backend canister: Rust compiles | `cargo build --target wasm32-unknown-unknown` |
| 5 | ☐ Deploy command succeeds | `dfx deploy --ic <canister>` |
| 6 | ☐ Verify canister accessible | Test in browser |

**Canister IDs:**
- Frontend: `zc67k-kiaaa-aaaal-qtmiq-cai`
- Backend: `au5zq-2qaaa-aaaal-qtowa-cai`

---

### 🎭 CSS/UI Workflow Checklist

**When to use:** Visual changes to `styles.css` or UI components

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ CSS syntax valid | Browser dev tools will show errors |
| 2 | ☐ Colors match design system | See UI/UX section |
| 3 | ☐ Mobile responsive | Test at 375px width |
| 4 | ☐ Dark theme consistency | No jarring light elements |
| 5 | ☐ No console errors | Check browser console |
| 6 | ☐ Build and deploy | Frontend workflow |

**Design System:**
- Background: `#1a1a1a`, Surfaces: `#2d2d2d`
- Text: `#ffffff`, Secondary: `#bbb`
- Borders: `#3d3d3d`
- Border radius: 6px buttons, 8px modals

---

### 🧠 MEMORY Workflow Checklist

**When to use:** Changes to context memory or user memory

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Frontend contextMemory.js logic correct | `trinity-icp/src/state/contextMemory.js` |
| 2 | ☐ Backend prompt builder matches | `backend/services/prompts.py` |
| 3 | ☐ Memory window size consistent | 6 messages frontend, matches backend |
| 4 | ☐ Summarization triggers correctly | Every 15 messages |
| 5 | ☐ User memory endpoint works | `/user/memory` GET/POST |
| 6 | ☐ Test multi-turn conversation | Verify context is maintained |

---

### 💾 STORAGE Workflow Checklist

**When to use:** Changes to autosave, encryption, or Lighthouse

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Frontend autosave.js correct | `trinity-icp/src/storage/autosave.js` |
| 2 | ☐ Backend storage.py matches | `backend/storage.py` |
| 3 | ☐ Encryption uses AES-256-GCM | `backend/encryption.py` |
| 4 | ☐ Lighthouse API key configured | `LIGHTHOUSE_API_KEY` env var |
| 5 | ☐ IPFS upload/download works | Test with real data |
| 6 | ☐ Debounce timing correct | 2-second debounce |

---

### 🤖 MODEL Workflow Checklist

**When to use:** Changes to prompts, model config, or reasoning

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ System prompt is clear | `backend/services/prompts.py` |
| 2 | ☐ Model name matches tier | `deploy/akash/deploy-tier*.yaml` |
| 3 | ☐ Token limits appropriate | Check `max_length` in frontend |
| 4 | ☐ Reasoning prompt forces thinking | `/think` command works |
| 5 | ☐ Prompt doesn't confuse small models | No role markers for TinyLlama |
| 6 | ☐ Test actual responses | Chat in production |

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
- Document attachments (browser-side PDF parsing)

---

## 🐛 Known Issues & Fixes

### TinyLlama Prompt Confusion (Critical - Jan 2026)

**Symptom:** Model echoes system prompt in responses, hallucinates fake user/assistant dialogue, produces garbage like:
```
"[System] You are Trinity... User: Wow, I didn't think... Assistant: Yes, I am Trinity..."
```

**Root Cause:** 
1. TinyLlama (1.1B params) is too small to properly follow multi-turn chat formatting
2. The prompt uses `[System]`, `User:`, `Assistant:` labels that confuse the model
3. Model sees these as patterns to continue/echo rather than role markers
4. Context memory saves garbage responses → fed back next turn → feedback loop

**Affected Files:**
- `backend/inference_server.py` lines 1261-1310 (system prompt + prompt building)
- `trinity-icp/src/state/contextMemory.js` (saves garbage to context)

**Fix Required:**
1. Strip all role markers (`[System]`, `User:`, `Assistant:`) for small models
2. Use simple prompt format: just the user's question
3. OR switch to a larger model (8B+) that handles chat formatting correctly

**Prompt Flow (Current - Broken for TinyLlama):**
```
[System]
You are Trinity, a decentralized AI assistant...

User: previous message
Assistant: previous response
User: current message
Assistant:
```

**Prompt Flow (Fixed for TinyLlama):**
```
{user's question}
```

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

*This document is maintained for AI assistants to quickly understand Trinity without re-exploring files. Last updated January 31, 2026 (v3.8.0 security audit).*
