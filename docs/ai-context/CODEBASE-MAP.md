# Trinity Codebase Map

> **Purpose:** Single-file reference for any LLM to understand Trinity without searching the codebase.
> **Last Updated:** February 13, 2026
> **Accuracy:** Verified against live codebase on `phase-5.5-legacy-cleanup` branch.

---

## What Is Trinity

Trinity is a **fully decentralized AI chat application** with self-custody authentication, encrypted storage, and live KaTeX math rendering. The frontend is hosted on ICP (Internet Computer Protocol), the backend runs on Akash Network (decentralized cloud) with Ollama for LLM inference, and chat data is encrypted with AES-256-GCM and backed up to IPFS via Lighthouse.

---

## Architecture

```
Browser → ICP Canister (Frontend) → Cloudflare Worker (SSL) → Akash Backend (Flask) → Ollama (LLM)
                                                                      ↓
                                                              Encrypted JSON on Akash disk
                                                                      ↓
                                                              IPFS Backup (Lighthouse)
```

| Layer | Technology | URL |
|-------|-----------|-----|
| Frontend | Vanilla JS on ICP | https://dubya.ai |
| SSL Proxy | Cloudflare Worker | https://api.dubya.ai |
| Backend | Python Flask on Akash | Port 8000 |
| LLM | Ollama (qwen2.5-coder:32b) | Port 11434 (internal) |

---

## Project Structure

### Backend (`backend/`)

```
backend/
├── inference_server.py      # App factory, blueprint registration, startup
├── config.py                # All constants, env vars, defaults
├── icp_auth.py              # Ed25519 signature verification
├── encryption.py            # AES-256-GCM encrypt/decrypt
├── storage.py               # Chat file I/O
├── validation.py            # Input sanitization
├── lighthouse.py            # IPFS upload/download via Lighthouse
├── database.py              # SQLAlchemy ORM (NOT integrated — future feature)
│
├── routes/                  # 8 blueprints
│   ├── __init__.py          # ALL_BLUEPRINTS list
│   ├── shared.py            # Shared helpers
│   ├── health.py            # /health, /metrics, /stats
│   ├── admin.py             # /admin/* cache & quota mgmt
│   ├── generate.py          # /generate, /generate/agent
│   ├── chat.py              # /chat/*, /user/* CRUD + memory
│   ├── tools.py             # /tools/* search, browse, documents
│   ├── v4.py                # /v4/* vector store, tool execution
│   ├── session.py           # /session/*, /funding/*
│   └── mcp.py               # /mcp (MCP JSON-RPC 2.0)
│
├── services/                # Business logic
│   ├── __init__.py          # Service exports
│   ├── agent.py             # Single-pass orchestrator (detect tools → ReAct or direct)
│   ├── agent_prompts.py     # System prompts, ReAct prompts
│   ├── react_loop.py        # ReAct agentic loop (dual-mode: native + XML tools)
│   ├── code_executor.py     # Tool dispatcher (all 13 tools)
│   ├── tools.py             # Tool definitions, detection, parsing
│   ├── memory_tools.py      # MemGPT save/recall/search with embeddings
│   ├── ollama.py            # Ollama HTTP client
│   ├── search.py            # Brave web search
│   ├── fact_check.py        # Dual-search fact verification
│   ├── embeddings.py        # FastEmbed (384-dim)
│   ├── vector_store.py      # Per-user SQLite vector DB
│   ├── memory.py            # Semantic memory retrieval
│   ├── caching.py           # Embedding + semantic + token caches
│   ├── prompts.py           # System prompt construction
│   ├── structured.py        # Structured output parsing
│   ├── loading_messages.py  # Phase update messages
│   ├── akash.py             # Akash deployment info
│   ├── mcp_server.py        # MCP server (JSON-RPC 2.0)
│   ├── mcp_client.py        # MCP client (external tool connector)
│   ├── repo_map.py          # Repository structure visualization
│   └── tracing.py           # Distributed tracing
│
├── middleware/
│   ├── __init__.py          # Middleware exports
│   ├── observability.py     # Prometheus metrics (single source of truth)
│   ├── rate_limit.py        # Per-principal rate limiting
│   └── icp_cache.py         # ICP deterministic caching
│
├── mcp_stdio_server.py      # MCP stdio entry point (Claude Desktop)
│
└── tests/                   # 615 tests, 91.30% coverage
    ├── conftest.py          # Root fixtures
    ├── fixtures/
    │   └── auth_fixtures.py # Ed25519 test keypairs
    ├── unit/                # Unit tests
    ├── integration/         # Integration tests
    └── e2e/                 # End-to-end tests
```

### Frontend — Vanilla JS (`trinity-icp/src/` — ACTIVE, deployed)

```
trinity-icp/src/
├── app.js                   # Orchestrator: imports modules, composes Actions, init()
├── config.js                # API endpoints, feature flags
├── tools.js                 # Tool registry
├── core/
│   ├── api.js               # HTTP client, signed requests, streaming
│   ├── sse.js               # Server-Sent Events parser
│   ├── environment.js       # Endpoint detection, version check
│   └── logger.js            # Structured logging
├── features/
│   ├── generate.js          # Agentic streaming (3-part DOM, code blocks, Continue button)
│   ├── auth.js              # Login/logout UI
│   ├── chatManagement.js    # Load/delete/new chat, sidebar
│   └── memory.js            # User memory CRUD modal
├── auth/
│   ├── authManager.js       # Ed25519 keypair management
│   ├── icp-auth.js          # Bundled ICP auth library (don't edit)
│   └── keyExportModal.js    # Key export/import UI
├── state/
│   └── store.js             # Zustand store (CONTEXT_WINDOW_SIZE=20)
├── storage/
│   ├── autosave.js          # Rate-limited autosave
│   ├── indexedDB.js         # Local IndexedDB persistence
│   └── lighthouse.js        # IPFS backup
├── ui/
│   ├── messages.js          # Message rendering, markdown, KaTeX
│   ├── sidebar.js           # Chat list
│   ├── modals.js            # Modal dialogs
│   ├── editMessage.js       # Inline message editing
│   ├── codePanel.js         # Code display
│   ├── loadingMessages.js   # Loading indicators
│   ├── notifications.js     # Toast notifications
│   └── rainbowBorder.js     # Visual effects
└── utils/
    ├── crypto.js            # AES-GCM encryption
    ├── math.js              # KaTeX rendering
    └── validation.js        # Client-side validation
```

### Frontend — React 19 (`trinity-icp/src-react/` — NEW, not yet deployed)

TypeScript rewrite with hooks-first architecture. Same Zustand store shape for compatibility. 62 files, 137 unit tests via Vitest.

### Deploy (`deploy/`)

```
deploy/
├── docker/
│   ├── Dockerfile           # NVIDIA CUDA base, Ollama, Flask
│   ├── build.sh             # Build script
│   └── startup.sh           # Container entrypoint (model pull + server start)
├── akash/
│   ├── deploy-tier1-basic.yaml      # Qwen3 1.7B
│   ├── deploy-tier2-balanced.yaml   # Qwen2.5 14B
│   └── deploy-tier3-complex.yaml    # Qwen2.5-Coder 32B
└── cloudflare-worker/
    └── worker.js            # SSL termination proxy
```

---

## API Endpoints (8 Blueprints)

### No Auth Required

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Server + Ollama status |
| GET | `/health/icp` | ICP-specific health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/stats` | Server statistics |
| POST | `/generate` | Standard inference |
| POST | `/generate/agent` | Agent inference with ReAct + tool calling |
| GET | `/v4/status` | V4 feature status |
| GET | `/funding/status` | Funding status |
| GET | `/session/status` | Session tier info |
| POST | `/session/request` | Request session |
| GET | `/session/check/<id>` | Check session validity |
| GET | `/mcp` | MCP server info |
| POST | `/mcp` | MCP JSON-RPC 2.0 handler |

### Auth Required (Ed25519 Signature)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat/autosave` | Save encrypted chat |
| GET | `/chat/list` | List user's chats |
| GET | `/chat/<chat_id>` | Load specific chat |
| DELETE | `/chat/<chat_id>` | Delete chat |
| POST | `/chat/<chat_id>/pin` | Pin/unpin chat |
| POST | `/chat/<chat_id>/archive` | Archive to IPFS |
| GET | `/chat/recover-archives` | Recover archived chats |
| GET | `/chat/archive/<cid>` | Load archived chat by CID |
| GET | `/chat/archive/status/<cid>` | Check archive status |
| GET | `/user/status` | User account status |
| GET | `/user/memory` | Get user memory |
| POST | `/user/memory` | Update user memory |
| POST | `/user/memory/fact` | Add memory fact |
| DELETE | `/user/memory/fact/<int:index>` | Delete memory fact |
| POST | `/tools/search` | Web search |
| POST | `/tools/browse` | Browse URL |
| POST | `/tools/search-and-summarize` | Search + summarize |
| POST | `/tools/documents/upload` | Upload document |
| POST | `/tools/documents/query` | Query documents (RAG) |
| POST | `/tools/transcript/clean` | Clean transcript |
| GET | `/tools/status` | Tools availability |
| POST | `/v4/vector/index` | Index vectors |
| POST | `/v4/vector/document` | Add document to vector store |
| POST | `/v4/vector/search` | Semantic vector search |
| POST | `/v4/vector/sync` | Sync vector store |
| POST | `/v4/tools/execute` | Execute tool |

### Admin Only (Principal in ADMIN_PRINCIPALS)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/cache/stats` | Cache statistics |
| POST | `/admin/cache/clear` | Clear cache |
| GET | `/admin/tokens/usage` | Token usage stats |
| GET | `/admin/quota/usage` | Quota usage stats |

---

## Authentication

### Auth Headers

Every `/chat/*`, `/tools/*`, and `/v4/*` request must include:

| Header | Required | Description |
|--------|----------|-------------|
| `ICP-Principal` | Yes | Base32-encoded principal ID |
| `ICP-Signature` | Yes | Ed25519 signature (hex) |
| `ICP-Timestamp` | Yes | Unix timestamp (ms) |
| `ICP-PublicKey` | Yes | Ed25519 public key (hex) |
| `ICP-Nonce` | No | UUID for replay protection |

### Signed Message Format

```
{timestamp}.{HTTP_METHOD}.{path}.{sha256(body)}
```

### Timestamp Window

**Actual enforcement:** 60 seconds (hardcoded in `icp_auth.py`).
Note: `config.py` defines `AUTH_TIMESTAMP_WINDOW_MS = 300000` (5 min) but this constant is **not used**.

---

## Key Constants (`backend/config.py`)

### Model & Inference

| Constant | Default |
|----------|---------|
| `MODEL_NAME` | `qwen2.5-coder:32b` |
| `NUM_CTX` | `32768` |
| `DEFAULT_MAX_TOKENS` | `8000` |
| `DEFAULT_TEMPERATURE` | `0.7` |
| `OLLAMA_TIMEOUT` | `600` (10 min) |
| `OLLAMA_TIMEOUT_TOOLS` | `300` (5 min) |

### ReAct Loop

| Constant | Default |
|----------|---------|
| `REACT_ENABLED` | `true` |
| `REACT_MAX_ITERATIONS` | `15` |
| `REACT_TOKEN_BUDGET` | `24000` |
| `REFLEXION_MAX_RETRIES` | `3` |

### Storage & Security

| Constant | Default |
|----------|---------|
| `CHATS_DIR` | `/var/lib/trinity/chats` |
| `MAX_PROMPT_LENGTH` | `50000` |
| `MAX_ARCHIVED_CHATS` | `20` |
| `CODE_EXECUTION_ENABLED` | `false` |
| `WORKSPACE_ROOT` | `/workspace` |

### RAG & Memory

| Constant | Default |
|----------|---------|
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_DIM` | `384` |
| `CHUNK_SIZE` | `500` |
| `RAG_TOP_K` | `5` |
| `WORKING_MEMORY_SIZE` | `3` |
| `SEMANTIC_MEMORY_SIZE` | `5` |

---

## State Management (Zustand)

**CRITICAL:** Zustand getters are read-only. Direct assignment fails **silently**.

```javascript
// ❌ WRONG — fails silently
State.isAuthenticated = true;

// ✅ CORRECT — use setter methods
State.setAuthenticated(principal, timestamp);
```

All state lives in `trinity-icp/src/state/store.js`. Key constants: `CONTEXT_WINDOW_SIZE = 20`.

---

## Security Model

| Feature | Implementation |
|---------|---------------|
| Encryption | AES-256-GCM, random salt + nonce per operation |
| Key Derivation | PBKDF2 with 100k iterations, principal as password |
| Auth | Ed25519 signatures with 60s timestamp window |
| Replay Protection | Nonce TTLCache (65s expiry, 10k max) |
| Rate Limiting | Per-principal, configurable per-route |
| CORS | Whitelist: dubya.ai, ICP canister origins |
| Container | Non-root `trinity` user in Docker |
| Input Validation | Sanitized prompts, max length enforcement |
| Admin | Principal-based access control for /admin/* |

---

## How To...

### Deploy to Production
```bash
./scripts/trinity-deploy-production.sh [tier]   # Handles everything
```

### Run Tests
```bash
cd backend && python -m pytest tests/ -x -q
```

### Check Health
```bash
curl https://api.dubya.ai/health
```

---

## Quick Lookup

| "I want to..." | File(s) |
|----------------|---------|
| Change an API endpoint | `backend/routes/<blueprint>.py` |
| Change LLM prompts | `backend/services/agent_prompts.py` |
| Add a tool | `backend/services/tools.py` + `code_executor.py` |
| Fix auth | `backend/icp_auth.py` |
| Change rate limits | `backend/middleware/rate_limit.py` |
| Fix metrics | `backend/middleware/observability.py` |
| Change state shape | `trinity-icp/src/state/store.js` |
| Fix autosave | `trinity-icp/src/storage/autosave.js` |
| Fix streaming | `trinity-icp/src/features/generate.js` |
| Modify Docker | `deploy/docker/Dockerfile` |
| Change Akash deploy | `deploy/akash/deploy-tier*.yaml` |

---

## Canister IDs

| Canister | ID | URL |
|----------|----|-----|
| Frontend | `zc67k-kiaaa-aaaal-qtmiq-cai` | https://dubya.ai |
| Backend | `au5zq-2qaaa-aaaal-qtowa-cai` | (on-chain) |

---

## Known Issues

| Issue | Details |
|-------|---------|
| `AUTH_TIMESTAMP_WINDOW_MS` unused | config.py defines 5min, icp_auth.py hardcodes 60s |
| `database.py` not integrated | 298-line ORM exists but unused |
| React frontend not deployed | `src-react/` ready but `src/` (vanilla JS) is active |
| Cold start delay | First request after Akash deploy takes 20-30s (LLM loading) |
