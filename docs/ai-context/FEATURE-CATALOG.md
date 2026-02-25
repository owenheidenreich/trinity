# Trinity Feature Catalog

> Complete inventory of production features.
> **Last Updated:** February 20, 2026

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

### Composable Pipeline (Refactored Feb 19, 2026)
- **Where**: `backend/services/pipeline.py`, `backend/services/context_loader.py`, `backend/services/query_classifier.py`, `backend/services/prompt_assembler.py`, `backend/services/think_filter.py`
- **How**: `context_loader.load_context()` (classify via ByteTransformer + load once) → `prompt_assembler.assemble()` (token-budgeted) → `StreamingPipeline.process_streaming()` (fast-path / ReAct / direct). Extracted from 1086-line `agent.py`. Classification uses trained neural classifiers, not regex.
- **Compat wrapper**: `backend/services/agent.py` (`AgentPipeline`) delegates to `StreamingPipeline`
- **Endpoint**: `POST /generate/agent`
- **Status**: Production

### ReAct Agentic Loop
- **Where**: `backend/services/react_loop.py`
- **How**: Iterative think→act→observe with dual-mode tool calling (native JSON + XML fallback). `think_filter.py` strips `<think>` blocks from llama-server stream. Defensive `<tool_call>` XML stripping in `_get_response_content()`.
- **Safeguards**: 48K token budget, 15 max iterations, Reflexion for code errors
- **Status**: Production

### 15 Tools
- **Where**: `backend/services/tools.py`, `backend/services/code_executor.py`
- **Tools**: calculator, code_display, web_search, fact_check, document_search, save_memory, recall_memory, search_memory, update_memory, forget_memory, read_file, write_file, list_directory, search_codebase, run_command
- **Parsing**: 4-tier `parse_tool_calls()` fallback: strict XML → lenient XML → nameless `<tool_call>` inference via `_TAG_TO_TOOL` mapping → bare tool name
- **Status**: Production (code execution disabled by default)

### Unified Knowledge Store (Refactored Feb 19, 2026)
- **Where**: `backend/services/knowledge_store.py` (new), `backend/services/embeddings.py`
- **How**: Unified retrieval across facts + messages + relationships. ANN via sqlite-vec (if available), brute-force fallback. Scoring: similarity × 0.6 + importance × 0.25 + recency × 0.15. KNN-based dedup (O(log n)).
- **Legacy shim**: `backend/services/memory.py` (being superseded)
- **Status**: Production

### Memory Tools (MemGPT)
- **Where**: `backend/services/memory_tools.py`
- **How**: save_memory (merge dedup >0.85, skip >0.95, heuristic contradiction detection), recall_memory, search_memory, update_memory, forget_memory (soft-delete)
- **Temporal metadata**: Facts have `valid_at`/`invalid_at` fields. Contradicted facts get `invalid_at` set and are excluded from retrieval.
- **Status**: Production

### User Profile System (v3 Canonical)
- **Where**: `backend/services/state_store.py`, `backend/services/profile_extractor.py`, `backend/services/ingestion_worker.py`, `backend/services/knowledge_store.py`
- **How**: Canonical encrypted SQLite + stable `fact_id` records. `ingestion_worker.py` (event-driven daemon) handles extraction, indexing, and summarization. `knowledge_store.py` handles retrieval and dedup. `prompt_assembler.py` handles token-budget injection.
- **Extraction categories**: identity, work, interests, preferences, relationships, general
- **Budgets**: PROFILE_TOKEN_BUDGET=3500, PROFILE_MAX_FACTS=25, KNOWLEDGE_TOP_K=20
- **Endpoints**: `GET /user/memory`, `POST /user/memory/fact`, `PATCH /user/memory/fact/{fact_id}`, `DELETE /user/memory/fact/{fact_id}`
- **Status**: Production

### Database Connection Factory (Feb 19, 2026)
- **Where**: `backend/services/db.py`
- **How**: sqlcipher whole-DB encryption (when available) + sqlite-vec ANN extension. Graceful fallback to plain sqlite3.
- **Status**: Production

### MCP (Model Context Protocol)
- **Where**: `backend/services/mcp_server.py`, `backend/services/mcp_client.py`, `backend/routes/mcp.py`
- **How**: Server exposes all 15 tools via JSON-RPC 2.0 (HTTP + stdio). Client connects to external MCP servers.
- **Status**: Production

### Memory Panel (Frontend)
- **Where**: `trinity-icp/src-react/components/sidebar/MemoryPanel.tsx`, `trinity-icp/src-react/styles/components/MemoryPanel.module.css`
- **How**: Collapsible sidebar section showing all stored user facts. Click-to-edit inline form with textarea, category dropdown, and importance dots. Delete and download (JSON blob) buttons. Refreshes via 3s delayed poll after each assistant response.
- **Store actions**: `updateMemoryFact(factId, updates)`, `deleteMemoryFact(factId)`
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
- **Count**: 1028+ tests
- **Run**: `cd backend && python -m pytest tests/ -x -q`
- **Rationale**: `docs/architecture/RATIONALE-TEST-COVERAGE.md`
- **Status**: All passing

---

## MicroGPT Overhaul (Feb 20, 2026)

Three-phase overhaul replacing hardcoded intelligence with trained models and direct LLM control.

### Temperature Routing (Phase 1)
- **Where**: `backend/services/query_classifier.py` (`classify_temperature()`), `backend/config.py`
- **How**: Maps query type to sampling temperature automatically. Code → 0.1, factual/tool/memory → 0.3, conversational → 0.7. Temperature threaded through `RequestContext` → `pipeline.process_streaming()` → `chat_stream()`.
- **Tests**: `backend/tests/unit/test_temperature_routing.py` (16 tests)
- **Status**: Production

### Tiny Classifiers (Phase 2)
- **Where**: `backend/services/tiny_classifier.py`, `backend/models/query_classifier.npz`, `backend/models/tool_detector.npz`
- **How**: Two trained ByteTransformer models (~100K params each, pure numpy inference). Query classifier: 7 classes (smalltalk, disclosure, code, lightweight, memory_recall, preference, general). Tool detector: 16 classes (15 tools + no_tool). Input is raw UTF-8 bytes, zero-padded to 256. Classifier-first with regex fallback: confidence < 0.75 falls to regex heuristics in `query_classifier.py` and `tools.py`, then defaults to FULL context / no tools.
- **Regex fallback**: Permanent safety net — 22 canonical smalltalk phrases, 6 disclosure patterns, 4 code patterns, 7 memory patterns in `query_classifier.py`; calculator/web/code/memory/filesystem patterns in `tools.py`. See [MICROGPT.md](MICROGPT.md) for full details.
- **Training**: `scripts/generate_training_data.py` (seed phrases + augmentation), `scripts/train_classifiers.py` (PyTorch, dev-only). Models are static — no continuous training.
- **Tests**: `backend/tests/unit/test_tiny_classifier.py` (32 tests), `backend/tests/unit/test_regex_fallback.py` (38 tests)
- **Status**: Production

### llama-server Migration (Phase 3)
- **Where**: `backend/services/llama_server_provider.py`, `backend/services/provider_factory.py`, `deploy/docker/Dockerfile`, `deploy/docker/startup.sh`
- **How**: Replaced Ollama with llama-server (llama.cpp HTTP server directly). OpenAI-compatible API (`/v1/chat/completions`, `/v1/completions`). SSE streaming. Dual instances: chat (port 8081, 32B model, 65K ctx) + ingest (port 8082, 8B model, 8K ctx). GGUF models downloaded from HuggingFace at startup.
- **Deleted**: `ollama_provider.py`, `ollama.py`
- **Unlocked**: KV cache persistence (`--prompt-cache`), native LoRA loading (`--lora`), inference isolation
- **Status**: Production

---

## Deleted Systems (Feb 2026 Overhaul)

Removed during the Intelligence Overhaul — do **not** re-implement:
- **LangGraph multi-agent** (`services/graph/` — 7 files, deleted)
- **Complexity router** (deleted)
- **Self-consistency voting** (deleted)
- **A/B experiment framework** (deleted)
- **Parallel pipeline** (deleted)
