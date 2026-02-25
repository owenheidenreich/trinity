# Trinity — AI Context Reference

> **Last Updated:** February 20, 2026 · **Model:** qwen3:32b on Akash via llama-server

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

This file is a quick orientation. For implementation detail, read the architecture docs:

| Document | Read when... |
|----------|-------------|
| [SYSTEM-OVERVIEW](../architecture/SYSTEM-OVERVIEW.md) | Understanding full stack, request lifecycle, security model, deployment |
| [FRONTEND](../architecture/FRONTEND.md) | Working on React components, hooks, state, or legacy vanilla JS |
| [BACKEND](../architecture/BACKEND.md) | Working on Flask routes, middleware, services, API endpoints |
| [MEMORY-SYSTEM](../architecture/MEMORY-SYSTEM.md) | Working on embeddings, vector store, semantic/user memory |
| [STORAGE-AND-ENCRYPTION](../architecture/STORAGE-AND-ENCRYPTION.md) | Working on encryption, IPFS, autosave, IndexedDB |
| [INTELLIGENCE-AND-ROUTING](../architecture/INTELLIGENCE-AND-ROUTING.md) | Working on agent pipeline, ReAct loop, tools, prompts |
| [MICROGPT](MICROGPT.md) | Working on classifiers, tool detection, temperature routing, training pipeline, learning roadmap |
| [CODEBASE-MAP](CODEBASE-MAP.md) | Need file-level map with exact paths, routes, constants |
| [FEATURE-CATALOG](FEATURE-CATALOG.md) | Need feature inventory with code locations |
| [CONVENTIONS](CONVENTIONS.md) | Quick do/don't rules for AI coding sessions |

### Context Loading Guide

- **Frontend-only change?** Read: this file + [FRONTEND.md](../architecture/FRONTEND.md). Skip backend sections of CODEBASE-MAP.
- **Backend route change?** Read: this file + [BACKEND.md](../architecture/BACKEND.md) + CODEBASE-MAP API section.
- **Deployment?** Read: this file + `deploy/` files. Skip architecture docs.
- **Bug fix?** Read: this file + relevant architecture doc + CODEBASE-MAP Quick Lookup.
- **New tool/feature?** Read: this file + [INTELLIGENCE-AND-ROUTING](../architecture/INTELLIGENCE-AND-ROUTING.md) + CONVENTIONS.md.
- **Classifier/routing/training?** Read: this file + [MICROGPT](MICROGPT.md).

**Check the relevant architecture doc before making changes** — it may contain constraints or design decisions that affect your approach.

---

## Project Layout

```
backend/                         # Python Flask server
├── inference_server.py          # App factory, blueprint registration
├── config.py                    # All constants + env vars
├── routes/                      # 9 blueprints, 54 endpoints
├── services/                    # 49 modules (pipeline, agent, tools, memory, knowledge, classifiers, etc.)
├── models/                      # Trained classifier weights (.npz files)
├── middleware/                  # Observability, rate limiting, ICP cache
└── tests/                       # 1055+ tests, 66% coverage

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

**Pipeline (refactored):** User prompt → `context_loader.load_context()` (classify via ByteTransformer + load all context once) → `prompt_assembler.assemble()` (token-budgeted) → `StreamingPipeline.process_streaming()` (ReAct / direct-with-rescue). Tool detection uses a 3-tier approach: ByteTransformer classifier (~50K params, <1ms) → regex confirmation gate (suppresses false positives below 0.92 confidence) → regex fallback — see [MICROGPT.md](MICROGPT.md). Temperature auto-routed per query type (code→0.1, factual→0.3, conversational→0.7). ReAct: max 5 iterations, 48K token budget, 15 tools, exact-duplicate guard, neutral observations, Reflexion self-correction. Direct-chat path has tool-call rescue (buffers first ~50 chars, detects raw tool-call JSON/XML, executes + re-prompts). `think_filter.py` strips `<think>` blocks from llama-server stream.

**Memory (refactored):** Four tiers — conversation context (25 messages), rolling summaries, semantic retrieval (top 20 via `knowledge_store.py`), user profile facts. New modules: `knowledge_store.py` (unified ANN retrieval with scoring: 0.6×similarity + 0.25×importance + 0.15×recency), `ingestion_worker.py` (background daemon for indexing + extraction + summarization), `db.py` (sqlcipher + sqlite-vec connection factory). 15 tools include `update_memory` and `forget_memory`. Frontend Memory Panel provides transparent read/edit/delete.

**Storage:** Per-principal encrypted SQLite (`state.db`) is canonical source of truth. AES-256-GCM + Argon2id KDF for field encryption. IPFS (Lighthouse) for backup via `state_checkpoint.py`. Frontend uses server-side persistence — no client-side IndexedDB for chat data.

---

## Critical Rules

**Deployment:**
- Docker builds MUST use `--platform linux/amd64` (dev = Apple Silicon, prod = amd64)
- Never put API keys in Akash YAML — use `.env` + runtime injection
- Deploy script: `./scripts/trinity-deploy-production.sh production` (or `test` / `tier3`)
- Three tiers: test (8B, any GPU), production (32B, 40GB+ GPU), tier3 (80B MoE Coder-Next, 80GB GPU)
- First request after deploy takes 20-30s (model loading) — this is normal

**LLM Backend (llama-server):**
- Backend uses llama-server (llama.cpp), NOT Ollama — Ollama has been fully removed
- Two instances: chat (port 8081, 32B/80B model, 65K ctx) and ingest (port 8082, 8B model, 8K ctx)
- Tier 3 uses Qwen3-Coder-Next (80B MoE, 3B activated) — split GGUF, requires A100-80GB/H100-80GB
- `think_filter.py` strips `<think>` blocks — do NOT pass `think=False` (that was Ollama-specific)
- GGUF models downloaded from HuggingFace at startup, cached on persistent volume
- Sampling params (top_p, top_k, min_p) are env-configurable per tier

**Frontend (Zustand):**
- Direct state assignments fail silently: `State.x = val` does nothing
- Always use setters: `State.setAuthenticated()`, `State.setChatHistory()`

**Testing:**
```bash
cd backend && python -m pytest tests/ -x -q    # 1055+ tests
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

- **Feb 20, 2026:** Tier 3 Deployment — Added Qwen3-Coder-Next (80B MoE, 3B activated, split GGUF) as high-performance tier. New `deploy-tier3.yaml` (A100-80GB/H100-80GB only, 64GiB RAM, 120GiB storage). Updated `startup.sh` with split GGUF download via `snapshot_download`, `--jinja`/`-fa` flags for qwen3_next architecture, 900s health timeout. Made sampling params (top_p, top_k, min_p) env-configurable in `config.py` and wired through `llama_server_provider.py`. Deploy script supports `tier3` argument.
- **Feb 20, 2026:** Pipeline Hardening — (1) Retrained ByteTransformer classifiers (80 epochs for tool detector, byte-level vocab=256, ~50K params), (2) Added regex confirmation gate — suppresses false positives when classifier confidence < 0.92 and regex disagrees, (3) Added tool-call rescue on direct-chat path — buffers first ~50 chars, detects raw JSON/XML tool calls the detector missed, executes + re-prompts, (4) ReAct loop redesigned — max iterations 15→5, exact-duplicate guard `(tool_name, params_json)`, neutral observation messages (no behavioral instructions), (5) Rewrote `diagnose_llm.py` from 42 to 126 tests across 18 categories, (6) Removed all hardcoded responses (smalltalk_fast_response, fast_path). Test count: 1028+ → 1055+.
- **Feb 20, 2026:** MicroGPT Overhaul — 3 phases: (1) Temperature routing (code→0.1, factual→0.3, conversational→0.7), (2) Trained ByteTransformer classifiers replaced ALL regex/word-list classification (query_classifier.py regex deleted, 180 lines of tool detection regex deleted from tools.py), (3) Ollama replaced with llama-server (llama.cpp) — dual instances (chat 8081 + ingest 8082), OpenAI-compatible API, GGUF models from HuggingFace. New files: `tiny_classifier.py`, `llama_server_provider.py`, `models/*.npz`. Deleted files: `ollama_provider.py`, `ollama.py`. Service count: 42 → 49. Test count: 978 → 1028+.
- **Feb 19, 2026:** Pipeline refactor — extracted 1086-line `agent.py` into `context_loader.py`, `query_classifier.py`, `prompt_assembler.py`, `pipeline.py`, `think_filter.py`. New `knowledge_store.py` (unified ANN retrieval), `ingestion_worker.py` (event-driven daemon), `db.py` (sqlcipher + sqlite-vec). Service count: 34 → 42.
- **Feb 2026:** Deleted LangGraph multi-agent, complexity router, voting, A/B experiments, parallel pipeline — replaced by single-pass agent + ReAct loop
- **Feb 2026:** Migrated frontend to React 19 + TypeScript (`src-react/`); vanilla JS in `src/` is now legacy
- **Feb 2026:** Added MCP server/client, 15 tools, MemGPT memory tools
- **Feb 2026:** Prometheus observability consolidated as single source of truth
- **Feb 2026:** AI context files optimized — CONVENTIONS.md added, copilot-instructions.md trimmed, deduplication across docs
- **Feb 2026:** Memory v2.0 overhaul — structured user profile (identity/work/interests/preferences/relationships), token-budget injection, auto-extraction, update_memory/forget_memory tools, soft-delete, bulk export ZIP, user stats endpoint
- **Feb 2026:** Upgraded model from qwen2.5-coder:32b to qwen3:32b; raised context window from 32K to 64K; IPFS layer migrated to pooled http_session with retry adapter and timing instrumentation
- **Feb 2026:** Fixed empty responses: `think=False` on all Ollama calls, `MAX_TOKENS` reduced from 48K→16K, context capping (10 msgs × 2000 chars)
- **Feb 2026:** Fixed tool_call XML leak: 4-tier `parse_tool_calls()` fallback (strict → lenient → nameless via `_TAG_TO_TOOL` → bare) + defensive XML stripping in `_get_response_content()`
- **Feb 2026:** GPU compatibility: deploy YAML now has GPU model allowlist (a100, a6000, h100, l40s, a40, rtx4090), `MIN_PRICE_MONTHLY` raised to $400 for production
- **Feb 2026:** Added `scripts/live_integration_test.py` (25 live integration tests) and `scripts/smoke_test.py` (5 smoke tests)
- **Feb 2026:** Akash `read_timeout` hard limit discovered and enforced at 60000ms
- **Feb 2026:** 20 Questions role inversion fix — switched `/api/generate` to `/api/chat`, stripped system prompt to minimal identity
- **Feb 2026:** Expanded capabilities: search patterns, `current_datetime` tool, context window raised from 20→50 messages
- **Feb 2026:** Input lock fix — moved post-streaming embedding work to daemon thread (non-blocking)
- **Feb 2026:** Hallucination fix — closed-world memory boundary footer prevents fabricated facts
- **Feb 2026:** Memory Panel — transparent, editable sidebar showing all stored user facts (MemoryPanel.tsx, PUT `/user/memory/fact/<index>`, store actions `updateMemoryFact`/`deleteMemoryFact`)
- **Feb 2026:** Storage rate limit raised from 10→30 req/min; consolidated dual memory polls to single 3s delayed poll
- **Feb 2026:** Atomic memory extraction — tightened all 39 regex patterns with conjunction-stopping capture groups (`and`/`but`/`or`), added possession/vehicle/pet/age patterns