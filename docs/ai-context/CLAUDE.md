# Trinity Codebase Reference

> **Purpose:** Comprehensive documentation for AI assistants to quickly understand the Trinity project
> **Last Updated:** February 13, 2026
> **Last Verified:** February 13, 2026
> **Status:** Production - V5.0 (ReAct + Memory Tools + MCP + Qwen3 Migration)
> **Version:** v5.0.0 (Qwen2.5 14B on RTX 3090, DSEQ 25505658)
>
> **See also:** [CODEBASE-MAP.md](CODEBASE-MAP.md) — Quick-reference map of all files, routes, and constants

---

## 🐛 Known Issues

| Issue | Status | Details |
|-------|--------|---------|
| **Timestamp Auth** | ⚠️ Mismatch | `icp_auth.py` enforces 60s; `config.py` defines 5min (`AUTH_TIMESTAMP_WINDOW_MS`) but constant is **unused** |
| **database.py** | 🔵 Orphaned | 298-line ORM exists but not imported by any production code, not in Dockerfile |

### ✅ Recently Fixed (Feb 5, 2026)
- **Stop Button** - `resetInput()` was disabling button immediately after `setGenerating()` enabled it
- **Copy Button** - ICP blocks Clipboard API; added `execCommand('copy')` fallback
- **Edit Button** - `showChatArea()` wasn't called when editing resulted in empty history
- **Edit Buttons on Saved Chats** - Added loop in `loadChat()` to add edit buttons after rendering
- **Chat Loading Double-Click** - Added `isLoadingChat` state guard + Zustand proxies
- **Export Double-Click** - Added `_isExporting` flag guard on export button
- **Model Badge Hover** - Added CSS with purple border animation

### ✅ Recently Fixed (Feb 6, 2026)
- **DEPLOYMENT_TIER=KING crash** - `int()` failed on non-numeric tier; added try/except in `akash.py`

### ✅ Recently Fixed (Feb 12-13, 2026) — Post-Opus Incident Recovery

**Opus Session Incident (6 features, 4-part failure chain):**
A prior Claude Opus session implemented ReAct loops, native tool calling, MemGPT memory tools, MCP server/client, and Qwen3 migration — but left `/generate` completely broken. See `docs/HANDOFF-INCIDENT-REPORT.md` for full forensics.

**Backend fixes applied (by prior recovery session):**
- **Think-block fallback** — `_get_response_content()` in `react_loop.py` now extracts answer from `<think>` blocks when stripping produces empty content
- **Tool detection tightened** — `detect_tools_needed()` patterns in `tools.py` now require context anchoring (e.g. `"current price|news|weather"` instead of `"current|today|now"`)
- **Context key mismatch** — `routes/generate.py` now reads `context_messages` with `contextMemory` fallback (4 locations)
- **REACT_NATIVE_TOOLS default** — Changed from `"auto"` to `"never"` in `config.py` (Qwen3 native tools + thinking = empty responses)
- **Dead code cleanup** — Deleted `model_router.py`, removed 11 stale tests
- **Admin auth tests** — Added `mock_admin_auth` fixture to 7 admin endpoint tests

**Frontend fixes applied (this session):**
- **Invisible code blocks (root cause 1)** — `preprocessToolCalls()` in `messages.js` stripped `<tool_call name="code_display">` with `<execute>true</execute>` to empty string. Fixed: always convert to fenced code blocks regardless of execute flag
- **Invisible code blocks (root cause 2)** — `generate.js` imported `parseMarkdownWithMath` from `editMessage.js` (which had a DUPLICATE unfixed `preprocessToolCalls`), not from `messages.js`. Fixed: synced the editMessage.js copy
- **Greedy orphaned tag regex** — `/<tool_call...>[\s\S]*$/` ate ALL text after any orphaned tool_call tag (e.g. malformed `<tool_call name="web_search"><query>...</query><tool_call>`). Fixed: surgical stripping of just the tag + XML children, plus cleanup of bare remnant tags
- **Anti-XML prompt instructions** — Added "NEVER use `<tool_call>` or `<code_display>` XML" to `EXECUTE_PROMPT_WITH_PLAN`, `EXECUTE_PROMPT_SIMPLE`, and `REACT_SYSTEM_PROMPT` in `agent_prompts.py`
- **Tool detection guard** — `detect_tools_needed()` code patterns gated behind `CODE_EXECUTION_ENABLED` flag in `tools.py`

**Deployment:**
- Docker image rebuilt and pushed (`gdubx/trinity-inference:latest`)
- Akash deployment: DSEQ `25505658`, provider `akash175llqyjvxfle9qwt740vm46772dzaznpzgm576`, RTX 3090 24GB
- Cloudflare Worker AKASH_URL secret updated
- ICP frontend canister redeployed (3 rebuilds for incremental fixes)
- `update_deployment.py` DSEQ updated to `25505658`

**Verification:**
- IQ stress tests v3: **8/8 PASS**, 0 think-block leaks, 58s total
- Local test suite: **709 passed**, 9 skipped, 91.30% coverage
- Production health: `qwen2.5:14b`, Ollama connected, RTX 3090

---

## 🚨 Deployment Workflow Rules

**CRITICAL: Changes require Docker rebuild to take effect on Akash**

### The Deployment Chain
```
Local Code Change → Docker Build → Docker Push → Akash Redeploy → Live
```

### ❌ Common Mistakes
| Mistake | Consequence | Prevention |
|---------|-------------|------------|
| Edit Python, don't rebuild Docker | Akash runs OLD code | Always rebuild after Python changes |
| Edit YAML env vars, don't test locally | Crash on deploy (wastes GPU hours) | Test with `docker run` first |
| Create new YAML without testing | `ValueError`, `ImportError`, etc. | Validate env vars match code expectations |
| Multiple Akash deploys simultaneously | Resource waste during model downloads | Deploy ONE, verify, then next |

### ✅ Safe Deployment Workflow
1. **Make code change** (Python, config, etc.)
2. **Test locally**: `python -c "from services.akash import *"` 
3. **Docker build**: `cd deploy/docker && ./build.sh`
4. **Docker push**: `docker push gdubx/trinity-inference:TAG`
5. **Deploy ONE instance** to Akash
6. **Verify logs** show server started successfully
7. **Test endpoint**: `curl $URL/health`
8. **Then** deploy additional instances if needed
9. **Update knowledge base**: If structural changes were made, run the 📚 KNOWLEDGE BASE Workflow Checklist

### YAML Environment Variable Rules
- **DEPLOYMENT_TIER**: Must be numeric (1, 2, 3) OR code must handle strings
- **All env vars**: Must have defaults in Python OR be guaranteed in YAML
- **Test new YAMLs**: Run `docker run -e VAR=VALUE ...` locally first

---

## ⚡ Quick Reference

| Component | Value |
|-----------|-------|
| **ICP Frontend Canister** | `zc67k-kiaaa-aaaal-qtmiq-cai` |
| **ICP Backend Canister** | `au5zq-2qaaa-aaaal-qtowa-cai` |
| **Primary URL** | https://dubya.ai |
| **Canister URL** | https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io |
| **Cloudflare Worker** | https://api.dubya.ai |
| **Docker Image** | `gdubx/trinity-inference:latest` |
| **Akash Wallet** | `akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp` |

---

## 🚀 Deployment (Single Command)

```bash
./scripts/trinity-deploy-production.sh [tier]

# Examples:
./scripts/trinity-deploy-production.sh      # Interactive tier selection
./scripts/trinity-deploy-production.sh 2    # Qwen2.5 14B (~$50/mo)
./scripts/trinity-deploy-production.sh 3    # Qwen3 32B (~$200/mo)
```

**⚠️ IMPORTANT FOR AI ASSISTANTS:**
- **DO NOT run the deployment script and then run other commands** - this will interrupt/cancel the deployment
- If the user says they are running the deployment, **wait for them to report the result**
- The deployment script takes 5-10 minutes to complete - do not run `sleep` or other commands that would interrupt it
- Only check terminal output if the user asks or reports an issue

**🔒 SECURITY RULES:**
- **NEVER put API keys in YAML files** - This is a security violation
- API keys are stored in `.env` file (gitignored) and injected at deployment time
- The deployment script reads from `.env` and passes to Docker/Akash securely
- If YAML needs env vars, use empty values: `- LIGHTHOUSE_API_KEY=` (set at runtime)

**The script handles EVERYTHING:**
1. Prerequisites check (Docker, provider-services CLI, wallet)
2. Local validation (Python syntax, Docker build)
3. Docker push to Docker Hub
4. Akash deployment via CLI (closes old deployments, creates new)
5. **SSL auto-detection** (checks if provider has valid SSL, uses HTTP if not)
6. **Funding prompt** (asks how much AKT to deposit after deploy)
7. Cloudflare Worker URL update (with correct HTTP/HTTPS scheme)
8. ICP frontend canister deployment
9. Production verification (/health, /generate tests)

**🔧 Deployment Script Features:**
- **Bad Provider Skip List**: Providers with DNS/connectivity issues in `scripts/akash_deploy.py`
- **SSL Auto-Detection**: `check_ssl_valid()` function tests HTTPS before using it
- **Timeout Tiers**: Tier 1 (3min), Tier 2 (7min), Tier 3 (20min) for provider bids
- **Akash YAML Timeout Limit**: Max 60000ms (60s) for `read_timeout`/`send_timeout`

---

## 📁 Project Structure

```
Trinity/
├── icp-deploy                   # → ICP canister deployment
├── README.md                    # Project overview
│
├── backend/                     # 🖥️ FLASK BACKEND
│   ├── inference_server.py      # Main server (endpoints, Flask app)
│   ├── icp_auth.py              # Ed25519 signature verification
│   ├── config.py                # Environment configuration
│   ├── encryption.py            # AES-256-GCM encryption
│   ├── storage.py               # File storage operations
│   ├── lighthouse.py            # IPFS/Filecoin uploads
│   ├── validation.py            # Input validation
│   ├── requirements.txt         # Python dependencies
│   ├── middleware/              # Request middleware
│   │   ├── __init__.py
│   │   ├── rate_limit.py        # Rate limiting
│   │   ├── icp_cache.py         # ICP caching
│   │   ├── observability.py     # Prometheus metrics (RED method) + legacy compat
│   │   └── ab_test.py           # A/B testing middleware
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── prompts.py           # System prompts
│   │   ├── akash.py             # Akash blockchain API
│   │   ├── ollama.py            # Ollama API client
│   │   ├── agent.py             # Legacy agentic pipeline (80% traffic)
│   │   ├── agent_prompts.py     # Multi-pass prompts + XML parsing
│   │   ├── complexity.py        # Question complexity classifier (0-10 scoring)
│   │   ├── search.py            # Brave web search integration
│   │   ├── loading_messages.py  # Whimsical loading phrases
│   │   ├── experiments.py       # A/B experiment framework (hash-based)
│   │   ├── caching.py           # Embedding + semantic response caching
│   │   ├── parallel.py          # Parallel pipeline execution
│   │   ├── embeddings.py        # V4: FastEmbed text embeddings
│   │   ├── vector_store.py      # V4: Per-user SQLite vector DB
│   │   ├── memory.py            # V4: Semantic memory retrieval
│   │   ├── tools.py             # V4: Tool registry and parser
│   │   ├── code_executor.py     # V4: Tool execution dispatcher
│   │   ├── react_loop.py        # V5: ReAct agentic loop (think/act/observe)
│   │   ├── memory_tools.py      # V5: MemGPT save/recall/search with embeddings
│   │   ├── mcp_server.py        # V5: MCP JSON-RPC 2.0 handler + stdio server
│   │   ├── mcp_client.py        # V5: External MCP server connector
│   │   ├── fact_check.py        # V5: Dual web-search fact verification
│   │   ├── voting.py            # V4: Self-consistency voting (experimental)
│   │   ├── structured.py        # V4: JSON schema enforcement (experimental)
│   │   └── graph/               # LangGraph multi-agent system (20% traffic)
│   │       ├── __init__.py
│   │       ├── state.py          # AgentState TypedDict
│   │       ├── llm.py            # LangChain Ollama wrapper
│   │       ├── agents.py         # Specialized agents (Supervisor, Research, etc.)
│   │       ├── nodes.py          # Graph node implementations
│   │       ├── edges.py          # Conditional routing logic
│   │       └── graph.py          # StateGraph assembly
│   ├── routes/                  # Route blueprints (50+ routes across 8 blueprints)
│   │   ├── __init__.py          # ALL_BLUEPRINTS list
│   │   ├── shared.py            # Shared route helpers
│   │   ├── health.py            # /health, /metrics, /stats (4 routes)
│   │   ├── admin.py             # /admin/* experiments & cache (8 routes)
│   │   ├── generate.py          # /generate, /generate/stream, /generate/agent (6 routes)
│   │   ├── chat.py              # /chat/*, /user/* CRUD + memory (14 routes)
│   │   ├── tools.py             # /tools/* search, browse, documents (7 routes)
│   │   ├── v4.py                # /v4/* vector store, tool execution (6 routes)
│   │   ├── mcp.py               # V5: /mcp endpoint (MCP JSON-RPC)
│   │   └── session.py           # /session/*, /funding/* (4 routes)
│   ├── mcp_stdio_server.py      # V5: MCP stdio entry point (Claude Desktop)
│   ├── database.py              # SQLAlchemy ORM (NOT integrated — future feature)
│   ├── eval/                    # Benchmarking & IQ tests
│   │   ├── benchmark_legacy_vs_langgraph.py  # Pipeline comparison
│   │   ├── run_iq_tests_v3.sh   # 8-test IQ stress suite
│   │   └── BENCHMARK_GUIDE.md   # Benchmark documentation
│   ├── tests/                   # Test suite (709 tests, 91.30% coverage)
│   │   ├── conftest.py          # Shared fixtures
│   │   ├── fixtures/
│   │   │   └── auth_fixtures.py # Ed25519 test keypairs
│   │   ├── e2e/
│   │   │   └── test_full_pipeline.py
│   │   ├── integration/
│   │   │   └── test_inference.py # Integration tests
│   │   └── unit/                # 17+ unit test files
│   │       ├── test_phase1_security.py, test_phase2_stability.py
│   │       ├── test_phase3_architecture.py, test_phase4_quality.py
│   │       ├── test_caching.py, test_complexity.py, test_encryption.py
│   │       ├── test_experiments.py, test_icp_auth.py, test_langgraph.py
│   │       ├── test_langgraph_endpoint.py, test_observability.py
│   │       ├── test_storage.py, test_validation.py
│   │       ├── test_mcp.py, test_memory_tools.py
│   │       ├── test_react_loop.py, test_tools_real.py
│
├── deploy/                      # 🚀 DEPLOYMENT CONFIGS
│   ├── akash/                   # Akash SDL manifests
│   │   ├── deploy-tier1-basic.yaml      # Qwen3 1.7B
│   │   ├── deploy-tier2-balanced.yaml   # Qwen2.5 14B
│   │   └── deploy-tier3-complex.yaml    # Qwen3 32B
│   ├── docker/                  # Docker build files
│   │   ├── Dockerfile           # Container definition
│   │   ├── build.sh             # Build script
│   │   └── startup.sh           # Container entrypoint
│   └── cloudflare-worker/       # SSL termination proxy
│       ├── worker.js            # Cloudflare Worker proxy
│       ├── wrangler.toml        # Wrangler config
│       └── package.json         # Dependencies
│
├── scripts/                     # 📜 AUTOMATION SCRIPTS
│   ├── trinity-deploy-production.sh  # ⭐ MAIN DEPLOYMENT SCRIPT
│   ├── akash_deploy.py          # Akash CLI helper (Python)
│   ├── switch-provider.sh       # Update Cloudflare Worker URL
│   └── docker-cleanup.sh        # Clean Docker cache
│
├── trinity-icp/                 # 🎨 FRONTEND (ICP)
│   ├── dfx.json                 # ICP canister config
│   ├── canister_ids.json        # Production canister IDs
│   ├── package.json             # npm dependencies
│   ├── vite.config.js           # Vite bundler config
│   └── src/                     # Source code
│       ├── app.js               # Application orchestrator (266 lines)
│       ├── config.js            # Environment config
│       ├── index.html           # HTML template
│       ├── styles.css           # CSS styling
│       ├── tools.js             # Tools dropdown
│       ├── core/                # 🆕 Infrastructure modules
│       │   ├── api.js           # HTTP client, signed requests, streaming
│       │   ├── environment.js   # Endpoint detection, version check
│       │   └── logger.js        # Structured logging utility
│       ├── features/            # 🆕 Feature modules (extracted from app.js)
│       │   ├── auth.js          # Login/logout UI flow
│       │   ├── generate.js      # Message send, streaming, stop button
│       │   ├── chatManagement.js # Load/delete/new chat, sidebar
│       │   └── memory.js        # User memory CRUD modal
│       ├── api/
│       │   └── canister-client.js  # ICP backend client
│       ├── auth/
│       │   ├── authManager.js   # Ed25519 keypair management
│       │   ├── keyExportModal.js # Key display modal
│       │   ├── auth-entry.js    # Auth entry point
│       │   └── icp-auth.js      # ICP auth library (bundled, don't edit)
│       ├── state/
│       │   ├── store.js         # Zustand state management
│       │   └── contextMemory.js # Conversation compression
│       ├── storage/
│       │   ├── autosave.js      # Debounced persistence
│       │   ├── lighthouse.js    # Filecoin/IPFS uploads
│       │   └── indexedDB.js     # Local-first storage
│       ├── ui/
│       │   ├── index.js         # UI module aggregator
│       │   ├── domCache.js      # DOM element caching
│       │   ├── messages.js      # Message rendering
│       │   ├── sidebar.js       # Chat list
│       │   ├── modals.js        # Dialog boxes
│       │   ├── notifications.js # Toast notifications
│       │   ├── editMessage.js   # 🆕 Inline message editing
│       │   ├── rainbowBorder.js # Rainbow effects
│       │   └── loadingMessages.js # Whimsical loading phrases
│       ├── utils/
│       │   ├── validation.js    # Input validation
│       │   ├── crypto.js        # AES-GCM encryption
│       │   └── math.js          # KaTeX rendering
│       └── backend_canister/    # ICP Backend (Rust)
│           ├── src/lib.rs       # HTTPS Outcalls canister
│           ├── Cargo.toml       # Rust dependencies
│           └── trinity_backend.did  # Candid interface
│
└── docs/                        # 📚 DOCUMENTATION
    ├── README.md                # Documentation index
    ├── ai-context/              # AI/LLM reference
    │   ├── CLAUDE.md            # This file (comprehensive AI reference)
    │   ├── CODEBASE-MAP.md      # 🆕 Quick-reference map (all files, routes, constants)
    │   └── FEATURE_CATALOG.md   # Complete feature inventory
    ├── backend/                 # Backend documentation
    │   ├── API.md               # All 49 API endpoints
    │   └── SERVICES.md          # Backend services docs
    ├── frontend/
    │   └── MODULES.md           # Frontend module documentation
    ├── deployment/
    │   └── WORKFLOW.md          # Deployment procedures
    ├── architecture/
    │   ├── trinity-storage-architecture.md
    │   └── decisions/           # 5 Architecture Decision Records
    ├── getting-started/         # Developer guides
    │   ├── developer-setup.md
    │   ├── common-tasks.md
    │   └── setup.md
    ├── security/                # Security documentation
    │   ├── SECURITY-AUDITOR-OVERVIEW.md
    │   └── security-audit.md
    ├── reference/
    │   └── AKASH_CLI_REFERENCE.md
    └── plans/                   # Implementation plans
        ├── CRITICAL-FIXES-ROADMAP.md
        ├── TRINITY-MONETIZATION-PLAN.md  # Definitive product plan (renamed)
        └── cost-analysis-research.md
```

---

## 🧠 Agentic Pipeline (v3.6.0)

Trinity uses a multi-pass reasoning pipeline that routes questions by complexity:

### Complexity Routing
| Complexity | Passes | Pipeline |
|------------|--------|----------|
| **Simple** | 1 | Direct answer |
| **Medium** | 3 | Understand → Execute → Critique |
| **Complex** | 5 | Understand → Plan → Execute → Critique → Refine |

### Automatic Detection
- **Complexity**: Word count, question marks, technical terms
- **Web Search**: Keywords like "current", "today", "price", "bitcoin", "latest"

### Pass Timeouts
| Pass | Timeout | Token Limit |
|------|---------|-------------|
| Understand | 120s | 1000 |
| Plan | 120s | 1000 |
| Execute | 300s (5 min) | 4000 |
| Critique | 120s | 1000 |
| Refine | 300s (5 min) | 4000 |
| Search | 30s | N/A |

### Data Persistence
| Data | Saved | Where |
|------|-------|-------|
| User messages | ✅ | Encrypted autosave |
| Final AI answer | ✅ | Encrypted autosave |
| Understanding | ❌ | Ephemeral (internal) |
| Planning | ❌ | Ephemeral (internal) |
| Critique | ❌ | Ephemeral (internal) |
| Search results | ❌ | Ephemeral (in prompt) |
| Phase messages | ❌ | UI only |

### Key Files
- `backend/services/agent.py` - Pipeline orchestrator
- `backend/services/agent_prompts.py` - Pass prompts + XML parsing
- `backend/services/complexity.py` - Question classifier
- `backend/services/search.py` - Brave web search
- `backend/services/loading_messages.py` - Whimsical phrases
- `trinity-icp/src/app.js` - `generateAgent()` function

### Tier Requirements
| Tier | Model | Agentic Support |
|------|-------|-----------------|
| 1 | TinyLlama 1.1B | ❌ Too small for XML parsing |
| 2 | Llama 8B | ✅ Works well |
| 3 | Qwen 32B | ✅ Best results |

---

## 🔬 LangGraph Multi-Agent System (Phase 3)

Trinity implements a production-ready LangGraph-based multi-agent orchestration system for complex queries.

### Architecture

```
User Query
    ↓
┌────────────────────────────────────────────────────────────┐
│                  COMPLEXITY ROUTER                          │
│  ┌──────────────┐    ┌──────────────┐   ┌──────────────┐  │
│  │   Simple     │    │   Medium     │   │   Complex    │  │
│  │  (Direct)    │    │ (3 passes)   │   │ (LangGraph)  │  │
│  └──────────────┘    └──────────────┘   └──────────────┘  │
└────────────────────────────────────────────────────────────┘
         │                    │                   │
         ↓                    ↓                   ↓
    ┌─────────┐        ┌─────────────┐     ┌─────────────┐
    │ Ollama  │        │  Agentic    │     │  LangGraph  │
    │ Direct  │        │  Pipeline   │     │  Workflow   │
    └─────────┘        └─────────────┘     └─────────────┘
                                                  │
                            ┌─────────────────────┼─────────────────────┐
                            ↓                     ↓                     ↓
                      ┌──────────┐          ┌──────────┐          ┌──────────┐
                      │ Planner  │          │ Executor │          │ Reviewer │
                      │  Agent   │          │  Agent   │          │  Agent   │
                      └──────────┘          └──────────┘          └──────────┘
```

### Complexity Classification
| Score | Classification | Pipeline | Traffic % |
|-------|---------------|----------|-----------|
| 0-3 | Simple | Direct Ollama | ~70% |
| 4-6 | Medium | Agentic (3-pass) | ~20% |
| 7-10 | Complex | LangGraph | ~10% |

### Key Files
| File | Purpose |
|------|---------|
| `backend/services/complexity.py` | Query complexity classification (0-10 score) |
| `backend/tests/unit/test_langgraph.py` | LangGraph workflow unit tests |
| `backend/tests/unit/test_langgraph_endpoint.py` | LangGraph endpoint integration tests |

### Experiment Flag
LangGraph routing is gated by the `langgraph_routing` experiment (see Experimentation Framework below). When enabled, complex queries are routed to the multi-agent workflow.

---

## 🧪 Experimentation Framework (Phase 4A)

A comprehensive A/B testing system for controlled feature rollouts.

### Experiment Configuration
```python
EXPERIMENTS = {
    'langgraph_routing': {
        'name': 'LangGraph Multi-Agent Routing',
        'enabled': True,
        'percentage': 20,  # 20% of complex queries
        'description': 'Route complex queries to LangGraph workflow'
    },
    'agent_mode': {
        'name': 'Agentic Processing Mode',
        'enabled': True,
        'percentage': 100,  # Fully rolled out
        'description': 'Use multi-pass agentic pipeline'
    }
}
```

### Hash-Based Assignment
Users are deterministically assigned to experiments using a hash of their session ID:
```python
def get_experiment_assignment(session_id: str, experiment_name: str) -> bool:
    hash_value = int(hashlib.sha256(f"{session_id}:{experiment_name}".encode()).hexdigest(), 16)
    return (hash_value % 100) < EXPERIMENTS[experiment_name]['percentage']
```

### Admin Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/experiments` | GET | List all experiments |
| `/admin/experiments/assignment/<session_id>` | GET | Get user's assignments |
| `/admin/experiments/<name>/enable` | POST | Enable experiment |
| `/admin/experiments/<name>/disable` | POST | Disable experiment |

### Key Files
| File | Purpose |
|------|---------|
| `backend/tests/unit/test_experiments.py` | 44 experiment tests |
| `docs/decisions/004-hash-based-experiments.md` | ADR for experiment design |

---

## 💾 Cost Optimization & Caching (Phase 4B)

Production-grade caching layer for reducing LLM API costs.

### Caching Architecture

```
User Query
    ↓
┌────────────────────────────────────────────────────────────┐
│                    CACHING LAYER                            │
│  ┌──────────────────┐    ┌──────────────────┐             │
│  │  Embedding Cache │    │  Semantic Cache  │             │
│  │    (LRU 1000)    │    │   (LRU 500)      │             │
│  │  Hash → Vector   │    │  Vector → Resp   │             │
│  └──────────────────┘    └──────────────────┘             │
│            │                      │                        │
│            ↓                      ↓                        │
│  ┌──────────────────────────────────────────────┐         │
│  │              Token Tracker                    │         │
│  │   • Per-user token counts (1hr window)       │         │
│  │   • Quota enforcement (10k tokens/hr)        │         │
│  │   • Usage metrics for billing                │         │
│  └──────────────────────────────────────────────┘         │
└────────────────────────────────────────────────────────────┘
```

### Cache Types
| Cache | Size | Key | Value | TTL |
|-------|------|-----|-------|-----|
| **EmbeddingCache** | 1000 | Text hash | Embedding vector | None (LRU eviction) |
| **SemanticResponseCache** | 500 | Query embedding | Full response | None (LRU eviction) |
| **TokenTracker** | Unbounded | Principal ID | Token counts | 1 hour rolling window |

### Cache Performance
- **Embedding Cache Hit Rate**: ~60-80% for repeat queries
- **Semantic Cache Hit Rate**: ~20-40% for similar queries (cosine > 0.95)
- **Token Savings**: Estimated 40-60% reduction in LLM calls for active users

### Admin Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/cache/stats` | GET | Cache hit/miss statistics |
| `/admin/cache/clear` | POST | Clear all caches |
| `/admin/tokens/usage` | GET | Token usage by user |
| `/admin/quota/usage` | GET | Quota status per user |

### Key Files
| File | Purpose |
|------|---------|
| `backend/tests/unit/test_caching.py` | 37 caching tests |
| `docs/decisions/005-in-memory-caching.md` | ADR for caching design |

---

## 🧪 Testing Infrastructure

Trinity maintains comprehensive test coverage using pytest.

### Test Summary
| Category | Tests | Coverage |
|----------|-------|----------|
| **Phase 1: Security** | 19 | 90%+ |
| **Phase 2: Stability** | 27 | 90%+ |
| **Phase 3: Architecture** | 34 | 85%+ |
| **Phase 4: Quality** | 43 | 90%+ |
| **Security & Auth** | 57 | 90%+ |
| **LangGraph** | 38 | 85%+ |
| **Observability** | 20+ | 80%+ |
| **Experiments** | 20+ | 95%+ |
| **Caching** | 38 | 90%+ |
| **Encryption** | 35 | 95%+ |
| **Validation** | 20+ | 95%+ |
| **Complexity** | 46 | 90%+ |
| **Storage** | 22 | 85%+ |
| **E2E Pipeline** | 23 | N/A |
| **Integration** | 11 | N/A |
| **ReAct Loop** | 22 | 90%+ |
| **Memory Tools** | 28 | 90%+ |
| **MCP Server/Client** | 25 | 85%+ |
| **Tools (Real)** | 18 | 85%+ |
| **Total** | **709** | **91.30%** |

### Running Tests
```bash
# Full test suite
cd backend && pytest tests/ --no-cov -q

# Specific test file
pytest tests/unit/test_caching.py -v

# With coverage report
pytest tests/ --cov=. --cov-report=html

# E2E tests only
pytest tests/e2e/ -v
```

### Test Organization
```
backend/tests/
├── e2e/
│   └── test_full_pipeline.py    # End-to-end HTTP tests
├── integration/
│   └── test_inference.py        # Integration tests
├── unit/
│   ├── test_phase1_security.py  # Phase 1 security tests
│   ├── test_phase2_stability.py # Phase 2 stability tests
│   ├── test_phase3_architecture.py # Phase 3 architecture tests
│   ├── test_phase4_quality.py   # Phase 4 quality tests
│   ├── test_caching.py          # Cache layer tests
│   ├── test_complexity.py       # Complexity classifier
│   ├── test_encryption.py       # AES-GCM encryption
│   ├── test_experiments.py      # A/B testing framework
│   ├── test_icp_auth.py         # Ed25519 auth tests
│   ├── test_langgraph.py        # LangGraph workflow tests
│   ├── test_langgraph_endpoint.py # LangGraph API tests
│   ├── test_observability.py    # Prometheus metrics
│   ├── test_storage.py          # File storage tests
│   └── test_validation.py       # Input validation
├── conftest.py                  # Shared fixtures
└── pytest.ini                   # Pytest configuration
```

### Coverage Tiers
| Tier | Target | Modules |
|------|--------|---------|
| **Critical** | 90%+ | Auth, Encryption, Validation |
| **High** | 80%+ | Storage, Caching, Complexity |
| **Medium** | 60%+ | LangGraph, Experiments |
| **Overall** | 91.30% | All modules |

See `docs/decisions/002-tiered-test-coverage.md` for rationale.

---

## 🧹 Phase 5.5: Code Cleanup & Analysis (February 2026)

Production-readiness overhaul across three sub-phases.

### Phase 5.5A: Prometheus-Only Metrics Migration
- **Deleted** `services/metrics.py` (legacy duplicate metrics system)
- **Removed** duplicate observability fallbacks from `agent.py` and `graph/nodes.py`
- **Migrated** all 21 `metrics.*` calls in `inference_server.py` to `middleware/observability.py`
- **Added** legacy compatibility functions (`start_request`, `end_request`, `record_request`, `get_prometheus_summary`, `get_system_info`) to observability module
- **Updated** `/health` and `/stats` endpoints to use Prometheus metrics
- Single source of truth: `middleware/observability.py` (Prometheus)
- See `docs/plans/PHASE-5.5A-CRITICAL-METRICS-MIGRATION.md` for full migration details

### Phase 5.5B: Automated Code Cleanup
- Applied `black` formatter across 52 Python files (100-char line length)
- Applied `isort` for consistent import ordering (stdlib → third-party → local)
- Applied `autoflake` to remove unused imports
- No functional changes — formatting only
- All 607+ tests passing after cleanup

### Phase 5.5C: Legacy vs LangGraph Benchmark Suite
- Created `backend/eval/benchmark_legacy_vs_langgraph.py`
- 300 test queries (100 simple, 100 medium, 100 complex)
- Compares both pipelines on P50/P95/P99 latency, success rate, token usage
- Decision framework: when to keep 80/20 split vs adjust routing
- See `backend/eval/BENCHMARK_GUIDE.md` for usage and interpretation

---

## 🚀 V5.0: ReAct + Memory Tools + MCP (February 2026)

Major feature session implementing six capabilities, followed by incident recovery and frontend fixes.

### New Capabilities

| Feature | File(s) | Status |
|---------|---------|--------|
| **ReAct Agentic Loop** | `services/react_loop.py` (465 lines) | Active (iterative think/act/observe tool calling) |
| **MemGPT Memory Tools** | `services/memory_tools.py` (244 lines) | Active (save/recall/search user facts with embeddings + dedup) |
| **MCP Server** | `services/mcp_server.py` (207 lines), `routes/mcp.py` | Active (JSON-RPC 2.0 + stdio, exposes 8 tools) |
| **MCP Client** | `services/mcp_client.py` (281 lines) | Disabled by default (`MCP_CLIENT_ENABLED=false`) |
| **Fact Checking** | `services/fact_check.py` (80 lines) | Active (dual web-search verification) |
| **Native Ollama Tools** | `services/tools.py` (native calling functions) | Disabled (`REACT_NATIVE_TOOLS="never"`) |

### New Config Variables (all in `backend/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `REACT_ENABLED` | `true` | Enable the ReAct agentic loop |
| `REACT_MAX_ITERATIONS` | `5` | Max tool-calling rounds before forced answer |
| `REACT_NATIVE_TOOLS` | `"never"` | Native tool mode: `never`/`auto`/`always` |
| `QWEN3_THINKING_MODE` | `"auto"` | Thinking: `auto`/`always`/`never` |
| `QWEN3_THINKING_BUDGET` | `4096` | Max tokens for internal reasoning |
| `MEMORY_TOOLS_ENABLED` | `true` | Enable save/recall/search memory tools |
| `MCP_SERVER_ENABLED` | `true` | Expose Trinity tools via MCP |
| `MCP_CLIENT_ENABLED` | `false` | Connect to external MCP servers |
| `CODE_EXECUTION_ENABLED` | `false` | Enable code execution tool |

### Frontend Display Pipeline (Critical Path)

The code display pipeline has been a source of bugs. Key files and their roles:

| File | Function | Used By |
|------|----------|---------|
| `ui/messages.js` | `preprocessToolCalls()` + `parseMarkdownWithMath()` | `showMessage()` (chat history rendering) |
| `ui/editMessage.js` | `preprocessToolCalls()` + `parseMarkdownWithMath()` (DUPLICATE) | `generate.js` (live streaming) |
| `features/generate.js` | Streaming renderer (stable/stream/tail DOM split) | All live AI responses |

**WARNING:** `generate.js` imports `parseMarkdownWithMath` from `editMessage.js`, NOT `messages.js`. Any fix to `preprocessToolCalls` must be applied to BOTH files.

### Incident Report Reference

See `docs/HANDOFF-INCIDENT-REPORT.md` for the full 4-part failure chain from the Opus session and all fixes applied.

---

## 🧠 V4.0 Intelligence Upgrade (January 2026)

A comprehensive intelligence enhancement adding semantic memory, tool use, multi-model routing, self-consistency voting, and structured outputs.

### Overview

V4.0 transforms Trinity from a simple prompt-response system into an intelligent agent with:
1. **Semantic Memory**: Retrieves relevant past conversations using embeddings
2. **Multi-Model Routing**: Uses different models for different task complexities
3. **Tool Use**: Calculator, code execution, web search with structured calls
4. **Self-Consistency Voting**: Multiple samples + majority vote for complex queries
5. **Structured Output**: JSON schema enforcement for reliable parsing

### Architecture Diagram

```
User Query
    ↓
┌─────────────────────────────────────────────────────────────┐
│                    INFERENCE SERVER                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │  Complexity  │───→│ Multi-Model  │───→│   Response   │   │
│  │  Classifier  │    │   Router     │    │   Pipeline   │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│         │                   │                    │           │
│         ↓                   ↓                    ↓           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Semantic   │    │    Tools     │    │   Voting     │   │
│  │   Memory     │    │  Executor    │    │   Engine     │   │
│  │  (FastEmbed) │    │ (Restricted) │    │ (3 samples)  │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│         │                   │                    │           │
│         ↓                   ↓                    ↓           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Vector Store │    │  Structured  │    │   Output     │   │
│  │  (per-user)  │    │   Output     │    │  Formatter   │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### New Files Created (v4.0)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `backend/services/embeddings.py` | FastEmbed wrapper for text embeddings | `embed_text()`, `embed_batch()`, `cosine_similarity()`, `V4_EMBEDDINGS_AVAILABLE` |
| `backend/services/vector_store.py` | SQLite-based per-user vector database | `VectorStore`, `get_user_vector_store()`, `V4_VECTOR_STORE_AVAILABLE` |
| `backend/services/memory.py` | Semantic memory retrieval system | `SemanticMemory`, `build_enhanced_context()`, `V4_MEMORY_AVAILABLE` |
| `backend/services/tools.py` | Tool registry and parser | `parse_tool_calls()`, `detect_tools_needed()`, `get_tool_definitions_for_prompt()`, `V4_TOOLS_AVAILABLE` |
| `backend/services/code_executor.py` | RestrictedPython sandbox | `execute_tool()`, `evaluate_math_expression()`, `execute_python_code()`, `V4_CODE_EXECUTOR_AVAILABLE` |
| `backend/services/voting.py` | Self-consistency voting pipeline | `run_voting_pipeline()`, `should_use_voting()`, `V4_VOTING_AVAILABLE` |
| `backend/services/structured.py` | JSON schema enforcement | `generate_structured()`, `SCHEMAS`, `V4_STRUCTURED_AVAILABLE` |

### Configuration (config.py)

```python
# Multi-Model Architecture
MULTI_MODEL_ENABLED = os.getenv('MULTI_MODEL_ENABLED', 'false').lower() == 'true'
FAST_MODEL = os.getenv('FAST_MODEL', 'phi3:mini')           # Classification/routing
SMART_MODEL = os.getenv('SMART_MODEL', 'llama3.1:8b')       # General tasks
REASONING_MODEL = os.getenv('REASONING_MODEL', 'qwen2.5:32b')  # Complex reasoning

# Embeddings (FastEmbed)
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-small-en-v1.5')
EMBEDDING_DIM = 384  # Output dimension for bge-small

# RAG Configuration
RAG_TOP_K = int(os.getenv('RAG_TOP_K', '5'))           # Retrieved documents
RAG_CHUNK_SIZE = int(os.getenv('RAG_CHUNK_SIZE', '512'))
RAG_CHUNK_OVERLAP = int(os.getenv('RAG_CHUNK_OVERLAP', '50'))

# Memory System
WORKING_MEMORY_SIZE = int(os.getenv('WORKING_MEMORY_SIZE', '3'))   # Recent messages
SEMANTIC_MEMORY_SIZE = int(os.getenv('SEMANTIC_MEMORY_SIZE', '5')) # Retrieved memories
RECENCY_WEIGHT = float(os.getenv('RECENCY_WEIGHT', '0.3'))         # Balance recency vs relevance

# Tool Use
CODE_EXECUTION_ENABLED = os.getenv('CODE_EXECUTION_ENABLED', 'true').lower() == 'true'
CODE_EXECUTION_TIMEOUT = int(os.getenv('CODE_EXECUTION_TIMEOUT', '5'))  # Seconds

# Voting
VOTING_ENABLED = os.getenv('VOTING_ENABLED', 'true').lower() == 'true'
VOTING_CANDIDATES = int(os.getenv('VOTING_CANDIDATES', '3'))
VOTING_COMPLEXITY_THRESHOLD = int(os.getenv('VOTING_COMPLEXITY_THRESHOLD', '7'))
```

### Module Deep Dive

#### 1. Embeddings (`embeddings.py`)

Uses FastEmbed with BAAI/bge-small-en-v1.5 model (384 dimensions, ONNX-based, CPU-friendly).

```python
# Key functions
embed_text(text: str) -> np.ndarray          # Single text → 384-dim vector
embed_batch(texts: List[str]) -> List[np.ndarray]  # Batch embedding
cosine_similarity(a: np.ndarray, b: np.ndarray) -> float
chunk_text(text: str, chunk_size=512, overlap=50) -> List[str]

# Availability check
V4_EMBEDDINGS_AVAILABLE = True  # Set at module load
```

**Lazy Loading**: Model is loaded on first use to avoid slow startup.

#### 2. Vector Store (`vector_store.py`)

Per-user SQLite database storing embeddings with metadata.

```python
class VectorStore:
    def __init__(self, principal_id: str)
    def add_message_embedding(content, role, timestamp, chat_id, metadata)
    def search_similar(query_text, top_k=5) -> List[Dict]
    def export_for_ipfs() -> bytes  # For IPFS backup
    def import_from_ipfs(data: bytes)  # Restore from backup

# Factory function
get_user_vector_store(principal_id: str) -> VectorStore
```

**Storage Location**: `/data/vectors/{principal_id}/vector.db`

**Schema**:
```sql
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    content TEXT,
    embedding BLOB,  -- numpy array as bytes
    role TEXT,       -- 'user' or 'assistant'
    timestamp REAL,
    chat_id TEXT,
    metadata TEXT    -- JSON
);
```

**Fallback Mode**: If sqlite-vss is not available, uses Python-based cosine similarity search (slower but functional).

#### 3. Semantic Memory (`memory.py`)

Combines working memory (recent) + semantic memory (relevant).

```python
class SemanticMemory:
    def __init__(self, principal_id: str)
    def add_interaction(user_msg, assistant_msg, chat_id)
    def get_relevant_context(query: str) -> List[Dict]
    
def build_enhanced_context(
    principal_id: str,
    current_query: str,
    chat_history: List[Dict]
) -> str  # Returns formatted context for LLM prompt
```

**Context Building Algorithm**:
1. Take last N messages (WORKING_MEMORY_SIZE=3) as "working memory"
2. Embed current query
3. Search vector store for semantically similar past messages
4. Score by: `relevance * (1 - RECENCY_WEIGHT) + recency * RECENCY_WEIGHT`
5. Return top SEMANTIC_MEMORY_SIZE results
6. Format as: `[Working Memory] + [Semantic Memory] + [Current Query]`

#### 4. Tools (`tools.py`)

Registry of available tools with structured calling.

```python
TOOL_REGISTRY = {
    'calculator': {
        'description': 'Evaluate mathematical expressions',
        'parameters': {'expression': 'string'},
        'handler': 'code_executor.evaluate_math_expression'
    },
    'code_execute': {
        'description': 'Execute Python code in sandbox',
        'parameters': {'code': 'string'},
        'handler': 'code_executor.execute_python_code'
    },
    'web_search': {
        'description': 'Search the web for current information',
        'parameters': {'query': 'string'},
        'handler': 'search.brave_search'
    },
    'document_search': {
        'description': 'Search user conversation history',
        'parameters': {'query': 'string'},
        'handler': 'memory.search_user_history'
    },
    'fact_check': {
        'description': 'Verify a factual claim',
        'parameters': {'claim': 'string'},
        'handler': 'tools.fact_check_claim'
    }
}

def detect_tools_needed(prompt: str) -> List[str]  # Heuristic detection
def parse_tool_calls(response: str) -> List[Dict]  # Parse <tool>...</tool> XML
def get_tool_definitions_for_prompt() -> str       # Format for system prompt
```

**Tool Call Format** (in LLM response):
```xml
<tool name="calculator">
  <param name="expression">sqrt(144) * 7</param>
</tool>
```

#### 5. Code Executor (`code_executor.py`)

Safe Python execution using RestrictedPython.

```python
def evaluate_math_expression(expr: str) -> Dict:
    """
    Safe math evaluation using AST parsing.
    Allowed: +, -, *, /, **, sqrt, sin, cos, tan, log, exp, abs, round
    """

def execute_python_code(code: str, timeout: int = 5) -> Dict:
    """
    Execute Python in RestrictedPython sandbox.
    - No file I/O
    - No network access
    - No imports (except math, random)
    - 5 second timeout
    - Limited builtins
    """

def execute_tool(tool_name: str, args: Dict, principal_id: str = None) -> Dict:
    """
    Main entry point - routes to appropriate handler.
    """
```

**Security Features**:
- RestrictedPython compiles code with restricted builtins
- Timeout via threading
- No access to `__import__`, `open`, `eval`, `exec`
- Whitelisted functions only

#### 6. Voting (`voting.py`)

Self-consistency voting for complex queries.

```python
def should_use_voting(query: str, complexity: int) -> bool:
    """Returns True if query complexity >= VOTING_COMPLEXITY_THRESHOLD (7)"""

def run_voting_pipeline(
    prompt: str,
    model: str,
    num_candidates: int = 3,
    temperatures: List[float] = [0.3, 0.7, 1.0]
) -> Dict:
    """
    1. Generate N responses at different temperatures
    2. Extract key claims/answers from each
    3. Find consensus (majority vote)
    4. Return best response + confidence score
    """
```

**Algorithm**:
1. Generate 3 responses at temperatures [0.3, 0.7, 1.0]
2. For each response, extract "answer fingerprint" (key facts/numbers)
3. Group similar fingerprints
4. Return response from largest group
5. Confidence = group_size / total_candidates

#### 7. Structured Output (`structured.py`)

JSON schema enforcement for reliable parsing.

```python
SCHEMAS = {
    'understanding': {
        'type': 'object',
        'properties': {
            'main_question': {'type': 'string'},
            'sub_questions': {'type': 'array'},
            'required_knowledge': {'type': 'array'},
            'complexity': {'type': 'integer'}
        }
    },
    'plan': {...},
    'critique': {...},
    'tool_call': {...}
}

def generate_structured(
    prompt: str,
    schema_name: str,
    model: str = None
) -> Dict:
    """
    Generate response conforming to JSON schema.
    Uses prompt engineering + post-processing.
    Fallback: Regex extraction if JSON parsing fails.
    """
```

**Note**: `outlines` library was removed due to Rust compiler requirement. Uses fallback JSON extraction.

### Multi-Model Routing

The agent pipeline routes queries based on complexity:

```python
def select_model_for_task(complexity: int, task_type: str) -> str:
    if not MULTI_MODEL_ENABLED:
        return MODEL_NAME  # Use default model
    
    if task_type == 'classification':
        return FAST_MODEL      # phi3:mini
    elif complexity <= 4:
        return SMART_MODEL     # llama3.1:8b
    else:
        return REASONING_MODEL # qwen2.5:32b
```

**Tier Configuration**:

| Tier | FAST_MODEL | SMART_MODEL | REASONING_MODEL | MULTI_MODEL_ENABLED |
|------|------------|-------------|-----------------|---------------------|
| 1 | - | - | - | false |
| 2 | phi3:mini | llama3.1:8b | qwen2.5:14b | true |
| 3 | phi3:mini | llama3.1:8b | qwen2.5:32b | true |

### API Endpoints (v4)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v4/status` | GET | No | Feature availability status |
| `/v4/vector/index` | POST | Yes | Bulk index chat history |
| `/v4/vector/document` | POST | Yes | Index a document |
| `/v4/vector/search` | POST | Yes | Semantic search |
| `/v4/vector/sync` | POST | Yes | Sync vector DB to/from IPFS |
| `/v4/tools/execute` | POST | Yes | Execute a tool |

### Startup Import Sequence

In `inference_server.py`, v4 modules are imported individually with error handling:

```python
V4_IMPORT_ERROR = None
V4_EMBEDDINGS_AVAILABLE = False
V4_VECTOR_STORE_AVAILABLE = False
# ... etc

try:
    from services.embeddings import ..., V4_EMBEDDINGS_AVAILABLE
    logger.info(f"✅ embeddings: V4_EMBEDDINGS_AVAILABLE={V4_EMBEDDINGS_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"embeddings: {e}"
    logger.error(f"❌ embeddings import failed: {e}")

# ... repeat for each module

V4_FEATURES_AVAILABLE = all([
    V4_EMBEDDINGS_AVAILABLE,
    V4_VECTOR_STORE_AVAILABLE,
    V4_MEMORY_AVAILABLE,
    V4_TOOLS_AVAILABLE,
    V4_CODE_EXECUTOR_AVAILABLE
])
```

### Troubleshooting V4

**Check v4 status**:
```bash
curl -s https://api.dubya.ai/v4/status | jq .
```

**Expected response (all working)**:
```json
{
  "available": true,
  "features": {
    "code_executor": true,
    "embeddings": true,
    "semantic_memory": true,
    "structured": true,
    "tools": true,
    "vector_store": true,
    "voting": true
  },
  "version": "4.0.0"
}
```

**If features show false**:
- Check for `import_error` field in response
- Common issues:
  - `fastembed` not installed → check requirements.txt
  - `RestrictedPython` not installed → check requirements.txt
  - numpy version mismatch → needs numpy 1.26.4

**Verify build timestamp**:
```bash
curl -s https://api.dubya.ai/health | jq '.build_timestamp'
```

### Dependencies Added (requirements.txt)

```
# V4.0 Intelligence Upgrade
fastembed>=0.3.0          # Text embeddings (uses ONNX, no GPU required)
RestrictedPython>=7.0     # Safe code execution sandbox
numpy>=1.26.0             # Vector operations

# REMOVED (compatibility issues):
# sqlite-vss              # Needs special build - using Python fallback
# outlines                # Needs Rust compiler - using regex fallback
```

### Output Limits (v4-unlimited)

Token and timeout limits were significantly increased to allow long-form generation:

| Setting | Old Value | New Value | Location |
|---------|-----------|-----------|----------|
| Default tokens | 800 | 4,000 | `inference_server.py` |
| Reasoning tokens | 4,000 | 8,000 | `inference_server.py` |
| Execute pass tokens | 4,000 | 8,000 | `agent.py` |
| Refine pass tokens | 4,000 | 8,000 | `agent.py` |
| Ollama timeout | 300s | 600s | `inference_server.py` |
| Akash HTTP timeout | 60s | 600s | `deploy-tier3-complex.yaml` |
| Cloudflare Worker timeout | 30s | 30s (max) | `wrangler.toml` |

### Testing V4 Features

**Benchmark Tests** (run after deployment):

```bash
# 1. Math reasoning
curl -s -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A store sells apples for $0.75 each. Buy 12+, get 15% off. How much for 15 apples?", "max_length": 400}' | jq -r '.response'

# 2. Logic puzzle
curl -s -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Alice, Bob, Carol have cat, dog, fish. Alice has no dog. Cat owner is not Carol. Bob has fish. Who has what?", "max_length": 400}' | jq -r '.response'

# 3. Code generation
curl -s -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write Python to find longest palindromic substring. Handle edge cases.", "max_length": 800}' | jq -r '.response'

# 4. Trick question
curl -s -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A farmer has 17 sheep. All but 9 run away. How many left?", "max_length": 200}' | jq -r '.response'
```

### Future Enhancements (Not Yet Implemented)

1. **Chain-of-Thought Prompting**: Explicit reasoning steps
2. **Retrieval-Augmented Generation (RAG)**: Document ingestion pipeline
3. **Fine-tuning Integration**: LoRA adapters for domain specialization
4. **Agent Loops**: Multi-turn tool use with reflection
5. **Streaming Tool Calls**: Show tool execution in real-time

---

## 📊 V4.0 Intelligence Assessment (January 31, 2026)

### Benchmark Results: 17/20 (85%) - Excellent

Trinity v4.0 running on **Tier 3 (Qwen 2.5 32B)** was evaluated against a standardized 7-test intelligence benchmark covering math reasoning, logic, code generation, factual accuracy, multi-hop reasoning, constraint following, and trick questions.

| Test | Category | Score | Max | Result |
|------|----------|-------|-----|--------|
| 1 | Multi-Step Math | 3 | 3 | ✅ Perfect |
| 2 | Logic Puzzle | 3 | 3 | ✅ Perfect |
| 3 | Code Generation | 4 | 4 | ✅ Perfect |
| 4 | Factual + Calculation | 3 | 3 | ✅ Perfect |
| 5 | Multi-Hop Reasoning | 2 | 2 | ✅ Perfect |
| 6 | Constraint Following | 0 | 3 | ❌ Failed |
| 7 | Trick Question | 2 | 2 | ✅ Perfect |
| **Total** | | **17** | **20** | **85%** |

### Demonstrated Strengths

#### 1. Mathematical Reasoning
Trinity now exhibits structured, step-by-step mathematical problem-solving. When asked to calculate a discounted price, it:
- Identified the base calculation (15 × $0.75 = $11.25)
- Applied the discount correctly (15% off = $11.25 × 0.85)
- Arrived at the precise answer ($9.5625 → $9.56)
- Showed all work with clear mathematical notation

This represents a significant improvement from baseline LLM behavior, likely enhanced by the **tool use framework** that allows the model to reason about calculations methodically.

#### 2. Logical Deduction
The logic puzzle test (Alice/Bob/Carol with cat/dog/fish) was solved flawlessly:
- Constraint parsing: Correctly identified all 3 constraints
- Elimination reasoning: Applied constraints in optimal order
- Verification: Confirmed solution satisfies all constraints

The **multi-pass agentic pipeline** (Understand → Plan → Execute) appears to help the model break down constraint satisfaction problems into manageable steps.

#### 3. Code Generation Quality
The longest palindromic substring problem showcased:
- **Algorithm selection**: Chose expand-around-center (O(n²)) - optimal for this problem
- **Edge case handling**: Empty string, single character
- **Code structure**: Clean Python with proper typing hints
- **Testing**: Included 4 test cases covering different scenarios

This quality suggests the **structured output** capabilities help organize code generation into logical components.

#### 4. Factual Accuracy with Calculation
The sunlight travel time question required both:
- Factual recall (speed of light ≈ 300,000 km/s, Sun distance ≈ 150M km)
- Mathematical computation (150,000,000 ÷ 300,000 = 500s = 8.33 min)

Trinity correctly integrated both knowledge retrieval and calculation, demonstrating the **semantic memory** system's ability to surface relevant facts.

#### 5. Multi-Hop Reasoning Chains
The height ordering problem (John > Mary > Susan > Tom > Lisa) required chaining 4 comparative statements. Trinity:
- Built the transitive relationship correctly
- Inverted the chain for "shortest to tallest" ordering
- Produced the exact correct answer: Lisa, Tom, Susan, Mary, John

The **complexity classifier** likely identified this as a medium-complexity query, engaging the appropriate reasoning model.

#### 6. Trap Question Resistance
The classic "17 sheep, all but 9 run away" trick question tests whether models:
- Parse language precisely ("all but 9" = 9 remain, not 17-9=8)
- Avoid pattern-matching to subtraction

Trinity answered correctly: **9 sheep**. This suggests the **self-consistency voting** mechanism may help by generating multiple interpretations and selecting the majority consensus.

### Known Limitation: Negative Character Constraints

The only failed test asked Trinity to write about climate change without using the letter "E". Both attempts contained numerous E's:
- "temperatures", "ice", "levels", "unprecedented", "escalates", "ecosystems"

This is a **fundamental LLM limitation**, not specific to Trinity:
- Tokenization operates on subwords, not characters
- Models lack character-level awareness during generation
- Negative constraints ("don't do X") are harder than positive ("do Y")

**Mitigation strategies** (not yet implemented):
- Post-generation filtering with retry
- Character-aware decoding constraints
- Fine-tuning on constraint-following datasets

### Impact of V4.0 Upgrades

| V4 Feature | Observed Benefit |
|------------|-----------------|
| **Semantic Memory** | Factual recall appears stronger; relevant knowledge surfaces naturally |
| **Multi-Model Routing** | Complex queries use larger model; simple queries stay fast |
| **Tool Use Framework** | Math problems show structured calculation attempts |
| **Self-Consistency Voting** | Trap question avoided; ambiguous queries resolved correctly |
| **Structured Output** | Code generation is well-organized with proper sections |
| **Complexity Classification** | Queries routed to appropriate reasoning depth |

### Performance by Tier

| Tier | Model | Expected Score | Use Case |
|------|-------|----------------|----------|
| 1 | TinyLlama 1.1B | 40-50% | Basic Q&A only |
| 2 | Llama 3.1 8B | 65-75% | General reasoning |
| 3 | Qwen 2.5 32B | **85%** (tested) | Complex analysis |

### Conclusion

Trinity v4.0 represents a **substantial intelligence upgrade** from baseline LLM inference:

1. **Reasoning Quality**: 6 of 7 tests passed with perfect scores
2. **Step-by-Step Thinking**: Math and logic problems show clear work
3. **Code Competence**: Production-quality Python with edge cases
4. **Trap Resistance**: Avoided classic "all but N" linguistic trap
5. **Knowledge Integration**: Combined recall with calculation seamlessly

The 85% score places Trinity in the **"Excellent"** category for a self-hosted, decentralized AI system. The only weakness (character-level constraints) is a known limitation of transformer architectures, not a Trinity-specific issue.

**Recommendation**: For production use, Tier 3 (Qwen 32B) provides the best intelligence. Tier 2 (Llama 8B) offers good performance at lower cost for general-purpose queries.

---

## 🏗️ Architecture

```
User Browser
    ↓ HTTPS
ICP Frontend Canister (zc67k-kiaaa-aaaal-qtmiq-cai)
    │
    ├─→ Direct API calls (most endpoints)
    │       ↓
    │   Cloudflare Worker (SSL termination)
    │       ↓
    │   Akash Backend (Flask + Ollama)
    │
    └─→ ICP Backend Canister (au5zq-2qaaa-aaaal-qtowa-cai)
            ↓ HTTPS Outcalls (for ICP consensus)
        Cloudflare Worker → Akash Backend
```

### Why Cloudflare Worker?
- Akash providers have invalid/self-signed SSL certificates
- ICP HTTPS Outcalls require valid SSL
- Cloudflare provides valid SSL and forwards requests via HTTP to Akash

---

## 🔧 Akash CLI Reference

### Prerequisites
```bash
# Install provider-services CLI
curl -sfL https://raw.githubusercontent.com/akash-network/provider/main/install.sh | bash

# Import wallet
provider-services keys add trinity-wallet --recover --keyring-backend os

# Verify wallet
provider-services keys show trinity-wallet --keyring-backend os -a
```

### Key Commands
```bash
# Check balance
provider-services query bank balances akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --node https://rpc.akashnet.net:443 -o json

# List active deployments
provider-services query deployment list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --state active --node https://rpc.akashnet.net:443 -o json

# Close deployment
provider-services tx deployment close --dseq <DSEQ> \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Create deployment
provider-services tx deployment create deploy.yaml \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Get bids
provider-services query market bid list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --dseq <DSEQ> --node https://rpc.akashnet.net:443 -o json

# Create lease
provider-services tx market lease create \
  --dseq <DSEQ> --gseq 1 --oseq 1 --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Send manifest
provider-services send-manifest deploy.yaml \
  --dseq <DSEQ> --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# Get lease status (includes URI)
provider-services query provider lease-status \
  --dseq <DSEQ> --gseq 1 --oseq 1 --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# View logs
provider-services lease-logs \
  --dseq <DSEQ> --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443 --follow
```

### Provider Selection
**GOOD (Reliable):**
- `*.pcgameservers.com` - Fast image caching, reliable ingress
- `*.akash.pub` domains (e.g., `hurricane.akash.pub`, `europlots.akash.pub`)

**AVOID (Unreliable):**
- `*.leet.haus` domains - ingress networking often broken
- `quanglong.org` - Very slow image pulls (26+ minutes)
- `digitalfrontier` providers - Intermittent 502 errors

---

## 📊 Model Tiers

| Tier | Model | GPU | Memory | Cost | Use Case |
|------|-------|-----|--------|------|----------|
| 1 | Qwen3 1.7B | T4/RTX3090 | 16GB | ~$25/mo | Testing |
| 2 | Qwen2.5 14B | RTX3090/P40 | 24GB | ~$50/mo | Balanced (current) |
| 3 | Qwen3 32B | A100 40GB | 64GB | ~$200/mo | Complex |

---

## 🔐 Authentication

### Ed25519 Self-Custody
- Keypairs generated in browser
- Principal ID derived from public key
- Private key stored in localStorage (user's responsibility)
- All `/chat/*` endpoints require signature

### Signature Verification
```python
# Backend decorator
@require_auth
def protected_endpoint():
    principal = request.principal  # Set by decorator
    # Access user-specific data
```

### Headers Required
```
ICP-Principal: <principal-id>
ICP-Timestamp: <unix-timestamp>
ICP-Signature: <base64-signature>
ICP-PublicKey: <hex-public-key>
```

---

## 💾 Storage Architecture

### Persistent Cloud Storage (v3.4.0+)
**CRITICAL FIX:** All autosaves now sync to Lighthouse (IPFS + Filecoin) in addition to local disk.
This ensures user data survives Akash redeployments.

**Data Flow:**
```
User Message → Autosave (2s debounce)
    ├─→ Local Disk (fast, ephemeral on Akash)
    └─→ Lighthouse Upload (IPFS + Filecoin, permanent)

User Login (after redeploy):
    1. Check local disk (fast)
    2. If empty → Recover from Lighthouse (IPFS gateway)
    3. Cache recovered data locally
```

### Storage Layers
| Layer | Speed | Persistence | Purpose |
|-------|-------|-------------|---------|
| IPFS (Lighthouse) | Medium | Permanent | **Source of truth** - all chat data |
| Akash Disk | Fast | Lost on redeploy | Metadata cache only |
| Browser (IndexedDB) | Instant | Session only | UI responsiveness |

**Note:** Filecoin archive feature was removed in v3.7.0. IPFS is now the primary permanent storage.

### Encryption
- AES-256-GCM with PBKDF2 key derivation
- Principal ID used as encryption password
- 100k PBKDF2 iterations, random salt + nonce
- All data encrypted before upload to IPFS

### Autosave (v3.7.0)
- 2-second debounce after each message
- Direct upload to IPFS (Lighthouse)
- CID stored in metadata for recovery
- Exponential backoff retry (5 attempts max)
- Rainbow wave animation during save

---

## ⚠️ Critical Conventions

### Zustand State Management
**CRITICAL:** Direct assignments fail silently!

```javascript
// ❌ WRONG - Fails silently
State.isAuthenticated = true;
State.chatHistory = [...messages];

// ✅ CORRECT - Use setter methods
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

### Docker Build (Apple Silicon)
```bash
# ✅ CORRECT - AMD64 for Akash
docker build --platform linux/amd64 -t image:tag .

# ❌ WRONG - ARM64 won't work on Akash
docker build -t image:tag .
```

---

## 🛠️ Common Tasks

### Deploy Everything
```bash
./scripts/trinity-deploy-production.sh 1  # Tier 1
./scripts/trinity-deploy-production.sh 2  # Tier 2
./scripts/trinity-deploy-production.sh 3  # Tier 3
```

### Frontend Only
```bash
cd trinity-icp && npm run build && dfx deploy --ic trinity_frontend
```

### Switch Akash Provider
```bash
./scripts/switch-provider.sh https://new-url.ingress.akash.pub
```

### Clean Docker
```bash
./scripts/docker-cleanup.sh
```

---

## 🧪 Testing

```bash
# Health check
curl https://api.dubya.ai/health

# Test LLM response
curl -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?", "max_length": 50}'

# ICP canister health
dfx canister --network ic call au5zq-2qaaa-aaaal-qtowa-cai health
```

---

## 📋 API Endpoints

**Security Features:**
- All `/chat/*` endpoints validate input parameters (chat_id, principal_id, CID format)
- All `/generate*` endpoints are rate-limited (30 requests/60 seconds per IP)
- All `/chat/*` endpoints are rate-limited (10 requests/minute per IP)
- Prompt length limited to 50KB max to prevent DoS
- CORS restricted to known origins only

| Endpoint | Method | Auth | Rate Limit | Purpose |
|----------|--------|------|------------|---------|
| `/health` | GET | No | None | Health check |
| `/health/icp` | GET | No | None | ICP consensus health |
| `/generate` | POST | No | 30/min | LLM generation |
| `/generate/agent` | POST | No | 30/min | Agentic pipeline |
| `/stats` | GET | No | None | Performance stats |
| `/chat/autosave` | POST | ✅ | 10/min | Save encrypted chat |
| `/chat/list` | GET | ✅ | 10/min | List user's chats |
| `/chat/<id>` | GET | ✅ | 10/min | Load specific chat |
| `/chat/<id>` | DELETE | ✅ | 10/min | Delete chat |
| `/user/memory` | GET/POST | ✅ | 10/min | User memory CRUD |
| `/tools/browse` | POST | No | 30/min | Web browsing (SSRF protected) |

---

## 🔒 Security Hardening (v3.8.0)

### v3.8.0 Security Audit Fixes (January 2026)
Major security audit identified 67 issues across the codebase. Key fixes implemented:

| Category | Fix | File |
|----------|-----|------|
| **API Key Exposure** | Removed hardcoded keys, now injected from `.env` at deploy time | `deploy/akash/deploy-tier*.yaml` |
| **XSS Prevention** | All innerHTML wrapped with DOMPurify sanitization | `trinity-icp/src/app.js` |
| **CORS Hardening** | Removed wildcard, restricted to known origins | `deploy/cloudflare-worker/worker.js` |
| **CSP Hardening** | Removed dangerous wildcard from connect-src | `trinity-icp/.ic-assets.json5` |
| **Docker Security** | Added non-root user (trinity) to prevent container escape | `deploy/docker/Dockerfile` |
| **Thread Safety** | Added locks to global state (document_store, funding_cache) | `backend/inference_server.py` |
| **Replay Attack** | Reduced auth timestamp window from 5min to 30s | `backend/icp_auth.py` |
| **DoS Prevention** | Added 5MB limit on document uploads | `backend/inference_server.py` |
| **Exception Handling** | Replaced bare `except:` with specific exception types | `backend/inference_server.py` |
| **Dependency Pinning** | Pinned exact versions (== instead of >=) | `backend/requirements.txt` |

### Backend Security
| Feature | Implementation | File |
|---------|----------------|------|
| Storage rate limiting | `@storage_rate_limit` decorator (10 req/min) | `middleware/rate_limit.py` |
| Prompt length validation | 50KB max, returns 400 if exceeded | `config.py`, `inference_server.py` |
| SSRF protection | `is_safe_url()` blocks private IPs, metadata endpoints | `validation.py` |
| CORS restriction | Whitelist of allowed origins | `inference_server.py` |
| Connection pooling | `requests.Session` with HTTPAdapter | `config.py` |
| Memory leak prevention | Auto-cleanup of stale rate limit IPs, document store TTL | `middleware/rate_limit.py` |
| Thread-safe globals | `threading.Lock()` on document_store and funding_cache | `inference_server.py` |
| Document size limit | 5MB max per upload, returns 413 if exceeded | `inference_server.py` |
| Auth timestamp validation | 30-second window prevents replay attacks | `icp_auth.py` |

### Frontend Security
| Feature | Implementation | File |
|---------|----------------|------|
| XSS prevention | DOMPurify sanitization on all dynamic HTML | `app.js` |
| Private key encryption | AES-GCM encryption in localStorage | `utils/crypto.js` |
| Content Security Policy | Hardened CSP without wildcards | `index.html`, `.ic-assets.json5` |
| Ed25519 signatures | Constant-time verification (cryptography lib) | `icp_auth.py` |
| Request cancellation | AbortController on all fetch calls | `app.js` |

### Proxy Security Headers
The Cloudflare Worker includes:
```javascript
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### Dependencies (Pinned Versions)
```
flask==3.0.3
flask-cors==4.0.0
flask-compress==1.15
requests==2.31.0
urllib3==2.2.1
psutil==5.9.8
APScheduler==3.10.4
pycryptodome==3.20.0
python-dotenv==1.0.1
cryptography==42.0.5
yfinance==0.2.37
feedparser==6.0.11
beautifulsoup4==4.12.3
argon2-cffi==23.1.0
```

### API Key Management
**CRITICAL:** API keys are now managed via `.env` file and injected at deploy time:
```bash
# .env file (never commit to git!)
LIGHTHOUSE_API_KEY=your-key-here
BRAVE_SEARCH_API_KEY=your-key-here
```
The `scripts/akash_deploy.py` script reads `.env` and injects values into YAML before deployment.

### SSRF Protection
The `/tools/browse` endpoint blocks:
- Private IP ranges (10.x, 172.16-31.x, 192.168.x)
- Localhost (127.x, ::1)
- Link-local addresses (169.254.x)
- Cloud metadata endpoints (169.254.169.254)

---

## 🐛 Troubleshooting

### Cold Start (20-30s first request)
**Expected behavior.** LLM loads into GPU memory on first request.

### No Consensus Error (ICP)
```
❌ No consensus could be reached. Replicas had different responses.
```
**Solution:** Use `/health/icp` endpoint. Backend strips non-deterministic fields for ICP requests with `X-Request-ID` header.

### Docker Disk Full
```bash
docker system prune -a --volumes -f
docker builder prune -a -f
```

### Git Slow
Delete build artifacts:
```bash
rm -rf trinity-icp/target trinity-icp/node_modules
```

### Browser Cache
Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows/Linux)

---

## 📚 Key Files Reference

| Need to... | Edit this file |
|------------|----------------|
| Change backend logic | `backend/inference_server.py` |
| Change auth verification | `backend/icp_auth.py` |
| Change frontend UI | `trinity-icp/src/ui/*.js` |
| Change state management | `trinity-icp/src/state/store.js` |
| Change context memory | `trinity-icp/src/state/contextMemory.js` |
| Change auth flow | `trinity-icp/src/auth/authManager.js` |
| Change autosave | `trinity-icp/src/storage/autosave.js` |
| Change environment config | `trinity-icp/src/config.js` |
| Change Cloudflare Worker | `deploy/cloudflare-worker/worker.js` |
| Change Akash deployment | `deploy/akash/deploy-tier*.yaml` |
| Change Docker build | `deploy/docker/Dockerfile` |
| Change deployment script | `scripts/trinity-deploy-production.sh` |
| Change ICP canister | `trinity-icp/src/backend_canister/src/lib.rs` |

---

## 🔄 Workflow Checklists (CRITICAL)

> **AI ASSISTANT RULE:** Before making ANY change, identify which section(s) are affected and complete the FULL checklist for each. This prevents broken deployments and missed dependencies.

### Section Dependency Map

```
Frontend ←→ Config ←→ Backend ←→ Docker ←→ Akash
   ↓           ↓          ↓
  UI         ICP      Services
   ↓                     ↓
  CSS              Middleware
```

---

### 🐳 DOCKER Workflow Checklist

**When to use:** Any change to `backend/*.py`, `backend/**/`, or `deploy/docker/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ All Python files have valid syntax | `python3 -m py_compile backend/*.py` |
| 2 | ☐ All imports exist and are correct | Check `import` statements in changed files |
| 3 | ☐ Dockerfile COPY includes all needed files/dirs | `deploy/docker/Dockerfile` |
| 4 | ☐ requirements.txt includes all dependencies | `backend/requirements.txt` |
| 5 | ☐ Build passes locally | `docker build --platform linux/amd64 -t test .` |
| 6 | ☐ Container starts without import errors | Check startup logs |
| 7 | ☐ Push to Docker Hub | `docker push gdubx/trinity-inference:tag` |
| 8 | ☐ Update Akash YAML with new image tag | `deploy/akash/deploy-tier*.yaml` |

**Files that MUST be in Dockerfile COPY:**
```dockerfile
COPY backend/inference_server.py .
COPY backend/icp_auth.py .
COPY backend/config.py .
COPY backend/encryption.py .
COPY backend/storage.py .
COPY backend/lighthouse.py .
COPY backend/validation.py .
COPY backend/middleware/ ./middleware/
COPY backend/services/ ./services/
COPY deploy/docker/startup.sh .
```

**Common Docker Failures:**
- `ModuleNotFoundError` → Missing directory in COPY
- Container exits immediately → Check startup.sh permissions
- Port not accessible → EXPOSE 8000 missing

---

### 🖥️ BACKEND Workflow Checklist

**When to use:** Any change to `backend/inference_server.py` or `backend/services/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Python syntax valid | `python3 -m py_compile backend/inference_server.py` |
| 2 | ☐ All imports exist | Check import statements |
| 3 | ☐ All decorators applied correctly | `@require_auth`, `@rate_limit` |
| 4 | ☐ Route paths match frontend expectations | Compare with `trinity-icp/src/app.js` API calls |
| 5 | ☐ Request/response format matches frontend | JSON field names must match |
| 6 | ☐ Config variables used consistently | Check `backend/config.py` |
| 7 | ☐ Docker workflow completed | See Docker checklist above |

**Backend Module Structure:**
```
backend/
├── inference_server.py   # App factory (349 lines) — blueprint registration, startup
├── icp_auth.py           # Auth decorators, signature verification
├── config.py             # Environment config (all constants and defaults)
├── encryption.py         # AES-256-GCM encryption
├── storage.py            # File storage operations
├── lighthouse.py         # IPFS/Filecoin uploads
├── validation.py         # Input validation functions
├── database.py           # SQLAlchemy ORM (not integrated — future feature)
├── routes/               # 🆕 7 blueprints, 49 routes (extracted from inference_server.py)
│   ├── health.py         # /health, /metrics, /stats
│   ├── admin.py          # /admin/* experiments & cache
│   ├── generate.py       # /generate, /generate/stream, /generate/agent
│   ├── chat.py           # /chat/*, /user/* CRUD + memory
│   ├── tools.py          # /tools/* search, browse, documents
│   ├── v4.py             # /v4/* vector store, tool execution
│   └── session.py        # /session/*, /funding/*
├── middleware/            # Rate limiting, observability, A/B testing
│   ├── __init__.py
│   ├── rate_limit.py     # Per-principal rate limiting
│   ├── icp_cache.py      # ICP verification cache
│   ├── observability.py  # Prometheus metrics (single source of truth)
│   └── ab_test.py        # A/B testing middleware
├── services/             # Business logic (21 modules + graph/)
│   ├── __init__.py
│   ├── prompts.py        # System prompts
│   ├── akash.py          # Akash blockchain API
│   ├── agent.py          # Multi-step agent orchestration
│   ├── complexity.py     # Complexity classifier (0-10)
│   ├── model_router.py   # Multi-model routing by complexity
│   ├── experiments.py    # A/B testing framework
│   ├── caching.py        # Embedding + semantic caching
│   ├── tracing.py        # Distributed tracing
│   └── graph/            # LangGraph multi-agent (7 files)
├── eval/                 # Benchmarking tools
└── tests/                # 607+ tests (unit + integration + e2e)
```

---

### 🎨 FRONTEND Workflow Checklist

**When to use:** Any change to `trinity-icp/src/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ JavaScript syntax valid | Vite build will catch errors |
| 2 | ☐ All imports exist | Check import paths |
| 3 | ☐ API endpoints match backend | Compare with `backend/inference_server.py` |
| 4 | ☐ Zustand state uses setter methods | Never `State.prop = value` |
| 5 | ☐ Build succeeds | `cd trinity-icp && npm run build` |
| 6 | ☐ Test in browser | Check console for errors |
| 7 | ☐ Deploy to ICP | `dfx deploy --ic trinity_frontend` |

**Frontend Module Structure:**
```
trinity-icp/src/
├── app.js              # Main application entry
├── config.js           # Environment detection
├── index.html          # HTML template + CSP
├── styles.css          # All CSS
├── tools.js            # Tools dropdown
├── api/
│   └── canister-client.js  # ICP backend client
├── auth/
│   ├── authManager.js      # Keypair management (encrypts keys in localStorage)
│   └── keyExportModal.js   # Key display modal
├── state/
│   ├── store.js            # Zustand store
│   └── contextMemory.js    # Memory compression
├── storage/
│   ├── autosave.js         # Debounced save
│   └── lighthouse.js       # Filecoin client
├── ui/
│   ├── domCache.js         # DOM element refs
│   ├── messages.js         # Message rendering
│   ├── sidebar.js          # Chat list
│   ├── modals.js           # Dialog boxes
│   ├── notifications.js    # Toasts
│   └── rainbowBorder.js    # Effects
├── utils/
│   ├── validation.js       # Input validation
│   └── crypto.js           # AES-GCM encryption for localStorage
└── backend_canister/       # ICP Backend (Rust)
```

**UI Features:**
- **Live KaTeX Rendering:** Math formulas render with 300ms debounce for performance
- **Smooth Typing:** 3 chars per 15ms interval for natural feel
- **Rainbow Borders:** Hover effects on interactive elements
- **Dark Theme:** `#1a1a1a` background, `#ffffff` text
- **Request Cancellation:** AbortController allows stopping in-flight requests

---

### 🌐 AKASH Workflow Checklist

**When to use:** Deploying to Akash or changing `deploy/akash/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Docker image pushed to Docker Hub | `docker push gdubx/trinity-inference:tag` |
| 2 | ☐ YAML has correct image tag | `deploy/akash/deploy-tier*.yaml` |
| 3 | ☐ YAML has correct environment variables | Check `env:` section |
| 4 | ☐ Deployment created successfully | Check for DSEQ |
| 5 | ☐ Bid accepted from reliable provider | Avoid `*.leet.haus` |
| 6 | ☐ Lease status shows URI | Note the ingress URL |
| 7 | ☐ Logs show "Server ready" | `provider-services lease-logs ...` |
| 8 | ☐ Health endpoint responds | `curl https://<url>/health` |
| 9 | ☐ Cloudflare Worker updated with new URL | `wrangler secret put AKASH_URL` |
| 10 | ☐ Frontend ICP canister redeployed | `dfx deploy --ic trinity_frontend` |

**Provider Reliability:**
- ✅ GOOD: `*.pcgameservers.com`, `*.akash.pub`
- ❌ AVOID: `*.leet.haus`, `*.quanglong.org`

---

### 🔵 ICP Workflow Checklist

**When to use:** Changes to ICP canisters or frontend deployment

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ dfx.json has correct canister IDs | `trinity-icp/dfx.json` |
| 2 | ☐ canister_ids.json matches | `trinity-icp/canister_ids.json` |
| 3 | ☐ Frontend builds successfully | `npm run build` |
| 4 | ☐ For backend canister: Rust compiles | `cargo build --target wasm32-unknown-unknown` |
| 5 | ☐ Deploy command succeeds | `dfx deploy --ic <canister>` |
| 6 | ☐ Verify canister accessible | Test in browser |

**Canister IDs:**
- Frontend: `zc67k-kiaaa-aaaal-qtmiq-cai`
- Backend: `au5zq-2qaaa-aaaal-qtowa-cai`

---

### 🎭 CSS/UI Workflow Checklist

**When to use:** Visual changes to `styles.css` or UI components

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ CSS syntax valid | Browser dev tools will show errors |
| 2 | ☐ Colors match design system | See UI/UX section |
| 3 | ☐ Mobile responsive | Test at 375px width |
| 4 | ☐ Dark theme consistency | No jarring light elements |
| 5 | ☐ No console errors | Check browser console |
| 6 | ☐ Build and deploy | Frontend workflow |

**Design System:**
- Background: `#1a1a1a`, Surfaces: `#2d2d2d`
- Text: `#ffffff`, Secondary: `#bbb`
- Borders: `#3d3d3d`
- Border radius: 6px buttons, 8px modals

---

### 🧠 MEMORY Workflow Checklist

**When to use:** Changes to context memory or user memory

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Frontend contextMemory.js logic correct | `trinity-icp/src/state/contextMemory.js` |
| 2 | ☐ Backend prompt builder matches | `backend/services/prompts.py` |
| 3 | ☐ Memory window size consistent | 6 messages frontend, matches backend |
| 4 | ☐ Summarization triggers correctly | Every 15 messages |
| 5 | ☐ User memory endpoint works | `/user/memory` GET/POST |
| 6 | ☐ Test multi-turn conversation | Verify context is maintained |

---

### 💾 STORAGE Workflow Checklist

**When to use:** Changes to autosave, encryption, or Lighthouse

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Frontend autosave.js correct | `trinity-icp/src/storage/autosave.js` |
| 2 | ☐ Backend storage.py matches | `backend/storage.py` |
| 3 | ☐ Encryption uses AES-256-GCM | `backend/encryption.py` |
| 4 | ☐ Lighthouse API key configured | `LIGHTHOUSE_API_KEY` env var |
| 5 | ☐ IPFS upload/download works | Test with real data |
| 6 | ☐ Debounce timing correct | 2-second debounce |

---

### 🤖 MODEL Workflow Checklist

**When to use:** Changes to prompts, model config, or reasoning

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ System prompt is clear | `backend/services/prompts.py` |
| 2 | ☐ Model name matches tier | `deploy/akash/deploy-tier*.yaml` |
| 3 | ☐ Token limits appropriate | Check `max_length` in frontend |
| 4 | ☐ Reasoning prompt forces thinking | `/think` command works |
| 5 | ☐ Prompt doesn't confuse small models | No role markers for TinyLlama |
| 6 | ☐ Test actual responses | Chat in production |

---

### 📚 KNOWLEDGE BASE Workflow Checklist

**When to use:** After ANY major production push, phase completion, or significant refactor.

> **Why this matters:** `docs/ai-context/CODEBASE-MAP.md` is the running knowledge base — the single source of truth that any LLM reads to understand the entire codebase without searching. If it drifts from reality, every future AI session starts with wrong assumptions, leading to broken code, wasted time, and compounding errors. Keeping it current is not optional.

| Step | Check | Details |
|------|-------|---------|
| 1 | ☐ CODEBASE-MAP.md project structure updated | Verify file tree matches reality: new files added, deleted files removed, line counts re-verified |
| 2 | ☐ API route count verified | Run `grep -r "@.*\.route" backend/routes/ \| wc -l` — update the route count if changed |
| 3 | ☐ Route table updated | New endpoints added to the correct auth-level table (No Auth / Auth Required / Admin Only) |
| 4 | ☐ Config constants table updated | Any new constants in `config.py` added with value and description |
| 5 | ☐ Test count updated | Run `pytest tests/unit/ -q` — update test count and coverage percentage |
| 6 | ☐ Known Issues table updated | New issues added, resolved issues removed or marked fixed |
| 7 | ☐ CLAUDE.md cross-references correct | Test counts, file descriptions, and project structure in CLAUDE.md match CODEBASE-MAP.md |
| 8 | ☐ No stale references in docs/ | Run `grep -r "old_value" docs/` for any values that changed (line counts, test counts, endpoint counts) |

**Trigger points (MANDATORY update):**
- Completion of any numbered phase (Phase 1, 2, 3, etc.)
- Any backend refactor that changes file structure (new files, moved files, deleted files)
- Any frontend refactor that adds/removes modules
- Adding or removing API routes
- After every production deployment that includes structural changes
- After test suite expansion (new test files or significant test count increase)

**Quick verification commands:**
```bash
# Verify current state vs docs
find backend/routes -name "*.py" -exec grep -l "@.*\.route" {} \;  # List route files
grep -c "def test_" backend/tests/unit/*.py | awk -F: '{s+=$2} END {print s}'  # Count tests
wc -l backend/inference_server.py  # Verify line count
```

---

## 🎯 Feature Status

### ✅ Complete
- Self-custody Ed25519 authentication
- Encrypted autosave (AES-256-GCM)
- Filecoin archive via Lighthouse SDK
- Context memory (6-message window + summarization)
- Modular frontend architecture (Zustand)
- ICP backend canister (HTTPS Outcalls)
- Cloudflare Worker SSL proxy
- Unified CLI deployment pipeline (`trinity-deploy-production.sh`)
- Custom domain (dubya.ai)
- Funding transparency (Akash escrow balance + ICP cycles)

### ⏳ Planned
- Lightweight RAG (FastEmbed + BM25)
- Document attachments (browser-side PDF parsing)

---

## 🐛 Known Issues & Fixes

### New Chat Deletes Saved Chat (Active - Feb 2026)

**Symptom:** Clicking "New Chat" button deletes the previously saved chat instead of preserving it.

**Status:** Under investigation. Autosave may not be completing before new chat clears state.

**Affected Files:**
- `trinity-icp/src/app.js` (newChat function)
- `trinity-icp/src/storage/autosave.js`
- `trinity-icp/src/ui/sidebar.js`

**Workaround:** Wait a few seconds after last message before clicking New Chat.

---

### TinyLlama Prompt Confusion (Critical - Jan 2026)

**Symptom:** Model echoes system prompt in responses, hallucinates fake user/assistant dialogue, produces garbage like:
```
"[System] You are Trinity... User: Wow, I didn't think... Assistant: Yes, I am Trinity..."
```

**Root Cause:** 
1. TinyLlama (1.1B params) is too small to properly follow multi-turn chat formatting
2. The prompt uses `[System]`, `User:`, `Assistant:` labels that confuse the model
3. Model sees these as patterns to continue/echo rather than role markers
4. Context memory saves garbage responses → fed back next turn → feedback loop

**Affected Files:**
- `backend/inference_server.py` lines 1261-1310 (system prompt + prompt building)
- `trinity-icp/src/state/contextMemory.js` (saves garbage to context)

**Fix Required:**
1. Strip all role markers (`[System]`, `User:`, `Assistant:`) for small models
2. Use simple prompt format: just the user's question
3. OR switch to a larger model (8B+) that handles chat formatting correctly

**Prompt Flow (Current - Broken for TinyLlama):**
```
[System]
You are Trinity, a decentralized AI assistant...

User: previous message
Assistant: previous response
User: current message
Assistant:
```

**Prompt Flow (Fixed for TinyLlama):**
```
{user's question}
```

---

## 🎨 UI/UX Design System

### Theme
- **Background:** `#1a1a1a` (main), `#2d2d2d` (surfaces)
- **Text:** `#ffffff` (primary), `#bbb` (secondary)
- **Borders:** `#3d3d3d`
- **Interactive Hover:** Rainbow gradient borders
- **Archive Indicator:** Purple `#9c27b0`

### Typography
- Font: System fonts (`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif`)
- Weights: 400, 500, 600
- Size range: 11px-18px

### Spacing
- Border radius: 6px (buttons), 8px (modals)
- Grid: 8px system

---

## 🔗 Quick Links

- **Production:** https://dubya.ai
- **ICP Direct:** https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io
- **Cloudflare Worker:** https://api.dubya.ai
- **Docker Hub:** https://hub.docker.com/r/gdubx/trinity-inference
- **Akash Console:** https://console.akash.network

---

## 🖥️ New Mac Setup Guide

> For users who already have an Akash wallet and are setting up Trinity on a new Mac.

### Prerequisites Checklist

| Tool | Purpose | Required |
|------|---------|----------|
| Docker Desktop | Build & push containers | ✅ Yes |
| Homebrew | Package manager for macOS | ✅ Yes |
| Node.js | Build frontend | ✅ Yes |
| Akash CLI | Deploy to Akash Network | ✅ Yes |
| Akash Wallet | Sign deployment transactions | ✅ Yes (with ~5 AKT) |
| Akash Certificate | Provider communication | ✅ Yes (created once) |
| Wrangler CLI | Cloudflare Workers deployment | ✅ Yes |
| dfx SDK | Deploy ICP canisters | ⚠️ Optional |
| Docker Hub account | Push container images | ✅ Yes |

### Step 1: Install Docker Desktop

1. Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Open the `.dmg` and drag Docker to Applications
3. **Launch Docker Desktop** (it must be running, not just installed)
4. Wait for Docker to fully start (whale icon in menu bar stops animating)

```bash
docker info  # Verify it works
```

### Step 2: Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add to PATH (Apple Silicon)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc

brew --version  # Verify
```

### Step 3: Install Node.js

```bash
brew install node
node --version  # Should show v20+ or v22+
```

### Step 4: Install Akash CLI

```bash
curl -sfL https://raw.githubusercontent.com/akash-network/provider/main/install.sh | sudo bash -s -- -b /usr/local/bin

provider-services version  # Verify
```

### Step 5: Import Akash Wallet

```bash
provider-services keys add trinity-wallet --recover --keyring-backend os
# Enter 24-word mnemonic when prompted

provider-services keys show trinity-wallet --keyring-backend os -a  # Verify
```

### Step 6: Create Akash Certificate

Required for provider communication. Only needs to be done once per wallet/machine.

```bash
# Generate certificate
provider-services tx cert generate client \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443

# Publish to blockchain
provider-services tx cert publish client \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y
```

### Step 7: Install Wrangler CLI (Cloudflare Workers)

```bash
npm install -g wrangler
wrangler login  # Opens browser for OAuth
wrangler whoami  # Verify
```

### Step 8: Deploy Cloudflare Worker (First Time)

```bash
cd deploy/cloudflare-worker
wrangler deploy
```

Then set the AKASH_URL secret (after Akash deployment):
```bash
echo "http://YOUR_AKASH_URI" | wrangler secret put AKASH_URL
```

### Step 9: Install dfx SDK (Optional)

```bash
sh -ci "$(curl -fsSL https://internetcomputer.org/install.sh)"
source ~/.zshrc
dfx --version  # Verify
```

### Step 10: Login to Docker Hub

```bash
docker login
```

### Step 11: Deploy

```bash
./scripts/trinity-deploy-production.sh 2  # Tier 2 recommended
```

---

## 🔧 Common Issues

| Problem | Solution |
|---------|----------|
| `zsh: command not found: brew` | Run Homebrew install (Step 2) |
| `zsh: command not found: provider-services` | Reinstall with `sudo` and `-b /usr/local/bin` flag |
| `docker info` fails | Start Docker Desktop app |
| Keychain password prompt | Grant access (Akash uses macOS Keychain) |
| Low AKT balance warning | Fund wallet with ~5 AKT |
| `could not open certificate PEM file` | Run Step 6 to create Akash certificate |
| `Missing entry-point to Worker script` | Run `wrangler deploy` from inside `deploy/cloudflare-worker/` directory |
| `out of gas` error | Add `--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5` flags |
| Cloudflare 526 SSL error | Use `http://` not `https://` for Akash URL in Worker secret |
| Akash provider DNS failure | Provider added to `skip_providers` list in `scripts/akash_deploy.py` |
| Akash provider invalid SSL | Deployment script auto-detects and uses HTTP (Cloudflare handles HTTPS) |
| `npm run build` ERESOLVE/vite conflict | Downgrade vite to `^5.4.0` in package.json |
| `Unknown Domain` on custom domain | Register domain with ICP (see below) |

---

## 🌐 ICP Custom Domain Registration

### DNS Records for dubya.ai (Cloudflare)

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `@` | `icp1.io` | ❌ DNS only |
| TXT | `_canister-id` | `zc67k-kiaaa-aaaal-qtmiq-cai` | ❌ DNS only |
| CNAME | `_acme-challenge` | `_acme-challenge.dubya.ai.icp2.io` | ❌ DNS only |
| CNAME | `www` | `dubya.ai` | ❌ DNS only |
| Worker | `api` | `trinity-proxy` | ☁️ Proxied |

### Register with ICP

```bash
# Validate DNS setup
curl -sL -X GET "https://icp0.io/custom-domains/v1/dubya.ai/validate" | jq .

# Register domain
curl -sL -X POST "https://icp0.io/custom-domains/v1/dubya.ai" | jq .

# Check status (should show "registered" after 1-2 minutes)
curl -sL -X GET "https://icp0.io/custom-domains/v1/dubya.ai" | jq .
```

---

## 📋 Manual Akash Deployment

If the automated script fails:

```bash
# 1. Create deployment
provider-services tx deployment create deploy/akash/deploy-tier2-balanced.yaml \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Note DSEQ from output, then wait 30s for bids:
provider-services query market bid list \
  --owner $(provider-services keys show trinity-wallet --keyring-backend os -a) \
  --dseq YOUR_DSEQ --node https://rpc.akashnet.net:443 -o json

# 2. Accept a bid
provider-services tx market lease create \
  --dseq YOUR_DSEQ --gseq 1 --oseq 1 --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# 3. Send manifest
provider-services send-manifest deploy/akash/deploy-tier2-balanced.yaml \
  --dseq YOUR_DSEQ --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# 4. Get URI
provider-services query provider lease-status \
  --dseq YOUR_DSEQ --gseq 1 --oseq 1 --provider PROVIDER_ADDRESS \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# 5. Update Cloudflare Worker (USE HTTP!)
cd deploy/cloudflare-worker
echo "http://YOUR_AKASH_URI" | wrangler secret put AKASH_URL
```

---

## ⚔️ War of Kings - Model Benchmarking

### Overview
A structured benchmark system for comparing LLM models on Akash deployments. Located in `docs/war-of-kings/`.

### Quick Battle (Recommended)
**Duration:** ~30 minutes | **Cost:** ~$10 | **Data Points:** ~150/king

```bash
cd docs/war-of-kings/execute
./quick-battle.sh
```

| Phase | Duration | What It Tests |
|-------|----------|---------------|
| Health Check | 2 min | Verify kings are online, warm-up |
| IQ Battle | 10 min | 25 scored questions (math, logic, coding) |
| Speed Trial | 8 min | Throughput: requests/second, latency |
| Reasoning Gauntlet | 10 min | 10 hard problems (code, proofs) |

### Overnight Endurance (Optional)
**Duration:** 5 hours | **Cost:** ~$150 | **Data Points:** ~1,100/king

```bash
nohup ./overnight-stress.sh > overnight.log 2>&1 &
```

### Key Metrics Collected
- **IQ Score:** X/25 correct answers
- **Avg Latency:** Seconds per response
- **Throughput:** Requests per second
- **Gauntlet Completion:** X/10 hard problems solved

### Output Structure
```
results/battles/battle_YYYYMMDD_HHMMSS/
├── BATTLE_REPORT.md      # Human-readable summary
├── health/               # Warm-up results
├── iq/{king}/            # Scored question results
├── speed/{king}/         # Throughput metrics
└── gauntlet/{king}/      # Complex problem results
```

### King Registry (Update endpoints when redeploying)
Edit `docs/war-of-kings/execute/quick-battle.sh`:
```bash
declare -A KINGS=(
    ["qwen"]="https://AKASH_URL|qwen2.5:72b|👑"
    ["llama"]="http://AKASH_URL|llama3.3:70b|🦙"
    ["mixtral"]="https://AKASH_URL|mixtral:8x22b|🔮"
)
```

### Analysis
```bash
# View report after battle
cat results/battles/battle_*/BATTLE_REPORT.md

# Feed to Claude for deep analysis
# Upload results folder + docs/war-of-kings/prompts/claude-judge-prompt.md
```

---

*This document is maintained for AI assistants to quickly understand Trinity without re-exploring files. Last updated February 13, 2026 (V5.0: ReAct + Memory Tools + MCP + frontend display fixes + Akash redeployment).*
