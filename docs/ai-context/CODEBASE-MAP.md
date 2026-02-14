# Trinity Codebase Map

> **Purpose:** Single-file reference for any LLM to understand Trinity without searching the codebase.
> **Last Updated:** February 13, 2026
> **Accuracy:** Verified against live codebase on `phase-5.5-legacy-cleanup` branch.

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

### Frontend — React 19 (`trinity-icp/src-react/` — ACTIVE, deployed)

TypeScript rewrite with hooks-first architecture. Zustand store, 4 custom hooks, 137 unit tests via Vitest.

```
trinity-icp/src-react/
├── App.tsx, main.tsx, config.ts
├── components/
│   ├── chat/           # CodeBlock, Message, MessageInput, MessageList,
│   │                   # StreamingMessage, MarkdownRenderer, MathBlock,
│   │                   # CopyAllButton, ContinueButton, DownloadCards
│   ├── layout/         # AppShell, EmptyState
│   ├── modals/         # AuthModal, ConfirmModal, InfoModal, KeyExportModal
│   ├── notifications/  # AutosaveIndicator, ToastProvider
│   └── sidebar/        # Sidebar
├── hooks/              # useAuth, useChat, useAutosave, useConnection
├── store/              # Zustand store (index.ts, types.ts)
├── types/              # api.ts, auth.ts, message.ts
├── utils/              # crypto, markdown, sse, indexedDB, lighthouse, logger
└── styles/             # CSS Modules + tokens.css + global.css
```

### Frontend — Vanilla JS (`trinity-icp/src/` — LEGACY, still buildable)

Imperative DOM manipulation app. Buildable via `npm run build:legacy` but no longer the default.

```
trinity-icp/src/
├── app.js                   # Orchestrator: imports modules, composes Actions, init()
├── config.js                # API endpoints, feature flags
├── core/                    # api.js, sse.js, environment.js, logger.js
├── features/                # generate.js, auth.js, chatManagement.js, memory.js
├── auth/                    # authManager.js, icp-auth.js, keyExportModal.js
├── state/                   # store.js (Zustand, CONTEXT_WINDOW_SIZE=20)
├── storage/                 # autosave.js, indexedDB.js, lighthouse.js
├── ui/                      # messages.js, sidebar.js, modals.js, etc.
└── utils/                   # crypto.js, math.js, validation.js
```

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
{principal}:{timestamp}:{endpoint}:{nonce}
```

Nonce is optional for backward compatibility. Without nonce: `{principal}:{timestamp}:{endpoint}`.

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
| Change LLM prompts | `backend/services/agent_prompts.py` |
| Add a tool | `backend/services/tools.py` + `code_executor.py` |
| Fix auth | `backend/icp_auth.py` |
| Change rate limits | `backend/middleware/rate_limit.py` |
| Fix metrics | `backend/middleware/observability.py` |
| Change state shape | `trinity-icp/src-react/store/index.ts` |
| Fix autosave | `trinity-icp/src-react/hooks/useAutosave.ts` |
| Fix streaming | `trinity-icp/src-react/hooks/useChat.ts` |
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

| Cold start delay | First request after Akash deploy takes 20-30s (LLM loading) |
