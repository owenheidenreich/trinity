# Trinity — Backend Architecture

> Last updated: February 25, 2026 · Covers the Python Flask inference server

## Overview

The backend is a Python Flask application that runs inside a Docker container on the Akash Network alongside two llama-server (llama.cpp) instances for LLM inference — one for chat (32B model, port 8081) and one for ingestion tasks (8B model, port 8082). It handles authentication, chat management, AI generation (with agentic tool-calling), encrypted storage, and exposes a Prometheus-compatible metrics endpoint.

---

## File Structure

```
backend/
├── inference_server.py        # App factory, blueprint registration, startup lifecycle
├── config.py                  # All configuration constants and defaults
├── database.py                # SQLAlchemy ORM models (NOT integrated — future feature)
├── encryption.py              # AES-256-GCM encryption with Argon2id/PBKDF2 KDF
├── icp_auth.py                # Ed25519 signature verification + auth decorators
├── storage.py                 # User data file operations (memory, metadata)
├── validation.py              # Input validation + SSRF protection
├── lighthouse.py              # IPFS/Lighthouse upload/download integration
│
├── routes/                    # 7 Flask Blueprints (31 endpoints)
│   ├── __init__.py            # Blueprint registration + ALL_BLUEPRINTS list
│   ├── health.py              # Health checks, metrics, system stats
│   ├── generate.py            # LLM inference (standard + agentic)
│   ├── chat.py                # Chat CRUD (state_store-backed)
│   ├── memory.py              # User memory facts CRUD
│   ├── user.py                # User status, stats, export
│   ├── tools.py               # Web search, browsing, documents
│   ├── passphrase.py          # Passphrase setup, unlock, change, lock, status
│   └── shared.py              # Shared utilities (error responses, caches)
│
├── middleware/                 # Request processing layers
│   ├── observability.py       # Prometheus metrics + context managers
│   ├── rate_limit.py          # Rate limiting + token quotas
│   └── icp_cache.py           # ICP idempotency cache (for subnet replicas)
│
├── services/                  # ~25 service modules + state_store package
│   │
│   │   # ── Pipeline (extracted from 1086-line agent.py) ──
│   ├── context_loader.py      # Single load_context() → RequestContext dataclass
│   ├── query_classifier.py    # Disclosure/memory detection, temperature routing
│   ├── prompt_assembler.py    # Token-budgeted prompt builder + auto-generated tool sections
│   ├── pipeline.py            # StreamingPipeline: ReAct / direct chat + tool-call rescue
│   ├── think_filter.py        # Streaming <think> block filter + code-fence helpers
│   ├── tiny_classifier.py     # ByteTransformer (pure numpy): classify_query(), detect_tools()
│   │
│   │   # ── Agent & Tools ──
│   ├── agent.py               # AgentPipeline (thin compat wrapper around StreamingPipeline)
│   ├── agent_prompts.py       # System prompts + tool documentation
│   ├── react_loop.py          # ReAct + Reflexion engine
│   ├── tools.py               # Tool definitions, parsing, detection (14 tools)
│   ├── code_executor.py       # Tool execution dispatcher + sandboxing
│   │
│   │   # ── Memory & Knowledge ──
│   ├── knowledge_store.py     # Unified retrieval: facts + messages + relationships (ANN/brute-force)
│   ├── memory_tools.py        # Memory tool handlers (save/recall/search/update/forget)
│   ├── ingestion_worker.py    # Background daemon: index, extract facts, update summaries
│   ├── profile_extractor.py   # LLM extraction → {facts}
│   ├── memory.py              # Semantic memory (legacy shim)
│   │
│   │   # ── Storage ──
│   ├── state_store/           # Canonical per-principal encrypted SQLite (state.db)
│   │   ├── _base.py           # Schema, encryption, connection
│   │   ├── _chats.py          # Chat CRUD
│   │   ├── _messages.py       # Message storage
│   │   ├── _facts.py          # Memory facts
│   │   ├── _summaries.py      # Conversation summaries
│   │   ├── _embeddings.py     # Vector embeddings
│   │   ├── _ingestion.py      # Ingestion job queue
│   │   └── _sync.py           # IPFS sync checkpoints
│   ├── db.py                  # Database connection factory (sqlcipher + sqlite-vec)
│   ├── state_checkpoint.py    # Periodic IPFS checkpoint/restore for state.db
│   │
│   │   # ── LLM Providers ──
│   ├── llama_server_provider.py  # llama-server (llama.cpp) provider — OpenAI-compatible API
│   ├── llm_provider.py        # Abstract LLM provider interface
│   ├── provider_factory.py    # Provider factory (llama-server)
│   │
│   │   # ── Search & RAG ──
│   ├── search.py              # Brave Search API integration
│   ├── fact_check.py          # Dual-search fact verification
│   ├── embeddings.py          # Text embeddings (FastEmbed, BAAI/bge-small-en-v1.5)
│   ├── caching.py             # Embedding cache, semantic cache, token tracker
│   │
│   │   # ── Infrastructure ──
│   ├── session_manager.py     # Session passphrase management
│   └── repo_map.py            # Workspace file structure analyzer
│
└── tests/                     # Test suite
    ├── conftest.py             # Shared fixtures
    ├── fixtures/               # Auth fixtures
    ├── unit/                   # Unit tests (~25 files, 934 tests)
    └── integration/            # Integration tests (2 files)
```

---

## Application Startup

The Flask app is created by the module-level code in `inference_server.py`:

```
App initialization
│
├── Create Flask app instance
├── Configure flask-compress (gzip responses)
├── Configure flask-cors (ICP canister origins, dubya.ai, localhost)
│
├── Register 7 route blueprints:
│   health_bp, generate_bp, chat_bp, memory_bp,
│   user_bp, tools_bp, passphrase_bp
│
├── Feature detection (try/except imports):
│   embeddings, memory, tools, code_executor
│   → Each sets a boolean flag; routes degrade gracefully
│
├── Register request hooks:
│   ├── @before_request: log_request() — log method + path
│   ├── @before_request: validate_origin() — CSRF protection
│   └── @after_request: add_rate_limit_headers()
│
├── Register error handlers (400, 401, 403, 404, 413, 429, 500)
│
├── Start APScheduler background jobs:
│   ├── cleanup_inactive_chats() — daily at 2 AM
│   └── checkpoint_all_state_stores() — every 15 minutes
│
└── atexit handler: checkpoint_all_state_stores() on shutdown
```

---

## API Endpoint Reference

See [backend/API.md](../backend/API.md) for the complete 31-endpoint reference.

**Summary:** 4 health/monitoring + 2 generate + 9 chat + 7 user/memory + 5 tools + 5 passphrase = 31 endpoints across 7 blueprints (health, generate, chat, memory, user, tools, passphrase).

---

## Middleware Stack

### 1. Observability (`middleware/observability.py`)

Prometheus metrics collection with context managers for timing.

**Metric Categories:**

| Category | Metrics | What They Track |
|----------|---------|----------------|
| HTTP (RED) | `REQUEST_COUNTER`, `REQUEST_LATENCY`, `REQUEST_IN_PROGRESS` | Request rate, duration, concurrency |
| Inference | `INFERENCE_COUNTER`, `INFERENCE_DURATION`, `TOKENS_GENERATED`, `TOKENS_PER_SECOND` | LLM performance |
| Errors | `ERROR_COUNTER` (by type) | Error classification |
| Storage | `STORAGE_OPERATIONS`, `STORAGE_LATENCY` | IPFS and file I/O |
| Auth | `AUTH_ATTEMPTS`, `AUTH_LATENCY` | Authentication performance |
| System (USE) | `SYSTEM_CPU`, `SYSTEM_MEMORY`, `UPTIME_SECONDS`, `MODEL_LOADED` | Resource utilization |
| Agent | `AGENT_PASS_DURATION`, `COMPLEXITY_CLASSIFICATIONS`, `TOOL_CALLS`, `TOOL_CALL_DURATION` | Agent pipeline |
| Cost | `EMBEDDING_CACHE_*`, `SEMANTIC_CACHE_*`, `TOKENS_PROMPT/COMPLETION`, `ESTIMATED_COST_USD` | Resource economics |

All metrics gracefully degrade to `NoOpMetric` if `prometheus_client` is not installed.

### 2. Rate Limiting (`middleware/rate_limit.py`)

| Limit Type | Threshold | Window |
|------------|-----------|--------|
| General API | 30 requests | 60 seconds |
| Storage operations | 30 requests | 60 seconds |
| Daily token quota | 100,000 tokens | 24 hours |
| Hourly token quota | 20,000 tokens | 1 hour |

**User identification** (resolution order): ICP principal → session ID → IP address.

### 3. ICP Idempotency Cache (`middleware/icp_cache.py`)

When called from an ICP canister via HTTP Outcalls, a request may be executed by all 13 subnet replicas simultaneously. This cache ensures all replicas receive identical responses:

- TTL: 30 seconds
- Key: `(method, path, body_hash)`
- First replica executes the handler; the other 12 receive the cached result

---

## Authentication System

Defined in `icp_auth.py`. Uses Ed25519 digital signatures with replay protection.

### Decorators

| Decorator | Behavior |
|-----------|----------|
| `@require_auth` | Verifies Ed25519 signature, timestamp window, nonce. Rejects with 401 on failure. |
| `@require_auth_or_anonymous` | Like `@require_auth` but allows unauthenticated requests (sets `request.principal` to guest ID). |

---

## Configuration (`config.py`)

All values have sensible defaults and can be overridden via environment variables.

### Server & Model

| Key | Default | Description |
|-----|---------|-------------|
| `MODEL_NAME` | `qwen3:32b` | Model name (maps to GGUF filename) |
| `MODEL_BACKEND` | `llama-server` | Inference backend |
| `LLAMA_SERVER_CHAT_PORT` | `8081` | Chat llama-server port |
| `LLAMA_SERVER_INGEST_PORT` | `8082` | Ingest llama-server port |
| `NUM_CTX` | `40960` | Context window size (tokens) |
| `DEFAULT_MAX_TOKENS` | `16384` | Max tokens per response |
| `DEFAULT_TEMPERATURE` | `0.7` | Default sampling temperature |
| `TEMPERATURE_CODE` | `0.1` | Temperature for code queries |
| `TEMPERATURE_FACTUAL` | `0.3` | Temperature for factual/tool queries |
| `TEMPERATURE_CONVERSATIONAL` | `0.7` | Temperature for conversational queries |

### ReAct Agent

| Key | Default | Description |
|-----|---------|-------------|
| `REACT_MAX_ITERATIONS` | `5` | Max Think→Act→Observe cycles |
| `REACT_TOKEN_BUDGET` | `48000` | Total token budget per request |
| `REFLEXION_MAX_RETRIES` | `3` | Self-correction attempts on tool errors |

### Limits

| Key | Default | Description |
|-----|---------|-------------|
| `MAX_QUEUE_SIZE` | `10` | Concurrent request limit |
| `MAX_ARCHIVED_CHATS` | `20` | Max archived chats per user |
| `CHAT_INACTIVE_DAYS` | `7` | Days before inactive chat cleanup |
| `MAX_DOCUMENT_CONTEXT_CHARS` | `60,000` | Max doc context injected into prompt |
| `CODE_EXECUTION_TIMEOUT` | `5` seconds | Python sandbox timeout |
| `LLM_TIMEOUT` | `600` seconds | Full generation timeout |
| `LLM_TIMEOUT_TOOLS` | `300` seconds | Tool/summarize timeout |

---

## Docker Container

**Base image:** `nvidia/cuda:12.2.0-runtime-ubuntu22.04`

**Key design choice:** GGUF models are NOT baked into the image. They are downloaded from HuggingFace by `startup.sh` at first boot and cached on the Akash persistent volume.

**Ports:** 8000 (Flask), 8081 (llama-server chat), 8082 (llama-server ingest)

---

## Deleted Systems (Feb 25, 2026)

The following were removed as unused/dead code with no frontend UI:

- **Routes:** admin.py, session.py, diagnostic.py, mcp.py (23 endpoints removed)
- **Services:** structured.py, vector_store.py, user_data_store.py, graph_memory.py, graph_extractor.py, model_router.py, loading_messages.py, slo_metrics.py, mcp_server.py, mcp_client.py, akash.py, mcp_stdio_server.py
- **State store:** _graph.py (GraphStoreMixin)
- **Tools:** document_search (15 → 14 tools)
