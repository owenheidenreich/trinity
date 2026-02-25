# MicroGPT Overhaul — Before vs. After

**Date:** February 20, 2026
**Status:** All 3 phases implemented. Deployment blocked on HuggingFace model filename casing (fix applied, needs deploy).

## Quick Summary

Three changes: (1) queries now get different LLM temperatures based on what they're asking, (2) all query/tool classification switched from brittle regex to trained neural classifiers, (3) the inference backend switched from Ollama to llama-server (llama.cpp directly), unlocking KV cache and LoRA support.


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
