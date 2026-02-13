# Trinity Codebase Map

> **Purpose:** Single-file reference for any LLM to understand Trinity without searching the codebase.
> **Last Updated:** February 10, 2026
> **Accuracy:** Verified against live codebase — all line counts, route counts, and constants are exact.

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
| LLM | Ollama | Port 11434 (internal) |

---

## Project Structure

### Backend (`backend/` — ~11,600 lines)

```
backend/
├── inference_server.py      # 349 lines — App factory, blueprint registration, startup
├── config.py                # 202 lines — All constants, env vars, defaults
├── icp_auth.py              # 286 lines — Ed25519 signature verification
├── encryption.py            # 129 lines — AES-256-GCM encrypt/decrypt
├── storage.py               # 124 lines — Chat file I/O
├── validation.py            # 131 lines — Input sanitization
├── lighthouse.py            # 303 lines — IPFS upload/download via Lighthouse
├── database.py              # 298 lines — SQLAlchemy ORM (NOT integrated — see Known Issues)
│
├── routes/                  # 2,853 lines — 7 blueprints, 49 routes
│   ├── __init__.py          #  44 lines — ALL_BLUEPRINTS list
│   ├── shared.py            #  77 lines — Shared helpers (build_context, etc.)
│   ├── health.py            # 113 lines — /health, /metrics, /stats (4 routes)
│   ├── admin.py             # 131 lines — /admin/* experiment & cache mgmt (8 routes)
│   ├── generate.py          # 736 lines — /generate, /generate/stream, /generate/agent (6 routes)
│   ├── chat.py              # 813 lines — /chat/*, /user/* CRUD + memory (14 routes)
│   ├── tools.py             # 367 lines — /tools/* search, browse, documents (7 routes)
│   ├── v4.py                # 259 lines — /v4/* vector store, tool execution (6 routes)
│   └── session.py           # 313 lines — /session/*, /funding/* (4 routes)
│
├── services/                # ~6,300 lines — Business logic
│   ├── __init__.py          # 201 lines — Service initialization, feature detection
│   ├── agent.py             # 797 lines — Multi-step agent orchestration
│   ├── agent_prompts.py     # 444 lines — Agent system prompts
│   ├── akash.py             # 232 lines — Akash deployment info
│   ├── caching.py           # 572 lines — Response caching with TTL
│   ├── code_executor.py     # 329 lines — Sandboxed Python execution
│   ├── complexity.py        # 370 lines — Query complexity scoring
│   ├── embeddings.py        # 231 lines — Text embedding generation
│   ├── experiments.py       # 338 lines — A/B testing framework
│   ├── loading_messages.py  # 197 lines — Random loading messages
│   ├── memory.py            # 286 lines — User memory management
│   ├── ollama.py            # 192 lines — Ollama HTTP client
│   ├── parallel.py          # 390 lines — Parallel inference
│   ├── prompts.py           # 216 lines — System prompt construction
│   ├── search.py            # 153 lines — Web search integration
│   ├── structured.py        # 282 lines — Structured output parsing
│   ├── tools.py             # 261 lines — Tool definitions and execution
│   ├── tracing.py           # 510 lines — Distributed tracing
│   ├── vector_store.py      # 455 lines — In-memory vector store + RAG
│   └── voting.py            # 270 lines — Best-of-N voting inference
│
├── services/graph/          # ~1,322 lines — LangGraph integration
│   ├── __init__.py          #  35 lines
│   ├── graph.py             # 215 lines — Graph builder
│   ├── agents.py            # 368 lines — Graph agent definitions
│   ├── nodes.py             # 242 lines — Graph node implementations
│   ├── edges.py             # 108 lines — Conditional edge logic
│   ├── llm.py               # 265 lines — LLM integration for graphs
│   └── state.py             #  89 lines — Graph state schema
│
├── middleware/               # ~1,958 lines
│   ├── __init__.py          # 137 lines — Middleware initialization
│   ├── observability.py     # 961 lines — Prometheus metrics, request logging
│   ├── rate_limit.py        # 427 lines — Per-principal rate limiting
│   ├── icp_cache.py         # 131 lines — Principal verification cache
│   └── ab_test.py           # 302 lines — A/B test assignment middleware
│
└── tests/                   # 607+ tests, 91.30% coverage
    ├── conftest.py          # 247 lines — Root fixtures
    ├── fixtures/
    │   └── auth_fixtures.py # 142 lines — Auth test helpers
    ├── unit/                # 14 test files
    │   ├── test_phase1_security.py       # 540 lines
    │   ├── test_phase2_stability.py      # 545 lines
    │   ├── test_phase3_architecture.py   # 458 lines
    │   ├── test_phase4_quality.py        # 487 lines
    │   ├── test_encryption.py            # 580 lines
    │   ├── test_icp_auth.py              # 482 lines
    │   ├── test_observability.py         # 1,111 lines
    │   ├── test_validation.py            # 686 lines
    │   ├── test_storage.py               # 373 lines
    │   ├── test_complexity.py            # 428 lines
    │   ├── test_caching.py               # 646 lines
    │   ├── test_experiments.py           # 640 lines
    │   ├── test_langgraph.py             # 495 lines
    │   └── test_langgraph_endpoint.py    # 278 lines
    ├── integration/
    │   └── test_inference.py # 137 lines
    └── e2e/
        └── test_full_pipeline.py # 484 lines
```

### Frontend (`trinity-icp/src/` — ~7,960 lines excluding bundled icp-auth.js)

```
trinity-icp/src/
├── index.html               # 162 lines — Entry point, CDN imports (KaTeX, marked.js)
├── styles.css               # 1,897 lines — Dark theme, rainbow borders, responsive
├── app.js                   # 266 lines — Orchestrator: imports modules, composes Actions, init()
├── config.js                # 196 lines — API endpoints, feature flags, version
├── tools.js                 # 111 lines — Tool registry for agent mode
│
├── core/                    # Infrastructure modules
│   ├── api.js               # 564 lines — HTTP client, signed requests, streaming
│   ├── environment.js       #  87 lines — Endpoint detection, version check
│   └── logger.js            #  43 lines — Structured logging with levels
│
├── features/                # Feature modules (extracted from app.js)
│   ├── auth.js              # 180 lines — Login/logout UI flow
│   ├── generate.js          # 377 lines — Message send, streaming response, stop button
│   ├── chatManagement.js    # 378 lines — Load/delete/new chat, sidebar management
│   └── memory.js            # 175 lines — User memory CRUD modal
│
├── auth/                    # Authentication
│   ├── authManager.js       # 304 lines — Ed25519 keypair management, request signing
│   ├── auth-entry.js        #  21 lines — Auto-init wrapper
│   ├── icp-auth.js          # 8,579 lines — Bundled ICP auth library (don't edit)
│   └── keyExportModal.js    # 111 lines — Key export/import UI
│
├── state/                   # State management
│   ├── store.js             # 335 lines — Zustand store (ALL state lives here)
│   └── contextMemory.js     #  76 lines — LLM context window management
│
├── storage/                 # Persistence
│   ├── autosave.js          # 356 lines — 2s debounce autosave with retry
│   ├── indexedDB.js         # 284 lines — Local IndexedDB for offline
│   └── lighthouse.js        # 265 lines — IPFS backup via Lighthouse SDK
│
├── ui/                      # UI components
│   ├── index.js             # 170 lines — UI module coordinator
│   ├── messages.js          # 486 lines — Message rendering, markdown, KaTeX
│   ├── modals.js            # 643 lines — All modal dialogs
│   ├── loadingMessages.js   # 199 lines — Loading animation with random messages
│   ├── notifications.js     # 133 lines — Toast notifications
│   ├── sidebar.js           # 112 lines — Chat list sidebar
│   ├── editMessage.js       # 129 lines — Inline message editing
│   ├── rainbowBorder.js     #  45 lines — Rainbow gradient hover effect
│   └── domCache.js          #  39 lines — DOM element cache
│
├── utils/                   # Utilities
│   ├── crypto.js            # 130 lines — Browser crypto helpers
│   ├── math.js              # 200 lines — KaTeX rendering utilities
│   └── validation.js        # 106 lines — Client-side input validation
│
└── api/                     # API clients
    └── canister-client.js   # 350 lines — ICP canister HTTP interface
```

### Deploy (`deploy/`)

```
deploy/
├── docker/
│   ├── Dockerfile           # 212 lines — NVIDIA CUDA base, Ollama, Flask
│   ├── build.sh             # Build script
│   └── startup.sh           # Container entrypoint
├── akash/
│   └── deploy.yaml          # Akash SDL manifest
├── cloudflare-worker/
│   └── worker.js            # SSL termination proxy
├── grafana/                 # Monitoring dashboards
└── prometheus/              # Metrics collection
```

---

## API Endpoints (49 Routes, 7 Blueprints)

### No Auth Required

| Method | Path | Blueprint | Description |
|--------|------|-----------|-------------|
| GET | `/health` | health | Server + Ollama status |
| GET | `/health/icp` | health | ICP-specific health check |
| GET | `/metrics` | health | Prometheus metrics |
| GET | `/stats` | health | Server statistics |
| POST | `/generate` | generate | Standard inference |
| POST | `/generate/simple` | generate | Quick inference (low tokens) |
| POST | `/generate/simple/stream` | generate | Quick streaming inference |
| POST | `/generate/stream` | generate | Streaming inference |
| POST | `/generate/agent` | generate | Multi-step agent inference |
| POST | `/generate/langgraph` | generate | LangGraph agent inference |
| GET | `/v4/status` | v4 | V4 feature status |
| GET | `/funding/status` | session | Funding status |
| GET | `/session/status` | session | Session tier info |
| POST | `/session/request` | session | Request session |
| GET | `/session/check/<session_id>` | session | Check session validity |

### Auth Required (Ed25519 Signature)

| Method | Path | Blueprint | Description |
|--------|------|-----------|-------------|
| POST | `/chat/autosave` | chat | Save encrypted chat |
| GET | `/chat/list` | chat | List user's chats |
| GET | `/chat/<chat_id>` | chat | Load specific chat |
| DELETE | `/chat/<chat_id>` | chat | Delete chat |
| POST | `/chat/<chat_id>/pin` | chat | Pin/unpin chat |
| POST | `/chat/<chat_id>/archive` | chat | Archive chat to IPFS |
| GET | `/chat/recover-archives` | chat | Recover archived chats |
| GET | `/chat/archive/<cid>` | chat | Load archived chat by CID |
| GET | `/chat/archive/status/<cid>` | chat | Check archive status |
| GET | `/user/status` | chat | User account status |
| GET | `/user/memory` | chat | Get user memory |
| POST | `/user/memory` | chat | Update user memory |
| POST | `/user/memory/fact` | chat | Add memory fact |
| DELETE | `/user/memory/fact/<int:index>` | chat | Delete memory fact |
| POST | `/tools/search` | tools | Web search |
| POST | `/tools/browse` | tools | Browse URL |
| POST | `/tools/search-and-summarize` | tools | Search + summarize |
| POST | `/tools/documents/upload` | tools | Upload document |
| POST | `/tools/documents/query` | tools | Query documents (RAG) |
| POST | `/tools/transcript/clean` | tools | Clean transcript |
| GET | `/tools/status` | tools | Tools availability |
| POST | `/v4/vector/index` | v4 | Index vectors |
| POST | `/v4/vector/document` | v4 | Add document to vector store |
| POST | `/v4/vector/search` | v4 | Semantic vector search |
| POST | `/v4/vector/sync` | v4 | Sync vector store |
| POST | `/v4/tools/execute` | v4 | Execute tool |

### Admin Only (Principal in ADMIN_PRINCIPALS)

| Method | Path | Blueprint | Description |
|--------|------|-----------|-------------|
| GET | `/admin/experiments` | admin | List experiments |
| POST | `/admin/experiments/<name>/enable` | admin | Enable experiment |
| POST | `/admin/experiments/<name>/disable` | admin | Disable experiment |
| GET | `/admin/experiments/assignment/<session_id>` | admin | Check assignment |
| GET | `/admin/cache/stats` | admin | Cache statistics |
| POST | `/admin/cache/clear` | admin | Clear cache |
| GET | `/admin/tokens/usage` | admin | Token usage stats |
| GET | `/admin/quota/usage` | admin | Quota usage stats |

---

## Authentication

### Auth Headers

Every `/chat/*`, `/tools/*`, and `/v4/*` request must include:

| Header | Required | Description |
|--------|----------|-------------|
| `ICP-Principal` | Yes | Base32-encoded principal ID |
| `ICP-Signature` | Yes | Ed25519 signature (hex) |
| `ICP-Timestamp` | Yes | Unix timestamp (ms) |
| `ICP-PublicKey` | Yes* | Ed25519 public key (hex) |
| `ICP-Nonce` | No | UUID for replay protection |

*Technically optional in code, but required in practice since principal-to-key lookup raises `NotImplementedError`.

### Signed Message Format

```
{timestamp}.{HTTP_METHOD}.{path}.{sha256(body)}
```

Example: `1707000000000.POST./chat/autosave.abc123def456...`

### Timestamp Window

**Actual enforcement:** 60 seconds (hardcoded in `icp_auth.py` line 91).
Note: `config.py` defines `AUTH_TIMESTAMP_WINDOW_MS = 300000` (5 min) but this constant is **not used** by `icp_auth.py`.

### Nonce Replay Protection

Uses `cachetools.TTLCache(maxsize=10000, ttl=65)` — nonces expire after 65 seconds.

---

## Key Constants (`backend/config.py`)

### Model Configuration

| Constant | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `"phi3"` | Primary model (env override) |
| `MODEL_BACKEND` | `"ollama"` | Inference backend |
| `FAST_MODEL` | `"qwen3:1.7b"` | Quick responses |
| `SMART_MODEL` | `"qwen3:8b"` | Complex queries |
| `REASONING_MODEL` | `"qwen3:32b"` | Deep reasoning |
| `MULTI_MODEL_ENABLED` | `DEPLOYMENT_TIER >= 2` | Multi-model routing |
| `OLLAMA_HOST` | `"http://localhost:11434"` | Ollama endpoint |

### Token Limits

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_PROMPT_LENGTH` | `50000` | Max input chars |
| `DEFAULT_MAX_TOKENS` | `8000` | Standard response |
| `DEFAULT_MAX_TOKENS_STREAM` | `4000` | Streaming response |
| `SIMPLE_MAX_TOKENS` | `150` | Simple mode |
| `SIMPLE_MAX_TOKENS_CAP` | `300` | Simple mode cap |
| `REASONING_MIN_TOKENS` | `8000` | Reasoning mode |
| `REASONING_MIN_TOKENS_STREAM` | `4000` | Reasoning streaming |

### Timeouts (seconds)

| Constant | Value | Description |
|----------|-------|-------------|
| `OLLAMA_TIMEOUT` | `600` | Standard inference |
| `OLLAMA_TIMEOUT_STREAM` | `300` | Streaming |
| `OLLAMA_TIMEOUT_SIMPLE` | `120` | Simple mode |
| `OLLAMA_TIMEOUT_TOOLS` | `300` | Tool execution |
| `WEB_FETCH_TIMEOUT` | `15` | Web scraping |
| `WEB_SEARCH_TIMEOUT` | `10` | Web search |

### Storage & Security

| Constant | Value | Description |
|----------|-------|-------------|
| `CHATS_DIR` | `"/var/lib/trinity/chats"` | Chat storage path |
| `PBKDF2_ITERATIONS` | `100000` | Key derivation rounds |
| `ENCRYPTION_KEY_LENGTH` | `32` | AES-256 key bytes |
| `AUTH_TIMESTAMP_WINDOW_MS` | `300000` | **UNUSED** — see icp_auth.py |
| `MAX_ARCHIVED_CHATS` | `20` | Max IPFS archives per user |
| `CHAT_INACTIVE_DAYS` | `7` | Days before cleanup |

### Vector Store & RAG

| Constant | Value |
|----------|-------|
| `EMBEDDING_MODEL` | `"BAAI/bge-small-en-v1.5"` |
| `EMBEDDING_DIM` | `384` |
| `CHUNK_SIZE` | `500` |
| `CHUNK_OVERLAP` | `50` |
| `RAG_TOP_K` | `5` |

### Voting & Complexity

| Constant | Value |
|----------|-------|
| `VOTING_CANDIDATES` | `3` |
| `VOTING_TEMPERATURES` | `[0.3, 0.7, 1.0]` |
| `VOTING_MIN_COMPLEXITY` | `7` |
| `CODE_EXECUTION_ENABLED` | `false` (env override) |
| `CODE_EXECUTION_TIMEOUT` | `5` |

---

## Model Tiers

| Tier | Primary Model | GPU/RAM | Cost/mo | Multi-Model |
|------|--------------|---------|---------|-------------|
| 1 | phi3 | CPU only | ~$0 (local) | No |
| 2 | llama3.1:8b | 16GB GPU | ~$50 | Yes |
| 3 | qwen2.5:72b | 64GB GPU | ~$200 | Yes |

Tier is derived from `MODEL_NAME` in `config.py`. Multi-model routing (fast/smart/reasoning) activates at Tier 2+.

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
| CSRF | Origin header validation on mutations |
| Container | Non-root `trinity` user in Docker |
| Input Validation | Sanitized prompts, max length enforcement |
| Admin | Principal-based access control for /admin/* |

---

## State Management (Zustand)

**CRITICAL:** Zustand getters are read-only. Direct assignment fails **silently** — no error, just broken state.

```javascript
// ❌ WRONG — fails silently, state never updates
State.isAuthenticated = true;
State.chatHistory = [...];

// ✅ CORRECT — use setter methods
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

All state lives in `trinity-icp/src/state/store.js`. Every UI module reads state via getters, writes via setters.

---

## How To...

### Add a New Backend Endpoint

1. Choose the appropriate blueprint in `backend/routes/` (or create a new one)
2. Add the route function with `@blueprint.route('/path', methods=['POST'])`
3. For auth: add `@require_auth` decorator (from `icp_auth.py`)
4. For admin: add `@require_admin` decorator
5. If new blueprint: register it in `backend/routes/__init__.py` → `ALL_BLUEPRINTS`
6. Add tests in `backend/tests/unit/`
7. Update `deploy/docker/Dockerfile` if new files were created outside existing COPY paths
8. Rebuild Docker → Push → Redeploy Akash

### Add a New Frontend Feature

1. Create module in `trinity-icp/src/features/` (or `core/` for infrastructure)
2. Import in `app.js` and add to the `Actions` object
3. Wire UI triggers via `data-action` attributes in HTML or event listeners in `init()`
4. Use `State.setX()` for state changes — never assign directly
5. Use `API.authenticatedRequest()` for backend calls requiring auth
6. Use `Logger.info/warn/error()` for structured logging
7. Deploy: `dfx deploy trinity_frontend --network ic`

### Deploy to Production

```bash
# Full pipeline (interactive tier selection):
./scripts/trinity-deploy-production.sh

# Auto-select tier:
./scripts/trinity-deploy-production.sh 2    # Tier 2 (~$50/mo)
./scripts/trinity-deploy-production.sh 3    # Tier 3 (~$200/mo)
```

This handles: Docker build → Push → Akash deploy → Cloudflare update → ICP deploy → Verify.

### Run Tests

```bash
cd backend
../.venv/bin/python -m pytest tests/unit/ -q           # All unit tests
../.venv/bin/python -m pytest tests/unit/ -q --tb=line  # Compact output
../.venv/bin/python -m pytest tests/ --cov --cov-report=html  # With coverage
```

### Check Health

```bash
curl https://api.dubya.ai/health          # Production
curl http://localhost:8000/health          # Local
```

### Add a Config Constant

1. Add to `backend/config.py` with env var override and sensible default
2. Import in consuming module: `from config import MY_CONSTANT`
3. Add to this document's Key Constants table
4. If it affects deployment, add to Akash YAML env vars

---

## Key Files Quick Reference

| "I want to..." | File(s) |
|----------------|---------|
| Change an API endpoint | `backend/routes/<blueprint>.py` |
| Add auth to a route | `backend/icp_auth.py` — `@require_auth` decorator |
| Change encryption | `backend/encryption.py` |
| Modify chat save/load | `backend/routes/chat.py` + `backend/storage.py` |
| Change LLM prompts | `backend/services/prompts.py` or `services/agent_prompts.py` |
| Adjust model routing | `backend/config.py` + `backend/services/agent.py` |
| Change rate limits | `backend/middleware/rate_limit.py` |
| Fix metrics | `backend/middleware/observability.py` |
| Add a frontend feature | `trinity-icp/src/features/` → import in `app.js` |
| Change UI components | `trinity-icp/src/ui/` |
| Fix auth flow | `trinity-icp/src/auth/authManager.js` + `features/auth.js` |
| Change state shape | `trinity-icp/src/state/store.js` |
| Fix autosave | `trinity-icp/src/storage/autosave.js` |
| Change API calls | `trinity-icp/src/core/api.js` |
| Update styles | `trinity-icp/src/styles.css` |
| Modify Docker image | `deploy/docker/Dockerfile` |
| Change Akash deployment | `deploy/akash/deploy.yaml` |
| Update Cloudflare proxy | `deploy/cloudflare-worker/worker.js` |
| Run/add tests | `backend/tests/unit/` |
| Change config defaults | `backend/config.py` |

---

## Known Issues

| Issue | Details | Impact |
|-------|---------|--------|
| `AUTH_TIMESTAMP_WINDOW_MS` unused | `config.py` defines 5min, `icp_auth.py` hardcodes 60s | Config constant is dead code |
| `database.py` not integrated | 298-line ORM exists but is not imported by any production code, not in Dockerfile | No impact — future feature |
| No frontend tests | All 607+ tests are backend only | Frontend regressions caught manually |
| Backup `.bak` files | Some backup files exist in codebase tree | No runtime impact, minor clutter |
| Cold start delay | First request after Akash deploy takes 20-30s (LLM loading) | Expected behavior |
| `icp-auth.js` is bundled | 8,579-line file — don't edit directly | Use authManager.js for auth changes |

---

## Canister IDs

| Canister | ID | URL |
|----------|----|-----|
| Frontend | `zc67k-kiaaa-aaaal-qtmiq-cai` | https://dubya.ai |
| Backend | `au5zq-2qaaa-aaaal-qtowa-cai` | (on-chain backend canister) |

---

## Memory System

| Type | Scope | Size | Storage |
|------|-------|------|---------|
| contextMemory | Per-request | Last 6 messages | In-memory (frontend) |
| conversationSummary | Per-chat | Compressed every 15 msgs | In-memory (frontend) |
| userMemory | Per-user, all chats | Persistent facts | `user_memory.json` on Akash disk |

Managed by `trinity-icp/src/state/contextMemory.js` (frontend) and `backend/services/memory.py` (backend).

---

## Deployment Pipeline

```
Code Change
    ↓
Docker Build (deploy/docker/Dockerfile)
    ↓
Docker Push (gdubx/trinity-inference:TAG)
    ↓
Akash Deploy (deploy/akash/deploy.yaml via provider-services CLI)
    ↓
Cloudflare Worker Update (if URL changed)
    ↓
ICP Deploy (dfx deploy trinity_frontend --network ic)
    ↓
Verify (curl https://api.dubya.ai/health)
```

**Script:** `./scripts/trinity-deploy-production.sh [tier]` handles the full pipeline.

---

## UI Design System

| Property | Value |
|----------|-------|
| Background | `#1a1a1a` |
| Text | `#ffffff` |
| Border Radius | 6px (elements), 8px (modals) |
| Interactive Hover | Rainbow gradient border animation |
| Labels | Text-only (no emojis) |
| Theme | Dark only |
