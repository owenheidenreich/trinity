# Trinity — AI Context Reference

> **Last Updated:** February 25, 2026 · **Model:** qwen3:32b on Akash via llama-server

---

## Session Start

1. Read this file (~100 lines) for orientation
2. State what you're changing
3. Read the relevant architecture doc from the map below
4. Check [CODEBASE-MAP.md](CODEBASE-MAP.md) Quick Lookup table if you need file paths
5. Check [CONVENTIONS.md](CONVENTIONS.md) for do/don't rules

---

## What Is Trinity

Fully decentralized AI chat with self-custody auth. No accounts, no passwords — your browser generates an Ed25519 keypair and that's your identity. Chats are encrypted client-side (AES-256-GCM) before the backend ever sees them. Backend can't read your messages.

```
dubya.ai → ICP Canister (React frontend) → Cloudflare Worker (SSL) → Akash (Flask + llama-server)
                                                                           ↓
                                                                  Encrypted storage + IPFS backup
```

**Stack:** React 19 / TypeScript / Zustand on ICP · Flask 3 / Python 3.11 on Akash · llama-server (llama.cpp, qwen3:32b GGUF / qwen3-coder-next GGUF) · Cloudflare Worker SSL proxy · IPFS via Lighthouse

---

## Documentation Map

| Document | Read when... |
|----------|-------------|
| [FRONTEND](../architecture/FRONTEND.md) | Working on React components, hooks, state, or legacy vanilla JS |
| [BACKEND](../architecture/BACKEND.md) | Working on Flask routes, middleware, services, API endpoints |
| [CHAT-SYSTEM](../architecture/CHAT-SYSTEM.md) | Working on chat lifecycle, message storage, memory integration |
| [STORAGE-AND-ENCRYPTION](../architecture/STORAGE-AND-ENCRYPTION.md) | Working on encryption, IPFS, autosave, IndexedDB |
| [MICROGPT](MICROGPT.md) | Working on classifiers, tool detection, temperature routing, training pipeline |
| [CODEBASE-MAP](CODEBASE-MAP.md) | Need file-level map with exact paths, routes, constants |
| [FEATURE-CATALOG](FEATURE-CATALOG.md) | Need feature inventory with code locations |
| [CONVENTIONS](CONVENTIONS.md) | Quick do/don't rules for AI coding sessions |

---

## Project Layout

```
backend/                         # Python Flask server
├── inference_server.py          # App factory, blueprint registration
├── config.py                    # All constants + env vars
├── routes/                      # 7 blueprints, 31 endpoints
├── services/                    # ~25 modules + state_store package (pipeline, agent, tools, memory, knowledge, classifiers)
├── models/                      # Trained classifier weights (.npz files)
├── middleware/                  # Observability, rate limiting, ICP cache
└── tests/                       # 934+ tests

trinity-icp/                     # Frontend (ICP canister)
├── src-react/                   # Active: React 19 + TypeScript (v3.0.0)
└── src/                         # Legacy: Vanilla JS (v2.8.0, still buildable)

deploy/                          # Docker, Akash YAML, Cloudflare Worker
scripts/                         # Deployment automation
docs/                            # Architecture docs, guides, AI context
```

---

## How It Works (Summary)

**Auth:** Ed25519 keypair → principal ID (base32). Signed message format: `{principal}:{timestamp}:{endpoint}:{nonce}`. Backend verifies via `@require_auth` decorator. 60s replay window.

**Pipeline:** User prompt → `context_loader.load_context()` (classify via ByteTransformer + load all context once) → `prompt_assembler.assemble()` (token-budgeted) → `StreamingPipeline.process_streaming()` (ReAct / direct-with-rescue). Tool detection uses a 3-tier approach: ByteTransformer classifier (~50K params, <1ms) → regex confirmation gate (suppresses false positives below 0.92 confidence) → regex fallback — see [MICROGPT.md](MICROGPT.md). Temperature auto-routed per query type (code→0.1, factual→0.3, conversational→0.7). ReAct: max 5 iterations, 48K token budget, 14 tools, exact-duplicate guard, neutral observations, Reflexion self-correction. Direct-chat path has tool-call rescue. `think_filter.py` strips `<think>` blocks from llama-server stream.

**Memory:** Four tiers — conversation context (25 messages), rolling summaries, semantic retrieval (top 20 via `knowledge_store.py`), user profile facts. `knowledge_store.py` (unified ANN retrieval with scoring: 0.6×similarity + 0.25×importance + 0.15×recency), `ingestion_worker.py` (background daemon for indexing + extraction + summarization), `db.py` (sqlcipher + sqlite-vec connection factory). 14 tools include `update_memory` and `forget_memory`. Frontend Memory Panel provides transparent read/edit/delete.

**Storage:** Per-principal encrypted SQLite (`state.db`) is canonical source of truth. AES-256-GCM + Argon2id KDF for field encryption. IPFS (Lighthouse) for backup via `state_checkpoint.py`. Frontend uses server-side persistence.

---

## Critical Rules

**Deployment:**
- Docker builds MUST use `--platform linux/amd64` (dev = Apple Silicon, prod = amd64)
- Never put API keys in Akash YAML — use `.env` + runtime injection
- Deploy script: `./scripts/trinity-deploy-production.sh production` (or `test` / `tier3`)

**LLM Backend (llama-server):**
- Backend uses llama-server (llama.cpp), NOT Ollama — Ollama has been fully removed
- Two instances: chat (port 8081, 32B model) and ingest (port 8082, 8B model)
- `think_filter.py` strips `<think>` blocks — do NOT pass `think=False` (that was Ollama-specific)

**Frontend (Zustand):**
- Direct state assignments fail silently: `State.x = val` does nothing
- Always use setters: `State.setAuthenticated()`, `State.setChatHistory()`

**Testing:**
```bash
cd backend && python -m pytest tests/ -x -q    # 934+ tests
```

---

## Key Identifiers

| Resource | Value |
|----------|-------|
| Production URL | https://dubya.ai |
| API URL | https://api.dubya.ai |
| Frontend canister | `zc67k-kiaaa-aaaal-qtmiq-cai` |
| Docker image | `gdubx/trinity-inference:latest` |

---

## Recent Changes

- **Feb 25, 2026 (Major Cleanup):** Deleted 30 files, 8700+ lines of dead code. Removed: 12 dead services (MCP, graph memory, vector_store, user_data_store, structured, model_router, loading_messages, slo_metrics, akash), 4 unused route blueprints (admin, session, diagnostic, mcp), graph system, document_search tool. 54→31 endpoints, 15→14 tools, 10→7 blueprints. 934 tests passing.
- **Feb 25, 2026 (Earlier Cleanup):** Deleted 35+ duplicate files, 4 `.bak` files. Removed dead modules: tracing.py, prompts.py, memory_eval.py, memory_ingestion.py. Refactored state_store.py into mixin package. Split routes/chat.py into chat.py + memory.py + user.py.
- **Feb 20, 2026:** Tier 3 + Pipeline Hardening + MicroGPT Overhaul — Added Qwen3-Coder-Next tier (80B MoE), retrained ByteTransformer classifiers, ReAct loop max iterations 15→5, Ollama replaced with llama-server.
- **Feb 19, 2026:** Pipeline refactor — extracted agent.py into context_loader, query_classifier, prompt_assembler, pipeline, think_filter. New knowledge_store, ingestion_worker, db.
