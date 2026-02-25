# Trinity MicroGPT Overhaul Plan

## Context

Trinity's pipeline has two categories of problems:

**1. Hardcoded intelligence.** Query classification, tool detection, and smalltalk detection use regex patterns and word lists. These produce false positives/negatives, can't generalize to unseen phrasing, and grow into messy patchwork. Karpathy's microgpt shows the core GPT algorithm works at any scale — a 50K-parameter model trained on your own data will outperform regex while running in <1ms on CPU.

**2. Abstracted-away capabilities.** Ollama wraps llama.cpp but hides critical features: KV cache persistence (`--prompt-cache`), native LoRA loading (`--lora`), and direct model control. Dropping Ollama for llama-server removes the middleman.

**Training data:** state.db currently contains test junk. Doesn't matter — tiny classifiers are trained via distillation (existing regex rules auto-label synthetic data) + hand-curated seeds (100-500 examples). Real user data improves them later but isn't required.

---

## Phase 1: Temperature Routing

**Goal:** Map query type to sampling temperature. Code → 0.1, tool use → 0.3, conversation → 0.7.

Currently hardcoded at `0.7` everywhere. `pipeline.py` calls `self.client.chat_stream(messages, max_tokens, timeout=timeout, think=False)` with no temperature argument.

### Changes

| File | Change |
|------|--------|
| [config.py](backend/config.py) | Add `TEMPERATURE_CODE=0.1`, `TEMPERATURE_FACTUAL=0.3`, `TEMPERATURE_CONVERSATIONAL=0.7` env-configurable constants |
| [query_classifier.py](backend/services/query_classifier.py) | Add `classify_temperature(prompt, context_level, is_code, tools_needed) → float` |
| [context_loader.py](backend/services/context_loader.py) | Add `temperature: float = 0.7` to `RequestContext` dataclass. Compute in `load_context()` after tool detection |
| [routes/generate.py](backend/routes/generate.py) | Pass `temperature=ctx.temperature` to `pipeline.process_streaming()` |
| [pipeline.py](backend/services/pipeline.py) | Accept `temperature` param, pass to `self.client.chat_stream()` and `react.execute_streaming()` |

Note: `react_loop.py` already accepts `temperature` as a parameter — just needs the caller to pass it.

### Tests
- New: `tests/unit/test_temperature_routing.py`
- Verify each query type maps to correct temperature
- Verify temperature reaches LLM provider (mock `chat_stream`, check kwarg)
- All existing tests pass unchanged

---

## Phase 2: Tiny Classifiers (Replace Regex/Hardcoded Lists)

**Goal:** Replace all hardcoded word lists and regex patterns with learned classifiers. **Delete the old regex code** — no hybrid fallback, no legacy backup.

### What Gets Replaced and Deleted

| Function | Location | What Happens |
|----------|----------|-------------|
| `is_trivial_smalltalk()` | [query_classifier.py:71-87](backend/services/query_classifier.py) | **Deleted** — replaced by classifier |
| `is_personal_disclosure()` | [query_classifier.py:124-133](backend/services/query_classifier.py) | **Deleted** — replaced by classifier |
| `is_code_generation_request()` | [query_classifier.py:188-195](backend/services/query_classifier.py) | **Deleted** — replaced by classifier |
| `_is_lightweight_prompt()` | [query_classifier.py:224-238](backend/services/query_classifier.py) | **Deleted** — replaced by classifier |
| `detect_tools_needed()` regex body | [tools.py:330-512](backend/services/tools.py) | **Deleted** — 180 lines of regex patterns removed |
| `_SMALLTALK_CANONICAL` | [query_classifier.py](backend/services/query_classifier.py) | **Deleted** |
| `_SMALLTALK_GREETING_TOKENS` | [query_classifier.py](backend/services/query_classifier.py) | **Deleted** |
| `_PERSONAL_DISCLOSURE_PATTERNS` | [query_classifier.py](backend/services/query_classifier.py) | **Deleted** |
| `_CODE_REQUEST_PATTERNS` | [query_classifier.py](backend/services/query_classifier.py) | **Deleted** |
| `_MEMORY_SIGNALS`, `_RETRIEVAL_SIGNALS` | [query_classifier.py](backend/services/query_classifier.py) | **Deleted** |

### Safety Net: Default to Full (Not Regex)

When the classifier isn't confident, default to `ContextLevel.FULL` — give the query everything. The penalty for uncertainty is extra compute, never a wrong response.

```python
def classify_context_level(prompt: str) -> ContextLevel:
    label, confidence = classify_query(prompt)
    if confidence >= 0.75:
        return LABEL_TO_LEVEL[label]
    return ContextLevel.FULL  # When in doubt, give it everything
```

No regex fallback. One code path. One system to debug.

### Architecture: ByteTransformer

Two tiny models, same architecture:

- **Input:** Raw UTF-8 bytes (vocabulary = 256, no tokenizer needed)
- **Model:** 2-layer transformer, 64-dim embeddings, 4 attention heads, 128-dim FFN
- **Max sequence:** 256 bytes
- **Size:** ~50K parameters, <200KB on disk
- **Speed:** <1ms on CPU
- **Runtime:** Pure numpy inference (no torch at runtime)

**Query classifier** — multi-class: smalltalk / disclosure / code / lightweight / memory_recall / preference / general
**Tool detector** — multi-label: sigmoid per tool, threshold at 0.5

### Files to Create

| File | Purpose |
|------|---------|
| `backend/services/tiny_classifier.py` | `ByteTransformer` class (pure numpy), `classify_query()`, `detect_tools()` |
| `backend/models/query_classifier.npz` | Trained weights (~150KB) |
| `backend/models/tool_detector.npz` | Trained weights (~180KB) |
| `scripts/generate_training_data.py` | Distillation: synthetic data labeled by existing regex |
| `scripts/train_classifiers.py` | PyTorch training, exports to numpy `.npz` |
| `scripts/validate_classifiers.py` | Accuracy validation against test set |
| `backend/tests/unit/test_tiny_classifier.py` | Unit tests |

### Files to Modify

| File | Change |
|------|--------|
| [query_classifier.py](backend/services/query_classifier.py) | Delete all regex/word-list functions. Replace `classify_context_level()` with classifier call + FULL fallback. Keep `ContextLevel` enum, `smalltalk_fast_response()`, `classify_temperature()` |
| [tools.py](backend/services/tools.py) | Delete 180 lines of regex patterns from `detect_tools_needed()`. Replace with `detect_tools()` call |
| [Dockerfile](deploy/docker/Dockerfile) | Add `COPY backend/models/ ./models/` |

### Training Pipeline

1. **Distillation** — `scripts/generate_training_data.py` generates 10K+ synthetic queries, labels them with existing regex functions (the regex is the teacher during training, then gets deleted)
2. **Curated seeds** — 100-500 hand-labeled edge cases per category, including cases the regex gets wrong
3. **Train** — `scripts/train_classifiers.py`: PyTorch training loop → export to `.npz`
4. **Validate** — `scripts/validate_classifiers.py`: accuracy on held-out test set (target >95%)

The classifiers are trained **once** and shipped as static files. No continuous training. No drift.

### Tests
- Unit tests for ByteTransformer forward pass (shape, dtype, edge cases)
- Classification accuracy on test set >95%
- Latency benchmark: <1ms on CPU
- Model files < 200KB each
- Docker build succeeds with `--platform linux/amd64`

---

## Phase 3: Replace Ollama with llama-server

**Goal:** Drop Ollama. Use llama-server (llama.cpp) directly to unlock KV cache persistence and native LoRA loading.

**Migration strategy:** Gradual with explicit cleanup milestones. Each step has a clear "what gets deleted."

### Why

| Feature | Ollama | llama-server |
|---------|--------|-------------|
| KV cache persistence | Not exposed | `--prompt-cache`, `--prompt-cache-all` |
| Native LoRA | Modelfile workaround | `--lora /path/to/adapter.gguf` |
| API | Custom `/api/chat` + `/api/generate` | OpenAI-compatible `/v1/chat/completions` |
| Model management | `ollama pull` (convenient) | Manual GGUF download (more control) |
| Think blocks | `think=False` parameter | Filter via `think_filter.py` (already exists) |

### Migration Steps with Cleanup

| Step | Action | What Gets Deleted |
|------|--------|-------------------|
| **3a** | Create `LlamaServerProvider(LLMProvider)` | Nothing yet — additive |
| **3b** | Add `MODEL_BACKEND=llama-server` config branch in `provider_factory.py` | Nothing yet |
| **3c** | Deploy with llama-server for chat, Ollama for ingest. Verify chat works. | — |
| **3d** | Refactor `profile_extractor.py` to use `LLMProvider` instead of direct HTTP | Delete direct Ollama HTTP calls from `profile_extractor.py` |
| **3e** | Move ingest to second llama-server instance | Delete `ollama_provider.py`, `ollama.py` (legacy helpers) |
| **3f** | Remove Ollama from Dockerfile + startup.sh | Delete `ollama install`, `ollama serve`, `ollama pull`. Clean break. |

**No Ollama code remains after Step 3f.** The gradual approach is about reducing risk during migration, not accumulating debt.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/services/llama_server_provider.py` | `LlamaServerProvider(LLMProvider)` — OpenAI-compatible API client |
| `deploy/docker/startup_llama.sh` | Start llama-server instances (chat + ingest) |

### Files to Modify

| File | Change |
|------|--------|
| [provider_factory.py](backend/services/provider_factory.py) | Add `MODEL_BACKEND="llama-server"` branch |
| [config.py](backend/config.py) | Add `LLAMA_SERVER_CHAT_PORT`, `LLAMA_SERVER_INGEST_PORT`, `PROMPT_CACHE_DIR` |
| [Dockerfile](deploy/docker/Dockerfile) | Replace Ollama install with llama.cpp build + GGUF model download |
| [startup.sh](deploy/docker/startup.sh) | Replace with `startup_llama.sh` logic |
| [deploy-production.yaml](deploy/akash/deploy-production.yaml) | Update env vars |
| [deploy-test.yaml](deploy/akash/deploy-test.yaml) | Update env vars |
| [profile_extractor.py](backend/services/profile_extractor.py) | Use `get_provider()` instead of direct HTTP |
| [routes/health.py](backend/routes/health.py) | Update health check |

### Files to Delete (after full migration)

| File | Why |
|------|-----|
| `backend/services/ollama_provider.py` | Replaced by `llama_server_provider.py` |
| `backend/services/ollama.py` | Legacy helpers no longer needed |
| All `OLLAMA_*` config vars | Replaced by `LLAMA_SERVER_*` vars |

### Dual Instance Architecture

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

GGUF models downloaded at startup from HuggingFace (replacing `ollama pull`):
```bash
huggingface-cli download Qwen/Qwen3-32B-GGUF qwen3-32b-q4_k_m.gguf \
    --local-dir /home/trinity/.models/
```

Cached on Akash persistent volume (same pattern as current Ollama model cache).

### KV Cache Persistence

llama-server with `--prompt-cache /data/kv_cache/` saves KV cache to disk. On next request with same prompt prefix, loads from cache instead of recomputing.

- Per-user cache files at `/data/kv_cache/<principal_id>.bin`
- Akash persistent volume at `/data/` already exists

### `think=False` → `think_filter.py`

Ollama's `think=False` is Ollama-specific. With llama-server, `think_filter.py` (already in the streaming pipeline) strips `<think>` blocks. No code changes needed — it's already wired up.

### Tests
- All existing tests pass (provider swap is behind `LLMProvider` ABC)
- Health check endpoint works
- Chat streaming works end-to-end
- Ingestion worker uses ingest instance (port 8082)
- KV cache files created in `/data/kv_cache/`
- Docker build + Akash deploy succeeds

---

## Postponed (Future Plans — Separate Planning Sessions)

| Feature | Why Postponed | Revisit When |
|---------|--------------|-------------|
| **Multi-layer pipeline** | Optimizes pipeline architecture, but the memory/retrieval strategy is still evolving. Don't optimize an architecture that's still being designed. | After memory/retrieval architecture settles |
| **LoRA adapters** | Exciting but needs dedicated planning: training triggers, adapter versioning, safetensors→GGUF conversion, base model updates. Requires Phase 3 (llama-server). | After Phases 1-3 are stable + dedicated planning session |
| **DPO / user feedback** | Needs thumbs up/down UI + volume per user. Noisy signal. | LoRA working + feedback UI |
| **Adapter marketplace** | Requires compatible base model across users. | Multiple active users with adapters |

---

## Implementation Sequence

```
Phase 1 (Temperature)           ←── No dependencies, start first
  |
  v
Phase 2 (Tiny Classifiers)      ←── Independent of Phase 1
  |                                  (can develop in parallel)
  v
Phase 3 (Ollama → llama-server) ←── Best after Phases 1-2 are stable
  |                                  (fewer moving parts during infra swap)
  |                                  Steps 3a-3f with cleanup at each step
  v
[Future: LoRA, multi-layer pipeline — separate planning sessions]
```

---

## Verification

### Phase 1 (Temperature)
- All existing tests pass
- New temperature unit tests pass
- Manual: code query → provider receives temperature=0.1
- Manual: conversational query → provider receives temperature=0.7

### Phase 2 (Tiny Classifiers)
- Old regex code fully deleted (no fallback, no hybrid)
- Classification accuracy on test set >95%
- Model files < 200KB each
- Inference latency < 1ms on CPU
- Docker build succeeds with `--platform linux/amd64`

### Phase 3 (llama-server)
- All existing tests pass
- Health check endpoint works
- Chat streaming end-to-end
- KV cache files created on disk
- Docker build + Akash deploy succeeds
- `think_filter.py` strips `<think>` blocks without `think=False`
- **No Ollama code remains** after Step 3f
