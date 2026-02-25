# Handoff: MicroGPT Overhaul — Complete Implementation Status

**Date:** February 20, 2026  
**Audience:** Next engineer picking up Trinity deployment  
**Previous Handoffs:**
- `docs/handoffs/2026-02-19-microgpt-overhaul-phase3.md` — Phase 3 plan + Phase 1-2 details
- `handoffs/2026-02-20-microgpt-phase3-progress.md` — Phase 3 progress (start of day)  

**Full Overhaul Plan:** `docs/plans/microgpt-overhaul-plan.md`  
**Test Status:** 1010 tests pass, 0 failures, 39 skipped  

---

## Executive Summary

The MicroGPT overhaul is a 3-phase refactoring of Trinity's inference pipeline:

1. **Phase 1 — Temperature Routing:** Route query types to different sampling temperatures
2. **Phase 2 — Tiny Classifiers:** Replace all regex-based query classification with trained 100K-param ByteTransformer models
3. **Phase 3 — llama-server Migration:** Drop Ollama, use llama.cpp HTTP server directly

**Phases 1 and 2 are complete.** Phase 3 code is complete, but **deployment is blocked** by a filename casing bug in the HuggingFace model download mapping. This bug has been identified and **fixed in this session** — the fix is in `deploy/docker/startup.sh` but has NOT been deployed yet.

---

## Current Blocker (Fixed, Needs Deploy)

### Problem
Akash deploy fails during model download. The `resolve_model()` function in `startup.sh` used **lowercase** filenames (`qwen3-8b-q4_k_m.gguf`) but HuggingFace repos use **PascalCase** (`Qwen3-8B-Q4_K_M.gguf`), causing a 404 error.

### Error
```
📥 Downloading qwen3-8b-q4_k_m.gguf from Qwen/Qwen3-8B-GGUF...
❌ Failed to download qwen3-8b-q4_k_m.gguf
# Underlying: 404 Not Found on https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/qwen3-8b-q4_k_m.gguf
```

### Fix Applied
`deploy/docker/startup.sh` → `resolve_model()` updated with **verified** filenames from HuggingFace:

| Model Tag | HF Repo | Correct Filename | Size |
|-----------|---------|-------------------|------|
| `qwen3:32b` | `Qwen/Qwen3-32B-GGUF` | `Qwen3-32B-Q4_K_M.gguf` | 19.8 GB |
| `qwen3:8b` | `Qwen/Qwen3-8B-GGUF` | `Qwen3-8B-Q4_K_M.gguf` | 5.03 GB |
| `qwen3:4b` | `Qwen/Qwen3-4B-GGUF` | `Qwen3-4B-Q4_K_M.gguf` | 2.5 GB |
| `qwen3:1.7b` | `Qwen/Qwen3-1.7B-GGUF` | `Qwen3-1.7B-Q8_0.gguf` | 1.83 GB |

**Note:** The 1.7B model only has Q8_0 quantization (no Q4_K_M available).

### Next Step
```bash
./scripts/trinity-deploy-production.sh test
```
This will rebuild the Docker image and deploy to Akash test tier with the corrected filenames.

---

## Phase 1: Temperature Routing — ✅ COMPLETE

Maps query type to sampling temperature instead of hardcoded 0.7 everywhere.

| Classification | Temperature | Use Case |
|----------------|-------------|----------|
| Code | `0.1` | Deterministic code generation |
| Factual | `0.3` | Factual recall, Q&A |
| Conversational | `0.7` | Chat, creative, general |

**Files modified:**
- `backend/config.py` — `TEMPERATURE_CODE`, `TEMPERATURE_FACTUAL`, `TEMPERATURE_CONVERSATIONAL`
- `backend/services/query_classifier.py` — `classify_temperature()` function
- `backend/services/context_loader.py` — `temperature` field on `RequestContext` dataclass
- `backend/routes/generate.py` — passes temperature through to pipeline
- `backend/services/pipeline.py` — accepts + forwards temperature

**Tests:** 16 new tests in `backend/tests/unit/test_temperature_routing.py`, all pass.

---

## Phase 2: Tiny Classifiers — ✅ COMPLETE (minor gaps)

Replaced all hardcoded regex patterns with trained ByteTransformer models (~100K params, <10ms inference, pure numpy).

### Files created
| File | Purpose |
|------|---------|
| `backend/services/tiny_classifier.py` | ByteTransformer inference (pure numpy, no PyTorch at runtime) |
| `backend/models/query_classifier.npz` | Trained query classifier weights (366KB, 7 classes) |
| `backend/models/tool_detector.npz` | Trained tool detector weights (369KB, 16 classes) |
| `scripts/generate_training_data.py` | Training data generator (seeds + augmentation) |
| `scripts/train_classifiers.py` | PyTorch training script (dev dependency only) |
| `backend/tests/unit/test_tiny_classifier.py` | 32 tests |

### Files rewritten (regex deleted)
- `backend/services/query_classifier.py` — 308 → 165 lines, all regex + word lists removed
- `backend/services/tools.py` — `detect_tools_needed()` reduced from 180 lines of regex to 5-line classifier call

### Known Minor Gaps (Low Priority)
1. **Missing `validate_classifiers.py`** — Plan called for a validation script but never created. Not blocking.
2. **Old regex functions not fully deleted** — `is_trivial_smalltalk()`, `is_personal_disclosure()`, etc. still exist as thin wrappers around the classifier. Plan said "delete" but they were refactored instead. Works fine, just extra indirection.
3. **Tool detector uses softmax, not sigmoid** — Plan said multi-label (sigmoid) but multi-class (softmax) was implemented because multi-label only achieved 39% accuracy. Single tool prediction works because the ReAct loop discovers additional tools.

**Tests:** 32 new tests in `backend/tests/unit/test_tiny_classifier.py`, all pass.

---

## Phase 3: llama-server Migration — ✅ CODE COMPLETE

### Architecture

```
┌──────────────────────────────────────────────────────┐
│  Akash Container (single pod)                         │
│                                                       │
│  llama-server (chat)     port 8081 (internal)         │
│  ├── Model: Qwen3-32B-Q4_K_M.gguf (prod)            │
│  ├── --ctx-size 65536                                 │
│  ├── --n-gpu-layers -1 (full GPU offload)            │
│  ├── --cache-type-k q8_0 --cache-type-v q8_0        │
│  └── --cont-batching                                  │
│                                                       │
│  llama-server (ingest)   port 8082 (internal)         │
│  ├── Model: Qwen3-8B-Q4_K_M.gguf                    │
│  ├── --ctx-size 8192                                  │
│  └── --cont-batching                                  │
│                                                       │
│  Flask server            port 8000 → exposed as :80   │
│  └── LlamaServerProvider → localhost:8081/8082        │
│                                                       │
│  startup.sh (PID 1)                                   │
│  ├── Downloads GGUF models via hf_hub_download()     │
│  ├── Starts both llama-servers as background procs    │
│  ├── Waits for /health on both                        │
│  ├── Starts Flask                                     │
│  └── Signal trap for clean shutdown                   │
└──────────────────────────────────────────────────────┘
```

### Step-by-Step Status

| Step | Description | Status | Notes |
|------|-------------|--------|-------|
| **3a** | Create `LlamaServerProvider` | ✅ | `backend/services/llama_server_provider.py` (~288 lines) |
| **3b** | Config vars + provider factory | ✅ | Factory only creates LlamaServerProvider now |
| **3c** | Verification deploy | ⏭ Skipped | No Akash access during code session |
| **3d** | Refactor `profile_extractor.py` | ✅ | No more direct Ollama HTTP calls |
| **3e** | Delete Ollama provider code | ✅ | `ollama_provider.py` + `ollama.py` deleted |
| **3f** | Docker/deployment cleanup | ✅ | Dockerfile + startup.sh + Akash YAMLs + health.py |

### Key Implementation Details

**LlamaServerProvider** (`backend/services/llama_server_provider.py`):
- Implements `LLMProvider` ABC with OpenAI-compatible endpoints
- `generate()`/`generate_stream()` → `/v1/completions`
- `chat()`/`chat_stream()` → `/v1/chat/completions`
- SSE streaming format (`data: {json}\n\n`, terminated by `data: [DONE]`)
- Does NOT pass `think=False` — `think_filter.py` in the pipeline strips `<think>` blocks
- Handles `tools` parameter for ReAct loop
- `check_connection()` → `GET /health`

**Provider Factory** (`backend/services/provider_factory.py`):
- Fully rewritten — only creates `LlamaServerProvider` (Ollama code deleted)
- Singletons cached by `(backend, host, model, num_ctx)` tuple
- `get_provider()` for chat, `get_ingest_provider()` for ingest

**Dockerfile** (`deploy/docker/Dockerfile`):
- Multi-stage: copies pre-built binary from `ghcr.io/ggml-org/llama.cpp:server-cuda`
- Runtime base: `ubuntu:22.04` (not NVIDIA image — CUDA runtime libs are copied in)
- No source compilation (QEMU can't run nvcc for cross-platform builds)
- Image size: ~1.25GB (models NOT baked in — downloaded at startup)
- llama-server version: v8115

**startup.sh** (`deploy/docker/startup.sh`):
- PID 1 process manager with SIGTERM/SIGINT trap
- Downloads models via Python `hf_hub_download()` API (NOT `huggingface-cli` — entry point breaks due to pip upgrade)
- Sets `LD_LIBRARY_PATH=/usr/local/lib` for CUDA shared libs
- Starts 2 llama-server instances (background, tracked PIDs)
- Waits for `/health` on both servers (600s timeout for chat, 300s for ingest)
- Starts Flask as foreground process

**Akash YAMLs** (`deploy/akash/deploy-production.yaml`, `deploy/akash/deploy-test.yaml`):
- `MODEL_BACKEND=llama-server`
- `LLAMA_SERVER_CHAT_PORT=8081`, `LLAMA_SERVER_INGEST_PORT=8082`
- Mount changed from `/home/trinity/.ollama` → `/home/trinity/.models`
- Removed `OLLAMA_CHAT_HOST`, `OLLAMA_INGEST_HOST`, `OLLAMA_HOST`
- Kept `OLLAMA_CHAT_MODEL`, `OLLAMA_INGEST_MODEL` (still used as model name vars in config.py)

**Health endpoints** (`backend/routes/health.py`):
- Both `/health` and `/health/icp` now return `"llm_connected"` alongside backward-compat `"ollama_connected"`

**Frontend types** (`trinity-icp/src-react/types/api.ts`):
- Added `llm_connected` to `HealthResponse` type

---

## Deployment Issues Resolved During This Session

### Issue 1: cmake/CUDA Build Failure
**Problem:** Original Dockerfile compiled llama.cpp from source with CUDA. Docker cross-compilation (macOS ARM → linux/amd64 via QEMU emulation) can't run `nvcc`.  
**Fix:** Rewrote Dockerfile to copy pre-built binary from official `ghcr.io/ggml-org/llama.cpp:server-cuda` image.

### Issue 2: huggingface-cli Not Found
**Problem:** `pip3 install --upgrade pip` in step 6 of Dockerfile destroyed the `huggingface-cli` entry point script installed as a dependency of fastembed.  
**Fix:** Replaced all `huggingface-cli` calls with direct Python API: `python3 -c 'from huggingface_hub import hf_hub_download; ...'`

### Issue 3: HuggingFace 404 (CURRENT)
**Problem:** `resolve_model()` used lowercase filenames (`qwen3-8b-q4_k_m.gguf`) but HuggingFace uses PascalCase (`Qwen3-8B-Q4_K_M.gguf`).  
**Fix:** Updated `resolve_model()` with verified filenames from HuggingFace file listings. **Applied but NOT yet deployed.**

---

## Files Modified/Created in This Overhaul

### Created
| File | Phase |
|------|-------|
| `backend/services/tiny_classifier.py` | 2 |
| `backend/models/query_classifier.npz` | 2 |
| `backend/models/tool_detector.npz` | 2 |
| `backend/tests/unit/test_tiny_classifier.py` | 2 |
| `scripts/generate_training_data.py` | 2 |
| `scripts/train_classifiers.py` | 2 |
| `data/training_queries.jsonl` | 2 |
| `data/tool_training.jsonl` | 2 |
| `backend/services/llama_server_provider.py` | 3 |
| `deploy/docker/startup.sh` | 3 |

### Modified
| File | Phase | What Changed |
|------|-------|-------------|
| `backend/config.py` | 1, 3 | Temperature constants, LLAMA_SERVER_* ports, MODEL_BACKEND default → "llama-server" |
| `backend/services/query_classifier.py` | 1, 2 | `classify_temperature()`, all regex replaced with classifier calls |
| `backend/services/context_loader.py` | 1 | `temperature` field on `RequestContext` |
| `backend/routes/generate.py` | 1 | Temperature threading |
| `backend/services/pipeline.py` | 1 | Temperature threading |
| `backend/services/tools.py` | 2 | `detect_tools_needed()` now uses classifier |
| `backend/services/provider_factory.py` | 3 | Fully rewritten — only LlamaServerProvider |
| `backend/services/profile_extractor.py` | 3 | Uses LLMProvider instead of direct HTTP |
| `backend/services/ingestion_worker.py` | 3 | Uses `get_ingest_provider().chat()` |
| `backend/services/agent.py` | 3 | Removed Ollama branch |
| `backend/routes/health.py` | 3 | Added `llm_connected` key |
| `deploy/docker/Dockerfile` | 3 | Complete rewrite (pre-built binary) |
| `deploy/akash/deploy-production.yaml` | 3 | llama-server env vars |
| `deploy/akash/deploy-test.yaml` | 3 | llama-server env vars |
| `trinity-icp/src-react/types/api.ts` | 3 | Added `llm_connected` type |

### Deleted
| File | Phase | Reason |
|------|-------|--------|
| `backend/services/ollama_provider.py` | 3 | Replaced by `llama_server_provider.py` |
| `backend/services/ollama.py` | 3 | Legacy helpers, no longer needed |
| `backend/tests/unit/test_ollama.py` | 3 | Tests for deleted modules |

---

## Residual Cleanup (Low Priority)

These are cosmetic/cleanup items that work correctly as-is:

1. **`OLLAMA_*` env var names in `config.py`:** `OLLAMA_CHAT_MODEL`, `OLLAMA_INGEST_MODEL` are still used as "the model name" vars even though Ollama is gone. Could rename to `CHAT_MODEL_NAME`/`INGEST_MODEL_NAME` but requires updating Akash YAMLs and deploy scripts.

2. **Dead config vars:** `OLLAMA_HOST`, `OLLAMA_CHAT_HOST`, `OLLAMA_INGEST_HOST` are still defined in `config.py` but unused by new code.

3. **CODEBASE-MAP.md outdated:** `docs/ai-context/CODEBASE-MAP.md` still references `ollama_provider.py`, `ollama.py`, and "Ollama" in the LLM Providers section. Should be updated to reflect `llama_server_provider.py`.

4. **`backend/services/structured.py`:** May contain dead Ollama-specific code paths.

---

## How to Deploy

### Test Tier
```bash
cd /Users/gduby/Documents/Trinity/Trinity
./scripts/trinity-deploy-production.sh test
```

### Production
```bash
./scripts/trinity-deploy-production.sh production
```

### Docker Build Only (Verify Image)
```bash
docker build --platform linux/amd64 -t gdubx/trinity-inference:latest -f deploy/docker/Dockerfile .
```

### Run Tests
```bash
cd backend && python -m pytest tests/ -x -q
```

### Verify Model Download URL (Quick Check)
```bash
# Should return 200:
curl -I "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf"
```

---

## What the Next Engineer Should Do

1. **Deploy to test tier** — `./scripts/trinity-deploy-production.sh test` — this tests the full chain: Docker build → push → Akash deploy → model download → llama-server startup → Flask startup
2. **Check Akash logs** — Look for `✅ Model cached:` or `✅ Downloaded:` messages, then `✅ chat llama-server healthy`, then `🌐 Starting Flask`
3. **Run a smoke test** — `curl https://<test-domain>/health` should return `"llm_connected": true`
4. **Send a chat message** — Verify end-to-end inference works
5. **If test passes → deploy production** — `./scripts/trinity-deploy-production.sh production` (note: 32B model takes ~10-20 min to download on first deploy)
6. **Optional cleanup** — Rename `OLLAMA_*` env vars, update CODEBASE-MAP.md

---

## Key Reference Files

| Task | File(s) |
|------|---------|
| Understand the full overhaul plan | `docs/plans/microgpt-overhaul-plan.md` |
| Understand project architecture | `docs/ai-context/CLAUDE.md`, `docs/ai-context/CODEBASE-MAP.md` |
| Debug model downloads | `deploy/docker/startup.sh` → `resolve_model()` + `download_model()` |
| Debug llama-server issues | `deploy/docker/startup.sh` → step 3 (server start) + step 4 (health wait) |
| Debug inference issues | `backend/services/llama_server_provider.py` |
| Debug provider creation | `backend/services/provider_factory.py` |
| Docker image structure | `deploy/docker/Dockerfile` |
| Akash deployment config | `deploy/akash/deploy-production.yaml`, `deploy/akash/deploy-test.yaml` |
| Run tests | `cd backend && python -m pytest tests/ -x -q` (1010 pass, 0 fail) |
