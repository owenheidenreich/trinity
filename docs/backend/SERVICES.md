# Trinity Backend Services

> **Last Updated:** February 25, 2026
> **Location:** [backend/services/](../../backend/services/)

---

## Overview

The backend uses a **single-pass pipeline** with optional ReAct tool calling. The former 1086-line `agent.py` god module was refactored into focused modules: context loading, query classification, prompt assembly, streaming pipeline, think-block filtering, knowledge store, ingestion worker, and database connection factory.

All deleted systems (LangGraph, voting, experiments, complexity router, parallel pipeline, A/B testing, MCP, graph memory, structured output, vector_store, user_data_store, model_router, loading_messages, slo_metrics, akash service) were removed in the Feb 2026 overhauls.

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
└── services/                # ~25 modules + state_store package
    │
    │   # ── Pipeline (extracted from agent.py) ──
    ├── context_loader.py    # Single load_context() → RequestContext dataclass
    ├── query_classifier.py  # Disclosure/memory detection, temperature routing
    ├── prompt_assembler.py  # Token-budgeted prompt builder + auto-generated tool sections
    ├── pipeline.py          # StreamingPipeline: ReAct / direct chat + tool-call rescue
    ├── think_filter.py      # Streaming <think> block filter + code-fence helpers
    │
    │   # ── Agent & Tools ──
    ├── agent.py             # AgentPipeline (thin wrapper for backward compat)
    ├── agent_prompts.py     # System prompts, ReAct prompts
    ├── react_loop.py        # ReAct agentic loop (dual-mode: native + XML tools)
    ├── code_executor.py     # Tool dispatcher (14 tools)
    ├── tools.py             # Tool definitions & parsing
    │
    │   # ── Memory & Knowledge ──
    ├── knowledge_store.py   # Unified retrieval: facts + messages + relationships
    ├── memory_tools.py      # MemGPT save/recall/search/update/forget
    ├── ingestion_worker.py  # Background daemon: index, extract, summarize
    ├── profile_extractor.py # LLM extraction → {facts}
    ├── memory.py            # Semantic memory (legacy shim)
    │
    │   # ── Storage ──
    ├── state_store/         # Canonical per-principal encrypted SQLite (8 mixins)
    ├── db.py                # Connection factory (sqlcipher + sqlite-vec)
    ├── state_checkpoint.py  # Periodic IPFS checkpoint/restore
    │
    │   # ── LLM Providers ──
    ├── llama_server_provider.py  # llama-server (llama.cpp) — OpenAI-compatible API
    ├── llm_provider.py      # Abstract LLM provider interface
    ├── provider_factory.py  # Provider factory (llama-server)
    │
    │   # ── Search & RAG ──
    ├── search.py            # Brave web search
    ├── fact_check.py        # Dual-search fact verification
    ├── embeddings.py        # FastEmbed (384-dim)
    ├── caching.py           # Embedding + semantic + token caches
    │
    │   # ── Infrastructure ──
    ├── session_manager.py   # Session passphrase management
    └── repo_map.py          # Repository structure visualization
```

---

## Request Pipeline

Every request follows one path:

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
  │  Tools needed → ReactLoop.execute()   │
  │  No tools → chat_stream() + filter    │
  └───────────────────────────────────────┘
```

### Context Loader (`services/context_loader.py`)

Single function replacing 5 divergent context-loading paths. Returns a `RequestContext` dataclass.

Every query gets full context: last 25 messages + summary + 20 semantic results + tools detection + temperature routing.

### Query Classifier (`services/query_classifier.py`)

Public API (after Feb 25 cleanup):
- `is_personal_disclosure()` — first-person self-disclosure detection
- `requests_personal_memory()` — memory recall detection
- `classify_temperature()` — code→0.1, tools/memory→0.3, else→0.7

Deprecated functions (smalltalk, context level classification) were removed.

### Prompt Assembler (`services/prompt_assembler.py`)

Token-budgeted prompt construction. Budget allocation:
- Conversation history: 55% (~2200 tokens)
- Knowledge items: remaining (~1800 tokens)
- Safety margin: 2000 tokens reserved

### Streaming Pipeline (`services/pipeline.py`)

Two paths:
1. **Tool path** — ReAct loop via `react_loop.execute_streaming()`
2. **Direct path** — `chat_stream()` with think-block filtering + tool-call rescue

### Think Filter (`services/think_filter.py`)

Streaming filter for Qwen3 `<think>...</think>` blocks. Safety: ~20k token think-block limit triggers flush.

---

## Knowledge Store (`services/knowledge_store.py`)

Unified retrieval layer. All knowledge items (facts, messages, relationships) in one vector index.

**Unified Scoring:** `combined_score = similarity × 0.6 + importance × 0.25 + recency × 0.15`

**Deduplication:** On save, query top-1 KNN neighbor:
- `> 0.95` similarity → skip (identical)
- `> 0.85` similarity → merge (update existing text)
- `< 0.85` → insert new fact

---

## Ingestion Worker (`services/ingestion_worker.py`)

Background daemon. Single daemon thread drains `ingestion_jobs` table from state.db.

**Job Lifecycle:**
1. `_index_message()` → embed + KnowledgeStore.index_message()
2. `_extract_and_save()` → LLM extraction → facts
3. `_maybe_update_summary()` → rolling conversation summary

**Model Isolation:** Uses ingest instance (port 8082, qwen3:8b), separate from chat model.

---

## Tool System

### Definitions (`services/tools.py`)
14 tools in `TOOL_DEFINITIONS`: calculator, code_display, web_search, fact_check, save_memory, recall_memory, search_memory, update_memory, forget_memory, read_file, write_file, list_directory, search_codebase, run_command.

### Dispatcher (`services/code_executor.py`)
`execute_tool(name, params, context)` routes to handler. Unknown tools return an error.

### Memory Tools (`services/memory_tools.py`)
MemGPT pattern: `save_memory`, `recall_memory`, `search_memory`, `update_memory`, `forget_memory`. Uses `KnowledgeStore` for retrieval and dedup.

---

## ReAct Loop (`services/react_loop.py`)

Iterative think→act→observe loop for tool-using queries.

**Dual-mode tool calling:**
- **Native**: llama-server `/v1/chat/completions` with `tools` parameter
- **XML fallback**: Prompt-based `<tool_call>` parsing (all models)

**Safeguards:** Token budget (48K), max iterations (5), Reflexion (3 retries for code errors)

---

## Storage Layer

| Service | File | Purpose |
|---------|------|---------|
| State store | `state_store/` | Canonical per-principal encrypted SQLite (8 mixin files) |
| DB factory | `db.py` | Connection factory with sqlcipher + sqlite-vec |
| Checkpoints | `state_checkpoint.py` | Periodic IPFS backup/restore for state.db |

---

## Provider Factory (`services/provider_factory.py`)

Cached singleton providers keyed by `(backend, host, model, num_ctx)`. Supports llama-server backend.

---

## Testing

```bash
cd backend && python -m pytest tests/ -x -q   # 934+ tests
```
