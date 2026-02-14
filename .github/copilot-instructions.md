# Trinity AI Copilot Instructions

> **Last Updated:** February 13, 2026

## Stack (source of truth: `docs/ai-context/CLAUDE.md`)

React 19 / TypeScript / Zustand on ICP · Flask 3 / Python 3.11 on Akash · Ollama (qwen2.5-coder:32b) · Cloudflare Worker SSL proxy · IPFS via Lighthouse

## Before Any Change

1. Read the relevant architecture doc (see `docs/ai-context/CLAUDE.md` → Documentation Map)
2. Check `docs/ai-context/CODEBASE-MAP.md` for exact file paths, routes, and constants
3. Follow the appropriate workflow checklist below

## Critical Rules

- **Zustand**: Never direct-assign state (`State.x = val` fails silently). Always use setters: `State.setAuthenticated()`, `State.setChatHistory()`
- **Docker**: Always build with `--platform linux/amd64` (dev = Apple Silicon, prod = amd64)
- **Deploy**: `./scripts/trinity-deploy-production.sh [tier]` handles everything
- **Auth**: Ed25519 signatures, 60s timestamp window (hardcoded in `icp_auth.py`), `@require_auth` decorator
- **Encryption**: AES-256-GCM + Argon2id KDF (primary) / PBKDF2 (fallback)
- **Frontend**: Active code is `trinity-icp/src-react/` (React 19). `trinity-icp/src/` is legacy.
- **Cold starts**: First request after Akash deploy takes 20-30s (model loading) — this is normal
- **Tests**: `cd backend && python -m pytest tests/ -x -q` (615 tests, 91% coverage)

## Workflow Checklists

**Backend change** → verify syntax → verify imports → verify Dockerfile COPY → Docker build → container starts → push → update Akash YAML → redeploy

**Frontend change** → lint → test → build → deploy ICP canister

**After major changes** → update `docs/ai-context/CODEBASE-MAP.md` → grep docs/ for stale values → verify cross-references

## Key File Locations

| Task | File(s) |
|------|---------|
| API routes | `backend/routes/<blueprint>.py` (8 blueprints, 42+ endpoints) |
| LLM prompts | `backend/services/agent_prompts.py` |
| Add a tool | `backend/services/tools.py` + `code_executor.py` |
| Auth | `backend/icp_auth.py` |
| State management | `trinity-icp/src-react/store/index.ts` |
| Deployment | `deploy/docker/Dockerfile`, `deploy/akash/deploy-tier*.yaml` |
| Constants | `backend/config.py` |

## Common Pitfalls

- Git slow? Check for `trinity-icp/target/` or `node_modules/` in tracking
- Storage tests pass locally but fail in prod — always test against Akash backend
- Zustand direct assignments don't throw errors — they just silently break