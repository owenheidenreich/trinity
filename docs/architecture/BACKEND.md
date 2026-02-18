# Trinity — Backend Architecture

> Last updated: February 2026 · Covers the Python Flask inference server

## Overview

The backend is a Python Flask application that runs inside a Docker container on the Akash Network alongside an Ollama instance for LLM inference. It handles authentication, chat management, AI generation (with agentic tool-calling), encrypted storage, and exposes a Prometheus-compatible metrics endpoint.

---

## File Structure

```
backend/
├── inference_server.py        # App factory, blueprint registration, startup lifecycle
├── config.py                  # All configuration constants and defaults
├── database.py                # SQLAlchemy ORM models + data access layer
├── encryption.py              # AES-256-GCM encryption with Argon2id/PBKDF2 KDF
├── icp_auth.py                # Ed25519 signature verification + auth decorators
├── storage.py                 # User data file operations (memory, metadata)
├── validation.py              # Input validation + SSRF protection
├── lighthouse.py              # IPFS/Lighthouse upload/download integration
├── mcp_stdio_server.py        # MCP stdio entry point (Claude Desktop integration)
│
├── routes/                    # 9 Flask Blueprints (54 endpoints)
│   ├── __init__.py            # Blueprint registration
│   ├── health.py              # Health checks, metrics, system stats
│   ├── generate.py            # LLM inference (standard + agentic)
│   ├── chat.py                # Chat CRUD, user memory, archives
│   ├── tools.py               # Web search, browsing, documents
│   ├── v4.py                  # Vector/RAG features
│   ├── admin.py               # Admin operations (cache, tokens, quotas, SLO, rollback)
│   ├── session.py             # Funding status, private sessions
│   ├── mcp.py                 # Model Context Protocol (JSON-RPC)
│   ├── passphrase.py          # Passphrase setup, unlock, change, lock, status
│   └── shared.py              # Shared utilities (error responses, caches)
│
├── middleware/                 # Request processing layers
│   ├── observability.py       # Prometheus metrics + context managers
│   ├── rate_limit.py          # Rate limiting + token quotas
│   └── icp_cache.py           # ICP idempotency cache (for subnet replicas)
│
├── services/                  # 34 business logic modules
│   ├── agent.py               # AgentPipeline orchestrator + OllamaClient
│   ├── agent_prompts.py       # System prompts + tool documentation
│   ├── react_loop.py          # ReAct + Reflexion engine
│   ├── tools.py               # Tool definitions, parsing, detection
│   ├── code_executor.py       # Tool execution dispatcher + sandboxing
│   ├── memory.py              # Semantic memory (working + semantic retrieval)
│   ├── memory_tools.py        # Memory tool handlers (save/recall/search)
│   ├── memory_ingestion.py    # Async ingestion worker for memory/profile/graph
│   ├── memory_eval.py         # Memory quality evaluation
│   ├── profile_extractor.py   # Background auto-extraction of user profile facts
│   ├── graph_memory.py        # Kuzu-backed graph memory
│   ├── graph_extractor.py     # Entity/relationship extraction for graph
│   ├── model_router.py        # Route queries to conversation vs coder model
│   ├── embeddings.py          # Text embeddings (FastEmbed, BAAI/bge-small-en-v1.5)
│   ├── vector_store.py        # Per-user SQLite vector database
│   ├── caching.py             # Embedding cache, semantic cache, token tracker
│   ├── ollama.py              # Ollama client utilities
│   ├── ollama_provider.py     # Ollama LLM provider implementation
│   ├── llm_provider.py        # Abstract LLM provider interface
│   ├── provider_factory.py    # Provider factory (Ollama, vLLM, etc.)
│   ├── prompts.py             # Core system prompts + prompt builders
│   ├── search.py              # Brave Search API integration
│   ├── fact_check.py          # Dual-search fact verification
│   ├── structured.py          # Constrained JSON generation (Outlines)
│   ├── akash.py               # Akash blockchain integration (AKT price, escrow)
│   ├── loading_messages.py    # Whimsical loading phrases by phase
│   ├── user_data_store.py     # IPFS persistence pipeline (retry, sync, manifest)
│   ├── session_manager.py     # Session passphrase management
│   ├── slo_metrics.py         # SLO tracking and burn-rate alerting
│   ├── repo_map.py            # Workspace file structure analyzer
│   ├── tracing.py             # Structured request tracing + quality reports
│   ├── mcp_server.py          # MCP server implementation
│   └── mcp_client.py          # MCP client manager (external tool servers)
│
└── tests/                     # Test suite
    ├── conftest.py             # Shared fixtures
    ├── fixtures/               # Auth fixtures
    ├── unit/                   # Unit tests (33 files)
    ├── integration/            # Integration tests (2 files)
    └── e2e/                    # End-to-end pipeline tests
```

---

## Application Startup

The Flask app is created by the `create_app()` factory in `inference_server.py`:

```
create_app()
│
├── Create Flask app instance
├── Configure flask-compress (gzip responses)
├── Configure flask-cors (ICP canister origins, dubya.ai, localhost)
│
├── Register 9 route blueprints:
│   health_bp, admin_bp, generate_bp, chat_bp,
│   tools_bp, v4_bp, session_bp, mcp_bp, passphrase_bp
│
├── Feature detection (try/except imports):
│   embeddings, vector_store, memory, tools,
│   code_executor, structured, mcp_server, mcp_client
│   → Each sets a boolean flag; routes degrade gracefully
│
├── Register request hooks:
│   ├── @before_request: log_request() — log method + path
│   ├── @before_request: validate_origin() — CSRF protection
│   └── @after_request: add_rate_limit_headers()
│
├── Register error handlers (400, 401, 403, 404, 413, 429, 500)
│
├── Start APScheduler background job:
│   └── cleanup_inactive_chats() — daily at 2 AM
│       Deletes chats inactive > 7 days (skips pinned/archived)
│
└── Return app instance
```

---

## API Endpoint Reference

### Health & Monitoring (4 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Full health check: Ollama status, CPU/RAM/disk, queue size, feature flags |
| GET | `/health/icp` | None | Deterministic health response for ICP HTTP Outcalls |
| GET | `/metrics` | None | Prometheus metrics (text format) |
| GET | `/stats` | None | JSON system statistics |

### LLM Inference (2 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/generate` | Rate-limited | Standard prompt → response generation. Supports document context, reasoning mode, user memory injection |
| POST | `/generate/agent` | Rate-limited | **Primary endpoint.** Agentic SSE streaming with tool detection, ReAct loop, and semantic memory indexing |

### Chat Management (9 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/chat/autosave` | `@require_auth` | Encrypt chat → upload to IPFS → update metadata |
| GET | `/chat/list` | `@require_auth` | List user's chats from IPFS metadata |
| GET | `/chat/<chat_id>` | `@require_auth` | Load and decrypt a specific chat |
| DELETE | `/chat/<chat_id>` | `@require_auth` | Mark chat as deleted (IPFS is immutable, so this updates metadata only) |
| POST | `/chat/<chat_id>/pin` | `@require_auth` | Toggle pin status |
| POST | `/chat/<chat_id>/archive` | `@require_auth` | Archive chat (max 20 archives) |
| GET | `/chat/recover-archives` | `@require_auth` | Recover from master bundle CID |
| GET | `/chat/archive/<cid>` | `@require_auth` | Download + decrypt specific archive by CID |
| GET | `/chat/archive/status/<cid>` | None | Check IPFS availability of an archive |

### User Memory (6 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/user/status` | `@require_auth` | Storage usage, rate limits, token quotas dashboard |
| GET | `/user/memory` | `@require_auth` | Get user memory (facts + preferences, embeddings stripped) |
| POST | `/user/memory` | `@require_auth` | Replace entire user memory |
| POST | `/user/memory/fact` | `@require_auth` | Add single fact (auto-deduplicates at >0.95 similarity) |
| PUT | `/user/memory/fact/<index>` | `@require_auth` | Edit fact text, category, or importance (re-embeds automatically) |
| DELETE | `/user/memory/fact/<index>` | `@require_auth` | Delete memory fact by index |

### External Tools (7 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tools/search` | Rate-limited | Web search via Brave Search API |
| POST | `/tools/browse` | Rate-limited | URL fetch with SSRF protection + HTML parsing |
| POST | `/tools/search-and-summarize` | Rate-limited | Combined search → fetch → format |
| POST | `/tools/documents/upload` | Rate-limited | Temporary document upload (1hr TTL, 5MB max) |
| POST | `/tools/documents/query` | `@require_auth` + rate-limited | Query uploaded document via LLM |
| POST | `/tools/transcript/clean` | `@require_auth` + rate-limited | Clean transcripts via LLM |
| GET | `/tools/status` | None | Tool availability check |

### V4 Vector/RAG Features (6 endpoints)

All gated behind `V4_FEATURES_AVAILABLE` flag — gracefully return 501 if dependencies missing.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v4/vector/index` | `@require_auth` | Bulk index chat messages into vector store |
| POST | `/v4/vector/document` | `@require_auth` | Embed document chunks for RAG |
| POST | `/v4/vector/search` | `@require_auth` | Semantic search across messages + documents |
| POST | `/v4/vector/sync` | `@require_auth` | Upload/download vector DB to/from IPFS |
| POST | `/v4/tools/execute` | `@require_auth` | Execute a specific tool by name |
| GET | `/v4/status` | None | Feature availability check |

### Admin (7 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/cache/stats` | `@require_admin` | Cache statistics |
| POST | `/admin/cache/clear` | `@require_admin` | Clear all caches |
| GET | `/admin/tokens/usage` | `@require_admin` | Token usage stats |
| GET | `/admin/quota/usage` | `@require_admin` | Per-user quota usage |
| GET | `/admin/storage/status` | `@require_admin` | IPFS sync status, pending syncs |
| POST | `/admin/storage/rollback/<principal_id>` | `@require_admin` | Rollback user manifest |
| GET | `/admin/slo/status` | `@require_admin` | SLO burn-rate status |

### Sessions & Funding (4 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/funding/status` | None | Deployment costs, AKT price, donation info |
| GET | `/session/status` | None | Current session type |
| POST | `/session/request` | None | Request private session |
| GET | `/session/check/<id>` | None | Check session status |

### MCP Protocol (2 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/mcp` | None | MCP server info + capabilities |
| POST | `/mcp` | `@require_auth` + rate-limited | JSON-RPC 2.0: `initialize`, `tools/list`, `tools/call`, `ping` |

### Passphrase (5 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/passphrase/setup` | `@require_auth` | Set up passphrase for user |
| POST | `/api/passphrase/unlock` | `@require_auth` | Unlock session with passphrase |
| POST | `/api/passphrase/change` | `@require_auth` | Change passphrase |
| POST | `/api/passphrase/lock` | `@require_auth` | Lock session |
| GET | `/api/passphrase/status` | `@require_auth` | Check passphrase status |

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

**Usage:** Context managers (`track_request()`, `track_inference()`, `track_storage()`, etc.) automatically manage timing and counters.

All metrics gracefully degrade to `NoOpMetric` if `prometheus_client` is not installed.

### 2. Rate Limiting (`middleware/rate_limit.py`)

| Limit Type | Threshold | Window |
|------------|-----------|--------|
| General API | 30 requests | 60 seconds |
| Storage operations | 30 requests | 60 seconds |
| Daily token quota | 100,000 tokens | 24 hours |
| Hourly token quota | 20,000 tokens | 1 hour |

**User identification** (resolution order): ICP principal → session ID → IP address.

**Response headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

Rate limit data persists to `/app/data/rate_limits.json` every 10 requests.

### 3. ICP Idempotency Cache (`middleware/icp_cache.py`)

When called from an ICP canister via HTTP Outcalls, a request may be executed by all 13 subnet replicas simultaneously. This cache ensures all replicas receive identical responses:

- TTL: 30 seconds
- Key: `(method, path, body_hash)`
- First replica executes the handler; the other 12 receive the cached result

---

## Database Layer

> **NOT INTEGRATED** — `database.py` contains 298 lines of SQLAlchemy ORM models but is not imported by any route or service. It exists as scaffolding for a future feature. Do not import from it.

SQLite database accessed via SQLAlchemy ORM (`database.py`).

### Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `RateLimit` | IP-based rate limiting | `ip`, `request_count`, `window_start` |
| `SessionRecord` | User sessions | `session_id`, `principal`, `data` (JSON), `last_activity` |
| `UsageStats` | Per-day token usage | `principal`, `date`, `tokens_used`, `requests` |
| `ChatMetadata` | Chat index | `id`, `principal`, `title`, `pinned`, `is_archived`, `cid`, `message_count` |

### Data Access (`TrinityDB`)

All methods are `@staticmethod` on the `TrinityDB` class:

- Rate limits: `get_rate_limit()`, `upsert_rate_limit()`, `cleanup_rate_limits()`
- Sessions: `create_session()`, `get_session()`, `update_session()`
- Usage: `record_usage()`, `get_usage_stats()`, `get_all_usage_for_date()`
- Chats: `upsert_chat_metadata()`, `get_chat_metadata()`, `get_chats_for_principal()`, `delete_chat_metadata()`

---

## Authentication System

Defined in `icp_auth.py`. Uses Ed25519 digital signatures with replay protection.

### Verification Flow

```
Incoming request with 5 headers
│
├── Extract: Principal, Signature, Timestamp, PublicKey, Nonce
│
├── Check timestamp within 60-second window
│   └── Reject if too old or too far in the future
│
├── Check nonce against TTLCache (10,000 entries, 65s TTL)
│   └── Reject if nonce already used (replay attack)
│
├── Reconstruct signed message:
│   "<principal>:<timestamp>:<endpoint>:<nonce>"
│
├── Verify Ed25519 signature against public key
│   └── Reject if signature invalid
│
├── Derive principal from public key
│   └── Reject if derived principal != ICP-Principal header
│
├── Record nonce in TTLCache
│
└── Set request.principal for downstream handlers
```

### Decorators

| Decorator | Behavior |
|-----------|----------|
| `@require_auth` | Runs full verification flow above. Rejects with 401 on failure. |
| `@require_admin` | `@require_auth` + checks `request.principal` is in `ADMIN_PRINCIPALS` env var. Rejects with 403. |

---

## Configuration (`config.py`)

All values have sensible defaults and can be overridden via environment variables.

### Server & Model

| Key | Default | Description |
|-----|---------|-------------|
| `MODEL_NAME` | `qwen3:32b` | Ollama model to use |
| `MODEL_BACKEND` | `ollama` | Inference backend |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API URL |
| `NUM_CTX` | `65536` | Context window size (tokens) |
| `DEFAULT_MAX_TOKENS` | `8000` | Max tokens per response |
| `OLLAMA_TIMEOUT` | `600` seconds | Request timeout |

### RAG & Embeddings

| Key | Default | Description |
|-----|---------|-------------|
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model |
| `EMBEDDING_DIM` | `384` | Embedding vector dimensions |
| `CHUNK_SIZE` | `500` characters | Document chunk size |
| `RAG_TOP_K` | `5` | Top results for retrieval |

### Memory

| Key | Default | Description |
|-----|---------|-------------|
| `WORKING_MEMORY_SIZE` | `5` | Recent messages kept in working memory |
| `SEMANTIC_MEMORY_SIZE` | `8` | Top semantic matches retrieved |
| `RECENCY_WEIGHT` | `0.3` | Weight given to recency vs similarity |

### ReAct Agent

| Key | Default | Description |
|-----|---------|-------------|
| `REACT_MAX_ITERATIONS` | `15` | Max Think→Act→Observe cycles |
| `REACT_TOKEN_BUDGET` | `48000` | Total token budget per request |
| `REFLEXION_MAX_RETRIES` | `3` | Self-correction attempts on tool errors |

### Security

| Key | Default | Description |
|-----|---------|-------------|
| Auth timestamp window | `60` seconds | Signature expiry |
| `PBKDF2_ITERATIONS` | `100,000` | PBKDF2 fallback key derivation rounds |
| `ADMIN_PRINCIPALS` | env var | Comma-separated admin principal IDs |

### Limits

| Key | Default | Description |
|-----|---------|-------------|
| `MAX_QUEUE_SIZE` | `10` | Concurrent request limit |
| `MAX_ARCHIVED_CHATS` | `20` | Max archived chats per user |
| `CHAT_INACTIVE_DAYS` | `7` | Days before inactive chat cleanup |
| `MAX_DOCUMENT_CONTEXT_CHARS` | `60,000` | Max doc context injected into prompt |
| `CODE_EXECUTION_TIMEOUT` | `5` seconds | Python sandbox timeout |

---

## Docker Container

**Base image:** `nvidia/cuda:12.2.0-runtime-ubuntu22.04`

```
Docker Build Layers:
│
├── CUDA runtime (cached, ~4GB)
├── System packages: python3.11, pip, curl, zstd
├── Ollama installation (curl | sh)
├── Python dependencies from requirements.txt (cached)
├── Non-root user 'trinity', data directories
├── Application code (~2MB, cache-busted)
│   └── Copies: inference_server.py, config.py, database.py,
│       encryption.py, icp_auth.py, storage.py, validation.py,
│       lighthouse.py, middleware/, services/, routes/
└── startup.sh entrypoint
```

**Key design choice:** Models are NOT baked into the image. They are pulled by `startup.sh` at first boot and cached on the Akash persistent volume. This keeps the image at ~4GB instead of ~20GB.

**Ports:** 8000 (Flask), 11434 (Ollama)

**Health check:** `curl http://localhost:8000/health` every 30 seconds with a 1200-second start period (for initial model download).

---

## External Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Flask | 3.0.3 | Web framework |
| flask-cors | Latest | CORS handling |
| flask-compress | Latest | Response compression |
| requests | Latest | HTTP client |
| SQLAlchemy | Latest | ORM (SQLite) |
| pycryptodome | 3.20.0 | AES-256-GCM encryption |
| cryptography | 42.0.5 | Ed25519 signature verification |
| argon2-cffi | Latest | Argon2id key derivation |
| cachetools | Latest | TTLCache for nonce protection |
| fastembed | 0.7.4 | Text embeddings |
| RestrictedPython | 8.1 | Sandboxed code execution |
| prometheus-client | 0.20.0 | Metrics export |
| APScheduler | Latest | Background job scheduling |
| beautifulsoup4 | Latest | HTML parsing |
| mcp | ≥1.0.0 | Model Context Protocol (optional) |
| psutil | Latest | System metrics |
| numpy | 1.26.4 | Numerical operations |

---

## Error Handling

All routes use standardized error responses via `shared.error_response()`:

```json
{
  "error": "Human-readable error message",
  "status": 400
}
```

Global error handlers catch:
- `400` — Bad request
- `401` — Authentication required
- `403` — Forbidden (admin-only)
- `404` — Not found
- `413` — Payload too large
- `429` — Rate limited
- `500` — Internal server error

---

## Background Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| `cleanup_inactive_chats()` | Daily at 2:00 AM | Deletes chat metadata for chats inactive longer than 7 days, skipping any that are pinned or archived |
