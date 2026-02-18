# Trinity — AI Context Reference

> **Last Updated:** February 17, 2026 · **Model:** qwen3:32b on Akash

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
dubya.ai → ICP Canister (React frontend) → Cloudflare Worker (SSL) → Akash (Flask + Ollama)
                                                                           ↓
                                                                  Encrypted storage + IPFS backup
```

**Stack:** React 19 / TypeScript / Zustand on ICP · Flask 3 / Python 3.11 on Akash · Ollama (qwen3:32b) · Cloudflare Worker SSL proxy · IPFS via Lighthouse

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
| [CODEBASE-MAP](CODEBASE-MAP.md) | Need file-level map with exact paths, routes, constants |
| [FEATURE-CATALOG](FEATURE-CATALOG.md) | Need feature inventory with code locations |
| [CONVENTIONS](CONVENTIONS.md) | Quick do/don't rules for AI coding sessions |

### Context Loading Guide

- **Frontend-only change?** Read: this file + [FRONTEND.md](../architecture/FRONTEND.md). Skip backend sections of CODEBASE-MAP.
- **Backend route change?** Read: this file + [BACKEND.md](../architecture/BACKEND.md) + CODEBASE-MAP API section.
- **Deployment?** Read: this file + `deploy/` files. Skip architecture docs.
- **Bug fix?** Read: this file + relevant architecture doc + CODEBASE-MAP Quick Lookup.
- **New tool/feature?** Read: this file + [INTELLIGENCE-AND-ROUTING](../architecture/INTELLIGENCE-AND-ROUTING.md) + CONVENTIONS.md.

**Check the relevant architecture doc before making changes** — it may contain constraints or design decisions that affect your approach.

---

## Project Layout

```
backend/                         # Python Flask server
├── inference_server.py          # App factory, blueprint registration
├── config.py                    # All constants + env vars
├── routes/                      # 9 blueprints, 54 endpoints
├── services/                    # 34 modules (agent, tools, memory, search, etc.)
├── middleware/                  # Observability, rate limiting, ICP cache
└── tests/                       # 978 tests, 66% coverage

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

**Agent Pipeline:** User prompt → heuristic tool detection → if tools needed, ReAct loop (max 15 iterations, 48K token budget, 15 tools) → if not, direct LLM generation. `think=False` on all Ollama calls (suppresses Qwen3 `<think>` blocks). Agent-level `MAX_TOKENS=16384`. Context capped to 10 messages × 2000 chars. Reflexion self-correction on errors. Auto-extraction of profile facts runs in daemon thread after each response (non-blocking).

**Memory:** Three tiers — working (last 5 messages), semantic (top 8 by vector similarity), user memory (v2.0 structured profile with categories, token-budget injection, soft-delete, auto-extraction, encrypted on IPFS). 15 tools include `update_memory` and `forget_memory`. Frontend Memory Panel provides transparent read/edit/delete of all stored facts.

**Storage:** AES-256-GCM + Argon2id KDF. Encrypted client-side before transmission. IPFS (Lighthouse) is source of truth; IndexedDB is session cache. Autosave with 2s debounce.

---

## Critical Rules

**Deployment:**
- Docker builds MUST use `--platform linux/amd64` (dev = Apple Silicon, prod = amd64)
- Never put API keys in Akash YAML — use `.env` + runtime injection
- Deploy script: `./scripts/trinity-deploy-production.sh production` (or `test` for smoke-testing)
- First request after deploy takes 20-30s (model loading) — this is normal

**Frontend (Zustand):**
- Direct state assignments fail silently: `State.x = val` does nothing
- Always use setters: `State.setAuthenticated()`, `State.setChatHistory()`

**Testing:**
```bash
cd backend && python -m pytest tests/ -x -q    # 978 tests
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

- **Feb 2026:** Deleted LangGraph multi-agent, complexity router, voting, A/B experiments, parallel pipeline — replaced by single-pass agent + ReAct loop
- **Feb 2026:** Migrated frontend to React 19 + TypeScript (`src-react/`); vanilla JS in `src/` is now legacy
- **Feb 2026:** Added MCP server/client, 15 tools, MemGPT memory tools
- **Feb 2026:** Prometheus observability consolidated as single source of truth
- **Feb 2026:** AI context files optimized — CONVENTIONS.md added, copilot-instructions.md trimmed, deduplication across docs
- **Feb 2026:** Memory v2.0 overhaul — structured user profile (identity/work/interests/preferences/relationships), token-budget injection, auto-extraction, update_memory/forget_memory tools, soft-delete, bulk export ZIP, user stats endpoint
- **Feb 2026:** Upgraded model from qwen2.5-coder:32b to qwen3:32b; raised context window from 32K to 64K; IPFS layer migrated to pooled http_session with retry adapter and timing instrumentation
- **Feb 2026:** MiniMax M2.5 migration attempted (vLLM, 4× A100 80GB on Akash) — abandoned due to Akash /dev/shm 64MB limitation blocking NCCL multi-GPU
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