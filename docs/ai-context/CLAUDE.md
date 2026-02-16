# Trinity — AI Context Reference

> **Last Updated:** February 15, 2026 · **Model:** qwen2.5-coder:32b on Akash

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

**Stack:** React 19 / TypeScript / Zustand on ICP · Flask 3 / Python 3.11 on Akash · Ollama LLM · Cloudflare Worker SSL proxy · IPFS via Lighthouse

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
├── routes/                      # 8 blueprints, 42+ endpoints
├── services/                    # 21 modules (agent, tools, memory, search, etc.)
├── middleware/                  # Observability, rate limiting, ICP cache
└── tests/                       # 858 tests, 91% coverage

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

**Agent Pipeline:** User prompt → heuristic tool detection → if tools needed, ReAct loop (max 15 iterations, 24K token budget, 15 tools) → if not, direct LLM generation. Reflexion self-correction on errors. Auto-extraction of profile facts runs in background after each response.

**Memory:** Three tiers — working (last 3 messages), semantic (top 5 by vector similarity), user memory (v2.0 structured profile with categories, token-budget injection, soft-delete, auto-extraction, encrypted on IPFS). 15 tools include `update_memory` and `forget_memory`.

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
cd backend && python -m pytest tests/ -x -q    # 726 tests, 91% coverage
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
- **Feb 2026:** MiniMax M2.5 migration attempted (vLLM, 4× A100 80GB on Akash) — abandoned due to Akash /dev/shm 64MB limitation blocking NCCL multi-GPU