# Trinity AI Copilot Instructions

> **Last Updated:** February 20, 2026

## Stack (source of truth: `docs/ai-context/CLAUDE.md`)

React 19 / TypeScript / Zustand on ICP · Flask 3 / Python 3.11 on Akash · llama-server (llama.cpp, qwen3:32b GGUF) · Cloudflare Worker SSL proxy · IPFS via Lighthouse

## Before Any Change

1. Read the relevant architecture doc (see `docs/ai-context/CLAUDE.md` → Documentation Map)
2. Check `docs/ai-context/CODEBASE-MAP.md` for exact file paths, routes, and constants
3. Follow the appropriate workflow checklist below

## Critical Rules

- **Zustand**: Never direct-assign state (`State.x = val` fails silently). Always use setters: `State.setAuthenticated()`, `State.setChatHistory()`
- **Docker**: Always build with `--platform linux/amd64` (dev = Apple Silicon, prod = amd64)
- **Deploy**: `./scripts/trinity-deploy-production.sh production` (or `test` for smoke-testing, `tier3` for Qwen3-Coder-Next)
- **Auth**: Ed25519 signatures, 60s timestamp window (hardcoded in `icp_auth.py`), `@require_auth` decorator
- **Encryption**: AES-256-GCM + Argon2id KDF (primary) / PBKDF2 (fallback)
- **Frontend**: Active code is `trinity-icp/src-react/` (React 19). `trinity-icp/src/` is legacy.
- **Cold starts**: First request after Akash deploy takes 20-30s (model loading) — this is normal
- **Tests**: `cd backend && python -m pytest tests/ -x -q` (1028+ tests)
- **LLM Backend**: llama-server (llama.cpp), NOT Ollama — Ollama has been fully removed. `think_filter.py` strips `<think>` blocks.
- **Classification**: Only the tool detector (`tiny_classifier.py` + `tools.py` regex fallback) drives pipeline behavior. Query classifier is deprecated for routing — every query gets full context + LLM call. Do NOT delete tool detection regex fallback patterns. See `docs/ai-context/MICROGPT.md`.
- **Temperature**: Auto-routed per query type — code→0.1, factual→0.3, conversational→0.7. Do NOT hardcode 0.7 everywhere.
- **GPU Allowlist**: Production deploy requires a100/a6000/h100/l40s/a40/rtx4090 for full model offloading. Tier 3 (Coder-Next 80B) requires a100-80gb/h100-80gb only.
- **Akash Timeout**: `read_timeout` hard limit is 60000ms — do not set higher

## Workflow Checklists

**Backend change** → verify syntax → verify imports → verify Dockerfile COPY → Docker build → container starts → push → update Akash YAML → redeploy

**Frontend change** → lint → test → build → deploy ICP canister

**After major changes** → update `docs/ai-context/CODEBASE-MAP.md` → grep docs/ for stale values → verify cross-references

## Key File Locations

| Task | File(s) |
|------|---------|
| API routes | `backend/routes/<blueprint>.py` (9 blueprints, 54 endpoints) |
| LLM prompts | `backend/services/agent_prompts.py` |
| LLM provider | `backend/services/llama_server_provider.py`, `backend/services/provider_factory.py` |
| Query classification | `backend/services/query_classifier.py` (deprecated stubs, disclosure/temperature) |
| Tool detection | `backend/services/tiny_classifier.py` (model), `backend/services/tools.py` (definitions) |
| Add a tool | `backend/services/tools.py` + `code_executor.py` |
| Memory system | `backend/storage.py`, `backend/services/memory_tools.py`, `backend/services/profile_extractor.py` |
| Auth | `backend/icp_auth.py` |
| State management | `trinity-icp/src-react/store/index.ts` |
| Deployment | `deploy/docker/Dockerfile`, `deploy/docker/startup.sh`, `deploy/akash/deploy-production.yaml`, `deploy/akash/deploy-tier3.yaml` |
| Constants | `backend/config.py` |
| Retrain classifiers | `scripts/generate_training_data.py` → `scripts/train_classifiers.py` |

## Common Pitfalls

- Git slow? Check for `trinity-icp/target/` or `node_modules/` in tracking
- Storage tests pass locally but fail in prod — always test against Akash backend
- Zustand direct assignments don't throw errors — they just silently break
- Do NOT reference `ollama_provider.py` or `ollama.py` — these files are deleted
- Do NOT delete regex fallback patterns in `tools.py` — they are the safety net for low-confidence tool detection
- Query classifier no longer drives routing — `classify_context_level()` is a deprecated stub. Do NOT add new ContextLevel branching.
- Do NOT pass `think=False` to llama-server — that was Ollama-specific. `think_filter.py` handles it.