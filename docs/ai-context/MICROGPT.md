# Trinity — MicroGPT Intelligence Architecture

> **Purpose:** Complete reference for Trinity's neural classification, tool detection, temperature routing, memory, and learning systems.
> **Last Updated:** February 20, 2026
> **Read when:** Working on tool detection, temperature routing, memory extraction, training pipeline, or the learning-from-user roadmap.

---

## Philosophy

Trinity's intelligence layer is built on [Karpathy's microgpt insight](../plans/microgpt-reference-docs/microgpt_article.md): the GPT algorithm works identically at any scale. A 4K-parameter transformer uses the same architecture — embeddings, multi-head attention, residual connections, layer norm, FFN — as a 70B production model. The only differences are parameter count and training data volume.

This means we can run **tiny purpose-built classifiers** (<1ms, pure numpy, no GPU) alongside a **full 32B reasoning model** (llama-server), each doing what it does best:

| Component | Purpose | Scale | Latency |
|-----------|---------|-------|---------|
| ByteTransformer tool detector | Decide which tool (if any) a query needs | ~50K params, 369KB | <1ms CPU |
| Regex fallback (tools) | Safety net when tool classifier returns low confidence | 0 params | <1ms CPU |
| qwen3-32b (llama-server) | Reasoning, generation, tool execution | 32B params | 2-30s GPU |
| qwen3-8b (llama-server) | Memory extraction, summarization | 8B params | 1-10s GPU |

> **Note:** The query classifier model (`query_classifier.npz`) still exists but **no longer drives pipeline routing**. It was stripped to tool-detection-only in the Feb 2026 simplification. The 7-class query classifier previously routed queries to different context levels (NONE/MINIMAL/DISCLOSURE/FULL) — that branching has been removed. Every query now gets full context and an LLM call. Only the tool detector still earns its keep.

**Key principle:** Every query gets the full LLM pipeline. Tool detection (classifier + regex fallback) determines whether the ReAct loop is needed. Temperature is auto-routed per query type. The LLM handles everything — no hardcoded responses, no fast-paths, no shortcuting.

---

## Architecture Overview

```
User prompt
    │
    ▼
context_loader.load_context()
    │
    ├── 1. Load conversation context (always full)
    │       ├── Last 25 messages
    │       ├── Conversation summary
    │       └── Knowledge search (top 20 facts, scored)
    │
    ├── 2. detect_tools_needed(prompt)  ← 3-tier detection
    │       ├── ByteTransformer detect_tools() → [tool_names]
    │       ├── Regex confirmation gate (suppresses false positives when conf < 0.92)
    │       └── If empty → _regex_detect_tools() fallback
    │
    ├── 3. Detect personal disclosure
    │       └── is_personal_disclosure(prompt) → bool (triggers ingestion)
    │
    ├── 4. classify_temperature(prompt, tools_needed)
    │       ├── code → 0.1 (deterministic)
    │       ├── tool/memory → 0.3 (precise)
    │       └── everything else → 0.7 (balanced)
    │
    └── Returns RequestContext dataclass
            │
            ▼
    prompt_assembler.assemble() → token-budgeted prompt
            │
            ▼
    pipeline.process_streaming()
        ├── tools_needed → ReAct loop (up to 5 iterations, exact-duplicate guard)
        └── no tools → direct chat_stream + tool-call rescue fallback
```

**What was removed (Feb 2026 simplification):**
- `ContextLevel` branching (NONE/MINIMAL/DISCLOSURE/FULL) — every query now gets FULL context
- `smalltalk_fast_response()` — no more hardcoded responses; the LLM handles all queries
- `fast_path` parameter — removed from pipeline, agent, and generate route
- `classify_context_level()` — deprecated stub (always returns FULL)
- `is_trivial_smalltalk()` — deprecated stub (always returns False)

---

## ByteTransformer Classifiers

### Architecture

Both classifiers use the same architecture, directly mirroring Karpathy's microgpt design scaled to a useful size:

```
Input: raw UTF-8 bytes (vocab=256, no tokenizer needed)
    │
    ▼
Token embedding (256 × 64) + Positional embedding (256 × 64)
    │
    ▼
┌─ Transformer Block × 2 ─────────────────────────┐
│  Pre-norm LayerNorm                               │
│  Multi-head self-attention (4 heads, 16-dim each) │
│  Residual connection                              │
│  Pre-norm LayerNorm                               │
│  FFN: Linear(64→128) → GELU → Linear(128→64)     │
│  Residual connection                              │
└───────────────────────────────────────────────────┘
    │
    ▼
Global average pooling (256 positions → 1 vector)
    │
    ▼
Classifier head: Linear(64 → n_classes)
    │
    ▼
Softmax → (predicted_class, confidence)
```

**Key design choices:**
- **Raw bytes as input** — no tokenizer. UTF-8 bytes are the tokens (vocab_size=256). This means zero preprocessing, zero tokenizer dependencies, and the model sees exactly what came over the wire.
- **256-byte max sequence** — enough for any reasonable query. Longer inputs are truncated (still works — queries front-load intent).
- **2 layers, 4 heads** — minimal depth that still captures multi-token patterns. Karpathy showed that even 1 layer works; 2 gives meaningful attention patterns.
- **GELU activation** — same as GPT-2/3/4. The `x * sigmoid(1.702 * x)` approximation keeps it pure numpy.
- **Global average pooling** — simpler than [CLS] token, works well for classification. Every position contributes equally to the final prediction.
- **Pure numpy inference** — no PyTorch/TensorFlow at runtime. The `.npz` file IS the model. Load, matrix multiply, done.

### Two Models

**Query classifier** (`backend/models/query_classifier.npz`, 366KB) — **DEPRECATED for pipeline routing:**

The query classifier still exists as a file and can still be called, but it **no longer drives pipeline behavior**. All queries now get full context. The 7-class labels are only used internally by `classify_temperature()` to detect code queries (→ temp 0.1) and by `is_personal_disclosure()` / `requests_personal_memory()` for disclosure/memory detection. The `classify_context_level()` function is a deprecated stub that always returns `FULL`.

| Class | Meaning | Current Use |
|-------|---------|-------------|
| `smalltalk` | Greetings, acknowledgements | *Ignored — LLM handles naturally* |
| `lightweight` | "ok", "sure", "got it" | *Ignored — LLM handles naturally* |
| `disclosure` | "my name is...", "I work at..." | Used by `is_personal_disclosure()` for ingestion gating |
| `preference` | "use bullet points", "be concise" | Used by `is_personal_disclosure()` for ingestion gating |
| `code` | "write a function...", "generate code..." | Used by `classify_temperature()` → 0.1 |
| `memory_recall` | "what do you know about me?" | Used by `requests_personal_memory()` + `classify_temperature()` → 0.3 |
| `general` | Everything else | Default — no special handling |

**Tool detector** (`backend/models/tool_detector.npz`, 369KB) — **ACTIVE, primary pipeline classifier:**
| Class | Tool | Trigger Examples |
|-------|------|-----------------|
| `calculator` | calculator | "what is 2+2", "calculate 15% of 200" |
| `web_search` | web_search | "latest AI news", "bitcoin price" |
| `document_search` | document_search | "search my docs for..." |
| `code_display` | code_display | "write a python function" |
| `fact_check` | fact_check | "is it true that..." |
| `recall_memory` | recall_memory | "what do you know about me" |
| `save_memory` | save_memory | "remember that I like..." |
| `search_memory` | search_memory | "search your memory for..." |
| `update_memory` | update_memory | "update my name to..." |
| `forget_memory` | forget_memory | "forget that I said..." |
| `read_file` | read_file | "show me config.py" |
| `write_file` | write_file | "create a file called..." |
| `list_directory` | list_directory | "list files in src/" |
| `search_codebase` | search_codebase | "find all TODO comments" |
| `run_command` | run_command | "run pytest" |
| `no_tool` | (none) | "explain quantum computing" |

### Confidence Thresholds

| Model | Threshold | Below-threshold behavior |
|-------|-----------|-------------------------|
| Query classifier | 0.75 | *Irrelevant — no longer drives routing. Stubs return safe defaults.* |
| Tool detector | 0.50 | Falls to regex confirmation gate → regex heuristics → default [] (no tools) |

The tool detector threshold is the only one that matters now. It's conservative: better to skip a tool (let the LLM handle it directly) than to inject the wrong tool into the ReAct loop.

---

## Regex Fallback System

Regex patterns serve as a **permanent safety net** for tool detection. The classifier gets first shot; regex catches what it misses.

### Query Classification Fallback — DEPRECATED

The query classification regex fallback (`_regex_is_smalltalk()`, `_regex_is_code()`) has been removed. `classify_context_level()` is now a deprecated stub that always returns `ContextLevel.FULL`. The following regex patterns still exist for **disclosure and memory detection** (not routing):

- **Disclosure:** `is_personal_disclosure()` — 6 positive patterns (`\bmy name is\b`, `\bi(?:'m| am)\b`, etc.) + 7 negative patterns to exclude questions. Used to gate memory ingestion.
- **Memory recall:** `requests_personal_memory()` — 7 patterns (`\bwhat do you know about me\b`, `\bdo you remember\b`, etc.). Used to detect memory-related queries for temperature routing (→ 0.3).

### Tool Detection Fallback — 3-TIER ACTIVE (`tools.py`)

Tool detection uses a 3-tier system: classifier first, regex confirmation gate to suppress false positives, then regex fallback for missed tools.

```
detect_tools_needed(query)
    │
    ├── 1. ByteTransformer detect_tools(query) → [tool_names] + confidence
    │
    ├── 2. Confirmation gate (suppress false positives):
    │       ├── confidence ≥ 0.92 → trust classifier unconditionally
    │       ├── confidence < 0.92 AND regex agrees → trust classifier
    │       └── confidence < 0.92 AND regex disagrees → suppress, fall to []
    │
    └── 3. If empty → _regex_detect_tools(query) fallback
            ├── calculator patterns (math operators, "calculate", "compute")
            ├── datetime patterns ("current time", "today's date")
            ├── web_search patterns ("search", "look up", "find online")
            ├── document_search patterns ("search my docs", "find the report")
            ├── code patterns ("write...code", "create...function")
            ├── fact_check patterns ("is it true", "verify")
            ├── recall_memory patterns ("what do you know about me")
            ├── forget_memory patterns ("forget", "erase", "remove memory")
            ├── save_memory patterns ("remember that", "save the fact")
            └── filesystem patterns ("list files", "read file")
```

### Why Regex Stays (for tool detection)

1. **Cold start** — if `.npz` files are missing or corrupted, regex still works
2. **Low confidence** — classifiers return confidence; regex has no confidence concept but matches patterns humans explicitly programmed
3. **Exception safety** — any numpy/model error gets caught, regex takes over
4. **Training teacher** — regex patterns are the ground truth that generated training data in the first place
5. **Observable** — regex matches are debuggable line-by-line; neural net outputs aren't

**Rule:** The tool detection regex fallback must always exist. As the tool classifier improves, regex fires less often — but removing it creates a single point of failure.

---

## Training Pipeline

Models are trained offline and shipped as static `.npz` files in the Docker image. No continuous training in production (yet).

### Data Generation (`scripts/generate_training_data.py`)

```
Seed phrases (hand-curated, 15-30 per category)
    │
    ▼
Augmentation (8-12 variants per seed):
    ├── Case variation (upper/capitalize)
    ├── Filler prepend ("um", "like", "so", "please")
    ├── Punctuation append ("!", ".", "?", "...")
    ├── Word swap (adjacent words)
    └── Typo simulation (drop random character)
    │
    ▼
Label assignment:
    ├── Seeds → intended label (authoritative)
    └── Variants → inherit parent's label
    │
    ▼
Output: data/training_queries.jsonl + data/tool_training.jsonl
```

This is **distillation**: the regex patterns (teacher) automatically label synthetic data, and the neural network (student) learns to generalize beyond the regex's rigid matching. The student can handle typos, rewordings, and edge cases the teacher can't.

### Training (`scripts/train_classifiers.py`)

```
Load JSONL → encode to byte arrays (pad/truncate to 256)
    │
    ▼
PyTorch TinyTransformer (mirrors ByteTransformer architecture exactly)
    │
    ▼
Training: AdamW optimizer, cosine annealing LR, 30 epochs (query) / 80 epochs (tools)
    │
    ▼
Export: extract weight matrices → numpy arrays → np.savez_compressed() → .npz
    │
    ▼
Output: backend/models/query_classifier.npz + tool_detector.npz
```

**Critical invariant:** The PyTorch `TinyTransformer` and numpy `ByteTransformer` must have identical architectures. Weight names, shapes, and operations must match exactly. The export function handles PyTorch→numpy weight transpositions (`.weight.T` for linear layers).

### Retraining Workflow

```bash
# 1. Generate fresh training data (uses seed phrases + augmentation)
cd backend && python3 ../scripts/generate_training_data.py

# 2. Train models (requires PyTorch — dev dependency only)
python3 ../scripts/train_classifiers.py

# 3. Models saved to backend/models/*.npz — commit and deploy
```

---

## Temperature Routing

Every query gets a temperature based on its classification — no more hardcoded 0.7 for everything.

| Query Type | Temperature | Rationale |
|-----------|-------------|-----------|
| Code generation | 0.1 (`TEMPERATURE_CODE`) | Deterministic — syntax errors at high temp |
| Tool use / factual / memory recall | 0.3 (`TEMPERATURE_FACTUAL`) | Precise — tools need exact params, facts need accuracy |
| Conversational / general | 0.7 (`TEMPERATURE_CONVERSATIONAL`) | Balanced — natural language benefits from variety |

**Implementation:** `classify_temperature()` in `query_classifier.py` checks: tools_needed contains code_display → 0.1; regex detects code keywords → 0.1; tools_needed non-empty → 0.3; `requests_personal_memory()` → 0.3; else → 0.7. Temperature flows through `RequestContext.temperature` → `pipeline.process_streaming()` → `chat_stream()` → llama-server `/v1/chat/completions` params.

---

## Memory System Integration

The MicroGPT classifiers don't just route queries — they determine how much memory context gets loaded and when the LLM should use memory tools.

### Context Loading (Simplified)

Every query now gets the same full context:

| Resource | Amount | Notes |
|----------|--------|-------|
| Messages | Last 25 | Conversation history |
| Summary | Yes | Rolling conversation summary |
| Knowledge Search | Top 20 | Scored by similarity (0.60) + importance (0.25) + recency (0.15) |
| Embeddings | Yes | Query embedding for knowledge search |
| Tool Detection | Yes | Classifier + regex fallback |
| Temperature | Auto | Code→0.1, tools/memory→0.3, else→0.7 |

The old 4-level system (NONE/MINIMAL/DISCLOSURE/FULL) has been removed. The `ContextLevel` enum still exists for backwards compatibility but is never used for branching.

### Memory Pipeline

```
User message arrives
    │
    ▼
context_loader: classify → load appropriate context → detect tools
    │
    ▼
pipeline: generate response (may call memory tools via ReAct)
    │
    ▼
ingestion_worker (background daemon):
    ├── Index message into KnowledgeStore (384-dim FastEmbed vector)
    ├── Extract profile facts via qwen3-8b (ingest instance, port 8082)
    │       └── profile_extractor.py: structured JSON extraction
    │           ├── facts: [{fact, category, importance}]
    │           └── triples: [{subject, predicate, object}]
    ├── Dedup against existing facts (KNN: skip >0.95, merge >0.85)
    ├── Contradiction detection (heuristic: same pattern, different value)
    └── Update rolling conversation summary
```

### Knowledge Store Scoring

When the pipeline needs context, `knowledge_store.search()` scores every candidate:

```
combined_score = similarity × 0.60 + importance × 0.25 + recency × 0.15
```

- **Similarity** (0.60): Cosine similarity between query embedding and stored fact embedding (384-dim FastEmbed)
- **Importance** (0.25): User-assigned or auto-extracted 1-5 rating, normalized to 0-1
- **Recency** (0.15): Linear decay over 30 days — recent facts rank higher

Top 20 items are injected into the prompt via `prompt_assembler.assemble()` (token-budgeted: max 3500 tokens for profile, max 25 facts).

---

## LLM Backend: llama-server

Trinity uses llama-server (llama.cpp's HTTP server) directly — **not** Ollama.

### Dual Instance Architecture

| Instance | Port | Model | Context | Purpose |
|----------|------|-------|---------|---------|
| Chat | 8081 | qwen3-32b (Q4_K_M GGUF) | 65K tokens | Reasoning, generation, tool execution |
| Ingest | 8082 | qwen3-8b (Q4_K_M GGUF) | 8K tokens | Memory extraction, summarization |

**Why dual instances:** Memory extraction happens in the background (ingestion_worker). Running it on the chat instance would steal GPU cycles from the user's active conversation. The 8B model is sufficient for structured JSON extraction and much faster.

### Key Features Unlocked

| Feature | How | Status |
|---------|-----|--------|
| **KV cache persistence** | `--prompt-cache /data/kv_cache.bin` | Available (not yet wired) |
| **LoRA adapter loading** | `--lora /path/to/adapter.gguf` | Available (not yet wired) |
| **OpenAI-compatible API** | `POST /v1/chat/completions` with SSE streaming | Production |
| **Think block stripping** | `think_filter.py` strips `<think>...</think>` from stream | Production |
| **GPU offloading** | `--n-gpu-layers 999` with A100/A6000/H100/L40S/A40/RTX4090 | Production |

---

## The Learning Roadmap

The current system is **classify → route → respond**. The roadmap extends this to **classify → route → respond → learn → improve**.

### Phase 1: Observation (Current)
- Classifiers are trained once on synthetic data and shipped static
- The ingestion_worker extracts and stores user facts, building a rich per-user profile
- Contradiction detection prevents stale facts from persisting
- All the infrastructure exists to observe and remember user behavior

### Phase 2: Feedback Loop (Next)
- **Implicit signals:** Track which tool calls succeed vs. fail, which queries get re-asked (user unsatisfied), which conversations are long (complex) vs. short (resolved quickly)
- **Classifier confidence logging:** Log every (query, predicted_label, confidence) tuple. Low-confidence predictions are training data candidates.
- **Active learning:** When confidence is between 0.5 and 0.75 (uncertain), save the query for human/LLM review. Build a growing labeled dataset from production traffic.

### Phase 3: Per-User Adaptation (Future)
- **LoRA fine-tuning:** llama-server supports `--lora`. Train a tiny LoRA adapter per user from their conversation history. User who mostly writes code gets a code-tuned adapter. User who mostly asks factual questions gets a fact-tuned adapter.
- **Classifier retraining:** Periodically retrain classifiers with accumulated production labels (from Phase 2). Each generation should need the regex fallback less.
- **DPO (Direct Preference Optimization):** Use user feedback (thumbs up/down, re-asks, conversation length) as preference signal. Fine-tune the base model to prefer responses the user actually values.

### Phase 4: Adapter Marketplace (Vision)
- Users can opt-in to share their LoRA adapters
- Community-trained adapters for specific domains (coding, research, creative writing)
- Adapters composable — stack a code adapter + a domain adapter
- All on IPFS — decentralized, user-owned, censorship-resistant

### What Exists Today vs. What's Next

| Capability | Status | File(s) |
|-----------|--------|---------|
| Static classification (trained once) | **Production** | `tiny_classifier.py`, `models/*.npz` |
| Regex safety net | **Production** | `query_classifier.py`, `tools.py` |
| Temperature routing | **Production** | `query_classifier.py` → `config.py` |
| Profile extraction (LLM-based) | **Production** | `profile_extractor.py`, `ingestion_worker.py` |
| Knowledge retrieval (ANN + scoring) | **Production** | `knowledge_store.py` |
| Contradiction detection | **Production** | `memory_tools.py` |
| Confidence logging | **Not started** | — |
| Active learning pipeline | **Not started** | — |
| LoRA per-user adapters | **Infra ready** | llama-server `--lora` flag |
| Classifier retraining from prod data | **Not started** | `scripts/train_classifiers.py` (exists, needs prod data input) |
| DPO from user feedback | **Not started** | — |
| Adapter marketplace | **Vision** | — |

---

## File Reference

| File | Purpose |
|------|---------|
| [backend/services/tiny_classifier.py](../../backend/services/tiny_classifier.py) | ByteTransformer inference (pure numpy), `classify_query()`, `detect_tools()` |
| [backend/services/query_classifier.py](../../backend/services/query_classifier.py) | Deprecated ContextLevel stubs, `is_personal_disclosure()`, `requests_personal_memory()`, `classify_temperature()` |
| [backend/services/tools.py](../../backend/services/tools.py) | Tool definitions, `detect_tools_needed()` with regex fallback, tool parsing |
| [backend/services/context_loader.py](../../backend/services/context_loader.py) | `load_context()` — single entry point, always loads full context |
| [backend/services/pipeline.py](../../backend/services/pipeline.py) | `StreamingPipeline` — ReAct loop (tools) or direct streaming (no fast-path) |
| [backend/services/knowledge_store.py](../../backend/services/knowledge_store.py) | Unified vector retrieval (ANN + brute-force), scoring, dedup |
| [backend/services/memory_tools.py](../../backend/services/memory_tools.py) | LLM-callable memory tools (save/recall/search/update/forget) |
| [backend/services/profile_extractor.py](../../backend/services/profile_extractor.py) | LLM-based structured fact + triple extraction |
| [backend/services/ingestion_worker.py](../../backend/services/ingestion_worker.py) | Background daemon: index, extract, summarize |
| [backend/services/llama_server_provider.py](../../backend/services/llama_server_provider.py) | llama-server LLM provider (OpenAI-compatible) |
| [backend/models/query_classifier.npz](../../backend/models/query_classifier.npz) | Query classifier weights (374KB, deprecated for routing) |
| [backend/models/tool_detector.npz](../../backend/models/tool_detector.npz) | Trained tool detector weights (378KB, **active**) |
| [scripts/generate_training_data.py](../../scripts/generate_training_data.py) | Seed phrases → augmented JSONL training data |
| [scripts/train_classifiers.py](../../scripts/train_classifiers.py) | PyTorch training → .npz export |
| [scripts/diagnose_llm.py](../../scripts/diagnose_llm.py) | Comprehensive LLM diagnostic suite (126 tests, 18 categories) |
| [data/training_queries.jsonl](../../data/training_queries.jsonl) | Query classification training data (83KB) |
| [data/tool_training.jsonl](../../data/tool_training.jsonl) | Tool detection training data (547KB) |
| [backend/tests/unit/test_regex_fallback.py](../../backend/tests/unit/test_regex_fallback.py) | ~47 tests: disclosure/memory detection, tool detection regex, deprecated stubs, diagnostic gaps |

---

## Pipeline Defense Layers

The tool pipeline has 4 layers of defense against tool-call failures:

| Layer | Where | What |
|-------|-------|------|
| **1. ByteTransformer** | `tiny_classifier.py` | Classifier detects tool from query (<1ms) |
| **2. Confirmation gate** | `tools.py` → `detect_tools_needed()` | Suppresses false positives: classifier must be high-confidence (≥0.92) OR regex-confirmed |
| **3. Regex fallback** | `tools.py` → `_regex_detect_tools()` | Catches tools the classifier missed |
| **4. Tool-call rescue** | `pipeline.py` → direct-chat path | Buffers first ~50 chars of LLM output; if it's raw tool-call JSON/XML, executes the tool and re-prompts |

### Tool-Call Rescue (Layer 4)

On the direct-chat path (no tools detected), the pipeline buffers the first ~50 characters of LLM output. If the model outputs tool-call JSON/XML instead of a natural answer (because the tool detector missed), the rescue:

1. Detects the pattern via `_is_tool_call_output()` (JSON, XML, markdown-bold, bare tool name)
2. Parses the tool call via `parse_tool_calls()`
3. Executes the tool via `execute_tool()`
4. Emits `tool_execution` and `tool_result` SSE phase events
5. Re-prompts the LLM with the tool result for a natural answer

Normal responses (first char is a letter) have **zero buffering delay** — the fast-exit triggers immediately.

---

## ReAct Loop Design

The ReAct loop (`react_loop.py`) allows multi-tool chains while preventing runaway loops:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REACT_MAX_ITERATIONS` | `5` | Enough for search→calculate→save, prevents 14-call runaway |
| `REACT_TOKEN_BUDGET` | `48000` | Force answer if approaching context limit |
| `REFLEXION_MAX_RETRIES` | `3` | Retry code execution errors with self-correction |

### Guardrails

1. **Exact-duplicate guard** — tracks `(tool_name, params_json)` in a `_seen_calls` set. If the model tries the exact same tool+params twice, the loop short-circuits and returns the cached result.
2. **Max iterations cap** — hard limit at 5 iterations. Multi-step queries (different tools or different params) work fine. Runaway same-tool loops are capped.
3. **Neutral observation messages** — tool results are injected as `[Tool Result: tool_name]\nresult_text` with no behavioral instructions. The system prompt already tells the model when to call tools vs. give a final answer.
4. **Token budget** — if messages approach 48K tokens, the loop forces a final answer.

### What's allowed vs. blocked

| Scenario | Allowed? | Why |
|----------|----------|-----|
| `calculator("17*23")` → `calculator("391+100")` | ✅ | Different params |
| `web_search("bitcoin price")` → `calculator("65000/7")` → `save_memory(...)` | ✅ | Different tools |
| `calculator("17*23")` → `calculator("17*23")` | ❌ | Exact duplicate → cached result returned |

---

## Critical Rules

1. **Never delete the tool detection regex fallback.** The tool classifier improves over time; regex is the permanent safety net.
2. **Every query gets an LLM call.** No hardcoded responses. No fast-paths. The LLM handles everything.
3. **Only the tool detector drives pipeline behavior.** The query classifier is deprecated for routing. `ContextLevel` exists only for backwards compatibility.
4. **PyTorch is dev-only.** Production inference is pure numpy. Never import torch in backend runtime code.
5. **Architecture must match.** `TinyTransformer` (PyTorch, training) and `ByteTransformer` (numpy, inference) must have identical layer shapes. If you change one, change both.
6. **Temperature is auto-routed.** Do NOT hardcode temperature. It flows from `classify_temperature()` through `RequestContext` to the LLM call.
7. **Dual LLM instances.** Chat on 8081 (32B), ingest on 8082 (8B). Don't use the chat instance for background extraction.
8. **Tool detector threshold is 0.50.** Conservative. Raising it increases regex usage (safe). Lowering it risks injecting wrong tools (dangerous).
9. **Training data comes from seeds, not production (yet).** The training pipeline uses curated seed phrases + augmentation. Production feedback loop is a future feature.
