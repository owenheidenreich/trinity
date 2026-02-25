# Handoff: MicroGPT Phase 3 — Ollama → llama-server Migration (In Progress)

**Date:** February 20, 2026  
**Previous Handoff:** `docs/handoffs/2026-02-19-microgpt-overhaul-phase3.md`  
**Full Plan:** `docs/plans/microgpt-overhaul-plan.md`  
**Test Status:** 1010 tests pass, 0 failures, 39 skipped  

---

## Summary

Phase 3 of the MicroGPT overhaul migrates Trinity from Ollama to llama-server (llama.cpp HTTP server). Steps 3a through 3e are **complete**. Step 3f (Docker/deployment cleanup) is **partially complete** — the Dockerfile is rewritten but `startup.sh` is missing and Akash YAMLs are not updated. **The Docker build is currently broken** because the Dockerfile references a `startup.sh` that was deleted and not yet recreated.

---

## Step Status

| Step | Description | Status |
|------|-------------|--------|
| **3a** | Create `LlamaServerProvider` | ✅ Complete |
| **3b** | Config vars + provider factory routing | ✅ Complete |
| **3c** | Verification deploy (skipped — no Akash access in this session) | ⏭ Skipped |
| **3d** | Refactor `profile_extractor.py` to use `LLMProvider` | ✅ Complete |
| **3e** | Delete Ollama provider code + fix all tests | ✅ Complete |
| **3f** | Docker/deployment cleanup | 🔶 Partial |

### Step 3f Breakdown

| Sub-task | Status | Notes |
|----------|--------|-------|
| Rewrite Dockerfile (multi-stage llama.cpp build) | ✅ Done | See `deploy/docker/Dockerfile` |
| Create new `startup.sh` | ❌ **MISSING** | Old script deleted, new one not yet created. **Docker build broken.** |
| Update Akash production YAML | ❌ Not started | Still has `OLLAMA_*` env vars |
| Update Akash test YAML | ❌ Not started | Still has `OLLAMA_*` env vars |
| Update `health.py` | ❌ Not started | Still has `"ollama_connected"` key |
| Update `config.py` defaults | ❌ Not started | `MODEL_BACKEND` still defaults to `"ollama"` |

---

## What Was Done (Details)

### Step 3a: LlamaServerProvider ✅

**File created:** `backend/services/llama_server_provider.py` (~288 lines)

Implements `LLMProvider` ABC with OpenAI-compatible endpoints:
- `generate()` / `generate_stream()` → `/v1/completions`
- `chat()` / `chat_stream()` → `/v1/chat/completions`
- `check_connection()` → `GET /health`
- `warmup()` → sends a short prompt to prime model

Key design decisions:
- SSE streaming format (`data: {json}\n\n`, terminated by `data: [DONE]`)
- Does NOT pass `think=False` — `think_filter.py` in the pipeline already strips `<think>` blocks
- Handles `tools` parameter (OpenAI-format tool definitions for ReAct loop)
- Handles `raw_message=True` (returns full message dict including `tool_calls`)
- `backend_name` property returns `"llama-server"`

### Step 3b: Config + Provider Factory ✅

**`backend/config.py`** — Added after line 72:
```python
LLAMA_SERVER_CHAT_PORT = int(os.getenv("LLAMA_SERVER_CHAT_PORT", "8081"))
LLAMA_SERVER_INGEST_PORT = int(os.getenv("LLAMA_SERVER_INGEST_PORT", "8082"))
PROMPT_CACHE_DIR = os.getenv("PROMPT_CACHE_DIR", "/data/kv_cache")
```

**`backend/services/provider_factory.py`** — Fully rewritten. Now creates only `LlamaServerProvider` (see **Known Issue #1** below). Provides:
- `create_provider()` → chat provider on `LLAMA_SERVER_CHAT_PORT`
- `get_provider()` → cached chat provider singleton (with model routing support)
- `create_ingest_provider()` → ingest provider on `LLAMA_SERVER_INGEST_PORT`
- `get_ingest_provider()` → cached ingest provider singleton
- `reset_provider()` → clears cache (for testing)

Caching is keyed by `(backend, host, model, num_ctx)` tuple.

### Step 3d: Profile Extractor Refactored ✅

**`backend/services/profile_extractor.py`** — Removed all direct Ollama HTTP calls:
- Removed imports: `OLLAMA_INGEST_HOST`, `OLLAMA_INGEST_MODEL`, `http_session`
- `_candidate_targets()` (returned `(host, model)` tuples) → renamed to `_candidate_providers()` (returns `LLMProvider` instances)
- `_call_model_once()` now takes a provider object and calls `provider.chat()` instead of `http_session.post()`

**`backend/services/ingestion_worker.py`** — `_summarize_incremental()` now calls `get_ingest_provider().chat()` instead of direct `http_session.post()`.

### Step 3e: Ollama Code Deleted + Tests Fixed ✅

**Files deleted:**
- `backend/services/ollama_provider.py` — replaced by `llama_server_provider.py`
- `backend/services/ollama.py` — legacy helpers, no longer needed
- `backend/tests/unit/test_ollama.py` — 18 tests that imported deleted modules

**`backend/services/agent.py`** — Cleaned up:
- `OllamaClient = None` (alias retained for any stray references)
- `AgentPipeline.__init__` — removed `elif ollama_host:` branch. Now accepts only `provider=` kwarg or falls back to `get_provider()`

**Test fixes after deletion (21 failures + 18 errors → 0 failures):**

| Test File | What Changed |
|-----------|-------------|
| `backend/tests/unit/test_providers.py` | Rewrote `TestOllamaProvider` → `TestLlamaServerProvider` (14 tests). Updated `test_create_ollama_provider` → `test_create_llama_server_provider`. Updated pipeline integration test. |
| `backend/tests/unit/test_memory_foundation.py` | 3 extraction tests updated: mock `_candidate_providers` instead of `_candidate_targets`, provide mock provider objects instead of `(host, model)` tuples |
| `backend/tests/unit/test_structured.py` | 3 tests updated: mock `services.provider_factory.get_provider` instead of `requests.post` |

### Step 3f (Partial): Dockerfile ✅

**`deploy/docker/Dockerfile`** — Fully rewritten as multi-stage build:

**Stage 1 (builder):** `nvidia/cuda:12.2.0-devel-ubuntu22.04`
- Clones llama.cpp, builds `llama-server` with CUDA support
- Targets GPU architectures: 80 (A100), 86 (A6000), 89 (L40S/RTX4090), 90 (H100)

**Stage 2 (runtime):** `nvidia/cuda:12.2.0-runtime-ubuntu22.04`
- Copies compiled `llama-server` binary from builder
- Installs `huggingface-hub` for model downloads
- Creates non-root `trinity` user
- Model directory: `/home/trinity/.models` (populated at startup, not baked in)
- KV cache directory: `/data/kv_cache`
- Exposes ports: 8000 (Flask), 8081 (chat llama-server), 8082 (ingest llama-server)
- `ENV MODEL_BACKEND=llama-server`
- References `startup.sh` which **does not exist yet**

---

## Known Issues (Must Fix Before Deploy)

### Issue 1: `startup.sh` Missing — Docker Build Broken

**Severity:** CRITICAL — Docker build fails at `COPY deploy/docker/startup.sh .`

The old Ollama-based `startup.sh` was deleted but a new llama-server version was never created. The Dockerfile's `CMD ["/app/startup.sh"]` will also fail at runtime.

**What the new `startup.sh` must do:**
1. Fix Akash PersistentVolume permissions (`chown trinity:trinity /home/trinity/.models /data`)
2. Download GGUF models via `huggingface-cli` if not already cached:
   - Chat model: `Qwen/Qwen3-32B-GGUF` → `qwen3-32b-q4_k_m.gguf` (or whatever `MODEL_NAME` resolves to)
   - Ingest model: smaller quantization (8b or same model)
3. Start llama-server for chat: `llama-server --host 0.0.0.0 --port 8081 --model /home/trinity/.models/<chat_model>.gguf --ctx-size 65536 --n-gpu-layers -1 --prompt-cache /data/kv_cache/ &`
4. Start llama-server for ingest: `llama-server --host 0.0.0.0 --port 8082 --model /home/trinity/.models/<ingest_model>.gguf --ctx-size 8192 --n-gpu-layers -1 &`
5. Wait for both llama-servers to respond on `/health`
6. Start Flask: `exec python3 inference_server.py` (as PID 1 for signal handling)

**Reference:** The plan mentions `deploy/docker/startup_llama.sh` as the target filename, but the Dockerfile uses `startup.sh`. Keep it as `startup.sh` since the Dockerfile already references it.

### Issue 2: Provider Factory Lost Ollama Branch

**Severity:** MEDIUM — Affects flexibility, not correctness

`provider_factory.py` was supposed to have a conditional `if MODEL_BACKEND == "llama-server": ... else: OllamaProvider(...)` for gradual migration. During Step 3e cleanup, the Ollama branch was removed entirely. The factory now **always** creates `LlamaServerProvider` regardless of `MODEL_BACKEND`.

This is fine if the intent is a clean break (Ollama is gone). But:
- `config.py` still defaults `MODEL_BACKEND="ollama"` — this is misleading
- The Dockerfile sets `MODEL_BACKEND=llama-server` — so Docker deploys work
- Local development without llama-server will fail

**Decision needed:** Either:
- **(A) Accept clean break** — change `config.py` default to `MODEL_BACKEND="llama-server"`. Remove stale `MODEL_BACKEND` conditional comments. This is the simpler path.
- **(B) Restore Ollama branch** — add back the `if MODEL_BACKEND == "ollama": ...` conditional for local dev. But `ollama_provider.py` is already deleted, so you'd need to recreate it or use a stub.

**Recommendation:** Option A (clean break). Change the `config.py` default and move on. Ollama code is already gone.

### Issue 3: `config.py` Still Has `OLLAMA_*` Env Var Names

**Severity:** LOW — Cosmetic, but confusing

`OLLAMA_CHAT_MODEL` and `OLLAMA_INGEST_MODEL` are still used throughout the codebase as "the model name" even though Ollama is gone. These are consumed by:
- `provider_factory.py` (imports `OLLAMA_CHAT_MODEL`, `OLLAMA_INGEST_MODEL`)
- `profile_extractor.py` (now indirectly via provider)

These could be renamed to `CHAT_MODEL_NAME` / `INGEST_MODEL_NAME`, but it would require updating Akash YAMLs and any scripts that set those env vars. **Not urgent** — they work fine as-is, they're just oddly named.

Also still present but unused by the new code: `OLLAMA_HOST`, `OLLAMA_CHAT_HOST`, `OLLAMA_INGEST_HOST`.

### Issue 4: Akash YAMLs Still Reference Ollama

**Severity:** HIGH — Deploys will use wrong env vars

**`deploy/akash/deploy-production.yaml`** still has:
```yaml
- OLLAMA_CHAT_HOST=http://localhost:11434
- OLLAMA_CHAT_MODEL=qwen3:32b
- OLLAMA_INGEST_HOST=http://localhost:11434
- OLLAMA_INGEST_MODEL=qwen3:8b
- MODEL_BACKEND=ollama
- OLLAMA_HOST=http://localhost:11434
mount: /home/trinity/.ollama
```

**`deploy/akash/deploy-test.yaml`** has the same pattern with `qwen3:8b`.

Both need:
```yaml
- MODEL_BACKEND=llama-server
- LLAMA_SERVER_CHAT_PORT=8081
- LLAMA_SERVER_INGEST_PORT=8082
- OLLAMA_CHAT_MODEL=qwen3:32b    # Keep the env var name (still read by config.py)
- OLLAMA_INGEST_MODEL=qwen3:8b   # Same — keep until renamed
mount: /home/trinity/.models      # Changed from .ollama
```

Remove: `OLLAMA_CHAT_HOST`, `OLLAMA_INGEST_HOST`, `OLLAMA_HOST` (no longer used).

### Issue 5: `health.py` Has `"ollama_connected"` Key

**Severity:** LOW — Backward compatibility concern

Both `/health` and `/health/icp` endpoints return `"ollama_connected": provider_healthy`. This works correctly (it just calls `get_provider().check_connection()`), but the key name is misleading.

**Options:**
- **(A)** Add `"llm_connected": provider_healthy` alongside existing key, then deprecate `"ollama_connected"` later
- **(B)** Rename to `"llm_connected"` outright (may break frontend/monitoring that checks this key)

Check if the frontend reads `"ollama_connected"` before deciding. The ICP canister frontend at `trinity-icp/src-react/` may reference it.

---

## Files Changed (Complete List)

### Created
| File | Lines | Purpose |
|------|-------|---------|
| `backend/services/llama_server_provider.py` | ~288 | LlamaServerProvider — OpenAI-compatible llama.cpp client |

### Modified
| File | What Changed |
|------|-------------|
| `backend/config.py` | Added `LLAMA_SERVER_CHAT_PORT`, `LLAMA_SERVER_INGEST_PORT`, `PROMPT_CACHE_DIR` after line 72 |
| `backend/services/provider_factory.py` | Fully rewritten — llama-server only, added `create_ingest_provider()` + `get_ingest_provider()` |
| `backend/services/profile_extractor.py` | Removed direct HTTP calls, uses `LLMProvider` via `_candidate_providers()` |
| `backend/services/ingestion_worker.py` | `_summarize_incremental()` uses `get_ingest_provider().chat()` |
| `backend/services/agent.py` | `OllamaClient = None`, removed `ollama_host` path from `AgentPipeline.__init__` |
| `deploy/docker/Dockerfile` | Full rewrite — multi-stage llama.cpp build with CUDA |
| `backend/tests/unit/test_providers.py` | `TestOllamaProvider` → `TestLlamaServerProvider`, factory tests updated |
| `backend/tests/unit/test_memory_foundation.py` | 3 extraction tests: `_candidate_targets` → `_candidate_providers` |
| `backend/tests/unit/test_structured.py` | 3 tests: mock provider instead of `requests.post` |

### Deleted
| File | Why |
|------|-----|
| `backend/services/ollama_provider.py` | Replaced by `llama_server_provider.py` |
| `backend/services/ollama.py` | Legacy Ollama helpers — no longer needed |
| `backend/tests/unit/test_ollama.py` | Tests for deleted modules |
| `deploy/docker/startup.sh` | Old Ollama-based startup — needs recreation as llama-server version |

---

## Remaining Work (Priority Order)

### 1. Create `deploy/docker/startup.sh` (CRITICAL)

Docker build is broken without this. See **Issue 1** above for the detailed spec of what it must contain.

Key model mapping logic needed:
- `MODEL_NAME` env var (e.g., `qwen3:32b`) → HuggingFace repo + filename
- The current Ollama model names use format `qwen3:32b`, but HuggingFace uses `Qwen/Qwen3-32B-GGUF` + `qwen3-32b-q4_k_m.gguf`
- Startup script needs a mapping function or naming convention

### 2. Update Akash YAML Files

See **Issue 4** above. Both `deploy/akash/deploy-production.yaml` and `deploy/akash/deploy-test.yaml` need env vars and mount paths updated.

### 3. Fix `config.py` MODEL_BACKEND Default

Change `MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ollama")` to `MODEL_BACKEND = os.getenv("MODEL_BACKEND", "llama-server")`.

### 4. Update `health.py` Keys

Add `"llm_connected"` key, keep `"ollama_connected"` for backward compat. Or rename if frontend doesn't depend on it.

### 5. (Optional) Rename OLLAMA_* Config Vars

Rename `OLLAMA_CHAT_MODEL` → `CHAT_MODEL_NAME`, `OLLAMA_INGEST_MODEL` → `INGEST_MODEL_NAME`, etc. Requires updating all references in `config.py`, `provider_factory.py`, Akash YAMLs. Low priority — they work fine with current names.

### 6. Verify Docker Build + Deploy

After all changes:
```bash
docker build --platform linux/amd64 -t trinity-inference:test -f deploy/docker/Dockerfile .
```

Then test deploy on Akash via `./scripts/trinity-deploy-production.sh test`.

---

## Architecture Reference

### Current Provider Flow
```
provider_factory.py
├── get_provider()         → LlamaServerProvider(host=localhost:8081, model=OLLAMA_CHAT_MODEL)
└── get_ingest_provider()  → LlamaServerProvider(host=localhost:8082, model=OLLAMA_INGEST_MODEL)
```

### Target Container Architecture
```
┌──────────────────────────────────────────────┐
│  Akash Container                              │
│                                               │
│  llama-server (chat)     port 8081            │
│  ├── Model: qwen3-32b-q4_k_m.gguf            │
│  ├── --ctx-size 65536                         │
│  ├── --n-gpu-layers -1                        │
│  └── --prompt-cache /data/kv_cache/           │
│                                               │
│  llama-server (ingest)   port 8082            │
│  ├── Model: qwen3-8b-q4_k_m.gguf             │
│  ├── --ctx-size 8192                          │
│  └── --n-gpu-layers -1                        │
│                                               │
│  Flask server            port 8000            │
│  └── LlamaServerProvider → localhost:8081/82  │
└──────────────────────────────────────────────┘
```

### Model Storage
- Models cached at `/home/trinity/.models/` (Akash persistent volume)
- KV cache at `/data/kv_cache/` 
- Chat storage at `/data/chats/`

---

## How to Run Tests

```bash
cd backend && python -m pytest tests/ -x -q
```

Expected: 1010 passed, 0 failed, 39 skipped.

If tests fail after your changes, common causes:
- Mocks patching old `_candidate_targets` instead of `_candidate_providers` in `profile_extractor.py`
- Mocks patching `requests.post` instead of `services.provider_factory.get_provider`
- Tests importing from deleted `ollama_provider` or `ollama` modules

---

## Key Files to Read

| File | Why |
|------|-----|
| `backend/services/llama_server_provider.py` | The new provider — understand API format and streaming contract |
| `backend/services/provider_factory.py` | How providers are created and cached |
| `backend/services/llm_provider.py` | The ABC interface (~135 lines) |
| `deploy/docker/Dockerfile` | Current multi-stage build (needs working startup.sh) |
| `deploy/akash/deploy-production.yaml` | Akash deployment — needs env var updates |
| `docs/plans/microgpt-overhaul-plan.md` | Full overhaul plan (Phase 3 section) |
| `docs/handoffs/2026-02-19-microgpt-overhaul-phase3.md` | Previous handoff with Phase 1-2 details |

---

## Critical Rules (from project copilot instructions)

- **Docker**: Always build with `--platform linux/amd64`
- **Deploy**: `./scripts/trinity-deploy-production.sh production` (or `test`)
- **Tests**: `cd backend && python -m pytest tests/ -x -q`
- **Zustand**: Never direct-assign state — use setters
- **think=False**: All Ollama calls passed this. With llama-server, `think_filter.py` handles it instead — do NOT add `think` parameter to llama-server API calls.
- **GPU Allowlist**: a100/a6000/h100/l40s/a40/rtx4090
- **Akash Timeout**: `read_timeout` hard limit is 60000ms
- **Cold starts**: First request after deploy takes 20-30s (model loading)
