# Trinity — AI Context Reference

> **Last Updated:** February 13, 2026
> **Status:** Post-overhaul (Intelligence + Frontend rewrites complete)
> **Model:** qwen2.5-coder:32b on Akash (RTX 3090)
> **See also:** [CODEBASE-MAP.md](CODEBASE-MAP.md) for file-level detail

---

## What Is Trinity

Decentralized AI chat: ICP frontend → Cloudflare Worker → Flask/Ollama backend on Akash. Ed25519 self-custody auth, AES-256-GCM encryption, IPFS backup via Lighthouse.

```
Browser (dubya.ai) → ICP Canister (frontend) → Cloudflare Worker (SSL) → Akash (Flask + Ollama)
                                                                              ↓
                                                                   Encrypted JSON + IPFS backup
```

| Layer | Tech | URL |
|-------|------|-----|
| Frontend | Vanilla JS + Zustand on ICP | https://dubya.ai |
| SSL Proxy | Cloudflare Worker | https://api.dubya.ai |
| Backend | Flask on Akash | Port 8000 |
| LLM | Ollama (qwen2.5-coder:32b) | Port 11434 (internal) |

---

## Architecture (Post-Overhaul)

### What Was Deleted
LangGraph multi-agent, complexity router, voting, experiments/A/B testing, parallel pipeline — all removed. Single-pass + ReAct replaced everything.

### Agent Pipeline (`services/agent.py`)

```
User Prompt → detect_tools_needed()
  ├── Tools needed → ReAct loop (iterative think→act→observe, max 15 turns)
  └── No tools    → Direct single-pass generation
```

- **ReAct loop** (`services/react_loop.py`): Dual-mode tool calling — native Ollama JSON tools for Qwen/Llama/Mistral, XML `<tool_call>` fallback for others
- **Token budget**: 24K (75% of 32K context window)
- **Reflexion**: Code execution errors trigger self-correction (up to 3 retries)
- **Think-block filtering**: `<think>…</think>` stripped before output

### 13 Tools (`services/tools.py` + `services/code_executor.py`)

| Tool | Category | Implementation |
|------|----------|---------------|
| calculator | Math | AST-safe eval |
| code_display | Code | RestrictedPython (disabled by default) |
| web_search | Search | Brave API |
| fact_check | Verify | Dual web search |
| document_search | RAG | Vector store embeddings |
| save_memory | Memory | MemGPT (384-dim embeddings) |
| recall_memory | Memory | Semantic + recency scoring |
| search_memory | Memory | Exact/semantic/hybrid |
| read_file | Workspace | Sandboxed to /workspace |
| write_file | Workspace | Max 5MB |
| list_directory | Workspace | Max depth 3 |
| search_codebase | Workspace | Regex, max 50 results |
| run_command | Workspace | python/pytest/node only |

### MCP (Model Context Protocol)

- **Server**: `POST /mcp` (HTTP) + `python mcp_stdio_server.py` (stdio for Claude Desktop)
- **Client**: Connects to external MCP servers, extends tool system
- Config: `MCP_SERVER_ENABLED=true` (default)

---

## Key Files

| Purpose | File |
|---------|------|
| Flask app | `backend/inference_server.py` |
| Config/constants | `backend/config.py` |
| Agent orchestrator | `backend/services/agent.py` |
| Agent prompts | `backend/services/agent_prompts.py` |
| ReAct loop | `backend/services/react_loop.py` |
| Tool dispatcher | `backend/services/code_executor.py` |
| Tool definitions | `backend/services/tools.py` |
| Memory tools (MemGPT) | `backend/services/memory_tools.py` |
| Web search | `backend/services/search.py` |
| Fact checker | `backend/services/fact_check.py` |
| Embeddings | `backend/services/embeddings.py` |
| Vector store | `backend/services/vector_store.py` |
| Semantic memory | `backend/services/memory.py` |
| Ollama client | `backend/services/ollama.py` |
| Prometheus metrics | `backend/middleware/observability.py` |
| Ed25519 auth | `backend/icp_auth.py` |
| Chat storage | `backend/storage.py` |
| IPFS backup | `backend/lighthouse.py` |

### Frontend (Vanilla JS — active)
| Purpose | File |
|---------|------|
| Orchestrator | `trinity-icp/src/app.js` |
| State (Zustand) | `trinity-icp/src/state/store.js` |
| API client | `trinity-icp/src/core/api.js` |
| Streaming/generate | `trinity-icp/src/features/generate.js` |
| Auth manager | `trinity-icp/src/auth/authManager.js` |
| Autosave | `trinity-icp/src/storage/autosave.js` |

### Frontend (React 19 — new, not yet primary)
Located in `trinity-icp/src-react/`. Same Zustand store shape, TypeScript, hooks-first architecture.

---

## Routes (8 Blueprints)

| Blueprint | Key Routes |
|-----------|------------|
| health | `/health`, `/metrics`, `/stats` |
| generate | `/generate`, `/generate/agent` |
| chat | `/chat/autosave`, `/chat/list`, `/chat/<id>`, `/user/memory/*` |
| tools | `/tools/search`, `/tools/browse`, `/tools/documents/*` |
| admin | `/admin/cache/*`, `/admin/tokens/*`, `/admin/quota/*` |
| v4 | `/v4/vector/*`, `/v4/search/*` |
| session | `/funding/status`, `/session/*` |
| mcp | `/mcp` (GET info, POST JSON-RPC 2.0) |

---

## Config (`backend/config.py`)

| Constant | Default | Notes |
|----------|---------|-------|
| `MODEL_NAME` | `qwen2.5-coder:32b` | Env override |
| `NUM_CTX` | `32768` | Ollama context window |
| `DEFAULT_MAX_TOKENS` | `8000` | Response limit |
| `OLLAMA_TIMEOUT` | `600` | 10 min generation |
| `MAX_PROMPT_LENGTH` | `50000` | Input limit |
| `REACT_MAX_ITERATIONS` | `15` | Tool-calling turns |
| `REACT_TOKEN_BUDGET` | `24000` | 75% of context |
| `CODE_EXECUTION_ENABLED` | `false` | Security: disabled in prod |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 384-dim |
| `RAG_TOP_K` | `5` | Retrieval results |

### Deployment Tiers
| Tier | Model | GPU |
|------|-------|-----|
| 1 | qwen3:1.7b | T4/3090 |
| 2 | qwen2.5:14b | Any NVIDIA |
| 3 | qwen2.5-coder:32b | A100/3090 |

---

## Deployment

```
Code → Docker build (--platform linux/amd64) → Push → Akash deploy → Cloudflare update → ICP deploy
```

**Script:** `./scripts/trinity-deploy-production.sh [tier]`

**Critical rules:**
- Docker builds MUST use `--platform linux/amd64` (dev = Apple Silicon, prod = amd64)
- NEVER put API keys in YAML — use `.env` + runtime injection
- Test with `docker run` locally before deploying

| Resource | Value |
|----------|-------|
| Frontend canister | `zc67k-kiaaa-aaaal-qtmiq-cai` |
| Backend canister | `au5zq-2qaaa-aaaal-qtowa-cai` |
| Docker image | `gdubx/trinity-inference:latest` |
| Akash wallet | `akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp` |

---

## Testing

```bash
cd backend && python -m pytest tests/ -x -q    # 615 passed, 91.30% coverage
```

---

## Known Issues

| Issue | Details |
|-------|---------|
| `AUTH_TIMESTAMP_WINDOW_MS` unused | config.py defines 5min, icp_auth.py hardcodes 60s |
| `database.py` not integrated | 298-line ORM exists but unused |
| React frontend not deployed | `src-react/` exists but `src/` (vanilla JS) is active |
| Code execution disabled | Intentional — `CODE_EXECUTION_ENABLED=false` in all Akash YAMLs |

---

## Overhaul History

**Intelligence Overhaul (Feb 2026):** Deleted ~2,700 lines (LangGraph, voting, experiments, complexity, parallel, A/B testing). Replaced multi-pass pipeline with single-pass + ReAct. Upgraded model to qwen2.5-coder:32b. Added filesystem tools, code execution, repo map.

**Frontend Overhaul (Feb 2026):** React 19 + TypeScript rewrite in `src-react/` (62 files, 137 tests). Vanilla JS in `src/` remains the active deployed frontend.

**QA Audit (Feb 2026):** See `docs/QA-HANDOFF.md` for post-overhaul verification matrix.
