# Trinity Codebase Reference

> **Purpose:** Comprehensive documentation for AI assistants to quickly understand the Trinity project  
> **Last Updated:** January 25, 2026  
> **Status:** Production - Full Stack Operational with Modular Architecture  
> **Version:** v2.2.0 (ICP Backend Canister + Lighthouse/Filecoin)  
> **Akash Backend:** https://u2k74jdr358rt168vo6bmi8mas.ingress.akashprovid.com  
> **ICP Frontend Canister:** zc67k-kiaaa-aaaal-qtmiq-cai
> **ICP Backend Canister:** au5zq-2qaaa-aaaal-qtowa-cai  
> **⚠️ Akash Backend URL Changes Frequently:** Check https://console.akash.network for current deployment URL, or inspect `cloudflare/workers/trinity-ai-proxy.js` for `AKASH_BACKEND` constant  
> **Next Phase:** See [plans/DECENTRALIZATION_ROADMAP.md](plans/DECENTRALIZATION_ROADMAP.md)

---

## 📋 Development Workflow Integration

**CLAUDE.md serves dual purposes:**
- **📖 Reference Document:** Current system state and implementation details
- **📝 Task Planning:** Status tracking for planned and completed work

**Update Protocol:**
1. **Before starting work:** Reference CLAUDE.md for current architecture and requirements
2. **During development:** Use as specification document for implementation details
3. **After completion:** Update status indicators and add implementation notes
4. **Commit updates:** Include CLAUDE.md changes with feature commits

**Status Indicators:**
- ✅ **COMPLETE** - Fully implemented and tested
- 🚧 **IN PROGRESS** - Currently being worked on
- ⏳ **PLANNED** - Specified but not yet implemented
- ❓ **NEEDS REVIEW** - Implementation complete, needs verification

---

## ⚡ Quick Overview

**Trinity** is a fully decentralized AI chat application featuring self-custody authentication, encrypted storage, and permanent archival on Filecoin.

### Core Features
- ✅ **Self-Custody Auth:** Ed25519 keypairs, no passwords, user owns private keys
- ✅ **Encrypted Autosave:** AES-256-GCM encryption, automatic persistence
- ✅ **Filecoin Archive:** Permanent IPFS + Filecoin storage via Lighthouse SDK (verified deals)
- ✅ **Context Memory:** 6-message sliding window with auto-summarization
- ✅ **Decentralized Stack:** ICP frontend + Akash backend + Filecoin storage
- ✅ **Modular Architecture:** State management with Zustand, UI/Auth/Storage modules
- ✅ **Cache Busting:** Version checking with automatic reload on updates
- ✅ **Sleek UI:** Dark theme with animated rainbow border effects on hover

### Live URLs
- **Production:** https://trinityai.cc
- **Backend:** https://u2k74jdr358rt168vo6bmi8mas.ingress.akashprovid.com
- **Model:** Llama 3.1 70B (2x NVIDIA A100 80GB)
- **Build System:** Vite 7.3.1 with IIFE bundling for file:// protocol support

---

## 🎨 UI/UX Design System

### Theme & Color Scheme
**Dark Minimalist with Rainbow Accents**

**Primary Palette:**
- **Backgrounds:** `#1a1a1a` (main), `#2d2d2d` (secondary surfaces)
- **Text:** `#ffffff` (primary), `#ececec` (high emphasis), `#bbb` (medium), `#999` (low emphasis)
- **Borders/Dividers:** `#3d3d3d`
- **Interactive Hover:** `#252525` (subtle lightening on hover states)

**Accent Colors:**
- **Rainbow Gradient:** Full spectrum (red → orange → yellow → green → cyan → blue → indigo → violet) used for interactive button borders on hover
- **Archive Indicator:** Purple `#9c27b0` (left border) and `#9333ea` (button background)
- **Status Success:** Green `#4CAF50` (authenticated state)

**Design Philosophy:**
- Clean, professional aesthetic with text-only labels (no emojis)
- Interactive elements provide visual feedback through subtle animations
- Rainbow accents add personality without overwhelming the interface
- Dark theme optimized for extended use and focus

**Typography:**
- Font Stack: `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif`
- Weights: 400 (regular), 500 (medium), 600 (semibold)
- UI elements use 11px-18px range

**Spacing & Layout:**
- Border radius: 6px (buttons, cards), 8px (modals)
- Padding: 10-16px for buttons, 12px for containers
- Consistent 8px grid system for spacing

---

## 📊 Implementation Status

### Phase 1: Self-Custody Authentication ✅ COMPLETE
- Ed25519 keypair generation in browser
- Principal ID derivation from public key
- Private key export/import functionality
- localStorage persistence with auto-restore
- **Status:** Production ready on trinityai.cc

### Phase 2: Backend Integration ✅ COMPLETE
- `@require_auth` decorator for all /chat/* endpoints
- Ed25519 signature verification (icp_auth.py)
- 5-minute timestamp window (replay protection)
- Principal-based access control
- **Status:** All 6 endpoints protected and tested

### Phase 3: Autosave System ✅ COMPLETE
- Automatic save after each message (2-second debounce)
- AES-256-GCM encryption with PBKDF2 key derivation
- Exponential backoff retry (5 attempts max)
- Sidebar auto-refresh after save
- UI indicators (rainbow wave animation)
- **Status:** Production deployed, working flawlessly

### Phase 4: Modular Frontend Architecture ✅ COMPLETE
**✅ Modularization Complete (January 2026):**
- **State Management:** Zustand 5.0.3 with immutable getters and setter methods
- **Module Extraction:** 
  - `state/store.js` (295 lines) - Centralized state with read-only API
  - `state/contextMemory.js` (75 lines) - Conversation compression logic
  - `auth/authManager.js` (210 lines) - Ed25519 keypair management
  - `auth/keyExportModal.js` (100 lines) - Security modal for key display
  - `storage/autosave.js` (180 lines) - Debounced persistence with retry
  - `storage/mock.js` (85 lines) - Test mode storage
  - `ui/index.js` - Main UI module with sub-modules:
    - `ui/domCache.js` (45 lines) - Element caching
    - `ui/messages.js` (266 lines) - Message rendering & typing animation
    - `ui/sidebar.js` (109 lines) - Chat list & auth buttons
    - `ui/modals.js` (80 lines) - Dialog boxes
    - `ui/notifications.js` (65 lines) - Toast notifications
  - `modules/archive.js` (210 lines) - Filecoin archival logic
  - `config.js` (88 lines) - Environment detection & API URLs
- **Build System:** Vite 7.3.1 with IIFE output for file:// protocol
- **Critical Fix:** All State mutations use proper Zustand setters (no direct assignments)
- **Bundle Size:** ~80KB main bundle (estimated), properly exposes window.Actions/API/UI/State
- **Status:** Production deployed via dfx, all buttons functional, modular & maintainable

### Phase 5: Filecoin Archive ✅ COMPLETE
**✅ Complete:**
- Individual chat archiving with immediate Lighthouse upload
- IPFS pinning + automatic Filecoin deal creation (verified storage)
- Lighthouse API for upload listing by principal ID
- Auto-recovery on login (archived chats restored automatically)
- Multi-gateway IPFS download (Lighthouse, ipfs.io, cloudflare-ipfs, dweb.link)
- Archive UI button with Filecoin upload confirmation
- AES-256-GCM encryption for all archived data
- Deal status endpoint for verifying Filecoin sealing

**Architecture (Lighthouse SDK - January 2026 Update):**
```
Principal ID → Lighthouse API → IPFS CID → Filecoin Deal (1-24 hours)
                    ↓
            gateway.lighthouse.storage/ipfs/{cid}
```

**Migration Note:** Replaced Pinata with Lighthouse SDK for direct Filecoin integration.
Lighthouse provides verified Filecoin deals, not just IPFS pinning.

**Recovery Flow:**
1. User logs in with principal ID
2. System queries Lighthouse API for uploads by principal
3. Downloads and decrypts archived chats from IPFS gateway
4. Lists all archived chats in sidebar
5. Individual chats downloadable on demand
6. Filecoin deal status checkable via `/chat/archive/status/<cid>`

**⏳ Future Enhancements:**
- Unarchive functionality (recover to active state)
- File attachment bundling with archives
- **Status:** Full Filecoin integration production-ready

### Phase 6: ICP Backend Canister ✅ COMPLETE (January 2026)
**Purpose:** Replace Cloudflare Workers with ICP HTTPS Outcalls for fully decentralized proxy.

**✅ Completed:**
- Rust canister with HTTPS Outcalls to Akash backend
- Ed25519 signature verification in canister
- Deterministic `/health/icp` endpoint for ICP consensus
- Idempotency cache with `X-Request-ID` header (handles 13 replica requests)
- Candid interface with proper type definitions
- Frontend client (`trinity-icp/src/api/canister-client.js`)
- A/B testing router for gradual migration (`trinity-icp/src/api/backend-router.js`)

**Canister IDs:**
- Frontend: `zc67k-kiaaa-aaaal-qtmiq-cai`
- Backend: `au5zq-2qaaa-aaaal-qtowa-cai`

**Key Files:**
- `trinity-icp/src/backend_canister/src/lib.rs` - Main Rust canister (550 lines)
- `trinity-icp/src/backend_canister/trinity_backend.did` - Candid interface
- `backend/inference_server.py` - Added `/health/icp` + `@icp_idempotent` decorator

**ICP Consensus Solution:**
The challenge with ICP HTTPS Outcalls is that all 13 subnet replicas make the same request.
If responses differ (timestamps, dynamic metrics), consensus fails.

Solution:
1. `/health/icp` endpoint returns ONLY static data (no timestamps)
2. `@icp_idempotent` decorator caches responses by `X-Request-ID`
3. Canister generates deterministic request IDs using time buckets

**Deployment Script:**
```bash
./icp-deploy              # Deploy both canisters
./icp-deploy frontend     # Frontend only
./icp-deploy backend      # Backend canister only
```

**Status:** ICP Backend Canister deployed and health check working

---

## 📋 Next Steps Analysis

**Reference Document:** [plans/next-steps.md](plans/next-steps.md) contains the complete roadmap of planned features and improvements.

### ✅ COMPLETED TASKS (from next-steps.md)

#### 1. Contextual Memory ✅ FULLY IMPLEMENTED
- **Stateless Model:** LLM treated as inference engine only, no internal memory
- **Conversation-Scoped Memory:** One memory object per chat session
- **ICP-Layer Storage:** Memory lives in frontend, not backend
- **Two-Part Memory:** Conversation summary + 6-message sliding window
- **Fixed System Prompt:** Consistent role, tone, and constraints
- **Structured Prompts:** System instructions + summary + recent messages + user input
- **6-Message Window:** Last 4-6 user/assistant exchanges to prevent context bloat
- **Periodic Summarization:** Re-summarize every 15 messages using background process
- **Post-Response Updates:** Memory updates after each LLM response
- **Session-Based:** Memory associated with conversation ID, discarded when session ends

#### 2. Security ✅ MOSTLY COMPLETE
- **HTTPS:** Cloudflare SSL certificate installed
- **Domain:** trinityai.cc active with Cloudflare DNS
- **ICP Security Handler:** ⏳ PLANNED - Better security handler for ICP hosting
- **ENS Domain:** ⏳ PLANNED - trinity.eth domain transition

#### 3. Save Chat Function (Filecoin) ✅ FULLY IMPLEMENTED
- **Archive Button:** Manual save functionality implemented
- **Filecoin Storage:** IPFS/Lighthouse SDK integration complete (verified deals)
- **Encryption:** AES-256-GCM for archived chats
- **Auto-Recovery:** Archived chats restore automatically on login
- **10-Chat Limit:** Archive enforcement implemented

#### 4. Privacy ✅ MOSTLY COMPLETE
- **Chat Encryption:** All saved chats encrypted with AES-256-GCM
- **Backend Logs:** ⚠️ PARTIALLY - Prompts are logged (first 50 characters visible in backend logs)
- **Memory Inclusion:** User memory can be included in archives for continuity

#### 5. Authentication ✅ IMPLEMENTED (Ed25519-based)
- **No Guest Login Required:** ✅ Implemented - users can chat without authentication
- **Keypair System:** Uses Ed25519 keypairs (principal ID as "username", private key as "password")
- **Self-Custody:** Users own their private keys, no server-side password storage
- **Traditional Username/Password:** ⏳ NOT IMPLEMENTED - No separate username/password system for paying customers

### ❌ REMAINING TASKS (from next-steps.md)

#### 1. Transparency ✅ PARTIALLY IMPLEMENTED
- **Provider Location Display:** ✅ IMPLEMENTED - Shows provider ID and environment ([LOCAL]/[PROD])
- **Tech Stack Display:** ✅ IMPLEMENTED - Shows model name (e.g., "Model: llama3.1:70b")
- **Cost/Burn Rate Display:** ⏳ NOT IMPLEMENTED - No visibility into AKT, ICP, FIL costs
- **Open Source Guidance:** ⏳ NOT IMPLEMENTED - No documentation on how to open source the project

#### 2. Dynamic Hardware and LLM Shifting ⏳ NOT IMPLEMENTED
- **Complexity Detection:** No prompt complexity analysis
- **Tier-Based Routing:** No automatic model switching (1/2/3 tiers)
- **Cost Optimization:** No routing to cheaper GPUs for simple tasks
- **Simultaneous Deployment:** No multiple model tiers running concurrently

#### 3. Donations ⏳ NOT IMPLEMENTED
- **Payment System:** No donation/payment infrastructure
- **Crypto Routing:** No automatic distribution to AKT, ICP, FIL
- **Incentive Structure:** No 99% routing to operational costs

### 🎯 Immediate Priorities (from next-steps.md analysis)

1. **Enhanced Transparency** - Add cost/burn rate display and open source guidance documentation
2. **Privacy Improvements** - Consider masking or removing prompt logging from backend
3. **ICP Security Handler** - Implement better security handling for ICP-hosted frontend
4. **ENS Domain** - Consider trinity.eth domain transition
5. **Dynamic Hardware/LLM Shifting** - Implement complexity-based model routing

---

## 🏗️ Architecture Overview

### Network Topology
```
User Browser
    ↓ HTTPS
Cloudflare (trinityai.cc)
    ├→ trinity-frontend-proxy → ICP Canister (Frontend)
    └→ trinity-api-proxy → Akash Network (Backend + Ollama)
```

### Storage Architecture
```
Layer 1 (Active): Akash Backend → Local Disk (encrypted JSON)
    └→ Autosave: Every message (2s debounce)

Layer 2 (Archive): Lighthouse SDK → IPFS + Filecoin (permanent storage with verified deals)
    └→ User-triggered: Archive button in sidebar
```

**See detailed diagrams:**
- Network: [diagrams/trinity-network-architecture.md](diagrams/trinity-network-architecture.md)
- Storage: [diagrams/trinity-storage-architecture.md](diagrams/trinity-storage-architecture.md)

---

## 🖥️ Environment Setup (Production vs Local Testing)

> **CRITICAL:** The local testing environment is NOT a full replica of production. It only provides AI inference capability - storage, memory, and Filecoin features are NOT available locally.

### Production Environment (Akash Network)

**Full-stack deployment with all features operational:**

| Component | Details |
|-----------|---------|
| **Compute** | Akash Network (decentralized cloud) |
| **Model** | Llama 3.1 70B |
| **Hardware** | 2x NVIDIA A100 80GB GPUs |
| **Backend** | `inference_server.py` with all endpoints |
| **Storage** | Encrypted JSON files on Akash disk |
| **Archive** | Filecoin/IPFS via Lighthouse SDK (verified deals) |
| **Proxy** | Cloudflare Workers (HTTPS → HTTP) |
| **Cost** | ~$50-120/month when deployed |

**Features available in production:**
- ✅ AI chat generation (Llama 70B)
- ✅ Autosave (encrypted chat persistence)
- ✅ Chat list and history management
- ✅ Filecoin archive (permanent storage)
- ✅ Archive recovery (cross-device sync)
- ✅ Context memory and summarization
- ✅ Ed25519 authentication

**Deployment workflow:**
```bash
# 1. Build Docker image
cd deploy/docker && ./build.sh

# 2. Deploy to Akash Console (manual)
# Copy deploy/akash/deploy-llama70.yaml
# Paste in Akash Console → Create Deployment

# 3. Update Cloudflare Worker with new Akash URL
# Edit cloudflare/workers/trinity-ai-proxy.js

# 4. Deploy frontend to ICP
cd trinity-icp && dfx deploy --ic trinity_frontend
```

### Local Testing Environment (TinyLlama)

**Minimal setup for AI inference testing ONLY:**

| Component | Details |
|-----------|---------|
| **Compute** | Local machine (Mac/Linux) |
| **Model** | TinyLlama 1.1B (~637MB) |
| **Backend** | Ollama via `deploy/local/start.sh` |
| **Storage** | ❌ NOT FUNCTIONAL |
| **Archive** | ❌ NOT FUNCTIONAL |
| **Proxy** | Direct localhost:8000 |
| **Cost** | Free |

**Features available locally:**
- ✅ AI chat generation (TinyLlama - lower quality)
- ✅ Health check endpoint
- ❌ Autosave (no storage backend)
- ❌ Chat list/history (no persistence)
- ❌ Filecoin archive (no Lighthouse config in local env)
- ❌ Archive recovery (no master bundle)
- ⚠️ Context memory (works but not persisted)

**Why local is limited:**
1. **No Akash disk:** Local Ollama doesn't have the same file system setup
2. **No Lighthouse config:** LIGHTHOUSE_API_KEY not configured locally by default
3. **Different backend path:** Local uses simplified startup, not full inference_server.py
4. **Purpose:** Quick iteration on AI inference and frontend UI, NOT storage features

**Local startup:**
```bash
# Start local backend (TinyLlama via Ollama)
cd deploy/local
./start.sh

# Backend runs at http://localhost:8000
# Only /health and /generate endpoints work reliably
```

### When to Use Each Environment

| Task | Environment | Reason |
|------|-------------|--------|
| Test AI response quality | **Local** | Fast iteration, free |
| Test UI rendering | **Local** | No backend needed for most UI |
| Test chat bubbles/animations | **Local** | Frontend-only |
| Test autosave system | **Production** | Requires Akash storage |
| Test Filecoin archive | **Production** | Requires Lighthouse API |
| Test archive recovery | **Production** | Requires master bundle |
| Test authentication flow | **Either** | Auth is frontend-only |
| Debug storage bugs | **Production** | Local has no storage |
| Final validation before release | **Production** | Full feature set |

### Testing New Backend Features

When implementing backend features that involve storage or Filecoin:

1. **Write the code** in `backend/inference_server.py`
2. **Build Docker image:** `cd deploy/docker && ./build.sh`
3. **Deploy to Akash:** Use Akash Console with updated YAML
4. **Test via production:** All storage features require Akash deployment
5. **Cannot test locally:** TinyLlama environment lacks storage infrastructure

### Environment Variables Comparison

**Production (Akash - set in YAML):**
```yaml
PROVIDER_ID: trinity-llama70b
MODEL_NAME: llama3.1:70b
MODEL_BACKEND: ollama
OLLAMA_HOST: http://localhost:11434
CHATS_DIR: /var/lib/trinity/chats
LIGHTHOUSE_API_KEY: cac651de...  # Lighthouse API key (required for archive)
GPU_TYPE: NVIDIA-A100
```

**Local Testing (set by start.sh):**
```bash
PROVIDER_ID: local-mac
MODEL_NAME: tinyllama:1.1b
MODEL_BACKEND: ollama
OLLAMA_HOST: http://localhost:11434
CHATS_DIR: $HOME/.trinity/chats  # May not be fully functional
FILECOIN_API_KEY: ""  # Not configured - archive won't work
```

### Common Mistake: Testing Storage Features Locally

❌ **Wrong approach:**
```bash
# Start local backend
./deploy/local/start.sh

# Try to test autosave → FAILS silently
# Try to test archive → FAILS with "API key not configured"
# Wastes time debugging local environment
```

✅ **Correct approach:**
```bash
# Build and deploy to Akash for storage testing
cd deploy/docker && ./build.sh
# Deploy to Akash Console
# Test storage features against production backend
```

---

## � Build & Deployment Processes

> **Summary:** Trinity has THREE independent deployment targets. Each can be updated separately, but code changes require specific rebuild steps.

### Component Overview

| Component | Where Deployed | Build Tool | When to Rebuild |
|-----------|----------------|------------|-----------------|
| **Backend** | Akash Network | Docker | When `backend/*.py` changes |
| **Frontend** | ICP (Internet Computer) | Vite + dfx | When `trinity-icp/src/*` changes |
| **ICP Backend Canister** | ICP | Cargo + dfx | When `trinity-icp/src/backend_canister/*` changes |
| **Cloudflare Workers** | Cloudflare | Wrangler | When proxy logic or Akash URL changes |

---

### 🐳 Docker + Akash (Backend)

**When to rebuild:**
- Changes to `backend/inference_server.py`
- Changes to `backend/icp_auth.py`
- Changes to `backend/requirements.txt`

**Process:**
```bash
# Step 1: Build Docker image and push to Docker Hub
cd /path/to/Trinity
./deploy/docker/build.sh

# This will:
# - Build gdubx/trinity-inference:v2-YYYYMMDD-HHMMSS
# - Push to Docker Hub
# - Auto-update all deploy/akash/*.yaml files with new image tag

# Step 2: Deploy to Akash (MANUAL via web console)
# 1. Go to https://console.akash.network
# 2. Find your deployment
# 3. Click "Update Deployment"
# 4. Paste contents of deploy/akash/deploy-llama70.yaml (or deploy-phi3.yaml)
# 5. Accept and wait for container restart

# Step 3: Verify deployment
curl https://<akash-url>/health
```

**Key files:**
- `deploy/docker/Dockerfile` - Container definition
- `deploy/docker/build.sh` - Build + push script
- `deploy/docker/startup.sh` - Container entrypoint
- `deploy/akash/deploy-*.yaml` - Akash deployment manifests

**Notes:**
- Akash URL changes every deployment (random subdomain)
- After Akash URL changes, update `cloudflare/workers/trinity-ai-proxy.js`
- Build script automatically updates YAML files with new image version

---

### 🌐 ICP Frontend Canister

**When to rebuild:**
- Changes to `trinity-icp/src/*.js`
- Changes to `trinity-icp/src/**/*.js`
- Changes to `trinity-icp/src/styles.css`
- Changes to `trinity-icp/src/index.html`

**Process:**
```bash
# From trinity-icp directory
cd trinity-icp

# Build frontend assets (Vite)
npm run build

# Deploy to ICP mainnet
dfx deploy --ic trinity_frontend

# This will:
# - Build JS/CSS bundle with Vite
# - Upload to ICP canister zc67k-kiaaa-aaaal-qtmiq-cai
# - Assets available at https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io
```

**Key files:**
- `trinity-icp/vite.config.js` - Bundler config
- `trinity-icp/dfx.json` - ICP canister config
- `trinity-icp/canister_ids.json` - Production canister IDs

**Notes:**
- Frontend-only changes don't require backend rebuild
- Uses version-based cache busting (see `config.js`)
- IIFE bundle format for file:// protocol support

---

### 🦀 ICP Backend Canister (Rust)

**When to rebuild:**
- Changes to `trinity-icp/src/backend_canister/src/lib.rs`
- Changes to `trinity-icp/src/backend_canister/trinity_backend.did`
- Changes to `trinity-icp/src/backend_canister/Cargo.toml`

**Process:**
```bash
# From trinity-icp directory
cd trinity-icp

# Build and deploy (dfx handles cargo build internally)
dfx deploy trinity_backend --network ic

# This will:
# - Compile Rust to WASM
# - Upload to ICP canister au5zq-2qaaa-aaaal-qtowa-cai
# - Upgrade canister code

# Verify deployment
dfx canister --network ic call trinity_backend health
dfx canister --network ic call trinity_backend get_canister_info
```

**Key files:**
- `trinity-icp/src/backend_canister/src/lib.rs` - Main canister code
- `trinity-icp/src/backend_canister/trinity_backend.did` - Candid interface
- `trinity-icp/Cargo.toml` - Workspace config

**Notes:**
- Canister must be deployed AFTER Akash if there are API changes
- Keep `.did` file in sync with Rust struct definitions
- Uses HTTPS Outcalls to communicate with Akash backend

---

### ☁️ Cloudflare Workers

**When to update:**
- Akash backend URL changes
- Proxy logic changes (CORS, routing)

**Process:**
```bash
# Edit the worker file directly
vim cloudflare/workers/trinity-ai-proxy.js

# Update AKASH_BACKEND constant with new URL
const AKASH_BACKEND = 'https://new-url.ingress.akashprovid.com';

# Deploy via Cloudflare Dashboard
# 1. Go to https://dash.cloudflare.com
# 2. Workers & Pages → trinity-ai-proxy
# 3. Click "Quick Edit"
# 4. Paste updated code
# 5. Deploy

# Or via Wrangler CLI:
wrangler deploy cloudflare/workers/trinity-ai-proxy.js
```

**Key files:**
- `cloudflare/workers/trinity-ai-proxy.js` - API proxy (trinityai.cc/api/*)
- `cloudflare/workers/trinity-frontend-proxy.js` - Frontend proxy (trinityai.cc → ICP)

---

### 📋 Common Deployment Scenarios

#### Scenario 1: Backend-only change (e.g., new endpoint)
```bash
# 1. Edit backend code
vim backend/inference_server.py

# 2. Build and push Docker
./deploy/docker/build.sh

# 3. Update Akash deployment (manual - console.akash.network)
# 4. If Akash URL changed, update Cloudflare worker
```

#### Scenario 2: Frontend-only change (e.g., UI fix)
```bash
cd trinity-icp
npm run build
dfx deploy --ic trinity_frontend
```

#### Scenario 3: Full-stack change (e.g., new API + UI)
```bash
# 1. Backend first
./deploy/docker/build.sh
# Update Akash via console

# 2. ICP Backend Canister (if using HTTPS Outcalls)
cd trinity-icp
dfx deploy trinity_backend --network ic

# 3. Frontend last
dfx deploy trinity_frontend --network ic
```

#### Scenario 4: ICP Canister API change (e.g., new endpoint)
```bash
cd trinity-icp

# 1. Update Rust code
vim src/backend_canister/src/lib.rs

# 2. Update Candid interface (MUST match Rust structs!)
vim src/backend_canister/trinity_backend.did

# 3. Deploy
dfx deploy trinity_backend --network ic
```

---

### ⚠️ Critical Reminders

1. **Candid/Rust Sync:** When changing ICP canister response types, update BOTH `lib.rs` AND `trinity_backend.did`. Mismatches cause deserialization errors.

2. **Akash URL Volatility:** Every Akash redeployment gets a new random URL. Update both:
   - `cloudflare/workers/trinity-ai-proxy.js`
   - `trinity-icp/src/backend_canister/src/lib.rs` (AKASH_URL constant)

3. **ICP Consensus:** For HTTPS Outcalls, responses must be deterministic. Use `/health/icp` instead of `/health` for ICP canister health checks.

4. **Build Order:** For full-stack changes: Akash → ICP Canister → Frontend

5. **Identity Safety:** Before ICP deploys, verify you're using the correct dfx identity:
   ```bash
   dfx identity whoami  # Should be "trinity"
   dfx identity get-principal  # Should match canister controller
   ```

---

## �📁 Project Structure

```
Trinity/
├── README.md                          # Quick start & project overview
├── STATUS.md                          # Deployment status & test results
├── DEPLOYMENT_INFO.md                 # Complete deployment guide
├── ORGANIZATION.md                    # Project organization reference
├── .gitignore                         # Python, Node, test data exclusions
│
├── trinity-icp/                       # 🎨 FRONTEND (ICP Canister)
│   ├── dfx.json                       # DFX CLI configuration (points to dist/)
│   ├── canister_ids.json              # Canister identifiers
│   ├── package.json                   # npm deps (Vite 7.3.1, Zustand 5.0.3)
│   ├── vite.config.js                 # Vite bundler config (IIFE format)
│   ├── scripts/
│   │   └── post-build.js              # Script injection after build
│   ├── dist/                          # 📦 PRODUCTION BUILD (deployed to ICP)
│   │   ├── index.html                 # Built HTML with injected scripts
│   │   ├── icp-auth.js                # Bundled ICP auth library
│   │   └── assets/
│   │       └── main-*.js              # IIFE-wrapped bundle (80KB)
│   └── src/                           # 💻 SOURCE CODE (modular architecture)
│       ├── app.js                     # Main app (1153 lines, orchestration)
│       ├── config.js                  # Environment detection (88 lines)
│       ├── index.html                 # Main HTML template
│       ├── styles.css                 # CSS styling (639 lines)
│       ├── state/
│       │   ├── store.js               # Zustand state management (295 lines)
│       │   └── contextMemory.js       # Conversation compression (75 lines)
│       ├── auth/
│       │   ├── authManager.js         # Ed25519 keypair management (210 lines)
│       │   ├── keyExportModal.js      # Key display modal (100 lines)
│       │   ├── auth-entry.js          # Auth entry point
│       │   ├── auth-client.js         # Auth client utilities
│       │   └── icp-auth.js            # ICP auth library source
│       ├── storage/
│       │   ├── autosave.js            # Debounced persistence (180 lines)
│       │   └── mock.js                # Test mode storage (85 lines)
│       ├── ui/
│       │   ├── index.js               # UI module aggregator
│       │   ├── domCache.js            # Element caching (45 lines)
│       │   ├── messages.js            # Message rendering (266 lines)
│       │   ├── sidebar.js             # Chat list rendering (109 lines)
│       │   ├── modals.js              # Dialog boxes (80 lines)
│       │   ├── notifications.js       # Toast notifications (65 lines)
│       │   └── rainbowBorder.js       # Rainbow border effects
│       └── modules/
│           └── archive.js             # Filecoin archival (210 lines)
│
├── backend/                           # 🖥️  BACKEND CODE
│   ├── inference_server.py            # Flask backend (1014 lines)
│   ├── icp_auth.py                    # Ed25519 verification (210 lines)
│   └── requirements.txt               # Python dependencies
│
├── deploy/                            # 🚀 DEPLOYMENT CONFIGS
│   ├── docker/                        # Docker build files
│   │   ├── Dockerfile                 # Container definition
│   │   ├── build.sh                   # Docker build & push script
│   │   └── startup.sh                 # Container entrypoint
│   ├── akash/                         # Akash SDL deployment configs
│   │   ├── deploy-llama70.yaml        # Llama 3.1 70B (PRODUCTION)
│   │   ├── deploy-qwen.yaml           # Qwen 2.5 72B
│   │   ├── deploy-mixtral.yaml        # Mixtral 8x22B
│   │   ├── deploy-llama3.yaml         # Llama 3.1 8B
│   │   └── deploy-phi3.yaml           # Phi-3 3.8B
│   └── local/                         # Local development
│       ├── docker-compose.yml         # Local dev setup
│       ├── start.sh                   # Local TinyLlama setup
│       ├── stop.sh                    # Stop local services
│       └── status.sh                  # Check local status
│
├── scripts/                           # 📜 ROOT SCRIPTS
│   ├── dev.sh                         # Start local development
│   ├── deploy.sh                      # Build & prepare deployment
│   ├── test-prod.sh                   # Test against production
│   ├── trinity-frontend.sh            # Frontend deployment helper
│   ├── diagnose-akash.sh              # Akash diagnostics
│   └── update-claude.sh               # Update CLAUDE.md
│
├── test/                              # 🧪 TESTING
│   ├── integration/                   # Integration tests
│   │   ├── test_filecoin_integration.py   # ✅ 4/4 passing
│   │   ├── test_phase2_integration.py     # Backend auth tests
│   │   ├── test_autosave_integration.py   # Autosave flow tests
│   │   ├── test_auth_backend.py           # Signature verification
│   │   ├── test_context_memory.py         # Context window tests
│   │   ├── test_signature_verification.py # Ed25519 tests
│   │   └── benchmark_models.py            # Model benchmarks
│   └── local/                         # Local testing
│       ├── docker-compose.local.yml   # Local Docker config
│       ├── start-local.sh             # Start local test env
│       └── LOCAL_TESTING.md           # Local dev guide
│
├── cloudflare/                        # ☁️  CLOUDFLARE WORKERS
│   └── workers/
│       ├── trinity-ai-proxy.js        # API proxy (trinityai.cc → Akash)
│       └── trinity-frontend-proxy.js  # Frontend proxy (domain → ICP)
│
├── docs/                              # 📚 DOCUMENTATION
│   ├── CLAUDE.md                      # This file (AI assistant ref)
│   ├── diagrams/                      # Architecture diagrams
│   │   ├── ARCHITECTURE.md
│   │   ├── trinity-network-architecture.md
│   │   └── trinity-storage-architecture.md
│   ├── plans/                         # Planning documents
│   │   └── next-steps.md              # Feature roadmap
│   └── user/                          # User documentation
│       └── quickstart.md              # Quick start guide
│
├── dev                                # 📜 ROOT WRAPPER: runs scripts/dev.sh
├── test-prod                          # 📜 ROOT WRAPPER: runs scripts/test-prod.sh
├── akash-deploy                       # 📜 ROOT WRAPPER: runs scripts/deploy.sh
└── icp-deploy                         # 📜 ICP DEPLOYMENT: builds & deploys both canisters
```


## 🔑 Key Identifiers & URLs

| Component | Value | Notes |
|-----------|-------|-------|
| **Production Domain** | `trinityai.cc` | Primary user-facing URL |
| **ICP Frontend Canister** | `zc67k-kiaaa-aaaal-qtmiq-cai` | Frontend assets canister |
| **ICP Backend Canister** | `au5zq-2qaaa-aaaal-qtowa-cai` | HTTPS Outcalls proxy to Akash |
| **ICP Direct URL** | `https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io` | Direct canister access |
| **API Endpoint** | `https://api.trinityai.cc` | Cloudflare Worker proxy |
| **Akash Backend** | `https://u2k74jdr358rt168vo6bmi8mas.ingress.akashprovid.com` | Production inference server (Jan 2026) - ⚠️ URL changes frequently |
| **Build Tool** | Vite 7.3.1 | IIFE bundler for file:// protocol |
| **State Management** | Zustand 5.0.3 | Immutable state with getters/setters |
| **Docker Hub** | `gdubx` | Container registry account |
| **Akash Wallet** | `akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp` | Deployment wallet |
| **Lighthouse API Key** | Set in Akash YAML | Filecoin upload credentials |
| **Test CID** | `QmZeYzPA3jTYKmjHDZzgDg4kEGTf6R1EUpaNsnKHKCLHoy` | Example archive CID |

---

## � Modular Frontend Architecture (Phase 4)

### Overview
The frontend codebase underwent a major refactoring in January 2026 to improve maintainability, testability, and developer experience. The original monolithic `app.js` (1846 lines) was split into 13 focused modules.

### Module Structure

#### 1. State Management (`state/`)
**Key Files:**
- `state/store.js` (295 lines) - Zustand-based state management
- `state/contextMemory.js` (75 lines) - Conversation compression logic

**Critical Pattern:**
```javascript
// ❌ WRONG - Direct assignment fails (read-only getters)
State.isAuthenticated = true;
State.chatHistory = [...];

// ✅ CORRECT - Use setter methods
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

**Architecture:**
- Internal Zustand store with private mutations
- External API layer with read-only getters
- All mutations via explicit setter methods
- Prevents silent failures from direct property assignment

**Key State:**
- `chatHistory` - Full conversation (persisted to Akash)
- `contextMemory` - Last 6 messages (sent to LLM)
- `conversationSummary` - Compressed older messages
- `userMemory` - Persistent facts across all chats
- `allChats` - User's chat list with metadata

#### 2. Authentication (`auth/`)
**Key Files:**
- `auth/authManager.js` (210 lines) - Ed25519 keypair management
- `auth/keyExportModal.js` (100 lines) - Security modal for key display

**Features:**
- Browser-based Ed25519 keypair generation
- Principal ID derivation from public key
- Private key export to hex format
- localStorage persistence with auto-restore
- Request signing with timestamp verification

**API:**
```javascript
await AuthManager.initialize();        // Restore from localStorage
await AuthManager.login();              // Generate new keypair
await AuthManager.logout();             // Clear identity
AuthManager.signMessage(message);       // Sign for backend
AuthManager.getPublicKeyHex();          // For signature verification
showKeyExportModal(keyHex, principal);  // Display security modal
```

#### 3. Storage (`storage/`)
**Key Files:**
- `storage/autosave.js` (180 lines) - Debounced persistence with retry
- `storage/mock.js` (85 lines) - Test mode storage

**Features:**
- 2-second debounce after each message
- Exponential backoff retry (5 attempts max)
- Success callbacks for UI refresh
- Rainbow wave animation during save
- Automatic title generation

**Usage:**
```javascript
AutosaveManager.scheduleAutosave(
    chatData,           // {messages, title}
    chatId,             // Current chat ID
    isAuthenticated,    // Auth status
    showIndicator,      // UI callback
    executeSave         // Save function
);
```

#### 4. UI Modules (`ui/`)
**Key Files:**
- `ui/index.js` - Module aggregator
- `ui/domCache.js` (45 lines) - Element caching for performance
- `ui/messages.js` (266 lines) - Message rendering & typing animation
- `ui/sidebar.js` (109 lines) - Chat list & auth buttons
- `ui/modals.js` (80 lines) - Dialog boxes
- `ui/notifications.js` (65 lines) - Toast notifications

**Critical Fixes:**
- Line 13 in `messages.js`: `State.setGenerating(isGenerating)` instead of direct assignment
- Line 104: `State.setChatStarted(true)` prevents chat bubble rendering failures
- Lines 138/146: `State.setKeyboardOpen()` for mobile keyboard handling

**Rendering Flow:**
```
User types → State.addMessage() → UI.showMessage() → typeMessage()
→ DOM update → autosave trigger → sidebar refresh
```

#### 5. Archive Module (`modules/`)
**Key File:**
- `modules/archive.js` (210 lines) - Filecoin archival logic

**Features:**
- Individual chat archiving to Lighthouse/Filecoin
- Multi-gateway IPFS recovery (4 gateways, 30s timeout)
- CID-based recovery dialog
- 10-archive limit enforcement
- Automatic new chat on current chat archive

#### 6. Configuration (`config.js`)
**Key File:**
- `config.js` (88 lines) - Environment detection & API URLs

**Features:**
- Automatic backend detection (localhost vs Akash)
- User preference persistence (localStorage)
- Environment switcher UI in dev mode
- File:// protocol support for local testing

**API URL Logic:**
```javascript
// Production domains → Akash backend
if (hostname === 'trinityai.cc' || hostname.includes('icp0.io')) {
    return 'http://hdol1m0mohfll4s4t8mhip33sg.ingress.a100.dsm.val.akash.pub';
}

// Development → localhost (if available)
if (isDevelopment && localAvailable) {
    return 'http://localhost:8000';
}
```

### Build System (Vite 7.3.1)

**Configuration:**
```javascript
// vite.config.js
export default {
    build: {
        lib: {
            entry: 'src/app.js',
            name: 'Trinity',
            formats: ['iife'],        // Critical for file:// protocol
            fileName: () => 'main.js'
        },
        rollupOptions: {
            output: {
                entryFileNames: 'assets/[name]-[hash].js',
                format: 'iife'
            }
        }
    }
}
```

**Post-Build Pipeline:**
```bash
npm run build
→ Vite bundles to dist/assets/main-[hash].js (IIFE format)
→ scripts/post-build.js injects <script> tags into dist/index.html
→ Copies icp-auth.js to dist/
→ Validates window.Actions/API/UI/State exposure
→ Result: dist/ folder ready for dfx deploy
```

**Deployment:**
```bash
# dfx.json now points to dist/ folder
dfx deploy --network ic trinity_frontend
# Deploys: dist/index.html + dist/assets/main-*.js + dist/icp-auth.js
```

### Critical Bug Fix (January 2026)

**Problem:** Application completely broken after initial modularization. All buttons non-functional, chat bubbles not appearing, logout broken.

**Root Cause:** Zustand State object uses read-only getters. Direct assignments like `State.isAuthenticated = true` fail silently with error: "Cannot set property isAuthenticated of #<Object> which has only a getter"

**Solution:** Converted ALL State mutations to use setter methods:
- Fixed 9 locations in `app.js`
- Fixed 4 locations in `ui/messages.js`
- Added 2 new setters to `state/store.js`

**Files Modified:**
- `src/app.js` - Lines 334, 335, 476, 505, 526, 547, 664-666, 820-821
- `src/ui/messages.js` - Lines 13, 104, 138, 146
- `src/state/store.js` - Added `incrementTestResponseIndex()`, `setKeyboardOpen()`

**Testing:**
- Debug tool (`debug.html`) revealed silent failures
- Grep searches found 15+ instances of direct mutations
- Fixed in two passes (app.js → ui/messages.js)
- Build validates window.Actions exposure
- All features now functional (auth, chat, logout, save)

### Event Handling Pattern

**Document-Level Delegation:**
```javascript
// Modal click protection (z-index >= 10000)
document.addEventListener('click', (e) => {
    // Ignore clicks inside modals
    let parent = e.target;
    while (parent) {
        const zIndex = window.getComputedStyle(parent).zIndex;
        if (zIndex && parseInt(zIndex) >= 10000) return;
        parent = parent.parentElement;
    }
    
    // Route data-action buttons
    const btn = e.target.closest('[data-action]');
    if (btn?.dataset.action === 'login') Actions.login();
    // ... more actions
});
```

**Modal Event Isolation:**
```javascript
// keyExportModal.js - Prevent event bubbling
modal.addEventListener('click', (e) => {
    e.stopPropagation();  // Block all modal clicks from reaching document
}, true);

confirmBtn.addEventListener('click', (e) => {
    e.stopImmediatePropagation();  // Prevent any other listeners
    if (confirm('Are you sure?')) modal.remove();
});
```

### Development Workflow

**Local Testing:**
```bash
# Option 1: Source files (unbundled, for quick iteration)
open trinity-icp/src/index.html

# Option 2: Production build (bundled, for deployment testing)
npm run build
open trinity-icp/dist/index.html  # ← USE THIS for accurate testing
```

**Browser Cache:** Always hard refresh (Cmd+Shift+R) after rebuilding to avoid serving cached old bundles.

---

## �🧪 Test Results

### Filecoin Integration Tests (Local)
```bash
$ python3 test/integration/test_filecoin_integration.py

============================================================
TRINITY FILECOIN INTEGRATION TEST
============================================================
Backend URL: http://localhost:5001
Model: tinyllama:1.1b (637MB)
Lighthouse API: Configured ✓

✅ PASS  HEALTH - Backend healthy
✅ PASS  API_KEY - Lighthouse API configured  
✅ PASS  ARCHIVE - Chat uploaded to Lighthouse
         CID: QmZeYzPA3jTYKmjHDZzgDg4kEGTf6R1EUpaNsnKHKCLHoy
✅ PASS  RECOVERY - 4 messages downloaded from IPFS

Total: 4/4 tests passed 🎉
============================================================
```

### Production Validation
- ✅ Frontend deployed to ICP (3 deployments during session)
- ✅ Backend deployed to Akash with Filecoin support
- ✅ Archive button visible on sidebar hover
- ✅ End-to-end archive flow tested
- ✅ All YAML files configured with LIGHTHOUSE_API_KEY
- ✅ Multi-gateway IPFS recovery working

---
---

## 🔧 Environment Variables

### Production Backend (Akash)
```yaml
PROVIDER_ID: trinity-llama70b
MODEL_NAME: llama3.1:70b
GPU_TYPE: NVIDIA-A100
MAX_QUEUE_SIZE: 5
OLLAMA_HOST: http://localhost:11434
LIGHTHOUSE_API_KEY: cac651de...  # Lighthouse API key
CHATS_DIR: /var/lib/trinity/chats
```

### Local Development
```bash
# Backend
export LIGHTHOUSE_API_KEY="your-lighthouse-api-key"
export CHATS_DIR="$HOME/.trinity/chats"
export MODEL_NAME="tinyllama:1.1b"
export OLLAMA_HOST="http://localhost:11434"

# Start local backend
cd deployment && ./start-local.sh
```

### Frontend Configuration
```javascript
// trinity-icp/src/config.js
const CONFIG = {
    get API_URL() {
        const hostname = window.location.hostname;
        if (hostname === 'trinityai.cc' || 
            hostname === 'www.trinityai.cc' ||
            hostname.includes('icp0.io')) {
            return 'https://api.trinityai.cc';  // Production (Cloudflare Worker)
        }
        return 'http://localhost:5000';  // Local development
    },
    HEALTH_CHECK_INTERVAL_MS: 30000,
    TYPE_ANIMATION_MAX_MS: 1500,
    // ... more config
};
```

---

## 🚀 Deployment Commands

### Frontend (ICP)
```bash
cd trinity-icp

# Deploy to mainnet
dfx deploy --ic trinity_frontend

# Expected output:
# Deployed canisters.
# URLs:
#   Frontend canister via browser
#     trinity_frontend: https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io/
```

### Backend (Akash)
```bash
cd deploy/docker

# Build and push Docker image
./build.sh
# Creates: gdubx/trinity-inference:v2-YYYYMMDD-HHMMSS
# Updates all 5 YAML files automatically

# Deploy via Akash Console:
# 1. Go to https://console.akash.network
# 2. Update deployment with deploy/akash/deploy-llama70.yaml
# 3. Wait for deployment (2-5 minutes)
# 4. Note new ingress URL
```

### Local Testing
```bash
# Start local backend with TinyLlama
cd deploy/local && ./start.sh
# Returns PID for management

# Run integration tests
python3 test/integration/test_filecoin_integration.py  # 4/4 should pass

# Stop local backend
pkill -f "python3.*inference_server"
```

### Cloudflare Workers
```bash
# Update API proxy
# Edit: cloudflare/workers/trinity-ai-proxy.js
# Deploy via Cloudflare Dashboard → Workers & Pages

# Update frontend proxy
# Edit: cloudflare/workers/trinity-frontend-proxy.js
# Deploy via dashboard
```

---

## 📊 Key Metrics & Performance

| Metric | Value | Notes |
|--------|-------|-------|
| **Frontend Size** | ~500KB | Minified assets (app.js + libs) |
| **Backend Image** | ~5GB | Includes Ollama + base model |
| **Model Size** | 40GB | Llama 3.1 70B weights |
| **Response Time** | 2-5s | Typical for 70B model on A100 |
| **Encryption** | AES-256-GCM | Authenticated encryption |
| **Key Derivation** | PBKDF2 | 100,000 iterations, SHA-256 |
| **Authentication** | Ed25519 | 256-bit elliptic curve |
| **Context Window** | 6 messages | Sliding window for LLM |
| **Summarization** | Every 15 msgs | Compresses older context |
| **Autosave Debounce** | 2 seconds | Prevents excessive saves |
| **Max Retries** | 5 attempts | Exponential backoff |

### Cost Structure

| Service | Tier | Monthly Cost |
|---------|------|--------------|
| Cloudflare | Free | $0 (Workers, DNS, SSL) |
| ICP Canister | Pay-per-use | ~$1-5 (cycles for compute/storage) |
| Akash Network | Pay-per-use | ~$50 (2x A100 80GB) |
| Lighthouse (Filecoin) | Free | $0 (verified Filecoin deals included) |
| Domain | Annual | ~$12/year (trinityai.cc) |
| **Total** | | **~$50-55/month** |

### Lighthouse/Filecoin Setup

Trinity uses **Lighthouse SDK** for direct IPFS/Filecoin integration with verified deals:

1. **Sign up:** Visit https://files.lighthouse.storage
2. **Generate API Key:** Account → API Key → Generate
3. **Configure backend:** Set environment variable `LIGHTHOUSE_API_KEY="cac651de..."`
4. **Verify:** Check `/health` endpoint shows `filecoin_configured: true`

**Storage:** Encrypted chats uploaded via Lighthouse SDK → pinned to IPFS → archived with verified Filecoin deals. Recovery uses Lighthouse gateway (https://gateway.lighthouse.storage/ipfs/{cid}) with fallback to public gateways.

### Available Models (Akash SDLs)

| Model | YAML File | GPU | Memory | Est. Cost |
|-------|-----------|-----|--------|-----------|
| Llama 3.1 70B | deploy-llama70.yaml | 2x A100 | 180GB | ~$50/mo |
| Qwen 2.5 72B | deploy-qwen.yaml | 1x A100 | 180GB | ~$50/mo |
| Mixtral 8x22B | deploy-mixtral.yaml | 2x A100 | 200GB | ~$50/mo |
| Llama 3.1 8B | deploy-llama3.yaml | 1x RTX 4090 | 32GB | ~$15/mo |
| Phi-3 3.8B | deploy-phi3.yaml | 1x RTX 3090 | 16GB | ~$8/mo |

---

## ⚠️ Known Failures & Lessons Learned

### Automated Akash Deployment
**Status:** ❌ FAILED - Must use Akash Console manually

**What we tried:**
- Akash CLI deployment automation
- Scripted SDL deployment with `akash tx deployment create`
- Automated bid selection and lease creation

**Why it failed:**
- Complex authentication flow (wallet signing)
- Provider bid acceptance requires manual verification
- Network connectivity issues with CLI
- State management between deployment steps unreliable

**Solution:** Use Akash Console web interface at https://console.akash.network
1. Build Docker image locally → push to Docker Hub
2. Manually create/update deployment in Console
3. Select provider bid from available options
4. Monitor logs in Console during startup

**Documented in:** Lines 1273-1330 (Full Production Deployment Workflow)

### Zustand State Read-Only Getters
**Status:** ❌ CRITICAL BUG - Silent failures

**What happened:**
- Modularized app.js to use Zustand for state management
- Direct property assignments like `State.isAuthenticated = true` failed silently
- Application completely broken: buttons non-functional, logout broken, no error messages

**Root cause:**
- Zustand uses read-only getters for state properties
- Direct assignments throw error: "Cannot set property X of #<Object> which has only a getter"
- Error not visible in production builds

**Solution:** ALL state mutations must use setter methods:
- ❌ `State.isAuthenticated = true`
- ✅ `State.setAuthenticated(principal, timestamp)`
- ❌ `State.chatHistory = [...]`
- ✅ `State.setChatHistory(messages)`

**Files affected:** 15+ locations across app.js and UI modules
**Documented in:** Phase 4 modularization section (lines 280-320)

### Cold Start Performance
**Status:** ✅ EXPECTED BEHAVIOR - Not a bug

**What seems like a problem:**
- First request after idle takes 20-30 seconds
- Users report "slow" or "hanging" responses

**Why it happens:**
- Ollama unloads models from VRAM after inactivity (cost efficiency)
- Llama 70B = 40GB weights need to reload into GPU memory
- This is normal behavior for Akash deployments

**Solution:** Set expectations, don't "fix" it:
- Document cold start time in UI
- Consider keep-alive pings (increases costs)
- Or use smaller models (Llama 8B loads faster)

**Documented in:** TROUBLESHOOTING.md (Cold Start Too Slow section)

---

## 🔐 Security Architecture

### Authentication Flow
```
1. User generates Ed25519 keypair in browser
2. Private key (64 bytes) stored in localStorage  
3. Public key (32 bytes) hashed → Principal ID (base32)
4. Every API request signed with private key
5. Backend verifies signature with public key
6. Timestamp validation (5-minute window)
```

### Encryption Flow
```
1. Principal ID used as password
2. PBKDF2 derives 256-bit AES key (100k iterations)
3. Random 16-byte salt per file
4. Random 12-byte IV per encryption
5. AES-256-GCM encrypts chat data
6. 16-byte auth tag ensures integrity
```

### Storage Security
- **Browser:** Private keys in localStorage (self-custody)
- **Akash:** Encrypted JSON files (cannot decrypt without principal)
- **Filecoin:** Encrypted files on IPFS (publicly accessible but encrypted)
- **Zero-knowledge:** No server stores user's private key or principal password

### API Endpoints (Auth Required)

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/health` | GET | Health check | No |
| `/generate` | POST | LLM generation | No |
| `/stats` | GET | Performance stats | No |
| `/chat/autosave` | POST | Save encrypted chat | ✅ Ed25519 |
| `/chat/list` | GET | List user's chats | ✅ Ed25519 |
| `/chat/<chatId>` | GET | Load specific chat | ✅ Ed25519 |
| `/chat/<chatId>` | DELETE | Delete chat | ✅ Ed25519 |
| `/chat/<chatId>/archive` | POST | Archive to Filecoin | ✅ Ed25519 |
| `/chat/recover-archives` | GET | Recover all archives for user | ✅ Ed25519 |
| `/chat/archive/<cid>` | GET | Download specific archive by CID | ✅ Ed25519 |

### CORS Configuration
```javascript
// cloudflare/workers/trinity-api-proxy.js
const ALLOWED_ORIGINS = [
  'https://trinityai.cc',
  'https://www.trinityai.cc',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',
  'http://localhost:8000',  // Local dev only
];

const allowedPaths = [
  '/health', '/generate', '/stats',
  '/chat/autosave', '/chat/list',
  '/chat/', // Matches /chat/{chatId}, /chat/recover-archives, /chat/archive/{cid}
];
```

---

## 📦 Frontend Architecture

### 1. Frontend (`trinity-icp/src/`)

**Type:** Modular HTML/CSS/JS application with Vite bundling
- `index.html` - HTML structure and DOM
- `app.js` - Main application orchestration
- `config.js` - Environment detection and API URLs
- `styles.css` - CSS styling and responsive design (639 lines)
- `auth/` - Authentication modules (authManager.js, icp-auth.js, etc.)
- `state/` - State management (store.js, contextMemory.js)
- `storage/` - Persistence (autosave.js, mock.js)
- `ui/` - UI modules (messages.js, sidebar.js, modals.js, etc.)

**Technologies:**
- Vanilla JavaScript (no frameworks)
- Marked.js v11.1.1 (Markdown rendering)
- Highlight.js v11.9.0 (syntax highlighting)
- DOMPurify v3.0.6 (XSS protection)
- @dfinity/agent@3.4.3, @dfinity/identity@3.4.3, @dfinity/principal@3.4.3, @dfinity/candid@3.4.3
- esbuild for bundling ICP libraries
- CSS Grid/Flexbox with dark theme

#### Frontend Architecture (Refactored January 2026)

The frontend is split into three files with JavaScript organized into 6 distinct modules:

**index.html** (80 lines)
- DOCTYPE, meta tags, link to stylesheets
- Link to external libraries (Highlight.js, Marked, DOMPurify)
- Semantic HTML structure (app-container, sidebar, main content area)
- Script tags loading external files (styles.css, app.js)

**styles.css** (639 lines)
- CSS variables and resets
- Component styling (sidebar, messages, input, buttons)
- Animations and color definitions (@keyframes rainbow, bounce)
- Mobile responsive media queries (768px and 576px breakpoints)

**app.js** (1609 lines)
```
├── CONFIG      (lines 16-55)    - Configuration constants
├── State       (lines 60-330)   - Centralized application state
├── API         (lines 335-570)  - Backend communication layer
├── Auth        (lines 50-270)   - Self-custody authentication
├── UI          (lines 575-1100) - DOM manipulation and rendering
├── Actions     (lines 1200-1450)- Business logic / user actions
├── init()      (lines 1500-1590)- Application initialization
└── Exports     (lines 1590-1609)- Global function exports for HTML
```

#### CONFIG Module

All configuration constants in one place:

```javascript
const CONFIG = {
    get API_URL() { /* returns URL based on hostname */ },
    HEALTH_CHECK_INTERVAL_MS: 30000,
    KEYBOARD_THRESHOLD: 0.75,
    TYPE_ANIMATION_MAX_MS: 1500,
    TYPE_BASE_SPEED_MS: 20,
    TEST_MODE: false,
    TEST_RESPONSES: [...]
};
```

#### State Module

Centralized mutable state with helper methods:

```javascript
const State = {
    // Chat state
    chatStarted: false,
    chatHistory: [],        // Array of {role: 'user'|'assistant', content: string}
    currentChatId: null,
    currentUserId: null,

    // UI state
    isGenerating: false,    // Prevents double-submit
    keyboardOpen: false,
    initialViewportHeight: number,

    // Cleanup tracking
    healthCheckIntervalId: null,

    // Context memory (LLM short-term memory) - FULLY FUNCTIONAL
    contextMemory: [],      // Last 6 messages for LLM context
    CONTEXT_WINDOW_SIZE: 6,

    // Conversation summarization (long-term memory) - FULLY FUNCTIONAL
    conversationSummary: null,  // Compressed history of older messages
    lastSummaryAt: 0,           // Message count when last summarized
    SUMMARY_INTERVAL: 15,       // Summarize every 15 messages

    // Authentication state - FULLY FUNCTIONAL
    isAuthenticated: false,     // User logged in with key
    principal: null,            // ICP Principal ID (derived from keypair)
    authenticatedSince: null,   // Timestamp of login

    // Methods
    reset(),                // Clear for new chat
    generateChatId(),       // Create unique ID
    getUserId(),            // Get/create from localStorage
    addMessage(role, content),
    updateContextMemory(),  // Maintain 6-message window
    getContextForLLM(),     // Get context + summary as system message
    compressContext()       // Async: summarize messages 1-(N-6)
};
```

#### Auth Module

Self-custody key management with Ed25519 keypairs:

| Method | Purpose |
|--------|---------|
| `Auth.initialize()` | Verify window.ICPAuth loaded, restore saved key from localStorage |
| `Auth.login()` | Generate new Ed25519KeyIdentity, export private key, show security modal |
| `Auth.logout()` | Clear identity and localStorage |
| `Auth.showKeyExportModal(hex)` | Display private key with copy button and security warnings |
| `Actions.importKey()` | Restore identity from pasted private key hex string |
| `Actions.exportKey()` | Re-display private key for logged-in user |

**Key Storage:**
- localStorage: `trinity_identity_key` (hex), `trinity_principal` (text)
- Auto-restore on page load if key exists
- Principal ID format: `xxn7o-7cigj-hygmy-s7...` (63 chars)
```

#### API Module

Centralized fetch wrappers with error handling:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `API.healthCheck()` | GET `/health` | Check backend connection |
| `API.generate(prompt, temp, skipContext)` | POST `/generate` | Send prompt with context (unless skipContext=true), get AI response |

#### UI Module

All DOM manipulation consolidated:

| Method | Purpose |
|--------|---------|
| `UI.init()` | Cache DOM element references |
| `UI.setGenerating(bool)` | Toggle loading state, disable input |
| `UI.showMessage(type, content, animate)` | Add message to chat |
| `UI.typeMessage(div, text)` | Typing animation for AI responses |
| `UI.removeMessage(id)` | Remove message by ID |
| `UI.clearMessages()` | Clear chat, show empty state |
| `UI.showChatArea()` | Hide empty state, show messages |
| `UI.updateConnectionStatus(...)` | Update sidebar status indicator |
| `UI.renderChatHistory()` | Render State.chatHistory to DOM |
| `UI.renderSidebar()` | Render auth buttons and chat list |
| `UI.resetInput()` | Clear input field |
| `UI.autoResize(textarea)` | Expand textarea as user types |
| `UI.handleKeyboardChange()` | Mobile keyboard visibility |
| `UI.scrollToBottom()` | Scroll messages container |
| `UI.showSummarizationIndicator()` | Show toast notification for context compression |
| `UI.showAutosaveIndicator(status)` | Show autosave status indicator |
| `UI.hideAutosaveIndicator()` | Hide autosave indicator |

#### Autosave Module

Automatic chat persistence:

| Method | Purpose |
|--------|---------|
| `Autosave.scheduleAutosave(chatData)` | Debounce and queue save (2s delay) |
| `Autosave.executeAutosave()` | Execute the actual save to backend |
| `Autosave.handleAutosaveError(error)` | Retry logic with exponential backoff |

#### Auth Module

Self-custody authentication:

| Method | Purpose |
|--------|---------|
| `Auth.initialize()` | Restore identity from localStorage |
| `Auth.login()` | Generate new Ed25519 identity |
| `Auth.logout()` | Clear localStorage and state |
| `Auth.signMessage(message)` | Sign requests with Ed25519 key |
| `Auth.getPublicKeyHex()` | Get public key for verification |
| `Auth.showKeyExportModal(privateKey)` | Display private key for user to save |

#### Actions Module

Business logic separated from UI:

| Method | Purpose |
|--------|---------|
| `Actions.checkConnection()` | Health check, update status |
| `Actions.generate()` | Main chat flow: validate → send → display → autosave |
| `Actions.newChat()` | Reset state for new conversation |
| `Actions.login()` | Trigger ICP authentication |
| `Actions.logout()` | Clear auth and reset state |
| `Actions.importKey()` | Restore identity from hex private key |
| `Actions.exportKey()` | Show private key modal |
| `Actions.loadChats()` | Fetch user's saved chats from backend |
| `Actions.loadChat(chatId)` | Load specific chat by ID |
| `Actions.deleteChat(chatId)` | Delete chat from backend |
| `Actions.toggleSidebar()` | Show/hide sidebar (mobile) |
| `Actions.handleKeyDown(event)` | Enter key to send |

#### Cached DOM Elements

```javascript
UI.elements = {
    messagesContainer,  // #messagesContainer
    emptyState,         // #emptyState
    promptInput,        // #promptInput
    sendBtn,            // #sendBtn
    chatArea,           // #chatArea
    sidebar,            // #sidebar
    statusDot,          // #statusDot
    statusText,         // #statusText
    providerInfo,       // #providerInfo
    modelInfo,          // #modelInfo
    inputContainer,     // #inputContainer
    toggleSidebarBtn,   // .toggle-sidebar-btn
    sidebarToggleBtn,   // .sidebar .toggle-btn
    newChatBtn,         // .new-chat-btn
    attachBtn           // .attach-btn
};
```

#### Event Flow

```
User types → UI.autoResize() → Enable send button
User clicks Send → Actions.generate():
  1. Validate input (non-empty, not already generating)
  2. Initialize chat if first message (State.chatStarted)
  3. UI.setGenerating(true) - disable input
  4. State.addMessage('user', prompt)
  5. State.updateContextMemory() - maintain 6-message window
  6. UI.showMessage('user', prompt)
  7. Show loading indicator
  8. API.generate(prompt) calls State.getContextForLLM() internally
     - Gets summary (if exists) + last 6 messages
     - Sends as contextMemory array with system message
  9. Remove loading indicator
  10. State.addMessage('assistant', response)
  11. State.updateContextMemory() - add AI response to context
  12. Check if chatHistory.length >= 15 → State.compressContext()
      - Summarizes messages 1-(N-6) using skipContext=true
      - Stores in State.conversationSummary
      - Next request will include summary as system message
  13. UI.typeMessage() - animate response
  14. UI.setGenerating(false) - re-enable input
```

#### API URL Logic

```javascript
// In app.js CONFIG.API_URL getter (lines 20-28):
if (hostname === 'trinityai.cc' ||
    hostname === 'www.trinityai.cc' ||
    hostname.includes('icp0.io')) {
    return 'https://api.trinityai.cc';  // Production
}
return 'http://...';  // Development fallback
```

---

### 2. API Proxy (`cloudflare/workers/trinity-ai-proxy.js`)

**Purpose:** Route `api.trinityai.cc/*` → Akash backend with CORS

**Configuration:**
```javascript
// ⚠️ Akash Backend URL changes frequently - check https://console.akash.network
const AKASH_BACKEND = 'http://cls1e8des1db50r65f6dpc8c7g.ingress.a100.dsm.val.akash.pub';

const ALLOWED_ORIGINS = [
  'https://trinityai.cc',
  'https://www.trinityai.cc',
  'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',
  'http://localhost:8000',
];

const allowedPaths = ['/health', '/generate', '/stats'];
```

**CORS Headers:**
- `Access-Control-Allow-Methods`: GET, POST, OPTIONS
- `Access-Control-Allow-Headers`: Content-Type, Accept
- `Access-Control-Max-Age`: 86400

**Security:** Origin whitelist, endpoint whitelist, 404 for unknown paths

---

### 3. Frontend Proxy (`cloudflare/workers/trinity-frontend-proxy.js`)

**Purpose:** Route `trinityai.cc/*` → ICP Canister

**Configuration:**
```javascript
const ICP_CANISTER_URL = 'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io';
```

**Behavior:** Simple pass-through proxy, preserves all headers/paths

---

### 4. Backend (`backend/inference_server.py`)

**Type:** Flask + Ollama inference server (1013 lines with auth, autosave & Filecoin)

**Dependencies:**
- flask >= 3.0.0
- flask-cors >= 4.0.0
- requests >= 2.31.0
- psutil >= 5.9.0
- APScheduler >= 3.10.4
- cryptography >= 41.0.0
- pycryptodome >= 3.19.0

**Key Classes:**

| Class | Purpose |
|-------|---------|
| `MetricsCollector` | Track requests, latency, success rate |
| `EncryptionUtils` | AES-256-GCM encryption for chat storage |

**API Endpoints:**

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | No | Health check with system metrics |
| `/generate` | POST | No | LLM text generation (supports context memory) |
| `/stats` | GET | No | Performance statistics |
| `/chat/autosave` | POST | Yes | Save chat with encryption |
| `/chat/list` | GET | Yes | List user's saved chats |
| `/chat/{chatId}` | GET | Yes | Load specific chat |
| `/chat/{chatId}` | DELETE | Yes | Delete chat |
| `/chat/{chatId}/archive` | POST | Yes | Archive to Filecoin/IPFS |
| `/chat/recover-archives` | GET | Yes | Recover all user's archives from Filecoin |
| `/chat/archive/{cid}` | GET | Yes | Download specific archive by CID |

**Authentication:**
- All `/chat/*` endpoints require ICP signature verification
- `@require_auth` decorator validates Ed25519 signatures
- Sets `request.principal` for access control

**Environment Variables:**
```bash
PROVIDER_ID=akash-provider-1
MODEL_NAME=qwen2.5:72b  # or llama3.1:70b, mixtral:8x22b, etc.
GPU_TYPE=NVIDIA-A100
OLLAMA_HOST=http://localhost:11434
MAX_QUEUE_SIZE=10
CHATS_DIR=/var/lib/trinity/chats  # or $HOME/.trinity/chats for local dev
FILECOIN_API_KEY=<pinata-jwt-token>  # Optional: for Filecoin archival
```

**Generate Request/Response:**
```json
// Request
{
  "prompt": "Hello", 
  "max_length": -1, 
  "temperature": 0.7,
  "contextMemory": [
    {"role": "user", "content": "Previous message"},
    {"role": "assistant", "content": "Previous response"}
  ]
}

// Response
{
  "generated_text": "...",
  "model": "qwen2.5:72b",
  "provider_id": "trinity-qwen72b",
  "latency_ms": 2345.6,
  "tokens_generated": 150
}
```

---

### 5. ICP Configuration

**dfx.json:**
```json
{
  "canisters": {
    "trinity_frontend": {
      "type": "assets",
      "source": ["dist"]
    }
  }
}
```

**canister_ids.json:**
```json
{
  "trinity_backend": {"ic": "au5zq-2qaaa-aaaal-qtowa-cai"},
  "trinity_frontend": {"ic": "zc67k-kiaaa-aaaal-qtmiq-cai"}
}
```

**.ic-assets.json5:** Security headers, CSP policy, caching rules

**.well-known/ic-domains:**
```
trinityai.cc
www.trinityai.cc
```

---

### 6. Docker Configuration

**Base Image:** `nvidia/cuda:12.2.0-runtime-ubuntu22.04`

**Exposed Ports:**
- `8000`: Flask inference server
- `11434`: Ollama API (internal)

**Startup Sequence (startup.sh):**
1. Start Ollama service
2. Wait for Ollama ready (60s timeout)
3. Pull AI model
4. Start Flask server
5. Monitor both processes

---

### 7. Akash Deployment Manifests

| File | Model | GPU | Memory | Price |
|------|-------|-----|--------|-------|
| `deploy-qwen.yaml` | qwen2.5:72b | A100 (1x) | 180GB | ~$50/mo |
| `deploy-llama70.yaml` | llama3.1:70b | A100 (2x) | 180GB | ~$50/mo |
| `deploy-mixtral.yaml` | mixtral:8x22b | A100 (2x) | 200GB | ~$50/mo |
| `deploy-llama3.yaml` | llama3.1:8b | RTX 4090 (1x) | 32GB | ~$15/mo |
| `deploy-phi3.yaml` | phi3:3.8b | RTX 3090 (1x) | 16GB | ~$8/mo |

---

## Data Flow

### Page Load
```
Browser → Cloudflare (trinityai.cc) → Worker → ICP Canister → HTML/JS/CSS
```

### Chat Message
```
Browser → Cloudflare (api.trinityai.cc) → Worker → Akash Backend → Ollama → Response
```

### Frontend Initialization
```
DOMContentLoaded → init()
  ├── UI.init() - cache DOM elements
  ├── marked.setOptions() - configure markdown
  ├── Attach event listeners
  ├── Collapse sidebar (mobile)
  ├── Actions.checkConnection() - initial health check
  └── setInterval(checkConnection) - periodic health check
```

---

## Common Tasks

### Deploy Frontend to ICP
```bash
cd trinity-icp
dfx deploy --ic trinity_frontend
```

### Update Cloudflare Worker
1. Edit worker file in `cloudflare/workers/`
2. Deploy via Cloudflare Dashboard → Workers & Pages

### Build & Push Docker Image
```bash
cd deploy/docker
./build.sh
# or manually:
docker buildx build --platform linux/amd64 -t gdubx/trinity-inference:latest --push .
```

### Update Akash Backend URL
**⚠️ Akash Backend URLs change frequently. Always check current URL first:**

```bash
# Check current Akash deployment at https://console.akash.network
# Or inspect the AKASH_BACKEND constant in:
cat cloudflare/workers/trinity-ai-proxy.js | grep AKASH_BACKEND
```

1. Edit `AKASH_BACKEND` in `cloudflare/workers/trinity-ai-proxy.js`
2. Edit fallback URL in `app.js` → `CONFIG.API_URL` getter
3. Redeploy Cloudflare Worker

### Add New API Endpoint
1. Add endpoint to `allowedPaths` in `trinity-ai-proxy.js`
2. Implement endpoint in `inference_server.py`
3. Add method to `API` module in `app.js`
4. Redeploy Cloudflare Worker and Akash deployment

### Add New UI Feature
1. Add any new state to `State` module
2. Add DOM manipulation to `UI` module
3. Add business logic to `Actions` module
4. Wire up event listeners in `init()`

---

## 🚀 ACTUAL DEPLOYMENT WORKFLOW (PRODUCTION)

> **CRITICAL:** Automated Akash deployment attempts have failed. Manual deployment via Akash Console is required.

### Full Production Deployment (From Scratch)

**Prerequisites:**
- Docker Desktop running
- Akash Console access (https://console.akash.network)
- Cloudflare Dashboard access (dash.cloudflare.com)
- DFX CLI installed and authenticated

**Steps:**

1. **Build Docker Image**
   ```bash
   cd deploy/docker
   ./build.sh
   ```
   - Generates timestamped Docker image (e.g., `gdubx/trinity-inference:v2-20260121-143522`)
   - Automatically updates all 5 YAML files in `deploy/akash/`
   - Pushes image to Docker Hub

2. **Copy YAML File**
   - Navigate to `deploy/akash/`
   - Select desired model YAML (usually `deploy-llama70.yaml` for production)
   - Copy entire YAML content to clipboard

3. **Deploy to Akash Console (Manual)**
   - Visit https://console.akash.network
   - Click "Create Deployment"
   - Select "SDL" tab
   - Paste YAML content
   - Click "Create Deployment"
   - **Wait for bids** (~30-60 seconds)
   - Review bids (check price, GPU type, provider reputation)
   - **Select a bid** and accept
   - **Wait for deployment** (~5-10 minutes for model download)

4. **Copy Akash URL**
   - Once deployment is running, copy the generated URL
   - Format: `http://[random-hash].ingress.[provider].akash.pub`
   - Example: `http://efe65tbon5adv7ko2i9fv30no4.ingress.a100.dsm.val.akash.pub`
   - **⚠️ Alternative:** Check current deployment at https://console.akash.network

5. **Update Frontend (app.js)**
   - Open `trinity-icp/src/app.js`
   - Find `CONFIG.API_URL` getter (around line 19-30)
   - Update fallback URL with new Akash URL
   - Save file

6. **Update Cloudflare Worker**
   - Visit https://dash.cloudflare.com
   - Navigate to Workers & Pages → `trinity-api-proxy`
   - Click "Edit Code"
   - Update `AKASH_BACKEND` constant (line ~4) with new Akash URL
   - Click "Save and Deploy"

7. **Redeploy ICP Canister**
   ```bash
   cd trinity-icp
   dfx deploy --ic trinity_frontend
   ```
   - Takes ~2-3 minutes
   - Uploads updated app.js to ICP network

8. **Wait for Akash to Finish Loading**
   - Monitor Akash Console logs
   - Wait for "Ollama server ready" message
   - Wait for model download to complete
   - Usually takes 5-10 minutes total

9. **Verify Connection**
   ```bash
   # Test backend health
   curl https://api.trinityai.cc/health | jq .
   
   # Test frontend
   open https://trinityai.cc
   ```
   - Sidebar should show "Connected ✅"
   - Try sending a test message

**Connection Successful! 🎉**

---

### Backend Code Update Only (No New Deployment)

**Use Case:** Updating `inference_server.py` logic without closing Akash deployment

**Steps:**

1. **Build Docker Image**
   ```bash
   cd deploy/docker
   ./build.sh
   ```
   - Creates new versioned image
   - Updates YAML files automatically

2. **Copy Updated YAML**
   - Copy the **same** YAML file currently running (e.g., `deploy-llama70.yaml`)
   - Important: Use the same model as before

3. **Update Deployment (Akash Console)**
   - Visit https://console.akash.network
   - Find your running deployment
   - Click "Update Deployment"
   - Paste updated YAML content
   - Click "Update"
   - **No need to select bid** (keeps same provider)
   - Wait ~2-3 minutes for restart

4. **Redeploy ICP Canister**
   ```bash
   cd trinity-icp
   dfx deploy --ic trinity_frontend
   ```

5. **Wait for Akash**
   - Monitor logs in Console
   - Model should reload faster (cached)
   - ~2-5 minutes

**Connection Successful! ✅**

---

### Cost Optimization & URL Changes

**Important Notes:**

- **URL changes when:** Closing deployment and creating new one (new provider bid)
- **URL stays same when:** Using "Update Deployment" on existing deployment
- **Why close deployments:** Akash is expensive (~$50/month for 2x A100)
  - Close deployment when not actively developing
  - Redeploy when needed for testing/demos

**Testing Environments:**
- **Local Testing:** TinyLlama 1.1B via Ollama on Mac (~637MB, free, instant)
- **Production:** Llama 3.1 70B on 2x A100 GPUs (Akash, ~$50/month when deployed)
- **Testing Strategy:** Develop locally with TinyLlama, deploy to Akash production only when needed for final validation or demos

---

### Rollback Strategy

**If deployment fails partway through:**

1. **System should automatically rollback** (to be implemented)
2. **Current manual fallback:**
   - Keep previous Akash deployment running until new one is verified
   - Test new deployment thoroughly before closing old one
   - If issues found, revert URLs back to old deployment
   - Close new deployment and troubleshoot locally

**Future Automation Goals:**
- Health check verification before URL updates
- Automatic rollback if health check fails
- Parallel deployment testing (blue-green deployment)

---

## Verification Commands

```bash
# Test frontend
curl -s "https://trinityai.cc/" | head -5

# Test API health
curl -s "https://api.trinityai.cc/health" | jq .

# Test LLM generation (no context)
curl -s -X POST "https://api.trinityai.cc/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "max_length": -1}' | jq -r '.generated_text'

# Test context memory
curl -s -X POST "https://api.trinityai.cc/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What number?",
    "contextMemory": [
      {"role": "user", "content": "Remember: 42"},
      {"role": "assistant", "content": "Got it, 42"}
    ]
  }' | jq -r '.generated_text'
# Should recall 42

# Test summarization (system message)
curl -s -X POST "https://api.trinityai.cc/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is my name?",
    "contextMemory": [
      {"role": "system", "content": "User name: Alice, Location: Tokyo"},
      {"role": "user", "content": "Tell me about cats"},
      {"role": "assistant", "content": "Cats are mammals..."}
    ]
  }' | jq -r '.generated_text'
# Should recall Alice from system message

# Test ICP domain registration
curl -s "https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io/.well-known/ic-domains"
```

## Browser Console Testing (Context Memory)

```javascript
// View current context
State.contextMemory

// View full chat history
State.chatHistory

// View conversation summary (after 15+ messages)
State.conversationSummary

// Check context details
console.log({
  contextSize: State.contextMemory.length,
  historySize: State.chatHistory.length,
  hasSummary: !!State.conversationSummary,
  summaryCoversMessages: State.lastSummaryAt
});

// Preview what gets sent to LLM
State.getContextForLLM()
```

---

## 🆘 Troubleshooting

### Frontend Can't Connect to Backend

**Symptoms:** "Disconnected" status in sidebar, health check failures

**Debug Steps:**
```javascript
// Browser console
console.log('API URL:', CONFIG.API_URL);
// Should be: https://api.trinityai.cc (production)

// Check CORS
fetch(CONFIG.API_URL + '/health')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error);
```

**Solutions:**
1. Verify Cloudflare Worker is deployed
2. Check ALLOWED_ORIGINS in trinity-api-proxy.js
3. Verify Akash backend URL in worker
4. Check browser console for CORS errors

### Autosave Not Working

**Symptoms:** No rainbow wave indicator, chat list empty

**Debug Steps:**
```javascript
// Browser console
console.log('Authenticated:', State.isAuthenticated);
console.log('Principal:', State.principal);
console.log('Current Chat ID:', State.currentChatId);

// Watch autosave attempts
// Should see logs like: "💾 Triggering autosave after message exchange..."
```

**Solutions:**
1. Ensure user is logged in (Auth.login())
2. Check backend @require_auth decorator
3. Verify Ed25519 signature generation
4. Check network tab for /chat/autosave requests

### Filecoin Archive Fails

**Symptoms:** "Failed to archive chat" error after clicking 📦

**Debug Steps:**
```bash
# Check Pinata JWT is configured
curl http://your-backend/health | jq .filecoin_configured
# Should return: true

# Check environment variable
echo $FILECOIN_API_KEY | wc -c
# Should be ~695 characters
```

**Solutions:**
1. Verify FILECOIN_API_KEY in YAML deployment
2. Check ~/.pinata_jwt file exists locally
3. Test Pinata API directly (see FILECOIN_SETUP.md)
4. Check backend logs for upload errors

### Copy ID Button Doesn't Work

**Symptoms:** Recovery ID not copied to clipboard

**Current Status:** Known issue - simple implementation without fallback

**Workaround:** Manual copy from modal text
- User can select text manually
- Press Ctrl+C (Cmd+C on Mac)

**Pending Fix:** Textarea + execCommand fallback (see IMPLEMENTATION_STATUS.md)

### Chat List Not Loading

**Symptoms:** Empty sidebar even though chats exist

**Debug Steps:**
```javascript
// Check authentication
State.isAuthenticated  // Should be: true
State.principal        // Should be: base32 string

// Try loading manually
Actions.loadChats().then(console.log);
```

**Solutions:**
1. Verify user is logged in
2. Check /chat/list endpoint returns data
3. Inspect network tab for 401/403 errors
4. Verify signature is being sent in headers

---

## 🔗 Related Documentation

### Core Documentation
- **[README.md](../README.md)** - Quick start & project overview
- **[STATUS.md](../STATUS.md)** - Current deployment status
- **[DEPLOYMENT_INFO.md](../DEPLOYMENT_INFO.md)** - Complete deployment guide
- **[ORGANIZATION.md](../ORGANIZATION.md)** - Project structure reference

### Architecture
- **[Network Architecture](diagrams/trinity-network-architecture.md)** - Cloudflare/ICP/Akash topology
- **[Storage Architecture](diagrams/trinity-storage-architecture.md)** - Akash/Filecoin integration

### Implementation
- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** - Phase completion status
- **[PHASE2_COMPLETE.md](PHASE2_COMPLETE.md)** - Authentication completion
- **[Claude-filecoin-save-and-memory-plan.md](Claude-filecoin-save-and-memory-plan.md)** - Storage plan

### Deployment Guides
- **[test/local/LOCAL_TESTING.md](../test/local/LOCAL_TESTING.md)** - Local dev setup

---

## 🎯 Quick Task Reference

| Task | Command / File |
|------|----------------|
| Deploy frontend | `cd trinity-icp && dfx deploy --ic trinity_frontend` |
| Build backend | `cd deploy/docker && ./build.sh` |
| Start local backend | `cd deploy/local && ./start.sh` |
| Run tests | `python3 test/integration/test_filecoin_integration.py` |
| Update API endpoint | Edit `cloudflare/workers/trinity-api-proxy.js` + redeploy |
| Change model | Update `deploy/akash/deploy-*.yaml` + redeploy |
| Add new endpoint | 1. Add to `allowedPaths` 2. Add to `backend/inference_server.py` 3. Redeploy |
| View logs | Browser console (frontend) or Akash logs (backend) |
| Check health | `curl https://api.trinityai.cc/health \| jq .` |
| Test generation | `curl -X POST https://api.trinityai.cc/generate -d '{"prompt":"Hi"}' \| jq .` |

---

## 💡 Known Limitations & Future Work

### Current Limitations
1. **Copy button:** Simple clipboard API without fallback
2. **No bulk archive:** Must archive chats individually
3. **No streaming:** Responses return complete, then animate
4. **Browser-only keys:** localStorage not synced across devices
5. **Single model:** Must redeploy to switch models
6. **No rate limiting:** Relies on Akash queue limits

### In Progress (See IMPLEMENTATION_STATUS.md)
1. **Bulk archive system:** All chats → one Filecoin CID
2. **Copy button fallback:** Textarea + execCommand for older browsers
3. **Recovery flow:** Handle both 3-part and 4-part recovery IDs

### Future Enhancements
1. **Response streaming:** Real-time token generation
2. **Model selection UI:** Choose model from frontend
3. **Multi-device sync:** Encrypted key backup to Filecoin
4. **Chat export:** PDF export functionality
5. **Search:** Full-text search within chats
6. **Auto-archive:** Automatic archiving of old chats
7. **Compression:** Compress chats before Filecoin upload
8. **Monitoring:** Dashboard for metrics and health

---

## 📞 Support & Contribution

**Project Owner:** Owen Heidenreich  
**Repository:** (Private development)  
**Docker Hub:** https://hub.docker.com/u/gdubx  

### Getting Help
1. Check this document first (comprehensive reference)
2. Review [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for feature status
3. Check [diagrams/](diagrams/) for architecture understanding
4. Review relevant test files in `test/integration/` for examples

### For AI Assistants
This document provides complete context for understanding Trinity. Key files to read based on task:
- **Frontend changes:** `trinity-icp/src/app.js` (main orchestration)
- **Backend changes:** `backend/inference_server.py` (1014 lines)
- **Auth logic:** `backend/icp_auth.py` (210 lines)
- **Deployment config:** `deploy/akash/deploy-*.yaml`
- **Network routing:** `cloudflare/workers/*.js`

---

## 📈 Project Milestones

### January 2026
- ✅ Phase 1: Self-custody authentication complete
- ✅ Phase 2: Backend integration complete
- ✅ Phase 3: Autosave system complete
- 🟡 Phase 4: Filecoin archive (partial - individual working, bulk pending)
- ✅ Production deployment (trinityai.cc operational)
- ✅ Docker image automated build pipeline
- ✅ All 5 Akash deployment configs with Filecoin support
- ✅ Comprehensive documentation and architecture diagrams

### Upcoming
- ⏳ Complete bulk archive implementation
- ⏳ Enhance copy button robustness
- ⏳ Add response streaming
- ⏳ Implement model selection UI
- ⏳ Create monitoring dashboard

---

*This document is maintained for AI assistants to quickly understand Trinity without re-exploring files. Last updated January 20, 2026.*

---

## File Quick Reference

| Need to... | Edit this file |
|------------|----------------|
| Change HTML structure | `trinity-icp/src/index.html` (80 lines) |
| Change styles/responsive design | `trinity-icp/src/styles.css` (639 lines) |
| Change configuration | `trinity-icp/src/config.js` |
| Change state management | `trinity-icp/src/state/store.js` |
| Change context memory | `trinity-icp/src/state/contextMemory.js` |
| Change API calls | `trinity-icp/src/app.js` → `API` module |
| Change DOM rendering | `trinity-icp/src/ui/` modules |
| Change business logic | `trinity-icp/src/app.js` → `Actions` module |
| Change authentication | `trinity-icp/src/auth/authManager.js` |
| Change initialization | `trinity-icp/src/app.js` → `init()` function |
| Change API routing/CORS | `cloudflare/workers/trinity-ai-proxy.js` |
| Change frontend routing | `cloudflare/workers/trinity-frontend-proxy.js` |
| Change backend logic | `backend/inference_server.py` |
| Change context formatting | `backend/inference_server.py` → build_prompt_with_context() |
| Change AI model | `deploy/akash/deploy-*.yaml` + env vars |
| Change ICP config | `trinity-icp/dfx.json` or `.ic-assets.json5` |
| Change security headers | `trinity-icp/.ic-assets.json5` |

---

## Known Limitations

1. **Session-only chats:** No persistence - chats exist only during active session (autosave system planned)
2. **Single model per deployment:** Must redeploy to switch models
3. **No streaming:** Responses return complete, then animate
4. **No rate limiting:** Currently relies on Akash queue limits
5. **Inline HTML handlers:** Some `onclick` attributes remain (delegated to Actions)
6. **LLM "overeager" behavior:** After summarization, LLM sometimes voluntarily mentions facts from summary even when not asked (proof system is working)
7. **15-message threshold:** Summarization only triggers after 15 messages (configurable via SUMMARY_INTERVAL)
8. **Local key storage:** Private keys stored in localStorage (browser-based, not synchronized across devices)

---

## Recent Changes (January 20, 2026)

### Self-Custody Authentication System - FULLY FUNCTIONAL ✅
- **Ed25519 key generation:** Users create cryptographic identity with Ed25519KeyIdentity
- **Private key export:** Modal displays private key with security warnings on creation
- **Copy functionality:** Textarea-based copy with execCommand fallback for compatibility
- **Import/restore:** Users can restore identity by pasting private key hex string
- **localStorage persistence:** Auto-login on page load if key saved
- **Principal ID display:** Full 63-char Principal ID shown in sidebar when authenticated
- **Export key button:** Logged-in users can re-export private key anytime
- **Security confirmations:** "Are you sure?" dialog before closing export modal
- **Web3 architecture:** Users own their keys, Trinity stores nothing server-side
- **Future integration ready:** Principal ID will control payment accounts and Filecoin storage paths
- **Build system:** esbuild bundles @dfinity libraries (296KB icp-auth.js) automatically during deployment
- **Status:** Production ready on trinityai.cc - create identity, logout, restore all working

### Context Memory & Summarization - FULLY FUNCTIONAL ✅
- **6-message context window:** LLM receives last 6 messages for conversation continuity
- **Auto-summarization:** Every 15 messages, older messages compressed into summary
- **System messages:** Backend supports role: 'system' for conversation summaries
- **Token optimization:** 36% token reduction in long conversations
- **Bug fix:** Fixed API.generate() to call getContextForLLM() instead of raw contextMemory
- **skipContext parameter:** Added to prevent circular summarization issues
- **Enhanced logging:** Console shows exactly what context is sent (preview of messages)
- **Production tested:** Verified AI recalls facts from message 1 even at message 20+
- **UI indicator:** Toast notification shows when compression occurs
- **Status:** Working perfectly in production on trinityai.cc

### Guest Mode Limitations Removed
- **Unlimited prompts:** No more 10-prompt guest limit
- **Simplified code:** Removed guestPromptCount, guestPromptTimestamps tracking
- **Cleaner UI:** Removed guest counter from sidebar
- **All users equal:** No distinction between guest and authenticated (auth not yet implemented)

### Cache Management Improvements
- **No-cache for JS/CSS:** Set Cache-Control: no-cache for app.js and styles.css
- **Instant updates:** Users get fresh code immediately after ICP deployment
- **No manual cache clearing:** Eliminates need to purge Cloudflare or hard refresh
- **HTML already no-cache:** Maintained existing no-cache policy for HTML files

### Deployment Workflow Lessons Learned
- **ICP canister updates:** Use `dfx deploy --ic trinity_frontend` to deploy frontend
- **Cloudflare caching:** Aggressive caching can prevent users from seeing updates
- **Solution:** Set no-cache headers in .ic-assets.json5 for frequently updated files
- **Akash backend:** Use versioned Docker tags (v2-YYYYMMDD-HHMMSS) to force image pulls
- **Testing:** Always verify in incognito/private window after deployment

### Removal of Persistence Layer (Earlier January 2026)
- **No chat saving:** Removed all save/autosave/load functionality
- **Stateless inference:** Backend now pure text generation only
- **Session-only chats:** Chat history exists only in browser memory during active session
- **Simplified API:** Only 3 endpoints now: /health, /generate, /stats
- **Cleaned dependencies:** Removed ChatStorage, APScheduler, background jobs

### Frontend Refactoring
- **Modular architecture:** Code organized into CONFIG, State, API, UI, Actions modules
- **XSS protection:** Added DOMPurify library for sanitizing markdown output
- **Race condition fix:** Added `State.isGenerating` flag to prevent double-submit
- **Interval cleanup:** Health check interval now tracked for proper cleanup
- **DOM caching:** All DOM elements cached in `UI.elements` for performance
- **Separation of concerns:** Business logic in Actions, DOM manipulation in UI

---

*This document is designed for AI assistants to quickly understand the Trinity codebase without re-exploring files.*

# Trinity - Decentralized AI Chat Platform

Fully decentralized AI chat application with ICP authentication, encrypted autosave, and Filecoin archival storage.

## Project Structure

```
Trinity/
├── backend/                 # Backend code
│   ├── inference_server.py  # Flask backend (1014 lines)
│   ├── icp_auth.py          # Ed25519 verification
│   └── requirements.txt     # Python dependencies
│
├── deploy/                  # Deployment configs
│   ├── docker/              # Docker build files
│   │   ├── Dockerfile
│   │   ├── build.sh
│   │   └── startup.sh
│   ├── akash/               # Akash YAML files
│   │   └── deploy-*.yaml (5 models)
│   └── local/               # Local development
│       ├── docker-compose.yml
│       ├── start.sh
│       ├── stop.sh
│       └── status.sh
│
├── scripts/                 # Root scripts
│   ├── dev.sh               # Start local dev
│   ├── deploy.sh            # Build & deploy
│   └── test-prod.sh         # Test production
│
├── test/                    # All testing
│   ├── integration/         # Integration tests
│   │   ├── test_filecoin_integration.py
│   │   ├── test_auth_backend.py
│   │   └── benchmark_models.py
│   └── local/               # Local test configs
│       ├── docker-compose.local.yml
│       └── LOCAL_TESTING.md
│
├── trinity-icp/             # ICP frontend canister
│   ├── src/                 # Source files
│   │   ├── app.js           # Main app
│   │   ├── config.js        # Environment config
│   │   ├── index.html       # HTML template
│   │   ├── styles.css       # Styling
│   │   ├── auth/            # Auth modules
│   │   ├── state/           # State management
│   │   ├── storage/         # Persistence
│   │   └── ui/              # UI modules
│   ├── dist/                # Production build
│   └── dfx.json             # DFX config
│
├── cloudflare/              # Cloudflare Workers
│   └── workers/
│       ├── trinity-ai-proxy.js
│       └── trinity-frontend-proxy.js
│
├── docs/                    # Documentation
│   ├── CLAUDE.md            # This file
│   ├── diagrams/            # Architecture diagrams
│   ├── plans/               # Roadmap
│   └── user/                # User docs
│
├── dev                      # Wrapper: scripts/dev.sh
├── test-prod                # Wrapper: scripts/test-prod.sh
└── akash-deploy             # Wrapper: scripts/deploy.sh
```

## Quick Start

### Production Deployment

```bash
cd deploy/docker
./build.sh
# Deploy deploy/akash/deploy-llama70.yaml to Akash Console
```

### Local Testing

```bash
cd deploy/local
./start.sh
```

### Frontend Development

```bash
cd trinity-icp
dfx deploy --ic trinity_frontend
```

## Architecture

- **Frontend**: Internet Computer (ICP) canister at trinityai.cc
- **Backend**: Akash Network (decentralized compute)
- **Proxies**: Cloudflare Workers for routing
- **Storage**: Filecoin/Pinata for permanent archives
- **Auth**: Ed25519 signature verification via ICP

## Current Production

- **Image**: `gdubx/trinity-inference:v2-20260121-132248`
- **Model**: Llama 3.1 70B
- **Hardware**: 2x A100 80GB
- **Cost**: ~$120-200/month

## Documentation

- [Local Testing Guide](test/local/LOCAL_TESTING.md)
- [Roadmap / Next Steps](docs/plans/next-steps.md)
- [Quick Start Guide](docs/user/quickstart.md)
---

## 🔒 Security Implementation (January 22, 2026)

### Mandatory Authentication System

Trinity now implements a comprehensive mandatory authentication gate with no loopholes. Users must authenticate before accessing any functionality.

#### Implementation Details

**1. Authentication Guards in Actions** (`trinity-icp/src/app.js`)
- `generate()` - Blocks sending messages if not authenticated, shows error notification
- `newChat()` - Blocks creating new chats if not authenticated
- `loadChat()` - Blocks loading chats if not authenticated

**2. UI Disable/Enable Functions** (`trinity-icp/src/ui/index.js`)
- `disableUI()` - Disables input field, send button, adds blur effect to entire app
- `enableUI()` - Re-enables all functionality after successful authentication

**3. UI Blocking During Auth** (`trinity-icp/src/app.js`)
```javascript
// Disable UI interactions until authenticated
UI.disableUI();
console.log('🚫 UI disabled - waiting for authentication');

// Initialize authentication (BLOCKS until authenticated)
await Actions.initAuth();

// Enable UI after authentication
UI.enableUI();
console.log('✅ UI enabled - user authenticated');
```

**4. CSS Protection** (`trinity-icp/src/styles.css`)
```css
.app-container.ui-disabled {
    pointer-events: none;
    opacity: 0.5;
    filter: blur(2px);
}

.modal-dialog {
    z-index: 9999;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(3px);
}
```

**5. Authentication Loop** (`trinity-icp/src/app.js`)
```javascript
async requireAuthentication() {
    while (!State.isAuthenticated) {
        await this.handleAuthenticationFlow();
        if (!State.isAuthenticated) {
            await new Promise(resolve => setTimeout(resolve, 500));
        }
    }
}
```

#### Authentication Flow

**New User:**
1. Page loads → UI disabled and blurred
2. "trinity" authentication modal appears automatically (non-dismissible)
3. User clicks "Create New Identity"
4. Credentials shown with warning (only "Okay" button)
5. User clicks "Okay" → automatically logged in
6. UI enabled → Trinity ready to use

**Returning User:**
1. Page loads → cached credentials detected
2. Auto-restore session
3. UI enabled immediately → Trinity ready to use

**Login with Existing Credentials:**
1. Page loads → UI disabled and blurred
2. "trinity" authentication modal appears
3. User clicks "Login"
4. Enter username (principal) and password (private key)
5. Cancel → returns to auth choice modal (loops back)
6. Success → UI enabled → Trinity ready to use

**Logout Flow:**
1. User clicks logout
2. Credentials cleared
3. `requireAuthentication()` called immediately
4. Auth modal appears → user must authenticate again

#### Security Features

✅ **No guest mode** - Must authenticate to access Trinity
✅ **No escape routes** - Cancel loops back to auth choice, cannot dismiss modals
✅ **Auto-login after creation** - Seamless new user experience
✅ **Cached sessions work** - Returning users auto-restored
✅ **Post-logout protection** - Forces re-authentication
✅ **Non-dismissible modals** - Cannot click outside or press escape to bypass
✅ **UI completely disabled** - Input field, send button, and all interactions blocked until auth
✅ **Generate blocked** - Shows error notification if attempted without auth
✅ **New chat blocked** - Prevents creating chats without auth
✅ **Load chat blocked** - Prevents accessing saved chats without auth
✅ **Modal supremacy** - z-index 9999 with backdrop blur ensures modals always on top

#### Files Modified

- `trinity-icp/src/app.js` - Authentication guards, UI blocking, auth loop
- `trinity-icp/src/ui/index.js` - disableUI() and enableUI() functions
- `trinity-icp/src/ui/modals.js` - Non-dismissible modals with backdrop click prevention
- `trinity-icp/src/styles.css` - UI disabled state, modal z-index and styling
- `trinity-icp/src/index.html` - Title changed from "Trinity [DEV MODE]" to "Trinity"

---

## 📚 Sources

This section provides official documentation, FAQ, and help URLs for all major technologies and components used in the Trinity project. Use these links for detailed guides, troubleshooting, and best practices.

### Core Technologies
- **ICP (Internet Computer Protocol)**: https://internetcomputer.org/docs/
- **Akash Network**: https://docs.akash.network/
- **Ollama**: https://github.com/jmorganca/ollama
- **Filecoin/IPFS**: https://docs.ipfs.tech/, https://docs.filecoin.io/
- **Pinata (IPFS Gateway)**: https://docs.pinata.cloud/

### Frontend Technologies
- **JavaScript**: https://developer.mozilla.org/en-US/docs/Web/JavaScript
- **HTML**: https://developer.mozilla.org/en-US/docs/Web/HTML
- **CSS**: https://developer.mozilla.org/en-US/docs/Web/CSS
- **Vite**: https://vitejs.dev/guide/
- **Zustand**: https://github.com/pmndrs/zustand

### Backend Technologies
- **Python**: https://docs.python.org/3/
- **Flask**: https://flask.palletsprojects.com/en/2.3.x/
- **Node.js**: https://nodejs.org/en/docs/

### Security & Cryptography
- **Ed25519**: https://ed25519.cr.yp.to/, https://tools.ietf.org/html/rfc8032
- **AES-256-GCM**: https://en.wikipedia.org/wiki/Galois/Counter_Mode
- **PBKDF2**: https://en.wikipedia.org/wiki/PBKDF2

### Infrastructure & Tools
- **Cloudflare Workers**: https://developers.cloudflare.com/workers/
- **Docker**: https://docs.docker.com/
- **Git**: https://git-scm.com/doc
- **GitHub**: https://docs.github.com/
- **VS Code**: https://code.visualstudio.com/docs
- **Homebrew**: https://docs.brew.sh/

### Command Line Tools
- **curl**: https://curl.se/docs/
- **jq**: https://stedolan.github.io/jq/manual/

### Operating System
- **macOS**: https://support.apple.com/macos