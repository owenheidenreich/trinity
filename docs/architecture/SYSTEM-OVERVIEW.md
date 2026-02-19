# Trinity — System Architecture Overview

> Last updated: February 19, 2026 · Version 3.0.0

## What Is Trinity?

Trinity is a **fully decentralized AI chat application** with self-custody authentication, end-to-end encrypted storage, and agentic tool-calling capabilities. The entire stack runs across three independent decentralized networks with no corporate accounts, no centralized databases, and no third-party auth providers.

---

## The Three Pillars

| Layer | Technology | Role |
|-------|-----------|------|
| **Frontend** | Internet Computer (ICP) | Hosts the React web app as a tamper-proof canister on a blockchain |
| **Backend** | Akash Network | Runs the Python inference server + Ollama LLM on decentralized GPU cloud |
| **Storage** | IPFS via Lighthouse | Stores encrypted chat data and user memory on the permanent web |

A Cloudflare Worker sits between the frontend and backend to provide SSL termination (Akash does not natively support HTTPS).

---

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER'S BROWSER                                 │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │               React 19 App  (v3.0.0)                              │     │
│   │                                                                   │     │
│   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │     │
│   │   │ useAuth  │  │ useChat  │  │ useAuto- │  │ useConnection│    │     │
│   │   │          │  │          │  │ save     │  │              │    │     │
│   │   │ Ed25519  │  │ SSE      │  │ Debounce │  │ Health poll  │    │     │
│   │   │ keypair  │  │ streaming│  │ 2s delay │  │ 30s interval │    │     │
│   │   └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │     │
│   │        │              │              │               │            │     │
│   │   ┌────┴──────────────┴──────────────┴───────────────┴──────┐    │     │
│   │   │                  Zustand Store                           │    │     │
│   │   │  chatHistory, contextMemory, auth state, autosave state │    │     │
│   │   └────────────────────────┬────────────────────────────────┘    │     │
│   │                            │                                     │     │
│   │   ┌────────────────────────┴────────────────────────────────┐    │     │
│   │   │              IndexedDB (Local-First Cache)               │    │     │
│   │   │  chats store  │  pendingSync store                       │    │     │
│   │   └──────────────────────────────────────────────────────────┘    │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│     Ed25519-signed requests                                                 │
│     (Principal, Signature, Timestamp, PublicKey, Nonce)                      │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │ HTTPS
                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      CLOUDFLARE WORKER  (api.dubya.ai)                       │
│                                                                              │
│  • SSL termination + CORS enforcement                                        │
│  • Forwards ICP auth headers                                                 │
│  • Passes through SSE streaming for /generate/agent                          │
│  • Security headers (CSP, X-Frame-Options, nosniff)                          │
└──────────────────────────┬───────────────────────────────────────────────────┘
                           │ HTTP
                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AKASH NETWORK  (Decentralized GPU Cloud)                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                     Docker Container                                   │  │
│  │                     nvidia/cuda:12.2.0-runtime-ubuntu22.04             │  │
│  │                                                                        │  │
│  │  ┌──────────────────────────────────┐  ┌────────────────────────────┐  │  │
│  │  │    Flask Inference Server :8000  │  │     Ollama LLM :11434     │  │  │
│  │  │                                  │  │                            │  │  │
│  │  │  ┌────────────┐ ┌────────────┐  │  │  qwen3:32b                  │  │
│  │  │  │ 9 Route    │ │ 3 Middle-  │  │  │  (or other model from     │  │
│  │  │  │ Blueprints │ │ ware       │  │  │   deployment tier)         │  │
│  │  │  │ 53 API     │ │ Modules    │  │  │                            │  │
│  │  │  │ endpoints  │ │            │  │  │  GPU: NVIDIA (Akash mkt)   │  │
│  │  │  └────────────┘ └────────────┘  │  │  Context: 65,536 tokens    │  │
│  │  │                                  │  │                            │  │  │
│  │  │  ┌────────────┐ ┌────────────┐  │  └────────────────────────────┘  │  │
│  │  │  │ 42 Service │ │ SQLite DB  │  │                                  │  │
│  │  │  │ Modules    │ │ (sessions, │  │  ┌────────────────────────────┐  │  │
│  │  │  │            │ │  rate lim, │  │  │  Persistent Volume         │  │  │
│  │  │  │ Agent      │ │  usage,    │  │  │  (Akash beta3 class)       │  │  │
│  │  │  │ Pipeline,  │ │  metadata) │  │  │                            │  │  │
│  │  │  │ ReAct Loop,│ │            │  │  │  • Cached Ollama models    │  │  │
│  │  │  │ Tools,     │ └────────────┘  │  │  • Per-user SQLite vector  │  │  │
│  │  │  │ Memory,    │                  │  │    databases               │  │  │
│  │  │  │ Embeddings,│                  │  │                            │  │  │
│  │  │  │ Caching    │                  │  └────────────────────────────┘  │  │
│  │  │  └────────────┘                  │                                  │  │
│  │  └──────────────────────────────────┘                                  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────────────────────┘
                           │ HTTPS
                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    IPFS / LIGHTHOUSE  (Decentralized Storage)                 │
│                                                                              │
│   • Encrypted chat archives (AES-256-GCM, Argon2id KDF)                      │
│   • User metadata bundles                                                    │
│   • Vector database snapshots                                                │
│   • Content-addressed (CID) — immutable, verifiable                          │
│   • Multi-gateway retrieval (Lighthouse, ipfs.io, dweb.link, Cloudflare)     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Frontend (ICP Canister)

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 19.2.4 | UI framework |
| TypeScript | 5.9.3 | Type safety |
| Zustand | 5.0.3 | State management |
| Vite | 5.4.0 | Build tooling |
| KaTeX | 0.16.28 | LaTeX math rendering |
| marked | 11.2.0 | Markdown parsing |
| highlight.js | 11.11.1 | Code syntax highlighting |
| DOMPurify | 3.3.1 | XSS sanitization |
| @dfinity/* | Latest | ICP canister interaction |
| Ed25519 | Browser crypto | Self-custody authentication |

### Backend (Akash Container)

| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11 | Runtime |
| Flask | 3.0.3 | Web framework |
| Ollama | Latest | LLM inference engine |
| SQLAlchemy | Latest | ORM (SQLite) |
| FastEmbed | 0.7.4 | Text embeddings (BAAI/bge-small-en-v1.5) |
| Prometheus | 0.20.0 | Metrics collection |
| PyCryptodome | 3.20.0 | AES-256-GCM encryption |
| Argon2-cffi | Latest | Key derivation (Argon2id) |
| RestrictedPython | 8.1 | Sandboxed code execution |
| APScheduler | Latest | Background task scheduling |

### Infrastructure

| Technology | Purpose |
|-----------|---------|
| Docker (CUDA 12.2) | Container runtime with GPU support |
| Akash Network | Decentralized GPU marketplace |
| Internet Computer (ICP) | Frontend hosting canister |
| Cloudflare Workers | SSL termination proxy |
| Lighthouse SDK | IPFS pinning and Filecoin deals |
| Prometheus + Grafana | Observability stack |

---

## Deployment Tiers

Trinity supports multiple deployment configurations depending on budget and compute needs:

| Tier | Model | GPU RAM | CPU | Storage | Approx. Cost |
|------|-------|---------|-----|---------|--------------|
| Production | `qwen3:32b` | 48 GB | 8 cores | 80 GB | ~$400-1000/mo |
| Test | `qwen3:32b` | 16 GB | 4 cores | 40 GB | ~$40-100/mo |

Deploy with `./scripts/trinity-deploy-production.sh production` or `./scripts/trinity-deploy-production.sh test`.

**GPU Model Allowlist (production):** a100, a6000, h100, l40s, a40, rtx4090 — enforced in `deploy-production.yaml` to ensure 40GB+ VRAM for full model offloading. `MIN_PRICE_MONTHLY: $400`.

**Akash Constraints:** `read_timeout: 60000` (60s hard limit enforced by Akash ingress).

---

## Request Lifecycle

### 1. User Sends a Message

```
Browser                  CF Worker              Akash Backend           Ollama
   │                        │                        │                     │
   │  POST /generate/agent  │                        │                     │
   │  + Auth Headers        │                        │                     │
   │───────────────────────>│  Forward + Strip SSL   │                     │
   │                        │───────────────────────>│                     │
   │                        │                        │  Rate limit check    │
   │                        │                        │  Auth verification   │
   │                        │                        │                     │
   │                        │                        │  Detect tools needed │
   │                        │                        │  Build context       │
   │                        │                        │  (memory + history)  │
   │                        │                        │                     │
   │                        │                        │  If tools detected:  │
   │                        │                        │  ┌─ ReAct Loop ────┐ │
   │                        │                        │  │ Think → Act →   │ │
   │                        │                        │  │ Observe → ...   │ │
   │                        │                        │  │ (max 15 iters)  ├─┤──> /api/chat
   │                        │                        │  └─────────────────┘ │<── streaming
   │                        │                        │                     │
   │                        │                        │  Else: direct chat   │
   │                        │                        │───────────────────>│
   │                        │                        │                     │
   │  SSE stream (tokens)   │   SSE passthrough      │<─ streaming tokens──│
   │<───────────────────────│<───────────────────────│                     │
   │                        │                        │                     │
   │  Stream complete       │                        │  Index to semantic   │
   │                        │                        │  memory (vector DB)  │
   │                        │                        │                     │
   │  POST /chat/autosave   │                        │                     │
   │  (2s debounce)         │                        │                     │
   │───────────────────────>│───────────────────────>│                     │
   │                        │                        │  Encrypt + IPFS save │
```

### 2. Authentication Flow

```
┌─ First Visit ──────────────────────────────────────────────────┐
│                                                                 │
│  1. App shows WelcomeModal (gates entire UI)                    │
│  2. User enters username + password                             │
│  3. Deterministic identity: Argon2id(password, username) → seed │
│  4. Ed25519KeyIdentity.fromSecretKey(seed) → keypair            │
│  5. Private key encrypted with AES-GCM + stored in localStorage │
│  6. Principal derived from public key (ICP standard)            │
│                                                                 │
├─ Every Request ────────────────────────────────────────────────┤
│                                                                 │
│  Headers built:                                                 │
│    ICP-Principal:  <principal text>                              │
│    ICP-Timestamp:  <Date.now()>                                  │
│    ICP-Nonce:      <random 16 bytes, hex>                        │
│    ICP-PublicKey:   <raw 32-byte pubkey, hex>                    │
│    ICP-Signature:  sign("<principal>:<timestamp>:                │
│                          <endpoint>:<nonce>")                    │
│                                                                 │
├─ Backend Verification ─────────────────────────────────────────┤
│                                                                 │
│  1. Extract 5 headers                                           │
│  2. Verify Ed25519 signature over canonical message             │
│  3. Check timestamp within 60-second window                     │
│  4. Check nonce not already used (TTLCache, 65s TTL)            │
│  5. Set request.principal for downstream use                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Auth** | Ed25519 self-custody (no OAuth, no passwords) | Full user sovereignty — no accounts, no email, no corporate dependency |
| **Encryption** | AES-256-GCM + Argon2id KDF | Military-grade encryption with modern memory-hard key derivation |
| **Storage** | IPFS (content-addressed, immutable) | No single point of failure, no server-owned data, user can verify integrity |
| **Frontend hosting** | ICP canister | Tamper-proof, no CDN, verifiable served content |
| **Compute** | Akash GPU marketplace | 60-80% cheaper than AWS/GCP, decentralized, no vendor lock-in |
| **LLM** | Self-hosted Ollama (not OpenAI API) | Full privacy — no data leaves the deployment, no API keys to manage |
| **State management** | Zustand (not Redux) | Minimal boilerplate, works outside React components via getState() |
| **Caching** | In-memory LRU (not Redis) | Zero-dependency for single-node Akash deployment (see [RATIONALE-CACHING](RATIONALE-CACHING.md)) |
| **Observability** | Self-hosted Prometheus + Grafana | $500+/mo savings vs SaaS alternatives (see [RATIONALE-PROMETHEUS](RATIONALE-PROMETHEUS.md)) |
| **Agent architecture** | Single-pass ReAct (not multi-pass routing) | Removed complexity overhead; single pipeline handles both simple and complex queries |

---

## Security Model

```
┌── Trust Boundaries ──────────────────────────────────────────────┐
│                                                                   │
│  BROWSER (trusted)                                                │
│  ├── Ed25519 private key (encrypted in localStorage)              │
│  ├── Local IndexedDB (unencrypted, local-only cache)              │
│  └── AES-GCM key derived from browser fingerprint                 │
│                                                                   │
│  ──────────────── HTTPS / Cloudflare Worker ─────────────────     │
│                                                                   │
│  BACKEND (trusted compute)                                        │
│  ├── Verifies Ed25519 signatures (60s window, nonce protection)   │
│  ├── Rate limiting (30 req/min API, 30 req/min storage)           │
│  ├── Token quotas (100K daily, 20K hourly per user)               │
│  ├── SSRF protection on URL fetching                              │
│  ├── RestrictedPython sandbox for code execution                  │
│  ├── Path traversal protection on filesystem tools                │
│  ├── CSRF protection via Origin/Referer validation                │
│  └── Input validation on all IDs (chat, principal, CID)           │
│                                                                   │
│  ──────────────── HTTPS / Multi-Gateway ─────────────────────     │
│                                                                   │
│  IPFS (untrusted storage)                                         │
│  ├── All data encrypted before upload (AES-256-GCM)               │
│  ├── Decryption key = user's principal (only they can read)       │
│  └── Content-addressing ensures integrity                         │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## Project Structure (Abridged)

```
Trinity/
├── backend/                          # Python Flask server
│   ├── inference_server.py           # App factory + startup
│   ├── config.py                     # All configuration constants
│   ├── database.py                   # SQLAlchemy models + DAO
│   ├── encryption.py                 # AES-256-GCM + Argon2id
│   ├── icp_auth.py                   # Ed25519 auth + decorators
│   ├── storage.py                    # User data file operations
│   ├── validation.py                 # Input validation + SSRF
│   ├── lighthouse.py                 # IPFS/Lighthouse integration
│   ├── routes/                       # 9 Flask blueprints (54 endpoints)
│   ├── middleware/                    # Observability, rate limiting, caching
│   ├── services/                     # 42 service modules (pipeline, agent, memory, knowledge, tools, etc.)
│   └── tests/                        # Unit, integration, and E2E tests
│
├── trinity-icp/                      # Frontend (ICP canister)
│   ├── src-react/                    # Active React 19 / TypeScript frontend (v3.0.0)
│   │   ├── components/               # UI components (chat, layout, modals, notifications, sidebar)
│   │   ├── hooks/                    # useAuth, useChat, useAutosave, useConnection
│   │   ├── store/                    # Zustand state management
│   │   ├── types/                    # TypeScript interfaces
│   │   ├── utils/                    # Crypto, markdown, SSE, IndexedDB, etc.
│   │   └── styles/                   # CSS Modules
│   ├── src/                          # Legacy vanilla JS frontend (v2.8.0, still buildable)
│   └── dfx.json                      # ICP canister config
│
├── deploy/                           # Deployment configurations
│   ├── docker/                       # Dockerfile (CUDA + Ollama)
│   ├── akash/                        # SDL files for 3 tiers + 6 specialty models
│   ├── cloudflare-worker/            # SSL termination proxy
│   └── docker-compose.monitoring.yml # Prometheus + Grafana
│
├── scripts/                          # Deployment and testing scripts
└── docs/                             # This documentation
```

---

## Related Architecture Documents

| Document | Focus |
|----------|-------|
| [FRONTEND.md](FRONTEND.md) | React component tree, hooks, state management, rendering pipeline |
| [BACKEND.md](BACKEND.md) | Flask server, routes, middleware, API endpoint reference |
| [MEMORY-SYSTEM.md](MEMORY-SYSTEM.md) | Three-tier memory architecture, embeddings, vector store |
| [STORAGE-AND-ENCRYPTION.md](STORAGE-AND-ENCRYPTION.md) | Encryption, IPFS persistence, autosave, IndexedDB, recovery |
| [INTELLIGENCE-AND-ROUTING.md](INTELLIGENCE-AND-ROUTING.md) | Agent pipeline, ReAct loop, tool system, decision-making |
| [RATIONALE-TEST-COVERAGE.md](RATIONALE-TEST-COVERAGE.md) | Why tiered test coverage targets |
| [RATIONALE-PROMETHEUS.md](RATIONALE-PROMETHEUS.md) | Why self-hosted Prometheus over SaaS |
| [RATIONALE-CACHING.md](RATIONALE-CACHING.md) | Why in-memory LRU over Redis |
