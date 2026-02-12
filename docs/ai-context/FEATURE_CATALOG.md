# Trinity Feature Catalog

> Complete inventory of every feature across all phases.
> **Last Updated:** February 6, 2026

---

## Core Infrastructure (Phase 1)

### Ed25519 Self-Custody Authentication
- **What**: Zero-knowledge identity — users own their keys, not Trinity
- **Where**: `backend/icp_auth.py`
- **How**: `@require_auth` decorator verifies Ed25519 signature + timestamp (60s window)
- **Endpoints**: All `/chat/*` and `/user/*` endpoints require auth headers
- **Status**: Production

### AES-256-GCM Encryption
- **What**: Client-side encryption for chat storage — server never sees plaintext
- **Where**: `backend/encryption.py`
- **How**: PBKDF2 key derivation (100k iterations), random salt + nonce per encryption
- **Status**: Production

### Input Validation & SSRF Protection
- **What**: Request validation — chat_id format, prompt length limits, URL safety checks
- **Where**: `backend/validation.py`
- **How**: Regex validation, reserved IP blocking, redirect chain following
- **Tests**: 70 tests (test_validation.py)
- **Status**: Production

### Rate Limiting
- **What**: Per-IP request throttling to prevent abuse
- **Where**: `backend/middleware/rate_limit.py`
- **How**: 30 req/min for generate endpoints, 10 req/min for storage endpoints
- **Status**: Production

### ICP Idempotency Cache
- **What**: Prevents duplicate processing for ICP consensus replay
- **Where**: `backend/middleware/icp_cache.py`
- **How**: Request deduplication by hash, TTL-based expiry
- **Status**: Production

### File Storage
- **What**: Encrypted chat persistence on server filesystem
- **Where**: `backend/storage.py`
- **Endpoints**: `POST /chat/autosave`, `GET /chat/list`, `GET /chat/<id>`, `DELETE /chat/<id>`
- **Status**: Production

### IPFS/Filecoin Uploads
- **What**: Decentralized storage via Lighthouse SDK
- **Where**: `backend/lighthouse.py`
- **Status**: Production

---

## Observability (Phase 2)

### Prometheus Metrics
- **What**: RED-method production monitoring (Rate, Errors, Duration)
- **Where**: `backend/middleware/observability.py`
- **Endpoint**: `GET /metrics` (Prometheus scrape format)
- **Key metrics**:
  - `trinity_http_requests_total` — Request counter by endpoint/method/status
  - `trinity_http_request_duration_seconds` — Latency histogram
  - `trinity_active_requests` — In-flight request gauge
  - `trinity_inference_duration_seconds` — LLM inference time
  - `trinity_tokens_generated_total` — Token counter
  - `trinity_errors_total` — Error counter by type
  - `trinity_auth_attempts_total` — Auth success/failure
  - `trinity_experiment_assignments_total` — A/B test assignments
  - `trinity_embedding_cache_*` — Cache hit/miss metrics
  - `trinity_semantic_cache_*` — Semantic cache metrics
  - `trinity_estimated_cost_usd` — Running cost estimate
- **Also provides**: Legacy compatibility functions (`start_request`, `end_request`, `record_request`, `get_prometheus_summary`) for backward-compatible `/health` endpoint
- **Status**: Production (single source of truth after Phase 5.5A migration)

---

## Intelligence Layer (Phase 3 + V4)

### Complexity Classifier
- **What**: Scores query complexity 0-10, determines which pipeline handles it
- **Where**: `backend/services/complexity.py`
- **How**: Heuristic scoring — word count, question marks, technical terms, domain indicators, multi-part detection
- **Thresholds**: 0-3 = simple (1 pass), 4-6 = medium (3 passes), 7-10 = complex (5 passes or LangGraph)
- **Tests**: test_complexity.py
- **Status**: Production

### Legacy Agent Pipeline (80% of traffic)
- **What**: Multi-pass agentic reasoning — Understand, Plan, Execute, Critique, Refine
- **Where**: `backend/services/agent.py`, `backend/services/agent_prompts.py`
- **How**: 1/3/5 passes based on complexity score, XML-structured inter-pass communication
- **Endpoint**: `POST /generate/agent`
- **Status**: Production (handles simple + medium queries)

### LangGraph Multi-Agent System (20% of traffic)
- **What**: StateGraph-based multi-agent orchestration for complex queries
- **Where**: `backend/services/graph/` (7 files)
  - `state.py` — AgentState TypedDict
  - `llm.py` — LangChain Ollama wrapper
  - `agents.py` — Specialized agents (Supervisor, Research, Code, Synthesis)
  - `nodes.py` — Graph node implementations
  - `edges.py` — Conditional routing logic (should_continue)
  - `graph.py` — StateGraph assembly
- **How**: Supervisor routes to specialist agents, conditional edges control flow, max 5 iterations
- **Endpoint**: `POST /generate/langgraph`
- **Tests**: 53 tests (test_langgraph.py + test_langgraph_endpoint.py)
- **Status**: Production (handles complex queries via complexity routing)
- **ADR**: `docs/decisions/001-complexity-routing.md`

### Semantic Memory (V4)
- **What**: Per-user vector store for conversation history retrieval
- **Where**: `backend/services/memory.py`, `backend/services/vector_store.py`, `backend/services/embeddings.py`
- **How**: FastEmbed generates embeddings, stored in per-user SQLite DB, cosine similarity search
- **Endpoints**: `GET/POST /user/memory`, `POST /v4/vector/search`
- **Status**: Production

### Tool Use (V4)
- **What**: Calculator, code execution, web search via structured XML tool calls
- **Where**: `backend/services/tools.py`, `backend/services/code_executor.py`
- **How**: LLM outputs `<tool_call>` XML, parsed and executed in RestrictedPython sandbox (5s timeout)
- **Endpoint**: `GET /v4/status` (shows tool availability)
- **Status**: Production

### Self-Consistency Voting (V4)
- **What**: Multiple LLM samples at different temperatures, majority vote selects best answer
- **Where**: `backend/services/voting.py`
- **How**: 3 responses at temps 0.3/0.7/1.0, answer fingerprint grouping, majority wins
- **Status**: Experimental

### Structured Output (V4)
- **What**: JSON schema enforcement for reliable parsing
- **Where**: `backend/services/structured.py`
- **How**: Prompt engineering with schema injection + regex fallback extraction
- **Status**: Experimental

---

## Experimentation Framework (Phase 4A)

### A/B Testing
- **What**: Hash-based deterministic experiment assignment — no database needed
- **Where**: `backend/services/experiments.py`, `backend/middleware/ab_test.py`
- **How**: `SHA256(session_id + experiment_name) % 100 < percentage` — stateless, deterministic
- **Defined experiments**:
  - `agent_mode` — LangGraph vs legacy routing (enabled)
  - `parallel_execution` — Run both pipelines simultaneously (disabled)
  - `complexity_threshold` — Threshold tuning (enabled)
- **Admin endpoints**:
  - `GET /admin/experiments` — List all experiments
  - `POST /admin/experiments/<name>/enable` — Enable experiment
  - `POST /admin/experiments/<name>/disable` — Disable experiment
  - `GET /admin/experiments/assignment/<session_id>` — Get assignments
- **Tests**: 44 tests (test_experiments.py)
- **ADR**: `docs/decisions/004-hash-based-experiments.md`
- **Status**: Production

### Parallel Pipeline Execution
- **What**: Run legacy + LangGraph simultaneously for comparison
- **Where**: `backend/services/parallel.py`
- **How**: ThreadPoolExecutor, returns both results with timing
- **Status**: Production (gated by `parallel_execution` experiment flag)

---

## Cost Optimization (Phase 4B)

### Embedding Cache
- **What**: LRU cache for text embeddings — avoids recomputing embeddings for repeated text
- **Where**: `backend/services/caching.py` (`EmbeddingCache` class)
- **How**: LRU(1000 entries), hash-keyed, ~60-80% hit rate
- **Status**: Production

### Semantic Response Cache
- **What**: Cache full LLM responses for semantically similar queries
- **Where**: `backend/services/caching.py` (`SemanticResponseCache` class)
- **How**: LRU(500 entries), cosine similarity > 0.95 threshold, ~20-40% hit rate
- **Status**: Production

### Token Tracking & Quotas
- **What**: Per-user token counting with hourly quotas to control costs
- **Where**: `backend/services/caching.py` (`TokenTracker` class)
- **How**: 10k tokens/hr rolling window per principal
- **Admin endpoints**:
  - `GET /admin/cache/stats` — Cache hit/miss statistics
  - `POST /admin/cache/clear` — Clear all caches
  - `GET /admin/tokens/usage` — Token usage by user
  - `GET /admin/quota/usage` — Quota status per user
- **Tests**: 37 tests (test_caching.py)
- **ADR**: `docs/decisions/005-in-memory-caching.md`
- **Status**: Production

---

## Testing & Benchmarking (Phase 5 + 5.5)

### Automated Test Suite
- **What**: 607+ tests across 14 unit test files + integration + e2e
- **Where**: `backend/tests/` (unit/ + integration/ + e2e/ + fixtures/)
- **Run**: `cd backend && pytest tests/ --no-cov -q` (~7 seconds)
- **Coverage tiers**: Critical 90%+ (auth, encryption), High 80%+ (caching, LangGraph), Overall 91.30%
- **ADR**: `docs/decisions/002-tiered-test-coverage.md`
- **Status**: All passing

### Legacy vs LangGraph Benchmark Suite
- **What**: Performance comparison of both pipelines across complexity levels
- **Where**: `backend/eval/benchmark_legacy_vs_langgraph.py`
- **Run**: `python3 -m eval.benchmark_legacy_vs_langgraph --sample-size 10`
- **Output**: P50/P95/P99 latencies, success rates, token usage, routing recommendation
- **Guide**: `backend/eval/BENCHMARK_GUIDE.md`
- **Status**: Ready to run

---

## Documentation (Phase 5)

### Architecture Decision Records (5 ADRs)
- **Where**: `docs/decisions/`
- `001-complexity-routing.md` — 80/20 split rationale
- `002-tiered-test-coverage.md` — Coverage targets by risk level
- `003-prometheus-over-saas.md` — Self-hosted vs SaaS ($500-2000/mo savings)
- `004-hash-based-experiments.md` — Stateless A/B testing design
- `005-in-memory-caching.md` — LRU cache with future Redis path

### Onboarding Guides (3 docs)
- **Where**: `docs/onboarding/`
- `developer-setup.md` — 5-minute quick start
- `architecture-walkthrough.md` — System architecture with diagrams
- `common-tasks.md` — Adding tests, endpoints, metrics, debugging

---

## API Quick Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check + system metrics |
| `/generate` | POST | No | LLM text generation |
| `/generate/stream` | POST | No | Streaming generation (SSE) |
| `/generate/agent` | POST | No | Legacy agentic pipeline |
| `/generate/langgraph` | POST | No | LangGraph multi-agent |
| `/metrics` | GET | No | Prometheus metrics scrape |
| `/stats` | GET | No | System statistics |
| `/chat/autosave` | POST | Yes | Save encrypted chat |
| `/chat/list` | GET | Yes | List user's chats |
| `/chat/<id>` | GET | Yes | Load specific chat |
| `/chat/<id>` | DELETE | Yes | Delete specific chat |
| `/user/memory` | GET/POST | Yes | User semantic memory |
| `/search/web` | POST | No | Brave web search |
| `/admin/experiments` | GET | No | List A/B experiments |
| `/admin/cache/stats` | GET | No | Cache statistics |
| `/v4/status` | GET | No | V4 feature availability |
| `/v4/vector/search` | POST | Yes | Semantic similarity search |
