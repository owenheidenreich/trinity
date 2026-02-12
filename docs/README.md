# Trinity Documentation

> **Last Updated:** February 10, 2026  
> Comprehensive documentation for Trinity - a decentralized AI chat application.

---

## Quick Navigation

| Document | Audience | Description |
|----------|----------|-------------|
| [CLAUDE.md](ai-context/CLAUDE.md) | **AI/LLMs** | Primary AI context document (2000+ lines) |
| [CODEBASE-MAP.md](ai-context/CODEBASE-MAP.md) | **AI/LLMs** | Quick-reference: all files, routes, constants |
| [backend/API.md](backend/API.md) | **Developers** | All 49 API endpoints with examples |
| [backend/SERVICES.md](backend/SERVICES.md) | **Developers** | Backend services documentation |
| [frontend/MODULES.md](frontend/MODULES.md) | **Developers** | Frontend module documentation |
| [deployment/WORKFLOW.md](deployment/WORKFLOW.md) | **DevOps** | Deployment procedures |

---

## For AI Assistants

**Start here:** [ai-context/CLAUDE.md](ai-context/CLAUDE.md)

This 2000+ line document contains everything you need:
- Architecture overview
- State management (Zustand patterns)
- Authentication (Ed25519 flow)
- All deployment workflows
- Common pitfalls and fixes

**Also useful:**
- [ai-context/CODEBASE-MAP.md](ai-context/CODEBASE-MAP.md) — Quick-reference map of all files, routes, and constants
- [ai-context/FEATURE_CATALOG.md](ai-context/FEATURE_CATALOG.md) — Feature inventory

---

## For Developers

### Getting Started
1. [getting-started/developer-setup.md](getting-started/developer-setup.md) — Local development setup
2. [getting-started/common-tasks.md](getting-started/common-tasks.md) — Day-to-day workflows
3. [getting-started/setup.md](getting-started/setup.md) — Production environment setup

### Technical Reference
- [backend/API.md](backend/API.md) — Complete API documentation (49 endpoints)
- [backend/SERVICES.md](backend/SERVICES.md) — Backend services (20+ modules)
- [frontend/MODULES.md](frontend/MODULES.md) — Frontend modules (32 files across 8 directories)

### Architecture
- [architecture/trinity-storage-architecture.md](architecture/trinity-storage-architecture.md) — Storage layer design
- [architecture/decisions/](architecture/decisions/) — Architecture Decision Records (5 ADRs)

---

## For Security Auditors

1. [security/SECURITY-AUDITOR-OVERVIEW.md](security/SECURITY-AUDITOR-OVERVIEW.md) — Start here
2. [security/security-audit.md](security/security-audit.md) — Test coverage and findings

---

## For DevOps

1. [deployment/WORKFLOW.md](deployment/WORKFLOW.md) — Deployment procedures
2. [reference/AKASH_CLI_REFERENCE.md](reference/AKASH_CLI_REFERENCE.md) — Akash CLI commands

---

## Project Structure

```
Trinity/
├── backend/                    # Flask + Ollama backend
│   ├── inference_server.py     # App factory (349 lines)
│   ├── routes/                 # 7 route blueprints (49 endpoints)
│   ├── middleware/             # Rate limiting, caching, observability
│   └── services/               # 20+ service modules
├── trinity-icp/src/            # ICP frontend
│   ├── app.js                  # Application orchestrator (266 lines)
│   ├── core/                   # Infrastructure (api.js, environment.js, logger.js)
│   ├── features/               # Feature modules (auth, generate, chat, memory)
│   ├── auth/                   # Ed25519 authentication
│   ├── state/                  # Zustand state management
│   ├── storage/                # Autosave, IPFS
│   └── ui/                     # UI components
├── deploy/                     # Deployment configs
│   ├── akash/                  # Akash YAML manifests
│   ├── docker/                 # Dockerfile
│   └── cloudflare-worker/      # SSL proxy
├── scripts/                    # Automation scripts
└── docs/                       # This documentation
```

---

## Key Links

| Resource | URL |
|----------|-----|
| Production Frontend | https://dubya.ai |
| API Endpoint | https://api.dubya.ai |
| Health Check | https://api.dubya.ai/health |
| Frontend Canister | zc67k-kiaaa-aaaal-qtmiq-cai |
| Backend Canister | au5zq-2qaaa-aaaal-qtowa-cai |

---

## Document Versions

| Document | Last Updated |
|----------|--------------|
| CLAUDE.md | February 10, 2026 |
| CODEBASE-MAP.md | February 10, 2026 |
| FEATURE_CATALOG.md | February 6, 2026 |
| MODULES.md | February 10, 2026 |
| B2B Pivot Strategy | February 10, 2026 |
| This README | February 10, 2026 |
