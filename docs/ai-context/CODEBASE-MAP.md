# Trinity Codebase Map

> **Purpose:** Single-file reference for any LLM to understand Trinity without searching the codebase.
> **Last Updated:** February 25, 2026
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
├── routes/                  # 7 blueprints, 31 endpoints
│   ├── __init__.py          # ALL_BLUEPRINTS list
│   ├── shared.py            # Shared helpers
│   ├── health.py            # /health, /metrics, /stats
│   ├── generate.py          # /generate, /generate/agent
│   ├── chat.py              # Chat CRUD (state_store-backed)
│   ├── memory.py            # /user/memory/* fact CRUD
│   ├── user.py              # /user/status, /user/stats, /user/export
│   ├── tools.py             # /tools/* search, browse, documents
│   └── passphrase.py        # /api/passphrase/* setup, unlock, change, lock, status
│
├── services/                # ~25 modules + state_store package
│   │
│   │   # ── Pipeline ──
│   ├── context_loader.py    # Single load_context() → RequestContext dataclass
│   ├── query_classifier.py  # is_personal_disclosure(), requests_personal_memory(), classify_temperature()
│   ├── prompt_assembler.py  # Token-budgeted prompt builder, auto-generated tool sections
│   ├── pipeline.py          # StreamingPipeline: ReAct loop (tools) / direct chat + tool-call rescue
│   ├── think_filter.py      # Streaming <think> block filter + code-fence helpers
│   ├── tiny_classifier.py   # ByteTransformer (pure numpy), classify_query(), detect_tools()
│   │
│   │   # ── Agent & Tools ──
│   ├── agent.py             # AgentPipeline (thin wrapper around StreamingPipeline)
│   ├── agent_prompts.py     # System prompts, ReAct prompts
│   ├── react_loop.py        # ReAct agentic loop (dual-mode: native + XML tools)
│   ├── code_executor.py     # Tool dispatcher (14 tools)
│   ├── tools.py             # Tool definitions, detection, parsing
│   │
│   │   # ── Memory & Knowledge ──
│   ├── knowledge_store.py   # Unified retrieval: facts + messages + relationships (ANN/brute-force)
│   ├── memory_tools.py      # MemGPT save/recall/search/update/forget with embeddings
│   ├── ingestion_worker.py  # Background daemon: index messages, extract facts, update summaries
│   ├── profile_extractor.py # LLM extraction for profile facts
│   ├── memory.py            # Semantic memory retrieval (legacy shim)
│   │
│   │   # ── Storage ──
│   ├── state_store/         # Canonical encrypted SQLite source-of-truth per principal
│   │   ├── _base.py         # Schema, encryption, connection
│   │   ├── _chats.py        # Chat CRUD
│   │   ├── _messages.py     # Message storage
│   │   ├── _facts.py        # Memory facts
│   │   ├── _summaries.py    # Conversation summaries
│   │   ├── _embeddings.py   # Vector embeddings
│   │   ├── _ingestion.py    # Ingestion job queue
│   │   └── _sync.py         # IPFS sync checkpoints
│   ├── db.py                # Database connection factory (sqlcipher + sqlite-vec)
│   ├── state_checkpoint.py  # Periodic IPFS checkpoint/restore for state.db
│   │
│   │   # ── LLM Providers ──
│   ├── llama_server_provider.py  # llama-server (llama.cpp) — OpenAI-compatible API
│   ├── llm_provider.py      # Abstract LLM provider interface
│   ├── provider_factory.py  # Provider factory (llama-server)
│   │
│   │   # ── Search & RAG ──
│   ├── search.py            # Brave web search
│   ├── fact_check.py        # Dual-search fact verification
│   ├── embeddings.py        # FastEmbed (384-dim)
│   ├── caching.py           # Embedding + semantic + token caches
│   │
│   │   # ── Infrastructure ──
│   ├── session_manager.py   # Session passphrase management
│   └── repo_map.py          # Repository structure visualization
│
├── middleware/
│   ├── __init__.py          # Middleware exports
│   ├── observability.py     # Prometheus metrics (single source of truth)
│   ├── rate_limit.py        # Per-principal rate limiting
│   └── icp_cache.py         # ICP deterministic caching
│
├── models/                  # Trained classifier weights
│   ├── query_classifier.npz # ByteTransformer query classifier (~370KB, 7 classes)
│   └── tool_detector.npz    # ByteTransformer tool detector (~370KB, 15 classes)
│
└── tests/                   # 934+ tests
    ├── conftest.py          # Root fixtures
    ├── fixtures/
    │   └── auth_fixtures.py # Ed25519 test keypairs
    ├── unit/                # Unit tests (~25 files)
    └── integration/         # Integration tests (2 files)
```

### Frontend — React 19 (`trinity-icp/src-react/` — ACTIVE, deployed)

TypeScript rewrite with hooks-first architecture. Zustand store, 4 custom hooks.

```
trinity-icp/src-react/
├── App.tsx, main.tsx, config.ts
├── components/
│   ├── chat/           # CodeBlock, Message, MessageInput, MessageList,
│   │                   # StreamingMessage, MarkdownRenderer, MathBlock,
│   │                   # CopyAllButton, DownloadCards, TypingIndicator
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

### Deploy (`deploy/`)

```
deploy/
├── docker/
│   ├── Dockerfile           # NVIDIA CUDA base, llama-server (llama.cpp), Flask
│   ├── startup.sh           # Container entrypoint (model download via HuggingFace + dual llama-server start)
├── akash/
│   ├── deploy-production.yaml       # Qwen3 32B (production)
│   ├── deploy-test.yaml            # Qwen3 8B (smoke-testing)
│   └── deploy-tier3.yaml           # Qwen3-Coder-Next 80B MoE (high-perf)
└── cloudflare-worker/
    └── worker.js            # SSL termination proxy
```

---

## API Endpoints (7 Blueprints, 31 Endpoints)

### No Auth Required

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Server + llama-server status |
| GET | `/health/icp` | ICP-specific health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/stats` | Server statistics |
| POST | `/generate` | Standard inference |

### Auth Required (Ed25519 Signature)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate/agent` | Canonical agent inference (server-side persistence + SSE IDs) |
| POST | `/chat/start` | Create chat, return canonical `chat_id` |
| GET | `/chat/list` | List user's chats |
| GET | `/chat/<chat_id>?before_message_id=&limit=` | Load paginated chat messages |
| PATCH | `/chat/<chat_id>` | Update title/pin/archive |
| DELETE | `/chat/<chat_id>` | Delete chat |
| POST | `/chat/<chat_id>/pin` | Pin/unpin chat |
| POST | `/chat/<chat_id>/archive` | Archive to IPFS |
| GET | `/chat/recover-archives` | Recover archived chats |
| GET | `/chat/archive/status/<cid>` | Check archive status |
| GET | `/user/status` | User account status |
| GET | `/user/memory` | Get user memory |
| POST | `/user/memory/fact` | Add memory fact |
| PATCH | `/user/memory/fact/<int:fact_id>` | Edit memory fact |
| DELETE | `/user/memory/fact/<int:fact_id>` | Soft-delete memory fact |
| GET | `/user/export` | Download all user data as ZIP |
| GET | `/user/stats` | User profile/chat/storage statistics |
| POST | `/tools/search` | Web search |
| POST | `/tools/browse` | Browse URL |
| POST | `/tools/search-and-summarize` | Search + summarize |
| POST | `/tools/documents/upload` | Upload document |
| POST | `/tools/documents/query` | Query documents (RAG) |

### Passphrase (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/passphrase/setup` | Set up passphrase |
| POST | `/api/passphrase/unlock` | Unlock with passphrase |
| POST | `/api/passphrase/change` | Change passphrase |
| POST | `/api/passphrase/lock` | Lock session |
| GET | `/api/passphrase/status` | Check passphrase status |

---

## Key Constants (`backend/config.py`)

### Model & Inference

| Constant | Default |
|----------|---------|
| `MODEL_NAME` | `qwen3:32b` |
| `MODEL_BACKEND` | `llama-server` |
| `LLAMA_SERVER_CHAT_PORT` | `8081` |
| `LLAMA_SERVER_INGEST_PORT` | `8082` |
| `NUM_CTX` | `40960` |
| `DEFAULT_MAX_TOKENS` | `16384` |
| `DEFAULT_TEMPERATURE` | `0.7` |
| `TEMPERATURE_CODE` | `0.1` |
| `TEMPERATURE_FACTUAL` | `0.3` |
| `TEMPERATURE_CONVERSATIONAL` | `0.7` |

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
| `CHATS_DIR` | `/data/chats` |
| `MAX_PROMPT_LENGTH` | `100000` |
| `MAX_ARCHIVED_CHATS` | `20` |
| `CODE_EXECUTION_ENABLED` | `false` |
| `LLM_TIMEOUT` | `600` |
| `LLM_TIMEOUT_TOOLS` | `300` |

### RAG & Memory

| Constant | Default |
|----------|---------|
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_DIM` | `384` |
| `WORKING_MEMORY_SIZE` | `5` |
| `SEMANTIC_MEMORY_SIZE` | `8` |
| `PROFILE_TOKEN_BUDGET` | `3500` |
| `PROFILE_MAX_FACTS` | `25` |
| `DEDUP_MERGE_THRESHOLD` | `0.85` |
| `DEDUP_SKIP_THRESHOLD` | `0.95` |

---

## Quick Lookup

| "I want to..." | File(s) |
|----------------|---------|
| Change an API endpoint | `backend/routes/<blueprint>.py` |
| Change LLM prompts | `backend/services/agent_prompts.py`, `backend/services/prompt_assembler.py` |
| Change context loading logic | `backend/services/context_loader.py` |
| Change the streaming pipeline | `backend/services/pipeline.py` |
| Change query classification | `backend/services/tiny_classifier.py`, `backend/models/*.npz` |
| Change tool detection | `backend/services/tiny_classifier.py` (model), `backend/services/tools.py` (definitions + regex gate) |
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
| Canonical message persistence | `backend/routes/generate.py`, `backend/services/state_store/` |
| Fix streaming | `trinity-icp/src-react/hooks/useChat.ts` |
| Retrain classifiers | `scripts/generate_training_data.py` → `scripts/train_classifiers.py` |
| Modify Docker | `deploy/docker/Dockerfile`, `deploy/docker/startup.sh` |
| Change Akash deploy | `deploy/akash/deploy-*.yaml` |

---

## Known Issues

| Issue | Details |
|-------|---------|
| `database.py` not integrated | 298-line ORM exists but unused |
| Cold start delay | First request after Akash deploy takes 20-30s (LLM loading) |
| `test_embed_text_uses_cache` | Known flaky test (passes in isolation, fails in full suite) |
