# Trinity Backend — Incident & Handoff Report

> **Date:** February 13, 2026  
> **Scope:** ~25 files modified/created, ~1,000 lines changed  
> **Session:** Claude Opus 4.6 session `toasty-foraging-rivest` (~11 hours)  
> **Status:** All fixes applied. 709 tests passing. Ready for production deployment.

---

## Executive Summary

A Claude Opus 4.6 session implemented six major features in a single session:

1. **ReAct Agentic Loop** — iterative think/act/observe tool calling
2. **Native Ollama Tool Calling** — Qwen3/Llama3.1+ JSON function calling
3. **MemGPT Memory Tools** — save/recall/search user facts with embeddings
4. **MCP Server** — JSON-RPC 2.0 + stdio transport exposing Trinity's 8 tools
5. **MCP Client** — connector for external MCP servers
6. **Qwen3 Migration** — all 3 deployment tiers migrated from Qwen2.5/TinyLlama/phi3 to Qwen3

After this session, the `/generate` endpoint was completely broken. Every request returned:

```
generate.js:528 ❌ No generated text received
```

The root cause was a **4-part failure chain** where individually reasonable design decisions combined to produce zero output. An additional **frontend-backend key mismatch** meant conversation history was silently dropped from every request.

---

## What Broke and Why

### Root Cause Chain (4 linked issues)

```
Step 1: REACT_NATIVE_TOOLS defaults to "auto"
    → Qwen3 models auto-detected as supporting native tools
    → Native JSON tool calling enabled for all requests

Step 2: detect_tools_needed() has overly broad regex patterns
    → Nearly EVERY query matches (including "Hello, how are you?")
    → ReAct loop triggered for all requests, not just tool-worthy ones

Step 3: Qwen3 + native tools + thinking mode → answer in <think> blocks
    → Model puts entire answer inside <think>...</think> tags
    → The `content` field outside think blocks is empty

Step 4: _get_response_content() strips <think> blocks → empty string
    → Zero tokens extracted → 0-length response
    → Frontend receives empty response → "No generated text received"
```

### Independent Bug: Context Key Mismatch

The frontend sends `context_messages` in the JSON payload. The backend reads `contextMemory`. Result: **zero conversation history** reaches the model on every request. Every response was contextless, as if the user had no prior messages.

This was never caught because standalone prompts still work — you just lose all conversation continuity.

---

## What Was Fixed (6 fixes applied)

### Fix 1: Think-Block Fallback (`backend/services/react_loop.py`, lines 200-219)

**Problem:** `_get_response_content()` stripped `<think>` blocks and got empty string.  
**Fix:** Before stripping, extract text from inside think blocks. If stripping produces empty content, use the think-block text as the answer.

```python
# Before: stripped to empty, returned ""
content = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip()

# After: fallback to think-block content when stripped is empty
think_contents = re.findall(r"<think>(.*?)</think>", raw, flags=re.DOTALL)
content = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip()
if not content and think_contents:
    content = "\n".join(tc.strip() for tc in think_contents if tc.strip())
    logger.info("Think-block fallback: extracted %d chars from think blocks", len(content))
```

### Fix 2: Tightened `detect_tools_needed()` (`backend/services/tools.py`, lines 223-290)

**Problem:** Old patterns were too broad. Examples of false positives:
- `r"current|today|now"` → matched "What should I do **now**?"
- `r"who is|where is"` → matched "**Who is** smarter, cats or dogs?"
- `r"code|function|program"` → matched "This **function** of government…"
- `r"really|actually"` → matched "Is it **really** that hard?"

**Fix:** Every pattern now requires context anchoring:

| Tool | Old Pattern | New Pattern |
|------|------------|-------------|
| web_search | `r"current\|today\|now"` | `r"current (price\|news\|weather\|status\|version)"` |
| web_search | `r"who is\|where is"` | `r"who is \w+\s+\w+\|where is \w+\s+\w+"` |
| code_display | `r"code\|function\|program"` | `r"(write\|create\|generate) (a )?(code\|function)"` |
| fact_check | `r"really\|actually"` | `r"is that (really\|actually\|correct\|true)"` |
| document_search | `r"document\|file"` | `r"(this\|the\|my) (document\|file\|pdf)"` |

### Fix 3: Context Key Mismatch (`backend/routes/generate.py`, 4 locations)

**Problem:** Frontend sends `context_messages`, backend reads `contextMemory`.  
**Fix:** Dual-key lookup with fallback at lines 98, 338, 437, 555:

```python
# Before:
context_memory = data.get("contextMemory", [])

# After:
context_memory = data.get("context_messages", data.get("contextMemory", []))
```

### Fix 4: `REACT_NATIVE_TOOLS` Default (`backend/config.py`, line 195)

**Problem:** Default `"auto"` enabled native tools for Qwen3, which conflicted with thinking mode.  
**Fix:** Default changed to `"never"`:

```python
# Qwen3 native tools + thinking mode produces empty content;
# XML-based tool calling works reliably. Re-enable with "auto" after validation.
REACT_NATIVE_TOOLS = os.getenv("REACT_NATIVE_TOOLS", "never")
```

### Fix 5: Dead Code Cleanup

- **Deleted** `backend/services/model_router.py` — Qwen2.5-based routing, replaced by config-based multi-model
- **Removed** `TestModelRouting` class from `tests/integration/test_inference.py` (2 dead tests)
- **Removed** `TestModelRouter` class from `tests/unit/test_phase3_architecture.py` (8 dead tests)
- **Removed** `test_dockerfile_bakes_models` — references stale `qwen2.5:3b`/`qwen2.5:14b`

### Fix 6: Admin Auth Tests (`backend/tests/e2e/test_full_pipeline.py`)

**Problem:** 7 admin endpoint tests hit `/admin/*` without authentication headers. These endpoints require admin auth since the security hardening phase.  
**Fix:** Added `mock_admin_auth` fixture and wired it into all 7 tests.

---

## Transcript Forensic Findings

The full Claude Opus session transcript was recovered and analyzed (1,804 lines, `~/.claude/projects/`). Key findings:

### What the engineer missed:

1. **Never flagged `detect_tools_needed()` as too broad** — treated it as reliable throughout the session, never tested with casual inputs like "hello" or "what should I do now?"

2. **Think-block stripping was designed as a feature, not anticipated as a failure mode** — `_strip_think_blocks()` was added explicitly, but the case where the *entire response* lives inside think blocks was never considered.

3. **`context_messages` vs `contextMemory` mismatch was never noticed** — the frontend key was never checked. The engineer worked purely on the backend.

4. **No end-to-end testing** — the `/generate/agent` endpoint was never tested with a real or mocked request. Unit tests passed (mock-isolated), but they didn't cover the integration point where all four bugs interact.

5. **Session ended after fixing MCP test mock targets** — Opus declared "all tests pass" and stopped. This was true for unit tests but missed the functional regression.

---

## Files Inventory

### New Files (created by Opus, working correctly as-is)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/services/react_loop.py` | 465 | ReAct agentic loop (think/act/observe) |
| `backend/services/memory_tools.py` | 244 | MemGPT save/recall/search with embeddings + dedup |
| `backend/services/mcp_server.py` | 207 | MCP JSON-RPC 2.0 handler + async stdio server |
| `backend/services/mcp_client.py` | 281 | External MCP server connector |
| `backend/services/fact_check.py` | 80 | Dual web-search fact verification |
| `backend/mcp_stdio_server.py` | 53 | MCP stdio entry point (for Claude Desktop) |
| `backend/routes/mcp.py` | 98 | Flask `/mcp` endpoint (Blueprint) |
| `backend/tests/unit/test_mcp.py` | 397 | MCP server/client/route tests |
| `backend/tests/unit/test_memory_tools.py` | 439 | Memory tool tests |
| `backend/tests/unit/test_react_loop.py` | 318 | ReAct loop tests |
| `backend/tests/unit/test_tools_real.py` | 262 | Real tool implementation tests |

### Modified Files (by Opus, working correctly as-is)

| File | What Changed |
|------|-------------|
| `backend/services/code_executor.py` | `execute_tool()` expanded with real web_search, fact_check, document_search, memory tools, MCP fallback (replaced placeholder stubs) |
| `backend/services/complexity.py` | Added `tools_needed` field, `HEAVYWEIGHT_TOOLS` set, complexity bumping |
| `backend/services/tools.py` | Memory tool definitions (`save_memory`, `recall_memory`, `search_memory`), native tool calling functions, MCP tool registry |
| `backend/services/loading_messages.py` | Added `tool_execution` and `tool_result` loading phrase categories |
| `backend/services/graph/state.py` | Added `principal_id` to `AgentState` |
| `backend/services/graph/nodes.py` | Added `_execute_tool_calls_from_text()` with principal_id context, removed `_maybe_execute_code()` |
| `backend/services/graph/agents.py` | Rewritten prompts with XML tool call syntax, added memory tools to agents |
| `backend/services/graph/graph.py` | Threading `principal_id` through `execute()`/`execute_streaming()` |
| `backend/services/graph/llm.py` | Qwen3 thinking mode (`/think`/`/no_think`), `_strip_think_blocks()` |
| `deploy/akash/deploy-tier1-basic.yaml` | TinyLlama 1.1B → Qwen3:1.7b |
| `deploy/akash/deploy-tier2-balanced.yaml` | Qwen2.5:14b → Qwen3:8b |
| `deploy/akash/deploy-tier3-complex.yaml` | Qwen2.5:32b → Qwen3:32b, multi-model with 1.7b/8b/32b |

### Deleted Files

| File | Reason |
|------|--------|
| `backend/services/model_router.py` | Dead code — Qwen2.5-based routing replaced by config-based multi-model |

---

## Configuration Reference

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
| `MCP_SERVERS` | `[]` | JSON array of external MCP server configs |

### Model Tiers (Updated)

| Tier | Old Model | New Model | GPU |
|------|-----------|-----------|-----|
| 1 (Test) | TinyLlama 1.1B | Qwen3:1.7b | T4/RTX3090 |
| 2 (Balanced) | Qwen2.5:14b | Qwen3:8b | P40/T4 (16GB) |
| 3 (Complex) | Qwen2.5:32b | Qwen3:32b + 8b + 1.7b | A100 40GB |

---

## What Needs Attention Going Forward

### Re-enabling Native Tool Calling

`REACT_NATIVE_TOOLS` was set to `"never"` as a safety fix. The underlying issue is that Qwen3's native tool calling + thinking mode puts answers inside `<think>` blocks with empty `content` fields. To re-enable:

1. Set `REACT_NATIVE_TOOLS="auto"` in environment
2. Verify Qwen3 produces non-empty `content` with native tools
3. If not, the `_get_response_content()` fallback should handle it — but test thoroughly
4. Consider setting `QWEN3_THINKING_MODE="never"` when native tools are active

### Pattern Tuning

The tightened `detect_tools_needed()` patterns may be too conservative now. Monitor for:
- Users asking "what's the current time" → should trigger web_search but might not
- "Code this for me" → should trigger code_display, currently requires "write/create/generate"
- Adjust patterns in `backend/services/tools.py` lines 223-290 as real usage data comes in

### Docker Build

The Dockerfile copies `services/` and `routes/` as directories, so all new files are included automatically. `mcp_stdio_server.py` is at the backend root and is **not** copied into the Docker image — this is correct since it's only used for local Claude Desktop integration.

### New Dependencies

Already in `requirements.txt`:
- `numpy==1.26.4` (for memory tool embeddings)
- `mcp>=1.0.0` (for MCP server/client)

---

## How to Deploy

```bash
# Build, push, deploy to Akash, update Cloudflare, deploy ICP frontend
./scripts/trinity-deploy-production.sh 2   # Tier 2 (Qwen3 8B, ~$50/mo)
```

### Post-Deploy Verification

```bash
# Health check
curl https://api.dubya.ai/health

# Simple generate (should return non-empty response)
curl -X POST https://api.dubya.ai/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, how are you?"}'

# MCP info
curl https://api.dubya.ai/mcp
```

---

## Test Status

```
709 passed, 9 skipped, 0 failed
```

All test suites:
- `tests/unit/` — 24 test files (complexity, encryption, MCP, memory tools, ReAct, tools, etc.)
- `tests/integration/` — Real Ollama tests (skipped without Ollama running)
- `tests/e2e/` — Full pipeline with mocked auth + Ollama
- `tests/fixtures/` — Shared auth fixtures

---

## Lessons Learned

1. **Broad regex patterns in routing logic are time bombs.** A pattern like `r"current|today|now"` will match conversational language and silently route simple queries through expensive agentic pipelines.

2. **Think-block stripping needs a fallback path.** When a model format puts the answer inside metadata tags, stripping those tags must check if the result is empty and recover gracefully.

3. **Frontend-backend key names must be verified at integration time.** Unit tests with mocked data won't catch `context_messages` vs `contextMemory` mismatches.

4. **Feature flags should default to the safest option.** `REACT_NATIVE_TOOLS="auto"` auto-enabled an untested code path. Defaulting to `"never"` until validation is the correct approach.

5. **End-to-end testing after large changes is non-negotiable.** This session created 6 new files and modified 16 existing ones. A single `curl` to `/generate` would have caught the regression immediately.
