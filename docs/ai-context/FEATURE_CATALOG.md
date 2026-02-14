# Trinity Feature Catalog

> Complete inventory of production features.
> **Last Updated:** February 13, 2026

---

## Core Infrastructure

### Ed25519 Self-Custody Authentication
- **Where**: `backend/icp_auth.py`
- **How**: `@require_auth` decorator verifies Ed25519 signature + timestamp (60s window)
- **Status**: Production

### AES-256-GCM Encryption
- **Where**: `backend/encryption.py`
- **How**: PBKDF2 key derivation (100k iterations), random salt + nonce per encryption
- **Status**: Production

### Input Validation & SSRF Protection
- **Where**: `backend/validation.py`
- **Status**: Production

### Rate Limiting
- **Where**: `backend/middleware/rate_limit.py`
- **How**: 30 req/min for generate, 10 req/min for storage, per-principal
- **Status**: Production

### ICP Idempotency Cache
- **Where**: `backend/middleware/icp_cache.py`
- **Status**: Production

### File Storage + IPFS Backup
- **Where**: `backend/storage.py`, `backend/lighthouse.py`
- **Status**: Production

---

## Observability

### Prometheus Metrics
- **Where**: `backend/middleware/observability.py`
- **Endpoint**: `GET /metrics`
- **Key metrics**: Request rate/errors/duration, inference time, tokens, auth attempts, cache hits, cost estimation
- **Status**: Production (single source of truth after Phase 5.5A migration)

---

## Intelligence Layer

### Single-Pass Agent Pipeline
- **Where**: `backend/services/agent.py`, `backend/services/agent_prompts.py`
- **How**: Detect tools → ReAct loop (if tools needed) or direct generation
- **Endpoint**: `POST /generate/agent`
- **Status**: Production

### ReAct Agentic Loop
- **Where**: `backend/services/react_loop.py`
- **How**: Iterative think→act→observe with dual-mode tool calling (native JSON + XML fallback)
- **Safeguards**: 24K token budget, 15 max iterations, Reflexion for code errors
- **Status**: Production

### 13 Tools
- **Where**: `backend/services/tools.py`, `backend/services/code_executor.py`
- **Tools**: calculator, code_display, web_search, fact_check, document_search, save_memory, recall_memory, search_memory, read_file, write_file, list_directory, search_codebase, run_command
- **Status**: Production (code execution disabled by default)

### Semantic Memory (V4)
- **Where**: `backend/services/memory.py`, `backend/services/vector_store.py`, `backend/services/embeddings.py`
- **How**: FastEmbed 384-dim embeddings, per-user SQLite vector DB, cosine similarity
- **Status**: Production

### Memory Tools (MemGPT)
- **Where**: `backend/services/memory_tools.py`
- **How**: save_memory, recall_memory, search_memory with deduplication (cosine > 0.95)
- **Status**: Production

### MCP (Model Context Protocol)
- **Where**: `backend/services/mcp_server.py`, `backend/services/mcp_client.py`, `backend/routes/mcp.py`
- **How**: Server exposes all 13 tools via JSON-RPC 2.0 (HTTP + stdio). Client connects to external MCP servers.
- **Status**: Production

---

## Cost Optimization

### Embedding Cache
- **Where**: `backend/services/caching.py` (`EmbeddingCache`)
- **How**: LRU(1000 entries), ~60-80% hit rate
- **Status**: Production

### Semantic Response Cache
- **Where**: `backend/services/caching.py` (`SemanticResponseCache`)
- **How**: LRU(500 entries), cosine similarity > 0.95 threshold
- **Status**: Production

### Token Tracking & Quotas
- **Where**: `backend/services/caching.py` (`TokenTracker`)
- **How**: Per-user token counting with hourly quotas
- **Admin endpoints**: `/admin/cache/stats`, `/admin/cache/clear`, `/admin/tokens/usage`, `/admin/quota/usage`
- **ADR**: `docs/architecture/decisions/005-in-memory-caching.md`
- **Status**: Production

---

## Testing

### Automated Test Suite
- **Where**: `backend/tests/`
- **Count**: 615 tests, 91.30% coverage
- **Run**: `cd backend && python -m pytest tests/ -x -q`
- **ADR**: `docs/architecture/decisions/002-tiered-test-coverage.md`
- **Status**: All passing

---

## Architecture Decisions

| ADR | Status | Description |
|-----|--------|-------------|
| 002-tiered-test-coverage | Active | Coverage targets by risk level |
| 003-prometheus-over-saas | Active | Self-hosted Prometheus ($500+/mo savings) |
| 005-in-memory-caching | Active | LRU cache with future Redis path |
| 001-complexity-routing | **Archived** | Superseded by single-pass pipeline |
| 004-hash-based-experiments | **Archived** | Experiments framework deleted |

---

## Deleted Systems (Feb 2026 Overhaul)

The following were removed during the Intelligence Overhaul:
- **LangGraph multi-agent** (`services/graph/` — 7 files)
- **Complexity router** (`services/complexity.py`)
- **Self-consistency voting** (`services/voting.py`)
- **A/B experiment framework** (`services/experiments.py`, `middleware/ab_test.py`)
- **Parallel pipeline** (`services/parallel.py`)

See `docs/ai-context/OVERHAUL-PROGRESS.md` for detailed deletion history.
