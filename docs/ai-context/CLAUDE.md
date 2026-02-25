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

This file is a quick orientation. For implementation detail, read the architecture docs:

| Document | Read when... |
|----------|-------------|
| [FRONTEND](../architecture/FRONTEND.md) | Working on React components, hooks, state, or legacy vanilla JS |
| [BACKEND](../architecture/BACKEND.md) | Working on Flask routes, middleware, services, API endpoints |
| [CHAT-SYSTEM](../architecture/CHAT-SYSTEM.md) | Working on chat lifecycle, message storage, memory integration |
| [STORAGE-AND-ENCRYPTION](../architecture/STORAGE-AND-ENCRYPTION.md) | Working on encryption, IPFS, autosave, IndexedDB |
| [MICROGPT](MICROGPT.md) | Working on classifiers, tool detection, temperature routing, training pipeline, learning roadmap |
| [CODEBASE-MAP](CODEBASE-MAP.md) | Need file-level map with exact paths, routes, constants |
| [FEATURE-CATALOG](FEATURE-CATALOG.md) | Need feature inventory with code locations |
| [CONVENTIONS](CONVENTIONS.md) | Quick do/don't rules for AI coding sessions |

### Context Loading Guide

- **Frontend-only change?** Read: this file + [FRONTEND.md](../architecture/FRONTEND.md). Skip backend sections of CODEBASE-MAP.
- **Backend route change?** Read: this file + [BACKEND.md](../architecture/BACKEND.md) + CODEBASE-MAP API section.
- **Deployment?** Read: this file + `deploy/` files. Skip architecture docs.
- **Bug fix?** Read: this file + relevant architecture doc + CODEBASE-MAP Quick Lookup.
- **New tool/feature?** Read: this file + [BACKEND.md](../architecture/BACKEND.md) + CONVENTIONS.md.
- **Classifier/routing/training?** Read: this file + [MICROGPT](MICROGPT.md).

**Check the relevant architecture doc before making changes** — it may contain constraints or design decisions that affect your approach.

---

## Project Layout

```
backend/                         # Python Flask server
├── inference_server.py          # App factory, blueprint registration
├── config.py                    # All constants + env vars
├── routes/                      # 10 blueprints, 54 endpoints
├── services/                    # 37 modules + state_store package (pipeline, agent, tools, memory, knowledge, classifiers, etc.)
├── models/                      # Trained classifier weights (.npz files)
├── middleware/                  # Observability, rate limiting, ICP cache
└── tests/                       # 1072+ tests

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
cd backend && python -m pytest tests/ -x -q    # 1072+ tests
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

- **Feb 25, 2026:** Codebase Cleanup — (1) Deleted 35+ duplicate "copy 2/3" files and 4 `.bak` files, (2) Removed dead modules: `tracing.py` (530 lines, zero imports), `prompts.py` (250 lines, zero imports), `memory_eval.py` (92 lines, dead code path), `memory_ingestion.py` (compat shim inlined), (3) Refactored `state_store.py` (1,549 lines) into mixin package: `_base`, `_chats`, `_messages`, `_facts`, `_summaries`, `_graph`, `_embeddings`, `_ingestion`, `_sync`, (4) Split `routes/chat.py` (430 lines) into `chat.py` + `memory.py` + `user.py` (10 blueprints now), (5) Archived completed plans/handoffs, fixed docs/README broken links, removed 2,290 lines of duplicate docs. Service count: 49 → 37 + state_store package. Test count: 1055+ → 1072+.
- **Feb 20, 2026:** Tier 3 + Pipeline Hardening + MicroGPT Overhaul — Added Qwen3-Coder-Next tier (80B MoE), retrained ByteTransformer classifiers, added regex confirmation gate + tool-call rescue, ReAct loop max iterations 15→5, Ollama replaced with llama-server (llama.cpp), temperature auto-routing per query type.
- **Feb 19, 2026:** Pipeline refactor — extracted 1086-line `agent.py` into `context_loader.py`, `query_classifier.py`, `prompt_assembler.py`, `pipeline.py`, `think_filter.py`. New `knowledge_store.py`, `ingestion_worker.py`, `db.py`.
- **Earlier Feb 2026:** Deleted LangGraph multi-agent / complexity router / voting / A/B experiments. Migrated frontend to React 19 + TypeScript. Added MCP server/client, 15 tools, MemGPT memory. Memory v2.0 overhaul. Upgraded to qwen3:32b with 64K context. Fixed empty responses, tool_call XML leak, hallucination boundary. Added Memory Panel, live integration tests, GPU allowlist.