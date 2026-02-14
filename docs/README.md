# Trinity Documentation

> **Last Updated:** February 13, 2026
> Comprehensive documentation for Trinity — a decentralized AI chat application.

---

## Quick Navigation

| Document | Audience | Description |
|----------|----------|-------------|
| [CLAUDE.md](ai-context/CLAUDE.md) | **AI/LLMs** | Concise project reference |
| [CODEBASE-MAP.md](ai-context/CODEBASE-MAP.md) | **AI/LLMs** | All files, routes, constants |
| [backend/API.md](backend/API.md) | **Developers** | API endpoint reference |
| [backend/SERVICES.md](backend/SERVICES.md) | **Developers** | Backend services |
| [frontend/MODULES.md](frontend/MODULES.md) | **Developers** | Frontend modules (vanilla JS + React) |
| [deployment/WORKFLOW.md](deployment/WORKFLOW.md) | **DevOps** | Deployment procedures |

---

## For AI Assistants

**Start here:** [ai-context/CLAUDE.md](ai-context/CLAUDE.md) — Concise reference covering architecture, key files, config, and deployment.

**Also useful:**
- [ai-context/CODEBASE-MAP.md](ai-context/CODEBASE-MAP.md) — File-level map with all routes and constants
- [ai-context/FEATURE_CATALOG.md](ai-context/FEATURE_CATALOG.md) — Feature inventory
- [QA-HANDOFF.md](QA-HANDOFF.md) — Post-overhaul QA audit and verification matrix

---

## For Developers

### Getting Started
1. [getting-started/developer-setup.md](getting-started/developer-setup.md) — Local development setup
2. [getting-started/common-tasks.md](getting-started/common-tasks.md) — Day-to-day workflows

### Technical Reference
- [backend/API.md](backend/API.md) — API endpoints (8 blueprints)
- [backend/SERVICES.md](backend/SERVICES.md) — Backend services
- [frontend/MODULES.md](frontend/MODULES.md) — Frontend modules

### Architecture
- [architecture/trinity-storage-architecture.md](architecture/trinity-storage-architecture.md) — Storage layer design
- [architecture/decisions/](architecture/decisions/) — Architecture Decision Records (3 active ADRs)

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
│   ├── inference_server.py     # App factory
│   ├── routes/                 # 8 blueprints
│   ├── middleware/             # Rate limiting, Prometheus, caching
│   └── services/               # Agent pipeline, tools, RAG, MCP
├── trinity-icp/
│   ├── src/                    # Vanilla JS frontend (active, deployed)
│   └── src-react/              # React 19 + TypeScript (new, not yet deployed)
├── deploy/
│   ├── akash/                  # Akash YAML manifests (3 tiers)
│   ├── docker/                 # Dockerfile + startup
│   └── cloudflare-worker/      # SSL proxy
├── scripts/                    # Automation (deploy, provider switching)
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

## Historical / Archive

| Document | Description |
|----------|-------------|
| [ai-context/OVERHAUL-PROGRESS.md](ai-context/OVERHAUL-PROGRESS.md) | Phase-by-phase overhaul audit trail |
| [QA-HANDOFF.md](QA-HANDOFF.md) | Post-overhaul QA verification matrix |
| [plans/INTELLIGENCE-OVERHAUL.md](plans/INTELLIGENCE-OVERHAUL.md) | Backend overhaul spec (completed) |
| [plans/FRONTEND-OVERHAUL-PROPOSAL.md](plans/FRONTEND-OVERHAUL-PROPOSAL.md) | Frontend overhaul spec (completed) |
| [architecture/decisions/001-complexity-routing.md](architecture/decisions/001-complexity-routing.md) | Archived — superseded by single-pass |
| [architecture/decisions/004-hash-based-experiments.md](architecture/decisions/004-hash-based-experiments.md) | Archived — experiments deleted |
