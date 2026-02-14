# Trinity Backend Services

> **Last Updated:** February 13, 2026
> **Location:** [backend/services/](../../backend/services/)

---

## Overview

The backend uses a single-pass agent pipeline with optional ReAct tool calling. All deleted systems (LangGraph, voting, experiments, complexity router, parallel pipeline, A/B testing) were removed in the Feb 2026 overhaul.

```
backend/
├── inference_server.py      # App factory, blueprint registration
├── config.py                # Environment variables and constants
├── encryption.py            # AES-256-GCM encryption
├── storage.py               # User directory management
├── validation.py            # Input validation, SSRF protection
├── icp_auth.py              # Ed25519 authentication
├── lighthouse.py            # IPFS/Filecoin storage
├── middleware/
│   ├── rate_limit.py        # Per-principal rate limiting
│   ├── icp_cache.py         # Idempotency cache
│   └── observability.py     # Prometheus metrics (single source of truth)
└── services/
    ├── agent.py             # Single-pass orchestrator
    ├── agent_prompts.py     # System prompts, ReAct prompts
    ├── react_loop.py        # ReAct agentic loop (dual-mode tools)
    ├── code_executor.py     # Tool dispatcher (13 tools)
    ├── tools.py             # Tool definitions & parsing
    ├── memory_tools.py      # MemGPT save/recall/search
    ├── ollama.py            # Ollama HTTP client
    ├── search.py            # Brave web search
    ├── fact_check.py        # Dual-search fact verification
    ├── embeddings.py        # FastEmbed (384-dim)
    ├── vector_store.py      # Per-user vector DB
    ├── memory.py            # Semantic memory retrieval
    ├── caching.py           # Embedding + semantic + token caches
    ├── prompts.py           # System prompt construction
    ├── structured.py        # Structured output parsing
    ├── loading_messages.py  # Phase update messages
    ├── akash.py             # Deployment info & costs
    ├── mcp_server.py        # MCP server (JSON-RPC 2.0)
    ├── mcp_client.py        # MCP client (external tools)
    ├── repo_map.py          # Repository structure visualization
    └── tracing.py           # Distributed tracing
```

---

## Agent Pipeline (`services/agent.py`)

Single-pass orchestrator. Routes every query through one path:

```
User Prompt → detect_tools_needed()
  ├── Tools needed + REACT_ENABLED → ReactLoop.execute_streaming()
  ├── Tools needed + !REACT_ENABLED → Direct generate_stream() (fallback)
  └── No tools needed → Direct generate_stream()
```

**Key class:** `AgentPipeline`
- `process_streaming()` — Main entry, yields SSE events
- `_format_user_memory()` — Formats raw memory dicts for prompt injection
- `_filter_think_blocks()` — Strips `<think>…</think>` from output

---

## ReAct Loop (`services/react_loop.py`)

Iterative think→act→observe loop for tool-using queries.

**Dual-mode tool calling:**
- **Native**: Ollama `/api/chat` with `tools` parameter (Qwen3, Llama3.1+, Mistral)
- **XML fallback**: Prompt-based `<tool_call>` parsing (all models)

**Protocol:**
1. Model generates reasoning + ONE tool call → STOP
2. Tool executed via `execute_tool()`, result fed back
3. Repeat until final answer or budget exhausted

**Safeguards:** Token budget (24K), max iterations (15), Reflexion (3 retries for code errors)

---

## Tool System

### Definitions (`services/tools.py`)
13 tools in `TOOL_DEFINITIONS`. Functions: `detect_tools_needed()`, `parse_tool_calls()`, `get_tool_definitions_for_prompt()`

### Dispatcher (`services/code_executor.py`)
`execute_tool(name, params, context)` — Routes to handler. Falls through to MCP client for unknown tools.

### Memory Tools (`services/memory_tools.py`)
MemGPT pattern: `save_memory`, `recall_memory`, `search_memory` with 384-dim embeddings and deduplication.

---

## Search & RAG

| Service | File | Purpose |
|---------|------|---------|
| Web search | `search.py` | Brave Search API |
| Fact check | `fact_check.py` | Dual-search verification |
| Embeddings | `embeddings.py` | FastEmbed (BAAI/bge-small-en-v1.5, 384-dim) |
| Vector store | `vector_store.py` | Per-user SQLite vector DB |
| Semantic memory | `memory.py` | Cross-chat retrieval |

---

## Caching (`services/caching.py`)

| Cache | Size | Purpose |
|-------|------|---------|
| `EmbeddingCache` | LRU(1000) | Avoid recomputing embeddings |
| `SemanticResponseCache` | LRU(500) | Cache similar query responses |
| `TokenTracker` | Per-user | Token counting + hourly quotas |

---

## MCP Integration

- **Server** (`mcp_server.py`): Exposes all 13 tools via JSON-RPC 2.0 (HTTP + stdio)
- **Client** (`mcp_client.py`): Connects to external MCP servers, namespaced as `server:tool`

---

## Middleware

| Module | Purpose |
|--------|---------|
| `observability.py` | Prometheus metrics (request, inference, token, cache) |
| `rate_limit.py` | Per-principal throttling (30/min generate, 10/min storage) |
| `icp_cache.py` | ICP consensus replay idempotency |

---

## Core Modules

| Module | Purpose |
|--------|---------|
| `config.py` | All env vars and constants |
| `icp_auth.py` | `@require_auth`, `@require_admin` decorators |
| `encryption.py` | AES-256-GCM with Argon2id (primary) / PBKDF2 (100k iterations, fallback) |
| `storage.py` | Chat file I/O, user directory management |
| `validation.py` | Input sanitization, SSRF protection |
| `lighthouse.py` | IPFS upload/download via Lighthouse |

---

## Testing

```bash
cd backend && python -m pytest tests/ -x -q    # 615 passed, 91.30% coverage
```
