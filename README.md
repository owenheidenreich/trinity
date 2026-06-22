<p align="center">
  <img src="https://img.shields.io/badge/status-live-brightgreen" alt="Status: Live">
  <img src="https://img.shields.io/badge/self--custody-Ed25519-ff6b6b" alt="Self-Custody">
  <img src="https://img.shields.io/badge/encryption-AES--256--GCM-ffd93d" alt="Encrypted">
  <img src="https://img.shields.io/badge/stack-fully%20decentralized-blueviolet" alt="Fully Decentralized">
</p>

<h1 align="center">Trinity</h1>

<h3 align="center"><em>Your Keys. Your Data. Your AI.</em></h3>

<p align="center">
The first AI chat application where you truly own everything.<br>
No accounts. No passwords. No company storing your conversations.<br>
Just cryptographic keys that belong to you.
</p>



---

## Reviewer Summary

- **What it is:** self-custody AI chat with browser-generated identity, encrypted memory, and decentralized hosting/compute goals.
- **Tech stack:** React/Vite frontend on ICP, Flask/Python backend, llama.cpp server, Akash GPU deployment, IPFS/Filecoin archival through Lighthouse, pytest/Vitest coverage.
- **Demo path:** open `https://dubya.ai` and use guest/anonymous chat or create a username/password identity.
- **Current deployment target:** low-cost Akash model for interview demonstration.
- **Secrets:** API keys are loaded from local or deployment environment variables only; `.env` files are not part of the public repo.

## Why Trinity Exists

Every AI chat service today follows the same model: create an account, hand over your data, trust them not to read it, sell it, or lock you out. You don't own your conversations—they do.

**Trinity inverts this entirely.**

When you open Trinity, your browser generates a cryptographic keypair. That's your identity—not an email, not a username, just mathematics. Your private key never leaves your device. Every message you save is encrypted *before* it leaves your browser with keys derived from your identity. The backend literally cannot read your chats.

If you lose your key, your data is gone forever. That's not a bug—it's the whole point. **True ownership means no backdoors, no recovery, no "forgot password."** Your keys, your responsibility, your freedom.

---

## The Trinity: Three Blockchains, One Stack

| Blockchain | Role | Replaces |
|------------|------|----------|
| **ICP** (Internet Computer) | Frontend hosting + identity | AWS S3, Cloudflare, Auth0 |
| **Akash** (AKT) | GPU compute for AI inference | AWS EC2, Google Cloud, Azure |
| **IPFS/Filecoin** | Permanent encrypted storage | AWS S3, Google Drive, Dropbox |

No single company. No single point of failure. No kill switch.

Like Neo choosing to see the truth, Trinity represents awakening to a different reality—one where you control your digital existence instead of renting it from corporations.


Three becoming one. Distinct technologies unified into a seamless experience. An homage to faith and the belief that something greater can emerge from the union of parts.

---

## What Makes This Different

<table>
<tr>
<th width="50%">Traditional AI Chat</th>
<th width="50%">Trinity</th>
</tr>
<tr>
<td>

❌ Create account with email/password  
❌ Company stores all conversations  
❌ Company can read your data  
❌ Company can ban you  
❌ Company can shut down  
❌ Limited export options  
❌ Servers in corporate data centers  

</td>
<td>

✅ Generate keypair in browser (30 seconds)  
✅ You encrypt before saving  
✅ Backend cannot decrypt your chats  
✅ No accounts = no bans  
✅ Decentralized = unstoppable  
✅ Full data portability (export key)  
✅ Compute on decentralized networks  

</td>
</tr>
</table>

**The backend operators—including me—cannot read your messages.** The encryption happens in your browser with keys derived from your cryptographic identity. I store ciphertext. That's it.

---

## Features

### 🔐 Self-Custody Authentication

No passwords. No accounts. No "forgot password" emails.

Your browser generates an Ed25519 keypair—the same cryptography used by SSH, Signal, and modern blockchains. Your public key becomes your **principal ID** (your identity). Your private key is yours to export, backup, and protect.

**Import your key on any device** and your identity comes with you. No company can lock you out because no company controls your access.

### 🔒 Zero-Knowledge Encryption

Every saved chat is encrypted with **AES-256-GCM** before leaving your browser:

- **PBKDF2 key derivation** with 100,000 iterations
- **Random salt + nonce** per encryption operation
- **Your principal ID** as the encryption password

The backend stores only ciphertext. Even if the server is compromised, attackers get encrypted blobs they cannot decrypt without your private key.

### 🧠 Single-Pass Agent Intelligence

Trinity doesn't just respond—it *thinks*. A single-pass agent pipeline with heuristic tool detection routes queries through a ReAct reasoning loop:

| Stage | What Happens |
|-------|-------------|
| **Heuristic Detection** | Pattern-match query to determine if tools are needed |
| **ReAct Loop** | Iterative Thought → Action → Observation cycle (max 15 iterations) |
| **Reflexion** | Self-correction when tool results don't satisfy the query |
| **13 Tools** | Web search, code execution, math, file operations, and more |

For current information, Trinity searches the web via Brave Search. Complex queries trigger multi-step reasoning with tool chaining.

### 💾 Three-Tier Memory

- **Working memory** — last 3 messages for immediate context
- **Semantic memory** — retrieves top 5 relevant past conversations using vector embeddings
- **User memory** — persistent facts across all chats (stored encrypted on IPFS)
- **Autosave** with 2-second debounce (never lose a message)

### 📊 LaTeX Mathematics

Full support for mathematical notation with **live rendering** as you chat:
- Inline: `$E = mc^2$` renders as $E = mc^2$
- Block equations with `$$...$$`
- Equations render progressively during response typing
- Powered by KaTeX for fast, beautiful rendering

### 🔬 Engineering Features

| Feature | Description |
|---------|-------------|
| **Prometheus Observability** | RED-method metrics (Rate, Errors, Duration) at `/metrics` |
| **Semantic Caching** | Two-tier cache (embedding + response) — 40-60% reduction in LLM calls |
| **Token Tracking & Quotas** | Per-user token counting with hourly quotas |
| **615 Automated Tests** | pytest suite with tiered coverage (90%+ security, 91% overall) |
| **3 ADRs** | Architecture Decision Records documenting every major design choice |

---

## The Stack

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TRINITY ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│    │       ICP        │  │      AKASH       │  │    FILECOIN      │    │
│    │  Internet        │  │   Decentralized  │  │   Permanent      │    │
│    │  Computer        │  │   Cloud          │  │   Storage        │    │
│    ├──────────────────┤  ├──────────────────┤  ├──────────────────┤    │
│    │ • Frontend       │  │ • GPU compute    │  │ • IPFS pinning   │    │
│    │ • Backend canister│  │ • LLM inference │  │ • Verified deals │    │
│    │ • Ed25519 auth   │  │ • Hot storage    │  │ • 540+ day proof │    │
│    │ • HTTPS outcalls │  │ • Flask API      │  │ • Multi-gateway  │    │
│    └──────────────────┘  └──────────────────┘  └──────────────────┘    │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  ZERO DEPENDENCE ON: AWS, Google Cloud, Azure, Cloudflare, Auth0       │
│  CUSTOM DOMAIN: dubya.ai → ICP boundary nodes (~200ms load)               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Engineering Architecture

```
Request → ICP Auth → Middleware Chain
                         │
              ┌──────────┴──────────┐
              │   Rate Limit        │
              │   Cache Check       │
              └──────────┬──────────┘
                         │
              Heuristic Tool Detection
              ┌──────────┴──────────┐
         No Tools             Tools Needed
              │                     │
         Direct LLM            ReAct Loop
         Response           (max 15 iters)
              │               13 tools
              └──────────┬──────────┘
                         │
              Response → Prometheus Metrics → Return
```

---

## Quick Start

### Local Development

```bash
git clone https://github.com/yourusername/Trinity.git
cd Trinity/backend

# Install dependencies
pip install -r requirements.txt

# Run tests (615 tests, ~7 seconds)
pytest tests/ --no-cov -q

# Start the server (requires the configured llama-server backend)
python3 inference_server.py
# → http://localhost:8000
```

### Production Deployment

```bash
# Copy environment template
cp .env.example .env
# Edit .env with your API keys (LIGHTHOUSE_API_KEY, BRAVE_SEARCH_API_KEY)

# Deploy (single command handles everything)
./scripts/trinity-deploy-production.sh production  # Qwen2.5-Coder 32B ~$600-1000/mo
./scripts/trinity-deploy-production.sh test        # Qwen2.5-Coder 7B ~$40-100/mo
```

### Deployment Tiers

| Tier | Model | Intelligence | Cost | Use Case |
|------|-------|--------------|------|----------|
| **production** | Qwen2.5-Coder 32B | Excellent | ~$600-1000/mo | Production |
| **test** | Qwen2.5-Coder 7B | Good | ~$40-100/mo | Smoke-testing |

---

## Security Model

### What The Operators Cannot Do

- **Read your chats** → Encrypted client-side before transmission
- **Recover your account** → No accounts exist, only keypairs
- **Ban you** → No identity system to ban
- **Comply with data requests** → Cannot decrypt what we cannot read
- **Sell your data** → We don't have readable data

### What You Control

- **Your private key** → Export, backup, protect it
- **Your encrypted archives** → Stored on Filecoin with your CIDs
- **Your chat history** → Delete anytime from local storage
- **Your identity** → Same key works across devices

### The Trade-Off

**If you lose your private key, your data is gone forever.**

There is no "forgot password." There is no recovery email. There is no customer support that can help you. This is the price of true ownership—and it's a feature, not a bug.

Back up your key. Store it safely. You are your own bank.

---

## Technical Deep Dive

### Authentication Flow

```
Browser                           Backend
   │                                 │
   │  1. Generate Ed25519 keypair    │
   │  2. Derive principal ID         │
   │                                 │
   │  ──── Request + Signature ───►  │
   │       (timestamp, payload)      │
   │                                 │
   │                   3. Verify signature
   │                   4. Check timestamp (5-min window)
   │                   5. Process request
   │                                 │
   │  ◄──── Encrypted Response ────  │
```

### Encryption Layers

| Layer | Algorithm | Purpose |
|-------|-----------|---------|
| Transport | TLS 1.3 | Network security |
| Application | AES-256-GCM | Chat encryption |
| Key Derivation | PBKDF2 (100k iterations) | Password to key |
| Identity | Ed25519 | Signatures + principal |

### Storage Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                       STORAGE ARCHITECTURE                        │
├───────────────────────────────────────────────────────────────────┤
│  IPFS (Lighthouse) = Source of Truth                             │
│  • All encrypted chats stored permanently                         │
│  • Metadata synced for recovery after redeployment               │
│  • Content-addressed (CID) for integrity verification            │
├───────────────────────────────────────────────────────────────────┤
│  Browser (IndexedDB) = Session Cache                             │
│  • Immediate responsiveness                                       │
│  • Cleared on logout                                              │
└───────────────────────────────────────────────────────────────────┘
```

**Note:** Akash disk is only used for temporary metadata caching (chat list) to speed up requests. All actual chat data lives on IPFS and survives Akash redeployments.

---

## Project Structure

```
Trinity/
├── backend/                     # Python Flask backend
│   ├── inference_server.py      # App factory + blueprint registration
│   ├── icp_auth.py              # Ed25519 signature verification
│   ├── config.py                # Environment configuration
│   ├── encryption.py            # AES-256-GCM encryption
│   ├── validation.py            # Input validation + SSRF protection
│   ├── storage.py               # Encrypted file storage
│   ├── lighthouse.py            # IPFS/Filecoin uploads
│   ├── middleware/              # Request middleware
│   │   ├── observability.py     # Prometheus metrics
│   │   ├── rate_limit.py        # Per-principal rate limiting
│   │   └── icp_cache.py         # ICP idempotency cache
│   ├── services/                # Business logic (17 modules)
│   │   ├── agent.py             # Single-pass agent orchestrator
│   │   ├── react_loop.py        # ReAct agentic loop (tool calling)
│   │   ├── tools.py             # 13 tool definitions
│   │   ├── code_executor.py     # Tool dispatcher
│   │   ├── caching.py           # Embedding + semantic caching
│   │   ├── memory.py            # Semantic memory retrieval
│   │   └── ...                  # embeddings, search, ollama, etc.
│   └── tests/                   # 615 automated tests
│       ├── unit/                # Unit tests
│       ├── integration/         # Integration tests
│       └── e2e/                 # End-to-end tests
│
├── trinity-icp/                 # Frontend (ICP-hosted)
│   ├── src-react/               # Active: React 19 + TypeScript (v3.0.0)
│   └── src/                     # Legacy: Vanilla JS (v2.8.0, still buildable)
│
├── deploy/                      # Deployment configs
│   ├── akash/                   # SDL manifests for model tiers
│   ├── docker/                  # Dockerfile (CUDA 12.2 + Ollama)
│   └── cloudflare-worker/       # SSL termination proxy
│
├── scripts/                     # Automation
│   └── trinity-deploy-production.sh  # One-command deployment
│
└── docs/                        # Documentation
    ├── architecture/            # 6 system architecture docs + 3 design rationale docs
    ├── ai-context/              # AI assistant references
    └── getting-started/         # Developer guides
```

---

## API Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check + system metrics |
| `/generate` | POST | No | LLM text generation |
| `/generate/agent` | POST | No | Agentic pipeline (ReAct + tools) |
| `/metrics` | GET | No | Prometheus metrics scrape |
| `/chat/autosave` | POST | Yes | Save encrypted chat |
| `/chat/list` | GET | Yes | List user's chats |
| `/chat/<id>` | GET/DELETE | Yes | Load or delete chat |
| `/user/memory` | GET/POST | Yes | User semantic memory |
| `/admin/cache/stats` | GET | No | Cache statistics |
| `/tools/*` | Various | No | Tool execution endpoints |

See [docs/ai-context/FEATURE-CATALOG.md](docs/ai-context/FEATURE-CATALOG.md) for the complete feature inventory with code locations.

---

## Testing

```bash
cd backend

# Full suite (615 tests, ~7 seconds)
pytest tests/ --no-cov -q

# Specific module
pytest tests/unit/test_encryption.py -v

# With coverage report
pytest tests/ --cov=. --cov-report=html
```

**Coverage Tiers**: Critical 90%+ (auth, encryption) | Overall 91%+

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/README.md](docs/README.md) | Documentation navigation hub |
| [Architecture Docs](docs/architecture/SYSTEM-OVERVIEW.md) | 6-part system architecture |
| [CLAUDE.md](docs/ai-context/CLAUDE.md) | AI assistant reference (full technical context) |
| [FEATURE-CATALOG.md](docs/ai-context/FEATURE-CATALOG.md) | Every feature with code locations |
| [Rationale: Test Coverage](docs/architecture/RATIONALE-TEST-COVERAGE.md) | Coverage targets |
| [Rationale: Prometheus](docs/architecture/RATIONALE-PROMETHEUS.md) | Metrics architecture |
| [Rationale: Caching](docs/architecture/RATIONALE-CACHING.md) | Caching strategy |
| [Developer Setup](docs/getting-started/developer-setup.md) | 5-minute quick start |
| [Common Tasks](docs/getting-started/common-tasks.md) | How-to guides |

---

## Roadmap

### Production Upgrade Phases (Completed)

- [x] **Phase 1:** Security tests + core test coverage
- [x] **Phase 2:** Prometheus observability + Grafana dashboards
- [x] **Phase 3:** Agentic pipeline with ReAct reasoning + 13 tools
- [x] **Phase 4:** Cost optimization (semantic caching + token tracking)
- [x] **Phase 5:** Documentation (3 ADRs, developer guides, E2E tests)
- [x] **Phase 6:** React 19 frontend migration (TypeScript + Zustand)
- [x] **Phase 7:** Intelligence overhaul (single-pass agent, Reflexion, 615 tests)

### Product Roadmap

- [x] Self-custody authentication (Ed25519)
- [x] Encrypted autosave (AES-256-GCM)
- [x] Filecoin archive (Lighthouse SDK)
- [x] ICP backend canister (HTTPS Outcalls)
- [x] Custom domain (dubya.ai)
- [x] Agentic reasoning pipeline
- [x] LaTeX mathematics (KaTeX)
- [x] Semantic memory (vector embeddings)
- [ ] Voice input/output
- [ ] Mobile PWA

---

## Support Trinity

Running decentralized infrastructure costs real money:

| Resource | Monthly Cost |
|----------|--------------|
| Akash GPU (current tier) | ~$50-200 |
| ICP Canister Cycles | ~$5-10 |
| Domain + DNS | ~$1 |

**Total: ~$60-220/month** depending on model tier.

---

## Contributing

Trinity is built for transparency. Every line of code is visible. Every decision is documented.

1. Fork the repository
2. Read [docs/ai-context/CLAUDE.md](docs/ai-context/CLAUDE.md) for technical context
3. Browse [docs/ai-context/FEATURE-CATALOG.md](docs/ai-context/FEATURE-CATALOG.md) for feature overview
4. Create a feature branch
5. Submit a pull request

---

## Links

- **Live App:** [dubya.ai](https://dubya.ai)
- **ICP Canister:** [zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io](https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io)
- **Documentation:** [docs/ai-context/CLAUDE.md](docs/ai-context/CLAUDE.md)
- **Feature Catalog:** [docs/ai-context/FEATURE-CATALOG.md](docs/ai-context/FEATURE-CATALOG.md)
- **Docker Hub:** [gdubx/trinity-inference](https://hub.docker.com/r/gdubx/trinity-inference)

---

<p align="center">
<strong>Built without permission. Runs without servers. Owned by no one.</strong>
</p>

<p align="center">
<em>Because your conversations with AI should belong to you.</em>
</p>
