# MicroGPT Overhaul — Before vs. After

**Date:** February 20, 2026
**Status:** All 3 phases implemented. Deployment blocked on HuggingFace model filename casing (fix applied, needs deploy).

## Quick Summary

Three changes: (1) queries now get different LLM temperatures based on what they're asking, (2) all query/tool classification switched from brittle regex to trained neural classifiers, (3) the inference backend switched from Ollama to llama-server (llama.cpp directly), unlocking KV cache and LoRA support.

---

## Feature Comparison Table

| Feature | Before | After |
|---------|--------|-------|
| **Sampling Temperature** | Hardcoded `0.7` for every query regardless of type | Code queries -> `0.1`, factual/tool/memory queries -> `0.3`, conversational -> `0.7`. Routed automatically per-request. |
| **Smalltalk Detection** | 22 canonical phrases + 18 token words in a hardcoded set. Only matched exact normalized strings like "hi", "hello there", "what's up". "heya", "howdy", "greetings" all missed. | ByteTransformer classifier trained on 257 smalltalk examples + augmented variations. Generalizes to unseen greetings. Confidence < 0.75 falls through to full context (safe default). |
| **Personal Disclosure Detection** | 6 regex patterns (`\bmy name is\b`, `\bi(?:'m\| am)\b`, etc.) with 7 negative patterns. Missed phrasings like "I'm building a decentralized AI app". False-positived on "I am confused about this code". | Classifier-backed. Trained on 191 disclosure examples. No regex -- no false positive/negative edge cases to patch. |
| **Code Request Detection** | 4 regex patterns checking for words like "write", "create", "generate" + "code", "script", "function". Had an execution-intent exclusion list. Missed "I need a function that calculates fibonacci numbers". | Classifier-backed. Trained on 127 code examples. Detects natural-language code requests without keyword matching. |
| **Memory Recall Detection** | 7 regex patterns (`\bwhat do you know about me\b`, `\bdo you remember\b`, etc.). Missed "tell me about me", "who am i to you". | Classifier-backed. Trained on 104 memory_recall examples. Generalizes beyond fixed phrases. |
| **Lightweight Prompt Detection** | Word count check (< 6 words) + exclusion lists for memory/retrieval signal words. "sure" and "ok" worked but "got it, thanks" didn't. | Classifier trained on 91 lightweight examples. Recognizes acknowledgements by pattern, not word count. |
| **Preference Query Detection** | Set intersection against 11 hint words: "style", "tone", "format", "verbose", etc. "respond more casually" missed because "casually" wasn't in the set. | Classifier-backed. Trained on 63 preference examples. |
| **Tool Detection** (`detect_tools_needed`) | 180 lines of regex across 8 tool categories (calculator, web_search, recall_memory, forget_memory, code_display, fact_check, document_search, filesystem). Each category had 3-15 regex patterns. Missing tools: save_memory, search_memory, update_memory, read_file, write_file, list_directory, search_codebase, run_command had no regex at all. | Single 5-line function calling a trained 100K-param classifier. Covers all 15 tools + no_tool class. Multi-class softmax (not multi-label). |
| **Context Level Classification** | Sequential if/else chain: `is_trivial_smalltalk()` -> NONE, `_is_lightweight_prompt()` -> MINIMAL, `is_personal_disclosure()` -> DISCLOSURE, else -> FULL. Order-dependent -- a short disclosure like "I'm Owen" could hit lightweight before disclosure. | Single classifier call -> label + confidence -> lookup in `_LABEL_TO_LEVEL` map. No order dependency. Confidence < 0.75 defaults to FULL. |
| **Classification Speed** | Regex: ~0.1ms per function, but called 6+ times per request (each function re-scans the prompt). Total: ~0.5ms. | ByteTransformer: single forward pass ~3-5ms, called once. Result cached and reused by all classifier-backed functions in the same request. |
| **Classification Maintainability** | Adding a new pattern = editing regex, risk of breaking existing matches, no test coverage for interactions between patterns. | Adding a new pattern = adding seed phrases to training data, re-running `train_classifiers.py`. Model generalizes automatically. |
| **LLM Backend** | Ollama (wraps llama.cpp). Custom API: `/api/chat`, `/api/generate`. NDJSON streaming. `ollama pull` for model management. `think=False` parameter to suppress Qwen3 thinking. | llama-server (llama.cpp directly). OpenAI-compatible API: `/v1/chat/completions`, `/v1/completions`. SSE streaming. GGUF models downloaded from HuggingFace at startup. `think_filter.py` strips `<think>` blocks from stream. |
| **KV Cache Persistence** | Not possible -- Ollama doesn't expose it. Every request recomputes the full prompt from scratch. | Unlocked via `--prompt-cache` flag on llama-server. Not yet wired to per-user caches, but the infrastructure is in place. |
| **Native LoRA Loading** | Not possible -- Ollama requires baking adapters into Modelfiles. | Unlocked via `--lora /path/to/adapter.gguf` flag. Not yet wired, but available for future per-user fine-tuning. |
| **Inference Isolation** | Single Ollama instance shared between chat and background ingestion (profile extraction, summarization). Heavy ingestion could starve chat requests. | Two separate llama-server instances: **chat** on port 8081 (32B model, 65K context), **ingest** on port 8082 (8B model, 8K context). No resource contention. |
| **Model Management** | `ollama pull qwen3:32b` -- convenient but opaque. Model stored in Ollama's internal format. | `hf_hub_download()` from HuggingFace -> raw GGUF files on persistent volume. Full control over quantization, model version. |
| **Docker Build** | Installs Ollama binary, starts `ollama serve`, runs `ollama pull`. | Copies pre-built `llama-server` binary from `ghcr.io/ggml-org/llama.cpp:server-cuda`. No source compilation (avoids QEMU/nvcc cross-build issues). |
| **Health Check** | `GET /api/tags` on Ollama, checks if model name appears in model list. | `GET /health` on llama-server, checks `status == "ok"`. Response includes both `llm_connected` and `ollama_connected` (backwards compat). |
| **`query_classifier.py` Size** | 308 lines (regex patterns, word lists, compiled patterns, helper functions) | 165 lines (classifier calls + enum + temperature routing) |
| **`tools.py` `detect_tools_needed()` Size** | 183 lines of regex patterns covering 8 tool categories | 12 lines (import + function wrapper) |
| **Files Deleted** | -- | `ollama_provider.py`, `ollama.py`, `test_ollama.py`, `Dockerfile.vllm`, `startup-vllm.sh` |
| **Files Created** | -- | `llama_server_provider.py`, `tiny_classifier.py`, `models/query_classifier.npz`, `models/tool_detector.npz`, `test_tiny_classifier.py`, `test_temperature_routing.py`, `generate_training_data.py`, `train_classifiers.py` |

---

## Expected Runtime Behavior

### When a User Sends a Message

```
User sends "write a python function to sort a list"
                    |
                    v
        +-- context_loader.load_context() --+
        |                                    |
        |  1. Tiny classifier classifies:    |
        |     -> label="code", conf=0.99     |
        |     -> ContextLevel.FULL           |
        |                                    |
        |  2. Tool detector:                 |
        |     -> ["code_display"]            |
        |                                    |
        |  3. Temperature:                   |
        |     -> 0.1 (TEMPERATURE_CODE)      |
        |                                    |
        |  4. Load messages, knowledge,      |
        |     embeddings from state.db       |
        +------------------------------------+
                    |
                    v
        +-- pipeline.process_streaming() ---+
        |  tools_needed=["code_display"]     |
        |  temperature=0.1                   |
        |  -> ReAct loop activated           |
        +------------------------------------+
                    |
                    v
        +-- ReactLoop.execute_streaming() --+
        |  Calls LlamaServerProvider         |
        |  POST /v1/chat/completions         |
        |  temperature=0.1                   |
        |  Stream SSE tokens back            |
        |  Think blocks stripped              |
        +------------------------------------+
                    |
                    v
        Tokens streamed to user via SSE
```

### Query Type Routing

| User Says | Classifier Label | Temperature | Path |
|-----------|-----------------|-------------|------|
| "hello" | smalltalk (0.93) | N/A | **Fast path** -- returns hardcoded response. No LLM call. |
| "my name is Owen" | disclosure (0.99) | 0.7 | **Disclosure path** -- last 5 messages, no embeddings/knowledge. |
| "ok" | lightweight (0.75) | 0.7 | **Minimal path** -- last 5 messages only. |
| "what do you know about me" | memory_recall (1.0) | 0.3 | **Full + ReAct** -- recall_memory tool called. |
| "what is 2 + 2" | * | 0.3 | **Full + ReAct** -- calculator tool called. |
| "explain quantum computing" | general (0.99) | 0.7 | **Full, direct streaming** -- no tools, full context. |
| "write a python function" | code (0.99) | 0.1 | **Full + ReAct** -- code_display tool, low temperature. |
| "search for latest AI news" | general | 0.7 | **Full** -- web_search tool or pipeline keyword search. |
| "forget my age" | general | 0.3 | **Full + ReAct** -- forget_memory tool called. |
