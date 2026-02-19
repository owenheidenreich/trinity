# Trinity Backend Services

> **Last Updated:** February 19, 2026
> **Location:** [backend/services/](../../backend/services/)

---

## Overview

The backend uses a **single-pass pipeline** with optional ReAct tool calling. The former 1086-line `agent.py` god module was refactored into 8 focused modules: context loading, query classification, prompt assembly, streaming pipeline, think-block filtering, knowledge store, ingestion worker, and database connection factory.

All deleted systems (LangGraph, voting, experiments, complexity router, parallel pipeline, A/B testing) were removed in the Feb 2026 overhaul.

```
backend/
├── inference_server.py      # App factory, blueprint registration
├── config.py                # Environment variables and constants
├── encryption.py            # AES-256-GCM encryption
├── storage.py               # Compatibility facade (memory payload helpers)
├── validation.py            # Input validation, SSRF protection
├── icp_auth.py              # Ed25519 authentication
├── lighthouse.py            # IPFS/Filecoin storage
├── middleware/
│   ├── rate_limit.py        # Per-principal rate limiting
│   ├── icp_cache.py         # Idempotency cache
│   └── observability.py     # Prometheus metrics (single source of truth)
└── services/                # 42 modules
    │
    │   # ── Pipeline (extracted from agent.py) ──
    ├── context_loader.py    # Single load_context() → RequestContext dataclass
    ├── query_classifier.py  # ContextLevel enum, smalltalk/disclosure/code detection
    ├── prompt_assembler.py  # Token-budgeted prompt builder + auto-generated tool sections
    ├── pipeline.py          # StreamingPipeline: fast-path / tools / direct chat
    ├── think_filter.py      # Streaming <think> block filter + code-fence helpers
    │
    │   # ── Agent & Tools ──
    ├── agent.py             # AgentPipeline (thin wrapper for backward compat)
    ├── agent_prompts.py     # System prompts, ReAct prompts
    ├── react_loop.py        # ReAct agentic loop (dual-mode: native + XML tools)
    ├── code_executor.py     # Tool dispatcher (15 tools)
    ├── tools.py             # Tool definitions & parsing
    │
    │   # ── Memory & Knowledge ──
    ├── knowledge_store.py   # Unified retrieval: facts + messages + relationships
    ├── memory_tools.py      # MemGPT save/recall/search/update/forget
    ├── ingestion_worker.py  # Background daemon: index, extract, summarize
    ├── profile_extractor.py # LLM extraction → {facts, triples}
    ├── graph_extractor.py   # Graph triple extraction compat layer
    ├── graph_memory.py      # Graph memory utilities
    ├── memory.py            # Semantic memory (legacy shim)
    ├── memory_ingestion.py  # Shim re-exports from ingestion_worker
    ├── memory_eval.py       # Memory quality evaluation
    │
    │   # ── Storage ──
    ├── state_store.py       # Canonical per-principal encrypted SQLite
    ├── db.py                # Connection factory (sqlcipher + sqlite-vec)
    ├── state_checkpoint.py  # Periodic IPFS checkpoint/restore
    ├── vector_store.py      # Per-user SQLite vector DB
    ├── user_data_store.py   # IPFS persistence pipeline
    │
    │   # ── LLM Providers ──
    ├── ollama.py            # Ollama HTTP client
    ├── ollama_provider.py   # Ollama provider implementation
    ├── llm_provider.py      # Abstract LLM provider interface
    ├── provider_factory.py  # Provider factory (Ollama, vLLM)
    ├── model_router.py      # Model routing logic
    │
    │   # ── Search & RAG ──
    ├── search.py            # Brave web search
    ├── fact_check.py        # Dual-search fact verification
    ├── embeddings.py        # FastEmbed (384-dim)
    ├── caching.py           # Embedding + semantic + token caches
    │
    │   # ── Infrastructure ──
    ├── prompts.py           # Core system prompts
    ├── structured.py        # Structured output parsing
    ├── loading_messages.py  # Phase update messages
    ├── akash.py             # Deployment info & costs
    ├── session_manager.py   # Session management
    ├── slo_metrics.py       # SLO tracking metrics
    ├── mcp_server.py        # MCP server (JSON-RPC 2.0)
    ├── mcp_client.py        # MCP client (external tools)
    ├── repo_map.py          # Repository structure visualization
    └── tracing.py           # Distributed tracing
```

---

## Request Pipeline (New Architecture)

The pipeline was refactored from a monolithic `agent.py` into composable modules. Every request follows one path:

```
POST /generate/agent
       │
  context_loader.load_context()      ← classify + load once
       │
  prompt_assembler.assemble()        ← token-budgeted prompt
       │
  StreamingPipeline.process_streaming()
       │
  ┌────┴──────────────────────────────────┐
  │  Fast-path (smalltalk) → instant SSE  │
  │  Tools needed → ReactLoop.execute()   │
  │  No tools → chat_stream() + filter    │
  └───────────────────────────────────────┘
```

### Context Loader (`services/context_loader.py`)

Single function replacing 5 divergent context-loading paths. Returns a `RequestContext` dataclass.

**Input:** store, knowledge_store, prompt, chat_id, principal_id
**Output:** `RequestContext` with level, messages, summary, knowledge_items, query_embedding, tools_needed

**Context Levels:**
| Level | What's Loaded | When |
|-------|--------------|------|
| `NONE` | Nothing | Trivial smalltalk |
| `MINIMAL` | Last 5 messages | Simple questions |
| `DISCLOSURE` | Last 5 messages | Personal self-disclosure |
| `FULL` | 25 messages + summary + 20 semantic results + graph context | Normal questions |

### Query Classifier (`services/query_classifier.py`)

Extracted from `agent.py`. All classification evaluated **once** per request:
- `is_trivial_smalltalk()` — regex-based greeting detection
- `is_personal_disclosure()` — first-person self-disclosure
- `is_code_generation_request()` — code intent detection
- `classify_context_level()` → `ContextLevel` enum

### Prompt Assembler (`services/prompt_assembler.py`)

Token-budgeted prompt construction replacing `build_chat_messages()` and `_format_user_memory()`.

**Token Budget Allocation (default 4000 tokens):**
- Conversation history: 55% (~2200 tokens)
- Knowledge items: remaining (~1800 tokens)
- Safety margin: 2000 tokens reserved

**Auto-generated tool section:** `get_tool_prompt_section()` generates from `TOOL_DEFINITIONS` (single source of truth, replaces hand-written TOOL_PROMPT_SECTION).

### Streaming Pipeline (`services/pipeline.py`)

Extracted from `agent.py`. Three paths:
1. **Fast-path** — trivial smalltalk → instant response, no LLM call
2. **Tool path** — ReAct loop via `react_loop.execute_streaming()`
3. **Direct path** — `chat_stream()` with think-block filtering

### Think Filter (`services/think_filter.py`)

Streaming filter for Qwen3 `<think>...</think>` blocks:
- `filter_think_blocks(token_stream, accumulator)` — generator that strips think blocks in real-time
- `contains_fenced_code(text)` / `looks_like_code(text)` — code detection
- `estimate_tokens(text)` — approximate token counting
- Safety: ~20k token think-block limit triggers flush

---

## Knowledge Store (`services/knowledge_store.py`)

Unified retrieval layer replacing scattered logic across `memory.py`, `agent.py`, and `memory_tools.py`.

**Architecture:**
- All knowledge items (facts, messages, relationships) in one vector index
- ANN search via `sqlite-vec` when available, brute-force fallback
- Dedup uses KNN query (O(log n)) instead of loading all facts (O(n))

**Unified Scoring:** `combined_score = similarity × 0.6 + importance × 0.25 + recency × 0.15`

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `search(query_embedding, top_k)` | ANN or brute-force retrieval |
| `save_fact(text, category, importance)` | Embed + dedup check + insert/merge |
| `index_message(chat_id, message_id, role, content)` | Embed and store for retrieval |
| `save_relationship(subject, predicate, object)` | Store as relationship-category fact |
| `soft_delete(fact_id)` | Mark `deleted_at` |

**Deduplication:** On save, query top-1 KNN neighbor:
- `> 0.95` similarity → skip (identical)
- `> 0.85` similarity → merge (update existing text)
- `< 0.85` → insert new fact

---

## Ingestion Worker (`services/ingestion_worker.py`)

Background daemon replacing `memory_ingestion.py`'s polling loop and `generate.py`'s fire-and-forget threads.

**Architecture:**
- Single daemon thread drains `ingestion_jobs` table from state.db
- `ThreadPoolExecutor` (2 workers) bounds concurrent LLM calls
- Event-driven wakeup (no polling delay on hot path)

**Job Lifecycle:**
```
enqueue_ingestion() → ingestion_jobs (queued)
       │
  daemon fetches due jobs
       │
  _process_job():
    1. _index_message() → embed + KnowledgeStore.index_message()
    2. _extract_and_save() → LLM extraction → facts + graph triples
    3. _maybe_update_summary() → rolling conversation summary
       │
  complete_job() or fail_job() (retry up to 5 attempts)
```

**Model Isolation:** Uses `OLLAMA_INGEST_HOST`/`OLLAMA_INGEST_MODEL` (qwen3:8b), separate from chat model (qwen3:32b).

---

## Database Connection Factory (`services/db.py`)

Replaces raw `sqlite3.connect()` calls in state_store.py.

**Features:**
- Whole-DB encryption via sqlcipher (when available)
- sqlite-vec extension loaded for ANN vector search
- Read/write connection separation (WAL mode)
- Graceful fallback to plain sqlite3 when extensions not installed

---

## Agent Pipeline (`services/agent.py`)

Now a **thin backward-compatibility wrapper** around `StreamingPipeline`. Legacy callers (`get_agent_pipeline()`, `AgentPipeline`) continue to work via transparent delegation.

---

## ReAct Loop (`services/react_loop.py`)

Iterative think→act→observe loop for tool-using queries.

**Dual-mode tool calling:**
- **Native**: Ollama `/api/chat` with `tools` parameter (Qwen3, Llama3.1+, Mistral)
- **XML fallback**: Prompt-based `<tool_call>` parsing (all models)

**Safeguards:** Token budget (48K), max iterations (15), Reflexion (3 retries for code errors)

---

## Tool System

### Definitions (`services/tools.py`)
15 tools in `TOOL_DEFINITIONS`. Functions: `detect_tools_needed()`, `parse_tool_calls()` (4-tier fallback), `get_tool_definitions_for_prompt()`

### Dispatcher (`services/code_executor.py`)
`execute_tool(name, params, context)` routes to handler. Falls through to MCP client for unknown tools.

### Memory Tools (`services/memory_tools.py`)
MemGPT pattern: `save_memory`, `recall_memory`, `search_memory`, `update_memory`, `forget_memory`. Now uses `KnowledgeStore` for retrieval and dedup.

---

## Search & RAG

| Service | File | Purpose |
|---------|------|---------|
| Web search | `search.py` | Brave Search API |
| Fact check | `fact_check.py` | Dual-search verification |
| Embeddings | `embeddings.py` | FastEmbed (BAAI/bge-small-en-v1.5, 384-dim) |
| Vector store | `vector_store.py` | Per-user SQLite vector DB |
| Knowledge store | `knowledge_store.py` | Unified retrieval across facts + messages + relationships |

---

## Storage Layer

| Service | File | Purpose |
|---------|------|---------|
| State store | `state_store.py` | Canonical per-principal encrypted SQLite (state.db) |
| DB factory | `db.py` | Connection factory with sqlcipher + sqlite-vec |
| Checkpoints | `state_checkpoint.py` | Periodic IPFS backup/restore for state.db |
| User data | `user_data_store.py` | IPFS persistence pipeline (retry, sync, manifest) |

---

## Caching (`services/caching.py`)

| Cache | Size | Purpose |
|-------|------|---------|
| `EmbeddingCache` | LRU(1000) | Avoid recomputing embeddings |
| `SemanticResponseCache` | LRU(500) | Cache similar query responses |
| `TokenTracker` | Per-user | Token counting + hourly quotas |

---

## MCP Integration

- **Server** (`mcp_server.py`): Exposes all 15 tools via JSON-RPC 2.0 (HTTP + stdio)
- **Client** (`mcp_client.py`): Connects to external MCP servers, namespaced as `server:tool`

---

## Middleware

| Module | Purpose |
|--------|---------|
| `observability.py` | Prometheus metrics (request, inference, token, cache) |
| `rate_limit.py` | Per-principal throttling (30/min generate, 30/min storage) |
| `icp_cache.py` | ICP consensus replay idempotency |

---

## Provider Factory (`services/provider_factory.py`)

Cached singleton providers keyed by `(backend, host, model, num_ctx)`:
- Model routing based on complexity (Tier 1/2/3 Qwen3 family)
- Supports Ollama and vLLM backends

---

## Testing

```bash
cd backend && python -m pytest tests/ -x -q
```
