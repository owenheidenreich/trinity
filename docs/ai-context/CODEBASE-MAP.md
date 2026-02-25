# Trinity Codebase Map

> **Purpose:** Single-file reference for any LLM to understand Trinity without searching the codebase.
> **Last Updated:** February 20, 2026
> **Accuracy:** Verified against live codebase on `main` branch.

---

> For stack overview, architecture diagram, and critical rules, see [CLAUDE.md](CLAUDE.md).
> This file is a **lookup reference** — file paths, API routes, constants, auth headers.

---

## Project Structure

### Backend (`backend/`)

```
backend/
├── inference_server.py      # App factory, blueprint registration, startup
├── config.py                # All constants, env vars, defaults
├── icp_auth.py              # Ed25519 signature verification
├── encryption.py            # AES-256-GCM encrypt/decrypt
├── storage.py               # Compatibility facade (memory payload helpers)
├── validation.py            # Input sanitization
├── lighthouse.py            # IPFS upload/download via Lighthouse
├── database.py              # SQLAlchemy ORM (NOT integrated — future feature)
│
├── routes/                  # 9 blueprints, 54 endpoints
│   ├── __init__.py          # ALL_BLUEPRINTS list
│   ├── shared.py            # Shared helpers
│   ├── health.py            # /health, /metrics, /stats
│   ├── admin.py             # /admin/* cache, quota, storage, SLO
│   ├── generate.py          # /generate, /generate/agent
│   ├── chat.py              # Canonical chat + memory CRUD (state_store-backed)
│   ├── tools.py             # /tools/* search, browse, documents
│   ├── session.py           # /session/*, /funding/*
│   ├── mcp.py               # /mcp (MCP JSON-RPC 2.0)
│   └── passphrase.py        # /api/passphrase/* setup, unlock, change, lock, status
│
├── services/                # 49 business logic modules
│   ├── __init__.py          # Service exports
│   │
│   │   # ── Pipeline (new: extracted from 1086-line agent.py god module) ──
│   ├── context_loader.py    # Single load_context() → RequestContext dataclass
│   ├── query_classifier.py  # Deprecated stubs, is_personal_disclosure(), classify_temperature()
│   ├── prompt_assembler.py  # Token-budgeted prompt builder, auto-generated tool sections
│   ├── pipeline.py          # StreamingPipeline: ReAct loop (tools) / direct chat + tool-call rescue
│   ├── think_filter.py      # Streaming <think> block filter + code-fence helpers
│   ├── tiny_classifier.py   # ByteTransformer (pure numpy), classify_query(), detect_tools()
│   │
│   │   # ── Agent & Tools ──
│   ├── agent.py             # AgentPipeline (thin wrapper around StreamingPipeline)
│   ├── agent_prompts.py     # System prompts, ReAct prompts
│   ├── react_loop.py        # ReAct agentic loop (dual-mode: native + XML tools)
│   ├── code_executor.py     # Tool dispatcher (all 15 tools)
│   ├── tools.py             # Tool definitions, detection, parsing
│   │
│   │   # ── Memory & Knowledge ──
│   ├── knowledge_store.py   # Unified retrieval: facts + messages + relationships (ANN/brute-force)
│   ├── memory_tools.py      # MemGPT save/recall/search/update/forget with embeddings
│   ├── ingestion_worker.py  # Background daemon: index messages, extract facts, update summaries
│   ├── profile_extractor.py # LLM extraction for profile facts + graph triples
│   ├── graph_extractor.py   # Compatibility layer for unified extraction triples
│   ├── graph_memory.py      # Graph memory utilities
│   ├── memory.py            # Semantic memory retrieval (legacy shim)
│   ├── memory_ingestion.py  # Shim re-exports from ingestion_worker
│   ├── memory_eval.py       # Memory quality evaluation
│   │
│   │   # ── Storage ──
│   ├── state_store.py       # Canonical encrypted SQLite source-of-truth per principal
│   ├── db.py                # Database connection factory (sqlcipher + sqlite-vec)
│   ├── state_checkpoint.py  # Periodic IPFS checkpoint/restore for state.db
│   ├── vector_store.py      # Per-user SQLite vector DB
│   ├── user_data_store.py   # IPFS checkpoint/archive pipeline
│   │
│   │   # ── LLM Providers ──
│   ├── llama_server_provider.py  # llama-server (llama.cpp) LLM provider — OpenAI-compatible API
│   ├── llm_provider.py      # Abstract LLM provider interface
│   ├── provider_factory.py  # Provider factory (llama-server)
│   ├── model_router.py      # Route queries to conversation vs coder model
│   │
│   │   # ── Search & RAG ──
│   ├── search.py            # Brave web search
│   ├── fact_check.py        # Dual-search fact verification
│   ├── embeddings.py        # FastEmbed (384-dim)
│   ├── caching.py           # Embedding + semantic + token caches
│   │
│   │   # ── Infrastructure ──
│   ├── prompts.py           # System prompt construction
│   ├── structured.py        # Structured output parsing
│   ├── loading_messages.py  # Phase update messages
│   ├── akash.py             # Akash deployment info
│   ├── session_manager.py   # Session passphrase management
│   ├── slo_metrics.py       # SLO tracking and burn-rate alerting
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
├── models/                  # Trained classifier weights
│   ├── query_classifier.npz # ByteTransformer query classifier (~370KB, 7 classes)
│   └── tool_detector.npz    # ByteTransformer tool detector (~370KB, 16 classes)
│
└── tests/                   # 1055+ tests
    ├── conftest.py          # Root fixtures
    ├── fixtures/
    │   └── auth_fixtures.py # Ed25519 test keypairs
    ├── unit/                # Unit tests (33 files)
    ├── integration/         # Integration tests (2 files)
    └── e2e/                 # End-to-end tests
```

### Frontend — React 19 (`trinity-icp/src-react/` — ACTIVE, deployed)

TypeScript rewrite with hooks-first architecture. Zustand store, 4 custom hooks, 137 unit tests via Vitest.

```
trinity-icp/src-react/
├── App.tsx, main.tsx, config.ts
├── components/
│   ├── chat/           # CodeBlock, Message, MessageInput, MessageList,
│   │                   # StreamingMessage, MarkdownRenderer, MathBlock,
│   │                   # CopyAllButton, DownloadCards,
│   │                   # TypingIndicator
│   ├── layout/         # AppShell, EmptyState
│   ├── modals/         # AuthModal, ConfirmModal, InfoModal, KeyExportModal,
│   │                   # PassphraseModal, WelcomeModal
│   ├── notifications/  # ToastProvider, AutosaveIndicator
│   └── sidebar/        # Sidebar, MemoryPanel
├── hooks/              # useAuth, useChat, useConnection, usePassphrase
├── services/           # canister.ts (ICP canister integration)
├── store/              # Zustand store (index.ts, types.ts)
├── types/              # api.ts, auth.ts, message.ts
├── utils/              # crypto, markdown, sse, lighthouse, logger, codeParser
└── styles/             # tokens.css + global.css + components/
```

### Frontend — Vanilla JS (`trinity-icp/src/` — LEGACY, still buildable)

Imperative DOM manipulation app. Buildable via `npm run build:legacy` but no longer the default.

```
trinity-icp/src/
├── app.js                   # Orchestrator: imports modules, composes Actions, init()
├── config.js                # API endpoints, feature flags
├── core/                    # api.js, sse.js, environment.js, logger.js
├── features/                # generate.js, auth.js, chatManagement.js, memory.js
├── auth/                    # auth-entry.js, authManager.js, icp-auth.js, keyExportModal.js
├── state/                   # store.js (Zustand, CONTEXT_WINDOW_SIZE=20)
├── storage/                 # autosave.js, indexedDB.js, lighthouse.js
├── ui/                      # messages.js, sidebar.js, modals.js, etc.
└── utils/                   # crypto.js, math.js, validation.js
```

### Deploy (`deploy/`)

```
deploy/
├── docker/
│   ├── Dockerfile           # NVIDIA CUDA base, llama-server (llama.cpp), Flask
│   ├── startup.sh           # Container entrypoint (model download via HuggingFace + dual llama-server start)
├── akash/
│   ├── deploy-production.yaml       # Qwen3 32B (production)
│   ├── deploy-test.yaml            # Qwen3 8B (smoke-testing)
│   └── deploy-tier3.yaml           # Qwen3-Coder-Next 80B MoE (high-perf, A100-80GB/H100-80GB)
└── cloudflare-worker/
    └── worker.js            # SSL termination proxy
```

---

## API Endpoints (9 Blueprints)

### No Auth Required

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Server + llama-server status |
| GET | `/health/icp` | ICP-specific health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/stats` | Server statistics |
| POST | `/generate` | Standard inference |
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
| POST | `/generate/agent` | Canonical agent inference (server-side persistence + SSE IDs) |
| POST | `/chat/start` | Create chat, return canonical `chat_id` |
| POST | `/chat/autosave` | Retired compatibility endpoint (backend persistence is server-owned) |
| GET | `/chat/list` | List user's chats |
| GET | `/chat/<chat_id>?before_message_id=&limit=` | Load paginated chat messages |
| PATCH | `/chat/<chat_id>` | Update title/pin/archive |
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
| PATCH | `/user/memory/fact/<int:fact_id>` | Edit memory fact (text, category, importance) |
| DELETE | `/user/memory/fact/<int:fact_id>` | Soft-delete memory fact |
| GET | `/user/export` | Download all user data as ZIP |
| GET | `/user/stats` | User profile/chat/storage statistics |
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
| GET | `/admin/storage/status` | IPFS sync status, pending syncs |
| POST | `/admin/storage/rollback/<principal_id>` | Rollback user manifest |
| GET | `/admin/slo/status` | SLO burn-rate status |

### Passphrase (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/passphrase/setup` | Set up passphrase for user |
| POST | `/api/passphrase/unlock` | Unlock with passphrase |
| POST | `/api/passphrase/change` | Change passphrase |
| POST | `/api/passphrase/lock` | Lock session |
| GET | `/api/passphrase/status` | Check passphrase status |

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
| `ICP-Nonce` | Yes | UUID for replay protection |

### Signed Message Format

```
{principal}:{timestamp}:{endpoint}:{nonce}
```

Nonce is required on protected endpoints.

### Timestamp Window

**Actual enforcement:** `AUTH_TIMESTAMP_WINDOW_MS` from `config.py` (default `60000` / 60 seconds).

---

## Key Constants (`backend/config.py`)

### Model & Inference

| Constant | Default |
|----------|---------|
| `MODEL_NAME` | `qwen3:32b` |
| `MODEL_BACKEND` | `llama-server` |
| `LLAMA_SERVER_CHAT_PORT` | `8081` |
| `LLAMA_SERVER_INGEST_PORT` | `8082` |
| `NUM_CTX` | `65536` |
| `DEFAULT_MAX_TOKENS` | `8000` |
| `DEFAULT_TEMPERATURE` | `0.7` |
| `TEMPERATURE_CODE` | `0.1` |
| `TEMPERATURE_FACTUAL` | `0.3` |
| `TEMPERATURE_CONVERSATIONAL` | `0.7` |
| `DEFAULT_TOP_P` | `0.8` (env-configurable, tier3: 0.95) |
| `DEFAULT_TOP_K` | `20` (env-configurable, tier3: 40) |
| `DEFAULT_MIN_P` | `0` (env-configurable) |

### ReAct Loop

| Constant | Default |
|----------|---------|
| `REACT_ENABLED` | `true` |
| `REACT_MAX_ITERATIONS` | `5` |
| `REACT_TOKEN_BUDGET` | `48000` |
| `REFLEXION_MAX_RETRIES` | `3` |

### Storage & Security

| Constant | Default |
|----------|---------|
| `CHATS_DIR` | `/var/lib/trinity/chats` |
| `MAX_PROMPT_LENGTH` | `100000` |
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
| `WORKING_MEMORY_SIZE` | `5` (env-configurable) |
| `SEMANTIC_MEMORY_SIZE` | `8` (env-configurable) |
| `PROFILE_TOKEN_BUDGET` | `3500` (env-configurable) |
| `PROFILE_MAX_FACTS` | `25` (env-configurable) |
| `DEDUP_MERGE_THRESHOLD` | `0.85` |
| `DEDUP_SKIP_THRESHOLD` | `0.95` |
| `PROFILE_CATEGORIES` | `identity, work, interests, preferences, relationships` |

### Fact Schema (v3 canonical)

Each fact in canonical `memory_facts` has:
```
fact_id, text, category, importance, created_at, updated_at,
deleted_at, valid_at, invalid_at, source_message_id
```
- `fact_id` — stable API key for edit/delete
- `valid_at` — when the fact became true (ms epoch)
- `invalid_at` — when the fact was superseded (ms epoch, null = still valid)
- facts with `deleted_at` or `invalid_at` are excluded from prompts

Conversation summaries are stored in `conversation_summaries`:
`{chat_id, summary, last_message_id, updated_at}`.
---

## State Management (Zustand)

Store: `trinity-icp/src-react/store/index.ts` · Types: `trinity-icp/src-react/store/types.ts`

**CRITICAL:** Direct state assignment fails silently. Use setters only. See [CLAUDE.md](CLAUDE.md) → Critical Rules.

---

## Security Model

| Feature | Implementation |
|---------|---------------|
| Encryption | AES-256-GCM, random salt + nonce per operation |
| Key Derivation | Argon2id (primary) / PBKDF2 100k iterations (fallback), principal as password |
| Auth | Ed25519 signatures with 60s timestamp window |
| Replay Protection | Nonce TTLCache (65s expiry, 10k max) |
| Rate Limiting | Per-principal, configurable per-route |
| CORS | Whitelist: dubya.ai, ICP canister origins |
| Container | Non-root `trinity` user in Docker |
| Input Validation | Sanitized prompts, max length enforcement |
| Admin | Principal-based access control for /admin/* |

---

## Quick Lookup

| "I want to..." | File(s) |
|----------------|---------|
| Change an API endpoint | `backend/routes/<blueprint>.py` |
| Change LLM prompts | `backend/services/agent_prompts.py`, `backend/services/prompt_assembler.py` |
| Change context loading logic | `backend/services/context_loader.py`, `backend/services/query_classifier.py` |
| Change the streaming pipeline | `backend/services/pipeline.py` |
| Change query classification | `backend/services/tiny_classifier.py`, `backend/models/*.npz` |
| Change tool detection | `backend/services/tiny_classifier.py` (model), `backend/services/tools.py` (definitions + regex confirmation gate) |
| Change LLM provider | `backend/services/llama_server_provider.py`, `backend/services/provider_factory.py` |
| Change temperature routing | `backend/services/query_classifier.py` (`classify_temperature()`), `backend/config.py` |
| Add a tool | `backend/services/tools.py` + `code_executor.py` |
| Fix memory retrieval | `backend/services/knowledge_store.py` |
| Fix memory ingestion | `backend/services/ingestion_worker.py` |
| Fix think-block filtering | `backend/services/think_filter.py` |
| Fix database connections | `backend/services/db.py` |
| Fix auth | `backend/icp_auth.py` |
| Change rate limits | `backend/middleware/rate_limit.py` |
| Fix metrics | `backend/middleware/observability.py` |
| Change state shape | `trinity-icp/src-react/store/index.ts` |
| Canonical message persistence | `backend/routes/generate.py`, `backend/services/state_store.py` |
| Fix streaming | `trinity-icp/src-react/hooks/useChat.ts` |
| Retrain classifiers | `scripts/generate_training_data.py` → `scripts/train_classifiers.py` |
| Modify Docker | `deploy/docker/Dockerfile`, `deploy/docker/startup.sh` |
| Change Akash deploy | `deploy/akash/deploy-production.yaml`, `deploy/akash/deploy-test.yaml`, `deploy/akash/deploy-tier3.yaml` |

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
| `database.py` not integrated | 298-line ORM exists but unused |
| Cold start delay | First request after Akash deploy takes 20-30s (LLM loading) |
| `.bak` files in services/ | 5 backup files from refactor — can be cleaned up |
