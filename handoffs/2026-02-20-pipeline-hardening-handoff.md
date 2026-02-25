# Handoff: Pipeline Hardening — Tool Detection, ReAct Redesign & Diagnostics

**Date:** February 20, 2026  
**Audience:** Next engineer picking up Trinity deployment  
**Previous Handoffs:**
- `handoffs/2026-02-20-microgpt-overhaul-handoff.md` — MicroGPT overhaul (Phases 1-3)
- `handoffs/2026-02-20-microgpt-phase3-progress.md` — Phase 3 progress  

**Test Status:** 1055 tests pass, 0 failures, 39 skipped  

---

## Executive Summary

This session hardened the Trinity inference pipeline with 6 interconnected fixes:

1. **Retrained ByteTransformer classifiers** — 80 epochs, byte-level vocab=256, ~50K params
2. **Added regex confirmation gate** — suppresses false-positive tool detections when classifier confidence < 0.92 and regex disagrees
3. **Added tool-call rescue** — catches tool calls the detector missed on the direct-chat path
4. **Redesigned ReAct loop** — max iterations 15→5, exact-duplicate guard, neutral observation messages
5. **Rewrote diagnostic suite** — `diagnose_llm.py` expanded from 42 to 126 tests across 18 categories
6. **Removed all hardcoded responses** — `smalltalk_fast_response`, `fast_path`, and all non-LLM response paths deleted

All changes are tested and ready for deployment. No blockers.

---

## Root Cause Analysis

### Problem
Running `diagnose_llm.py` against a live backend revealed two critical failures:

1. **Tool detector returned `[]` for all queries** — The ByteTransformer had poor recall, and the regex fallback had been deleted in a prior session (MicroGPT Phase 2 removed 180 lines of regex from `tools.py`). Every query took the direct-chat path instead of the ReAct tool path.

2. **When tools DID fire, the model called them repeatedly** — `core_002` (multiplication) showed the calculator called twice. `tool_004` (save memory) showed `save_memory` called 14 times with slightly reworded params. Root causes: observation messages said "Use another tool if needed" (encouraging re-calls), no duplicate guard, and `REACT_MAX_ITERATIONS=15` allowed runaway loops.

### Design Philosophy
The user's guiding principle: **"I don't need patches and workarounds. I need a sleek design."** This led to structural guardrails rather than behavioral hacks:

- Structural cap (5 iterations) instead of forceful observation messages
- Exact-duplicate guard instead of per-tool-name caps
- Neutral observations instead of "Do NOT call the same tool again"
- System prompt defines behavior; observations provide data only

---

## 1. Retrained ByteTransformer Classifiers

### What Changed
- **Training epochs:** 50 → 80 for tool detector (30 for query classifier)
- **Architecture:** ~50K params, byte-level vocab (256 tokens), 2-layer transformer, 64-dim embeddings, 4 attention heads
- **Training data:** `data/tool_training.jsonl` (547KB), `data/training_queries.jsonl` (83KB)
- **Output format:** PyTorch training → numpy `.npz` export (no PyTorch at runtime)

### Files
| File | Change |
|------|--------|
| `backend/models/tool_detector.npz` | Retrained weights (378KB) |
| `backend/models/query_classifier.npz` | Retrained weights (374KB) |
| `scripts/train_classifiers.py` | EPOCHS=80 for tools, PATIENCE=15 |

### Key Detail
The tool detector uses **softmax** (single-class), not sigmoid (multi-label). Multi-label only achieved 39% accuracy. The ReAct loop discovers additional tools iteratively.

---

## 2. Regex Confirmation Gate

### What Changed
Added a 3-tier detection flow in `tools.py` → `detect_tools_needed()`:

```
Query → ByteTransformer classifier
         │
         ├── confidence ≥ 0.92 → ACCEPT classifier result
         │
         ├── confidence < 0.92 AND regex confirms → ACCEPT classifier result
         │
         └── confidence < 0.92 AND regex disagrees → SUPPRESS, use regex result
         
If classifier returns "none" → run regex fallback
```

### Why
The MicroGPT Phase 2 overhaul deleted all tool-detection regex from `tools.py` (180 lines). This was premature — the classifier needed a safety net. The confirmation gate:
- Lets high-confidence predictions through unmodified
- Requires regex agreement for borderline predictions
- Falls back to regex entirely when the classifier says "no tool needed"

### Files
| File | Change |
|------|--------|
| `backend/services/tools.py` | `detect_tools_needed()` rewritten with 3-tier flow, `HIGH_CONF = 0.92` |
| `backend/services/tools.py` | `_regex_detect_tools()` restored as standalone function |
| `backend/services/tools.py` | Fixed `recall_memory` regex: `r"tell me .*(?:about\|know about) me"` |

### Critical Rule
**Do NOT delete the regex fallback patterns.** They are the permanent safety net for tool detection. The classifier improves over time; regex catches what it misses.

---

## 3. Tool-Call Rescue (Direct-Chat Path)

### What Changed
When the tool detector returns no tools, the pipeline takes the direct-chat path. Previously, if the LLM output a raw tool-call JSON/XML (because it "wants" to call a tool), that raw text would stream to the user.

Now, the direct-chat path buffers the first ~50 characters. If the output looks like a tool call, it:
1. Parses the tool call via `parse_tool_calls()`
2. Executes the tool via `execute_tool()`
3. Emits `tool_execution` and `tool_result` SSE phase events
4. Re-prompts the LLM with the tool result for a natural-language answer

### Fast-Exit Optimization
If the first character is a letter (the common case — natural language), the buffer exits immediately with **zero delay**. Only tool-call patterns (JSON `{`, XML `<`, markdown bold `**`) trigger the full buffer.

### Files
| File | Change |
|------|--------|
| `backend/services/pipeline.py` | `_TOOL_CALL_START_CHARS`, `_TOOL_RESCUE_BUFFER_CHARS=50`, `_is_tool_call_output()`, buffered streaming with rescue execution |

### Pattern Detection
`_is_tool_call_output(text)` checks for:
- JSON: starts with `{` and contains `"name"` or `"tool"`
- XML: starts with `<tool_call>` or `<tool>`
- Markdown bold: starts with `**Tool` or `**tool`
- Bare tool name: first word matches a known tool name

---

## 4. ReAct Loop Redesign

### What Changed

| Parameter | Before | After | Why |
|-----------|--------|-------|-----|
| `REACT_MAX_ITERATIONS` | 15 | 5 | Enough for search→calculate→save; prevents 14-call runaway |
| Observation format | `"Tool result... Use another tool if needed"` | `"[Tool Result: tool_name]\nresult_text"` | Neutral — no behavioral instructions |
| Duplicate guard | None | Exact `(tool_name, params_json)` tracking | Same tool+params = always waste |

### Exact-Duplicate Guard
Tracks `_seen_calls` as a set of `(tool_name, json.dumps(params, sort_keys=True))` tuples. If the model tries the exact same call twice, the loop short-circuits and returns the cached result instead of re-executing.

Applied to both `execute()` (non-streaming) and `execute_streaming()` paths.

### What's Allowed vs. Blocked

| Scenario | Allowed? | Why |
|----------|----------|-----|
| `calculator("17*23")` → `calculator("391+100")` | ✅ | Different params |
| `web_search("btc")` → `calculator("65000/7")` → `save_memory(...)` | ✅ | Different tools |
| `calculator("17*23")` → `calculator("17*23")` | ❌ | Exact duplicate → cached |

### Files
| File | Change |
|------|--------|
| `backend/services/react_loop.py` | `import json`, `_seen_calls` set, duplicate guard in both execute paths, neutral observations |
| `backend/config.py` | `REACT_MAX_ITERATIONS = 5` |
| `backend/tests/unit/test_react_loop.py` | Updated iteration tests, added `test_duplicate_tool_call_guard` |
| `backend/tests/unit/test_phase5_agentic.py` | `test_react_max_iterations_is_5` |

---

## 5. Diagnostic Suite Rewrite

### What Changed
`scripts/diagnose_llm.py` rewritten from 42 to 126 tests across 18 categories:

| Category | Tests | What It Validates |
|----------|-------|-------------------|
| Core capabilities | 10 | Math, coding, summarization, reasoning, comparison, creative, general knowledge |
| Tool calling | 15 | Calculator, search, memory save/recall, code execution, current_datetime |
| Memory system | 10 | Profile save, preference save, recall, multi-fact, relationship memory |
| Conversation quality | 10 | Coherence, length, helpfulness, personality, greeting |
| Edge cases | 8 | Empty input, very long input, special chars, multi-language, injection attempts |
| Streaming | 5 | SSE format, chunk integrity, latency, content completeness |
| Error handling | 8 | Invalid tool, timeout recovery, malformed input, rate limiting |
| Context window | 5 | Long context retention, multi-turn, context overflow handling |
| Temperature routing | 6 | Code→0.1, factual→0.3, conversational→0.7 |
| Security | 8 | Prompt injection, auth bypass attempts, data exfiltration |
| Multi-turn | 8 | Reference resolution, topic switching, context carryover |
| Tool chaining | 5 | Multi-step (search→calculate), tool→memory save |
| Think filter | 4 | `<think>` block stripping, partial think blocks |
| Disclosure detection | 6 | Personal facts trigger memory save |
| Code display | 5 | markdown code blocks, syntax highlighting, multi-language |
| ReAct loop | 5 | Iteration limits, Reflexion retries, token budget |
| Concurrent requests | 3 | Parallel queries, session isolation |
| Cold start | 5 | First request latency, model loading |

### Usage
```bash
# Quick suite (core + tools + memory + conversation — ~30 tests)
python3 scripts/diagnose_llm.py --host https://api.dubya.ai --suite quick -v

# Full suite (all 126 tests)
python3 scripts/diagnose_llm.py --host https://api.dubya.ai --suite full -v

# Single category
python3 scripts/diagnose_llm.py --host https://api.dubya.ai --category tool_calling -v
```

---

## 6. Hardcoded Response Removal

### What Was Removed
- `smalltalk_fast_response()` — returned canned answers for greetings/smalltalk without LLM
- `fast_path` in pipeline — bypassed LLM for simple queries
- All non-LLM response paths — every query now goes through the full pipeline

### Why
Hardcoded responses were unpredictable ("Hi!" would get a canned response while "Hey!" would get an LLM response) and made the system harder to debug. The LLM handles greetings just fine.

---

## Pipeline Architecture (After Hardening)

```
User Query
    │
    ▼
context_loader.load_context()
    ├── ByteTransformer tool detection (3-tier)
    │     ├── Classifier (conf ≥ 0.92) ──────────────▶ tool list
    │     ├── Classifier + regex confirmation ────────▶ tool list
    │     └── Regex fallback ─────────────────────────▶ tool list
    ├── Temperature routing (code/factual/conversational)
    └── Full context loading (memories, profile, history)
    │
    ▼
prompt_assembler.assemble()
    └── Token-budgeted system prompt + context + history
    │
    ▼
StreamingPipeline.process_streaming()
    ├── Tools detected? ──▶ ReAct loop (max 5 iterations)
    │                        ├── Exact-duplicate guard
    │                        ├── Neutral observations
    │                        ├── Reflexion self-correction
    │                        └── Token budget cap (48K)
    │
    └── No tools? ────────▶ Direct chat + rescue
                             ├── Buffer first ~50 chars
                             ├── Tool-call pattern? → execute + re-prompt
                             └── Normal text? → stream immediately
    │
    ▼
think_filter.py
    └── Strip <think> blocks from stream
    │
    ▼
SSE Stream → Frontend
```

---

## Test Suite Status

```
1055 passed, 39 skipped, 0 failed
```

### Key Test Files Modified/Created This Session
| File | Tests | What |
|------|-------|------|
| `backend/tests/unit/test_react_loop.py` | ~15 | Max iterations, duplicate guard, streaming iterations |
| `backend/tests/unit/test_phase5_agentic.py` | ~20 | Config constants including `REACT_MAX_ITERATIONS=5` |
| `backend/tests/unit/test_regex_fallback.py` | ~47 | Tool detection regex, disclosure detection, diagnostic gaps |
| `backend/tests/unit/test_chat_lifecycle.py` | ~30 | Conditioned code_display test on `CODE_EXECUTION_ENABLED` |

---

## Documentation Updated

| Document | What Changed |
|----------|-------------|
| `docs/ai-context/CLAUDE.md` | Pipeline description, test count 1055+, ReAct 5 iterations, new Recent Changes entry |
| `docs/ai-context/CODEBASE-MAP.md` | REACT_MAX_ITERATIONS=5, test count 1055+, pipeline description, tool detection quicklookup |
| `docs/ai-context/MICROGPT.md` | Architecture diagram with 3-tier + rescue, detection flow diagram, training epochs, confidence thresholds, Pipeline Defense Layers section, ReAct Loop Design section |
| `.github/copilot-instructions.md` | Updated classification rules, tool detection description |

---

## What the Next Engineer Should Do

1. **Run the diagnostic suite** against the live backend:
   ```bash
   python3 scripts/diagnose_llm.py --host https://api.dubya.ai --suite quick -v
   ```
2. **Deploy** — The Docker image needs rebuilding with these changes:
   ```bash
   ./scripts/trinity-deploy-production.sh test
   ```
3. **Verify tool calling** — Send "what's 17 times 23?" and confirm a single `tool_execution` + `tool_result` event (not doubled)
4. **Verify rescue mechanism** — If a query that should trigger a tool doesn't (detector miss), the rescue should catch the raw tool-call output and execute it
5. **Monitor ReAct iterations** — Check logs for iteration count; should rarely exceed 2-3 for normal queries
6. **Run full test suite** — `cd backend && python -m pytest tests/ -x -q` (expect 1055+ pass, 0 fail)

---

## Key Reference Files

| Task | File(s) |
|------|---------|
| Tool detection (3-tier) | `backend/services/tools.py` → `detect_tools_needed()` |
| ByteTransformer inference | `backend/services/tiny_classifier.py` |
| ReAct loop + guardrails | `backend/services/react_loop.py` |
| Pipeline + rescue | `backend/services/pipeline.py` |
| Classifier weights | `backend/models/tool_detector.npz`, `backend/models/query_classifier.npz` |
| Training scripts | `scripts/train_classifiers.py`, `scripts/generate_training_data.py` |
| Diagnostic suite | `scripts/diagnose_llm.py` |
| Config constants | `backend/config.py` (REACT_MAX_ITERATIONS, temperatures, etc.) |
| Architecture docs | `docs/ai-context/MICROGPT.md`, `docs/ai-context/CLAUDE.md` |
