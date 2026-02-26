# Trinity Documentation

> **Last Updated:** February 2026 · v3.0.0
> Comprehensive documentation for Trinity — a fully decentralized AI chat application.

---

## Quick Navigation

### Architecture (Start Here)

| Document | Description |
|----------|-------------|
| [architecture/FRONTEND.md](architecture/FRONTEND.md) | React component tree, hooks, state management, rendering pipeline |
| [architecture/BACKEND.md](architecture/BACKEND.md) | Flask server, 31 API endpoints, middleware, configuration |
| [architecture/CHAT-SYSTEM.md](architecture/CHAT-SYSTEM.md) | Chat lifecycle, message storage, memory integration, archiving |
| [architecture/STORAGE-AND-ENCRYPTION.md](architecture/STORAGE-AND-ENCRYPTION.md) | Encryption, IPFS, autosave, recovery |

### For Developers

| Document | Description |
|----------|-------------|
| [getting-started/developer-setup.md](getting-started/developer-setup.md) | Local development environment setup |
| [getting-started/common-tasks.md](getting-started/common-tasks.md) | Day-to-day development workflows |
| [backend/API.md](backend/API.md) | Backend API documentation |
| [backend/SERVICES.md](backend/SERVICES.md) | Backend service modules reference |
| [frontend/MODULES.md](frontend/MODULES.md) | Frontend module documentation |

### For DevOps

| Document | Description |
|----------|-------------|
| [deployment/WORKFLOW.md](deployment/WORKFLOW.md) | Deployment procedures (Docker, Akash, ICP) |
| [reference/AKASH_CLI_REFERENCE.md](reference/AKASH_CLI_REFERENCE.md) | Akash CLI command reference |
| [getting-started/setup.md](getting-started/setup.md) | New machine setup (Akash wallet, dfx, Docker) |

### For Security Auditors

| Document | Description |
|----------|-------------|
| *(Security doc planned)* | Security architecture, trust boundaries, crypto details |

### For AI Assistants

| Document | Description |
|----------|-------------|
| [ai-context/CLAUDE.md](ai-context/CLAUDE.md) | Concise AI context: key files, routes, config, deployment |
| [ai-context/CODEBASE-MAP.md](ai-context/CODEBASE-MAP.md) | File-level map with all routes and constants |
| [ai-context/FEATURE-CATALOG.md](ai-context/FEATURE-CATALOG.md) | Feature inventory with code locations |
| [ai-context/CONVENTIONS.md](ai-context/CONVENTIONS.md) | Machine-readable do/don't rules for AI coding sessions |
| [ai-context/MICROGPT.md](ai-context/MICROGPT.md) | Neural classifiers, tool detection, training pipeline |

---

## Project Structure

```
Trinity/
├── backend/                         # Python Flask inference server
│   ├── inference_server.py          # App factory + blueprint registration
│   ├── routes/                      # 7 blueprints (31 endpoints)
│   ├── middleware/                   # Observability, rate limiting, caching
│   ├── services/                    # ~25 service modules + state_store package
│   └── tests/                       # Unit, integration, and E2E tests
│
├── trinity-icp/                     # Frontend (ICP canister)
│   ├── src-react/                   # Active React 19 / TypeScript (v3.0.0)
│   └── src/                         # Legacy vanilla JS (v2.8.0, still buildable)
│
├── deploy/                          # Deployment configurations
│   ├── docker/                      # Dockerfile (CUDA + llama-server)
│   ├── akash/                       # SDL files for 3 tiers (test/production/tier3)
│   ├── cloudflare-worker/           # SSL termination proxy
│   └── docker-compose.monitoring.yml
│
├── scripts/                         # Deployment + testing automation
└── docs/                            # This documentation
```

---

## Key Links

| Resource | URL |
|----------|-----|
| Production Frontend | https://dubya.ai |
| API Endpoint | https://api.dubya.ai |
| Health Check | https://api.dubya.ai/health |
| Frontend Canister | `zc67k-kiaaa-aaaal-qtmiq-cai` |

---

## Design Rationale

| ADR | Status | Summary |
|-----|--------|---------|
| [Tiered Test Coverage](architecture/decisions/002-tiered-test-coverage.md) | Active | Risk-based coverage targets (P0: 90%, P1: 70%) |
| [Prometheus over SaaS](architecture/decisions/003-prometheus-over-saas.md) | Active | Self-hosted monitoring ($500+/mo savings) |

---

## Archive

Completed plans and historical documents: [archive/](archive/)
