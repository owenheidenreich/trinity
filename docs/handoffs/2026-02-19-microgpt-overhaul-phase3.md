# Handoff: MicroGPT Overhaul — Phase 3 Remaining (Ollama → llama-server)

**Date:** February 19, 2026
**Context:** Phases 1-2 of the MicroGPT overhaul are complete. Phase 3 (Ollama → llama-server migration) was started but not yet implemented.
**Priority:** P1 — Infrastructure upgrade to unlock KV cache persistence and native LoRA loading
**Branch:** `main` (all Phase 1-2 changes are uncommitted but working)
**Full plan:** [docs/plans/microgpt-overhaul-plan.md](../plans/microgpt-overhaul-plan.md)

---

## What's Already Done

### Phase 1: Temperature Routing ✅

Maps query type to sampling temperature instead of hardcoded 0.7 everywhere.

| File | What Changed |
|------|-------------|
| `backend/config.py` | Added `TEMPERATURE_CODE=0.1`, `TEMPERATURE_FACTUAL=0.3`, `TEMPERATURE_CONVERSATIONAL=0.7` (env-configurable) |
| `backend/services/query_classifier.py` | Added `classify_temperature()` function |
| `backend/services/context_loader.py` | Added `temperature: float = 0.7` field to `RequestContext` dataclass, computed in `load_context()` |
| `backend/routes/generate.py` | Passes `temperature=ctx.temperature` to `pipeline.process_streaming()` |
| `backend/services/pipeline.py` | Accepts `temperature` param, passes to `self.client.chat_stream()` and `react.execute_streaming()` |
| `backend/tests/unit/test_temperature_routing.py` | 16 new tests, all pass |

**Note:** `react_loop.py` already accepted `temperature` as a parameter — no changes were needed there.

### Phase 2: Tiny Classifiers (Replace ALL Regex) ✅

Replaced all hardcoded regex patterns and word lists with trained 50K-parameter ByteTransformer models.

#### Files Created
| File | Purpose |
|------|---------|
| `backend/services/tiny_classifier.py` | `ByteTransformer` class — pure numpy inference, no PyTorch at runtime. ~100K params, <10ms on CPU. Public API: `classify_query(text) → (label, confidence)`, `detect_tools(text) → [tool_names]` |
| `backend/models/query_classifier.npz` | Trained query classifier weights (366KB). 7 classes: smalltalk, disclosure, code, lightweight, memory_recall, preference, general. Training accuracy: 94.4% |
| `backend/models/tool_detector.npz` | Trained tool detector weights (369KB). 16 classes: 15 tools + no_tool. Multi-class (softmax, not multi-label). Training accuracy: 100% |
| `scripts/generate_training_data.py` | Generates training data from curated seed phrases + augmentation (capitalization, fillers, punctuation, typos). ~970 query examples, ~2035 tool examples. No longer imports from query_classifier.py (the old regex functions were deleted) |
| `scripts/train_classifiers.py` | PyTorch training script. `TinyTransformer(nn.Module)` → exports to `.npz` via `export_to_npz()`. Config: VOCAB_SIZE=256, D_MODEL=64, N_HEADS=4, N_LAYERS=2, D_FFN=128, MAX_SEQ=256. Query: 30 epochs, Tool: 50 epochs. Requires `pip install torch` (dev dependency only) |
| `backend/tests/unit/test_tiny_classifier.py` | 32 tests covering model loading, forward pass, classification accuracy, tool detection, edge cases (empty/long/unicode input), speed benchmark, integration with query_classifier.py and tools.py |
| `data/training_queries.jsonl` | Generated query training data |
| `data/tool_training.jsonl` | Generated tool training data |

#### Files Rewritten (Regex Deleted)
| File | What Changed |
|------|-------------|
| `backend/services/query_classifier.py` | **All regex patterns, word lists, and regex-based functions DELETED.** File went from 308 lines → 165 lines. Functions like `is_trivial_smalltalk()`, `is_personal_disclosure()`, `requests_personal_memory()`, `is_code_generation_request()` now call `classify_query()` from `tiny_classifier.py` internally. `ContextLevel` enum, `smalltalk_fast_response()`, `classify_temperature()`, and `classify_context_level()` retained with classifier-backed implementations. Confidence threshold: 0.75 — below this defaults to `ContextLevel.FULL`. |
| `backend/services/tools.py` | `detect_tools_needed()` — **180 lines of regex patterns DELETED.** Replaced with 5-line function that calls `detect_tools()` from `tiny_classifier.py`. |
| `backend/services/memory_eval.py` | Updated import: now imports `requests_personal_memory` from `query_classifier` (was importing dead `_question_requests_personal_memory` from agent.py). Added fallback `_format_user_memory` for missing import. |
| `backend/tests/unit/test_memory_phase3.py` | Updated two test methods to import from `services.query_classifier` instead of `services.agent` |
| `backend/tests/unit/test_chat_lifecycle.py` | Updated `test_write_file_with_explicit_path_triggers_filesystem_tools` and `test_debug_code_request_triggers_code_display` to accept classifier-compatible tool names (the old tests expected regex-specific routing) |

#### Key Architecture Decisions
- **Tool detector is multi-class (softmax), NOT multi-label (sigmoid).** Original plan said multi-label but it only achieved 39% exact-match accuracy. Multi-class works because most queries need 0 or 1 tool — the ReAct loop discovers additional tools dynamically. The `detect_tools()` function returns `[]` for "no_tool" predictions or low confidence.
- **Training data uses curated seeds + augmentation, NOT regex distillation.** The original plan called for regex-as-teacher distillation, but the regex functions were deleted from `query_classifier.py`, so `generate_training_data.py` now uses only seed phrases. The `label_query()` function is a stub that returns "general" — it's only used for the regex-agreement stat printout.
- **Model files are ~370KB each** (slightly over the plan's <200KB target). This is because the actual param count is ~100K, not 50K as originally estimated. Still <400KB and loads instantly.
- **Padding fix was critical.** Training pads all inputs to 256 bytes with zeros, so inference MUST do the same. The initial implementation used variable-length input which produced garbage results. Fixed by adding `byte_ids = np.zeros(self.MAX_SEQ, dtype=np.int64)` padding in `forward()`.

#### Test Results
- **1028 tests pass, 0 fail, 39 skip** (full test suite)
- Phase 1 tests: 16 pass
- Phase 2 tests: 32 pass

---

## What Remains: Phase 3 (Ollama → llama-server)

### Goal
Drop Ollama. Use llama-server (llama.cpp HTTP server) directly. This unlocks:
- **KV cache persistence** via `--prompt-cache` flag
- **Native LoRA loading** via `--lora` flag
- **OpenAI-compatible API** (`/v1/chat/completions`)
- **Direct model control** (no middleman)

### Why
Ollama wraps llama.cpp but hides critical features. Trinity already has a clean `LLMProvider` ABC abstraction, so the provider swap is isolated behind the interface.

### Migration Steps (6 steps, each with explicit cleanup)

#### Step 3a: Create `LlamaServerProvider` (additive, nothing deleted)
**Create:** `backend/services/llama_server_provider.py`

This implements `LLMProvider` ABC using OpenAI-compatible `/v1/chat/completions` API. The existing `OllamaProvider` uses Ollama's custom `/api/chat` and `/api/generate` endpoints.

Key interface methods to implement:
```python
class LlamaServerProvider(LLMProvider):
    def generate(self, prompt, max_tokens, temperature, timeout, **kwargs) -> str
    def generate_stream(self, prompt, max_tokens, temperature, timeout, **kwargs) -> Generator
    def chat(self, messages, max_tokens, temperature, timeout, tools, raw_message, **kwargs) -> str
    def chat_stream(self, messages, max_tokens, temperature, timeout, **kwargs) -> Generator
    def check_connection(self) -> bool
    def warmup(self) -> bool
```

The yield contract for streaming: `yield str` for tokens, `yield {"__done_reason": "stop"}` for stream end.

**Important:** llama-server uses OpenAI-compatible SSE format (`data: {"choices": [{"delta": {"content": "..."}}]}`) NOT Ollama's NDJSON format.

**`think=False` handling:** Ollama has a `think` parameter. llama-server does not. The existing `think_filter.py` in the streaming pipeline already strips `<think>` blocks — no changes needed. But the `LlamaServerProvider` should NOT pass `think` to the API.

#### Step 3b: Update `provider_factory.py` + `config.py`
**Modify:** `backend/services/provider_factory.py` — Add `MODEL_BACKEND="llama-server"` branch that creates `LlamaServerProvider` instead of `OllamaProvider`.

**Modify:** `backend/config.py` — Add new config vars:
```python
LLAMA_SERVER_CHAT_PORT = int(os.getenv("LLAMA_SERVER_CHAT_PORT", "8081"))
LLAMA_SERVER_INGEST_PORT = int(os.getenv("LLAMA_SERVER_INGEST_PORT", "8082"))
PROMPT_CACHE_DIR = os.getenv("PROMPT_CACHE_DIR", "/data/kv_cache")
```

#### Step 3c: Deploy with llama-server for chat (verification step)
Deploy with llama-server handling chat while Ollama still handles ingestion. Verify end-to-end.

#### Step 3d: Refactor `profile_extractor.py` to use `LLMProvider`
**Modify:** `backend/services/profile_extractor.py` — Currently makes direct HTTP calls to Ollama. Refactor to use `get_provider()` from `provider_factory.py`.

**Delete:** Direct Ollama HTTP calls from `profile_extractor.py`.

#### Step 3e: Delete Ollama provider code
**Delete:** `backend/services/ollama_provider.py`
**Delete:** `backend/services/ollama.py` (legacy helpers)

#### Step 3f: Remove Ollama from Docker/deployment
**Modify:** `deploy/docker/Dockerfile` — Replace Ollama install with llama.cpp build + GGUF model download
**Modify/Replace:** `deploy/docker/startup.sh` → `deploy/docker/startup_llama.sh`
**Modify:** `deploy/akash/deploy-production.yaml` — Update env vars
**Modify:** `deploy/akash/deploy-test.yaml` — Update env vars
**Modify:** `backend/routes/health.py` — Update health check

### Target Architecture

```
┌──────────────────────────────────────────────┐
│  Akash Container                              │
│                                               │
│  llama-server (chat)     port 8081            │
│  ├── Model: qwen3-32b.gguf                   │
│  ├── --ctx-size 65536                         │
│  ├── --prompt-cache /data/kv_cache/           │
│  └── --lora /data/adapters/<principal>.gguf   │
│                                               │
│  llama-server (ingest)   port 8082            │
│  ├── Model: qwen3-8b.gguf                    │
│  └── --ctx-size 8192                          │
│                                               │
│  Flask server            port 5000            │
│  └── LlamaServerProvider → localhost:8081/82  │
└──────────────────────────────────────────────┘
```

### Model Management
GGUF models downloaded at startup from HuggingFace:
```bash
huggingface-cli download Qwen/Qwen3-32B-GGUF qwen3-32b-q4_k_m.gguf \
    --local-dir /home/trinity/.models/
```
Cached on Akash persistent volume.

---

## Key Files to Read Before Starting

| File | Why |
|------|-----|
| `backend/services/llm_provider.py` | The ABC interface you're implementing — 135 lines, defines all methods |
| `backend/services/ollama_provider.py` | The existing implementation you're replacing — 280 lines, shows exact yield contract and error handling patterns |
| `backend/services/provider_factory.py` | Where providers are created/cached — 77 lines, needs `llama-server` branch |
| `backend/config.py` | All config constants — add `LLAMA_SERVER_*` vars here |
| `backend/services/pipeline.py` | Main streaming pipeline — calls `self.client.chat_stream()` and `self.client.chat()` |
| `backend/services/react_loop.py` | ReAct loop — calls `self.provider.chat()` with tools |
| `backend/services/profile_extractor.py` | Makes direct Ollama HTTP calls — needs refactoring to use LLMProvider |
| `deploy/docker/Dockerfile` | Docker build — currently installs Ollama |
| `deploy/docker/startup.sh` | Container startup — currently starts `ollama serve` + `ollama pull` |
| `deploy/akash/deploy-production.yaml` | Akash deployment — has OLLAMA_* env vars |

## Critical Gotchas

1. **Docker builds MUST use `--platform linux/amd64`** — Dev machine is Apple Silicon (arm64) but Akash providers are amd64
2. **`think_filter.py` already strips `<think>` blocks** — Don't add `think=False` to llama-server calls. The streaming pipeline handles it.
3. **The `chat()` method must handle `tools` parameter** — llama-server supports OpenAI-format tool definitions. The ReAct loop passes `tools` to `provider.chat()`.
4. **The `chat()` method must handle `raw_message=True`** — When True, return the full message dict (including tool_calls) instead of just content string.
5. **`num_ctx` maps to `--ctx-size` on llama-server** — Currently 65536 for chat.
6. **Streaming format difference:** Ollama uses NDJSON (one JSON per line). llama-server uses SSE (`data: {json}\n\n` lines, ending with `data: [DONE]`).
7. **The `generate()` and `generate_stream()` methods** use `/v1/completions` (NOT `/v1/chat/completions`). Or you can wrap the prompt in a chat message — llama-server supports both.

## Uncommitted Changes

All Phase 1-2 changes are currently uncommitted on `main`. Run `git status` to see the full list. Key modified files:
- `backend/services/query_classifier.py` (rewritten — regex deleted)
- `backend/services/tools.py` (detect_tools_needed regex deleted)
- `backend/config.py` (temperature constants added)
- `backend/services/context_loader.py` (temperature field added)
- `backend/routes/generate.py` (temperature threading)
- `backend/services/pipeline.py` (temperature threading)

Key new files:
- `backend/services/tiny_classifier.py`
- `backend/models/query_classifier.npz`
- `backend/models/tool_detector.npz`
- `scripts/generate_training_data.py`
- `scripts/train_classifiers.py`
- `backend/tests/unit/test_tiny_classifier.py`
- `backend/tests/unit/test_temperature_routing.py`

## Postponed (Future — Separate Planning Sessions)

| Feature | Why Postponed |
|---------|--------------|
| Multi-layer pipeline | Memory/retrieval architecture still evolving |
| LoRA adapters | Needs dedicated planning (training triggers, versioning, conversion) |
| DPO / user feedback | Needs thumbs up/down UI + user volume |
| Adapter marketplace | Needs compatible base model across users |

## Verification Checklist for Phase 3

- [ ] `LlamaServerProvider` implements all `LLMProvider` ABC methods
- [ ] `provider_factory.py` routes to correct provider based on `MODEL_BACKEND`
- [ ] All existing tests pass (1028+)
- [ ] Health check endpoint works with llama-server
- [ ] Chat streaming works end-to-end
- [ ] ReAct loop tool calling works (tools parameter passed correctly)
- [ ] Ingestion worker uses ingest instance (port 8082)
- [ ] `think_filter.py` strips `<think>` blocks without `think=False`
- [ ] Docker build succeeds with `--platform linux/amd64`
- [ ] Akash deploy configs updated
- [ ] No Ollama code remains after Step 3f
- [ ] KV cache files created in `/data/kv_cache/` (stretch goal)
