# Trinity Feature Catalog

> Complete inventory of production features.
> **Last Updated:** February 17, 2026

---

## Core Infrastructure

### Ed25519 Self-Custody Authentication
- **Where**: `backend/icp_auth.py`
- **How**: `@require_auth` decorator verifies Ed25519 signature + timestamp (60s window)
- **Status**: Production

### AES-256-GCM Encryption
- **Where**: `backend/encryption.py`
- **How**: Argon2id key derivation (primary) / PBKDF2 100k iterations (fallback), random salt + nonce per encryption
- **Status**: Production

### Input Validation & SSRF Protection
- **Where**: `backend/validation.py`
- **Status**: Production

### Rate Limiting
- **Where**: `backend/middleware/rate_limit.py`
- **How**: 30 req/min for generate, 30 req/min for storage, per-principal
- **Status**: Production

### ICP Idempotency Cache
- **Where**: `backend/middleware/icp_cache.py`
- **Status**: Production

### File Storage + IPFS Persistence
- **Where**: `backend/storage.py`, `backend/lighthouse.py`, `backend/services/user_data_store.py`
- **How**: IPFS is source of truth, local disk is cache. Exponential-backoff retry (3 attempts: 1s/4s/16s), at-least-once delivery via `_pending_syncs`, per-user sync status tracking
- **Monitoring**: `GET /admin/storage/status` returns pending syncs, per-user sync state, manifest CIDs
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
- **How**: Iterative think→act→observe with dual-mode tool calling (native JSON + XML fallback). `think=False` on all 4 LLM call sites to suppress Qwen3 `<think>` blocks. Defensive `<tool_call>` XML stripping in `_get_response_content()`.
- **Safeguards**: 48K token budget, 15 max iterations, Reflexion for code errors
- **Status**: Production

### 15 Tools
- **Where**: `backend/services/tools.py`, `backend/services/code_executor.py`
- **Tools**: calculator, code_display, web_search, fact_check, document_search, save_memory, recall_memory, search_memory, update_memory, forget_memory, read_file, write_file, list_directory, search_codebase, run_command
- **Parsing**: 4-tier `parse_tool_calls()` fallback: strict XML → lenient XML → nameless `<tool_call>` inference via `_TAG_TO_TOOL` mapping → bare tool name
- **Status**: Production (code execution disabled by default)

### Semantic Memory (V4)
- **Where**: `backend/services/memory.py`, `backend/services/vector_store.py`, `backend/services/embeddings.py`
- **How**: FastEmbed 384-dim embeddings, per-user SQLite vector DB, cosine similarity
- **Status**: Production

### Memory Tools (MemGPT)
- **Where**: `backend/services/memory_tools.py`
- **How**: save_memory (merge dedup >0.85, skip >0.95, heuristic contradiction detection), recall_memory, search_memory, update_memory, forget_memory (soft-delete)
- **Temporal metadata**: Facts have `valid_at`/`invalid_at` fields. Contradicted facts get `invalid_at` set and are excluded from retrieval.
- **Status**: Production

### User Profile System (v2.0)
- **Where**: `backend/storage.py`, `backend/services/profile_extractor.py`, `backend/services/agent.py`
- **How**: Structured profile (identity/work/interests/preferences/relationships), token-budget injection (2500 tokens), auto-extraction from user AND assistant messages via 39 compiled regex patterns with conjunction-stopping capture groups, schema migration v1→v2
- **Extraction categories**: identity, location, work, education, interests, preferences, relationships, possession, vehicle, pet, age
- **Budgets**: WORKING_MEMORY_SIZE=5, SEMANTIC_MEMORY_SIZE=8, PROFILE_TOKEN_BUDGET=2500 (all env-configurable)
- **Endpoints**: `GET /user/export` (ZIP), `GET /user/stats`, `GET /user/memory`, `PUT /user/memory/fact/<index>`
- **Status**: Production

### MCP (Model Context Protocol)
- **Where**: `backend/services/mcp_server.py`, `backend/services/mcp_client.py`, `backend/routes/mcp.py`
- **How**: Server exposes all 15 tools via JSON-RPC 2.0 (HTTP + stdio). Client connects to external MCP servers.
- **Status**: Production

### Memory Panel (Frontend)
- **Where**: `trinity-icp/src-react/components/sidebar/MemoryPanel.tsx`, `trinity-icp/src-react/styles/components/MemoryPanel.module.css`
- **How**: Collapsible sidebar section showing all stored user facts. Click-to-edit inline form with textarea, category dropdown, and importance dots. Delete and download (JSON blob) buttons. Refreshes via 3s delayed poll after each assistant response.
- **Store actions**: `updateMemoryFact(index, updates)`, `deleteMemoryFact(index)`
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
- **Rationale**: `docs/architecture/RATIONALE-CACHING.md`
- **Status**: Production

---

## Testing

### Automated Test Suite
- **Where**: `backend/tests/` (35 files, 969 test functions)
- **Count**: 978 tests
- **Run**: `cd backend && python -m pytest tests/ -x -q`
- **Rationale**: `docs/architecture/RATIONALE-TEST-COVERAGE.md`
- **Status**: All passing

---

## Deleted Systems (Feb 2026 Overhaul)

Removed during the Intelligence Overhaul — do **not** re-implement:
- **LangGraph multi-agent** (`services/graph/` — 7 files, deleted)
- **Complexity router** (deleted)
- **Self-consistency voting** (deleted)
- **A/B experiment framework** (deleted)
- **Parallel pipeline** (deleted)
