# Trinity Documentation

> **Last Updated:** February 2026 · v3.0.0
> Comprehensive documentation for Trinity — a fully decentralized AI chat application.

---

## Quick Navigation

### Architecture (Start Here)

| Document | Description |
|----------|-------------|
| [architecture/SYSTEM-OVERVIEW.md](architecture/SYSTEM-OVERVIEW.md) | **Full system overview** — tech stack, diagrams, request lifecycle, security model |
| [architecture/FRONTEND.md](architecture/FRONTEND.md) | React component tree, hooks, state management, rendering pipeline |
| [architecture/BACKEND.md](architecture/BACKEND.md) | Flask server, 54 API endpoints, middleware, configuration |
| [architecture/MEMORY-SYSTEM.md](architecture/MEMORY-SYSTEM.md) | Four-tier memory: working, semantic, knowledge store, and user profile |
| [architecture/STORAGE-AND-ENCRYPTION.md](architecture/STORAGE-AND-ENCRYPTION.md) | Encryption, IPFS, autosave, IndexedDB, recovery |
| [architecture/INTELLIGENCE-AND-ROUTING.md](architecture/INTELLIGENCE-AND-ROUTING.md) | Agent pipeline, ReAct loop, 15 tools, decision-making |

### For Developers

| Document | Description |
|----------|-------------|
| [getting-started/developer-setup.md](getting-started/developer-setup.md) | Local development environment setup |
| [getting-started/common-tasks.md](getting-started/common-tasks.md) | Day-to-day development workflows |
| [backend/API.md](backend/API.md) | Backend API documentation |
| [backend/SERVICES.md](backend/SERVICES.md) | Backend service modules reference |
| [frontend/MODULES.md](frontend/MODULES.md) | Frontend module documentation |
| [handoffs/2026-02-16-security-and-ui-corrections.md](handoffs/2026-02-16-security-and-ui-corrections.md) | Security hardening + UI chat persistence fixes + validation results |

### For DevOps

| Document | Description |
|----------|-------------|
| [deployment/WORKFLOW.md](deployment/WORKFLOW.md) | Deployment procedures (Docker, Akash, ICP) |
| [reference/AKASH_CLI_REFERENCE.md](reference/AKASH_CLI_REFERENCE.md) | Akash CLI command reference |
| [getting-started/setup.md](getting-started/setup.md) | New machine setup (Akash wallet, dfx, Docker) |

### For Security Auditors

| Document | Description |
|----------|-------------|
| [security/SECURITY-AUDITOR-OVERVIEW.md](security/SECURITY-AUDITOR-OVERVIEW.md) | Security architecture, trust boundaries, crypto details |

### For AI Assistants

| Document | Description |
|----------|-------------|
| [ai-context/CLAUDE.md](ai-context/CLAUDE.md) | Concise AI context: key files, routes, config, deployment |
| [ai-context/CODEBASE-MAP.md](ai-context/CODEBASE-MAP.md) | File-level map with all routes and constants |
| [ai-context/FEATURE-CATALOG.md](ai-context/FEATURE-CATALOG.md) | Feature inventory with code locations |
| [ai-context/CONVENTIONS.md](ai-context/CONVENTIONS.md) | Machine-readable do/don't rules for AI coding sessions |

---

## Project Structure

```
Trinity/
├── backend/                         # Python Flask inference server
│   ├── inference_server.py          # App factory + blueprint registration
│   ├── routes/                      # 9 blueprints (54 endpoints)
│   ├── middleware/                   # Observability, rate limiting, caching
│   ├── services/                    # 42 service modules (pipeline, agent, memory, tools, etc.)
│   └── tests/                       # Unit, integration, and E2E tests
│
├── trinity-icp/                     # Frontend (ICP canister)
│   ├── src-react/                   # Active React 19 / TypeScript (v3.0.0)
│   └── src/                         # Legacy vanilla JS (v2.8.0, still buildable)
│
├── deploy/                          # Deployment configurations
│   ├── docker/                      # Dockerfile (CUDA + Ollama)
│   ├── akash/                       # SDL files for 3 tiers + specialty models
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
| [Rationale: Test Coverage](architecture/RATIONALE-TEST-COVERAGE.md) | Active | Risk-based coverage targets (P0: 90%, P1: 70%) |
| [Rationale: Prometheus](architecture/RATIONALE-PROMETHEUS.md) | Active | Self-hosted monitoring ($500+/mo savings) |
| [Rationale: Caching](architecture/RATIONALE-CACHING.md) | Active | LRU caches vs Redis for single-node deployment |

---

## Archive

Completed plans and historical documents:

| Document | Description |
|----------|-------------|
| [archive/INTELLIGENCE-OVERHAUL.md](archive/TEAM-A-ANALYSIS.md) | Backend overhaul research (completed Feb 2026) |
| [archive/FRONTEND-OVERHAUL.md](archive/TEAM-B-ANALYSIS.md) | Frontend overhaul research (completed Feb 2026) |
| [plans/TRINITY-MONETIZATION-PLAN.md](plans/TRINITY-MONETIZATION-PLAN.md) | Product/monetization strategy |
| [archive/TRINITY-B2B-PIVOT.md](archive/TRINITY-B2B-PIVOT.md) | Superseded B2B pivot strategy |
| [archive/TEAM-A-ANALYSIS.md](archive/TEAM-A-ANALYSIS.md) | Intelligence upgrade research (Team A) |
| [archive/TEAM-B-ANALYSIS.md](archive/TEAM-B-ANALYSIS.md) | Intelligence upgrade research (Team B) |
