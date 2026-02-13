# Trinity Agentic Overhaul — Complete Engineering Specification

**Date:** February 12, 2026
**Status:** Pre-implementation — approved for Phase 1 execution
**Authors:** Development Team + Research Team
**Purpose:** Definitive contract between dev and research teams. Every change enumerated with exact paths, line numbers, rationale, and verification.

---

## Table of Contents

1. [Current State Audit](#1-current-state-audit)
2. [Phase 1: Dead Code Removal](#2-phase-1-dead-code-removal)
3. [Phase 2: Pipeline Simplification](#3-phase-2-pipeline-simplification)
4. [Phase 3: Memory System Overhaul](#4-phase-3-memory-system-overhaul)
5. [Phase 4: Model Upgrade](#5-phase-4-model-upgrade)
6. [Phase 5: Agentic Scaffolding](#6-phase-5-agentic-scaffolding)
7. [Verification Matrix](#7-verification-matrix)
8. [Risk Register](#8-risk-register)
9. [Decisions Log](#9-decisions-log)
10. [Appendices](#appendices)

---

## 1. Current State Audit

### 1.1 File Inventory — What Exists

| File | Lines | Purpose | Verdict |
|------|-------|---------|---------|
| `backend/services/agent.py` | ~1,150 | Multi-pass pipeline orchestrator | **GUT** — keep ReAct routing, delete multi-pass |
| `backend/services/agent_prompts.py` | ~513 | 6 prompt templates + 3 XML parsers | **GUT** — keep 2 prompts, delete 4 + parsers |
| `backend/services/complexity.py` | ~401 | Regex-based complexity classifier | **DELETE ENTIRELY** |
| `backend/services/react_loop.py` | ~480 | ReAct tool-calling loop | **KEEP** — fix native tool dead code |
| `backend/services/tools.py` | ~418+ | Tool definitions + native tool code | **KEEP** — delete native tool functions |
| `backend/services/memory.py` | ~200+ | Semantic memory retrieval | **FIX** — return type bug |
| `backend/services/memory_tools.py` | ~300+ | MemGPT-style persistent facts | **FIX** — format inconsistency |
| `backend/services/vector_store.py` | ~250+ | FastEmbed vector indexing | **KEEP** — fix indexing calls |
| `backend/services/embeddings.py` | ~195 | FastEmbed wrapper + caching | **KEEP** |
| `backend/services/graph/` | 7 files | LangGraph parallel pipeline | **DELETE ENTIRELY** |
| `backend/services/parallel.py` | ~200+ | Parallel execution experiments | **DELETE ENTIRELY** |
| `backend/services/experiments.py` | ~150+ | A/B test experiments | **DELETE ENTIRELY** |
| `backend/services/voting.py` | ~270 | Self-consistency voting | **DELETE ENTIRELY** |
| `backend/middleware/ab_test.py` | ~100+ | A/B test middleware | **DELETE ENTIRELY** |
| `backend/routes/generate.py` | ~737 | 6 generation endpoints | **GUT** — collapse to 2-3 endpoints |
| `backend/routes/admin.py` | ~131 | Admin experiment endpoints | **GUT** — remove experiment endpoints |
| `backend/config.py` | ~241 | All configuration | **GUT** — remove dead config sections |
| `backend/inference_server.py` | ~368 | Flask app + feature detection | **EDIT** — remove LangGraph/voting detection |
| `trinity-icp/src/state/store.js` | ~335 | Zustand state + context window | **FIX** — increase CONTEXT_WINDOW_SIZE |
| `trinity-icp/src/state/contextMemory.js` | ~65 | Conversation summarization | **EVALUATE** — may become unnecessary |

### 1.2 Dependency Inventory — What Can Be Removed

| Package | Size | Used By | Verdict |
|---------|------|---------|---------|
| `langgraph==0.2.62` | ~50MB | `services/graph/` only | **REMOVE** from requirements.txt |
| `langchain-core==0.3.29` | ~30MB | `services/graph/` only | **REMOVE** from requirements.txt |
| `langchain-community==0.3.14` | ~20MB | `services/graph/` only | **REMOVE** from requirements.txt |
| `fastembed==0.7.4` | ~100MB | `embeddings.py`, `vector_store.py` | **KEEP** |
| `numpy==1.26.4` | ~30MB | `vector_store.py`, `memory.py` | **KEEP** |
| `RestrictedPython==8.1` | ~1MB | `code_executor.py` | **KEEP** |
| `mcp>=1.0.0` | ~5MB | `mcp_server.py`, `mcp_client.py` | **KEEP** (optional) |

**Net dependency reduction:** ~100MB removed from Docker image.

### 1.3 Endpoint Inventory — Current vs Target

| Endpoint | Current Purpose | Frontend Usage | Target |
|----------|----------------|----------------|--------|
| `POST /generate` | Non-streaming, full auth/metrics | Fallback path | **KEEP** |
| `POST /generate/stream` | Streaming with context/reasoning | Main chat path | **KEEP — becomes primary** |
| `POST /generate/simple` | Non-streaming, no auth/context | `api.js generateSimple()` | **KEEP** (used by frontend) |
| `POST /generate/simple/stream` | Streaming, no auth/context | **NOT USED** by frontend | **DELETE** |
| `POST /generate/agent` | Agent multi-pass streaming | Main agent path | **MERGE into /generate/stream** |
| `POST /generate/langgraph` | LangGraph multi-agent | **NOT USED** by frontend | **DELETE** |

### 1.4 Known Bugs — Exhaustive List

| ID | Location | Bug Description | Impact | Fix Phase |
|----|----------|----------------|--------|-----------|
| B1 | `agent.py L107-115` | `_format_user_memory()` does `f"- {fact}"` on dict objects, rendering as `"- {'text': '...', 'embedding': [0.1, ...]}"` | Model sees Python dict syntax + 384-float arrays in prompt | Phase 3 |
| B2 | `generate.py L493` | `add_message_embedding()` called without required `chat_id` and `message_index` params | SQLite INSERT fails — semantic memory never populated | Phase 3 |
| B3 | `generate.py L466` | `build_enhanced_context()` returns `str` but caller destructures as `(enhanced_context, semantic_context)` tuple | TypeError crash → falls back to raw context, V4 semantic memory is dead | Phase 3 |
| B4 | `memory_tools.py` vs `chat.py` | Two incompatible fact schemas: API creates `{"fact": "..."}`, tools create `{"text": "...", "embedding": [...]}` | `recall_memory` can't find API-created facts (no embeddings); prompt formatting crashes on tool-created facts | Phase 3 |
| B5 | `store.js` | `CONTEXT_WINDOW_SIZE = 6` — only 6 messages in sliding window | Model forgets everything beyond 3 exchanges — catastrophic for coding sessions | Phase 3 |
| B6 | `contextMemory.js` | `conversationSummary` stored only in Zustand state (client-side RAM) | Long conversation context disappears on page refresh | Phase 3 |
| B7 | `react_loop.py` | Native tool calling code paths exist but `REACT_NATIVE_TOOLS = "never"` permanently | Dead code branches that add complexity and risk | Phase 1 |
| B8 | `agent_prompts.py L470` | Same dict-as-string rendering as B1, different code path (`build_execute_prompt`) | Duplicate of B1 — both must be fixed | Phase 3 |

### 1.5 Current Memory Architecture — 4 Layers

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Context Memory (Frontend — store.js)              │
│  Sliding window of last 6 messages                          │
│  Stored in Zustand (lost on refresh)                        │
│  Sent to backend as context_messages array                  │
│  PROBLEM: 6 messages is catastrophically small              │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: Conversation Summary (Frontend — contextMemory.js)│
│  LLM-compressed summary every 15 messages                   │
│  Cumulative bullet points, prepended as system message      │
│  PROBLEM: Lossy, lost on refresh, same model compresses     │
├─────────────────────────────────────────────────────────────┤
│  LAYER 3: Semantic Memory (Backend — memory.py + vector_*)  │
│  FastEmbed 384-dim embeddings, SQLite storage per user      │
│  retrieve_context() → working memory + semantic matches     │
│  PROBLEM: Never indexed (B2), return type broken (B3)       │
├─────────────────────────────────────────────────────────────┤
│  LAYER 4: User Memory / MemGPT (Backend — memory_tools.py) │
│  Persistent facts with embeddings, dedup at 0.95 cosine    │
│  save_memory / recall_memory / search_memory tools          │
│  PROBLEM: Dual schemas (B4), dict rendering (B1/B8)         │
└─────────────────────────────────────────────────────────────┘
```

### 1.6 Current Pipeline Architecture — Multi-Pass

```
User Question
     ↓
┌─────────────────────────────────────────────────┐
│  COMPLEXITY CLASSIFIER (complexity.py)          │
│  Regex-based: simple / medium / complex         │
│  401 lines of pattern matching                  │
└─────────────────────────────────────────────────┘
     ↓
┌─ SIMPLE (1 pass) ──────────────────────────────┐
│  Direct execute → stream response              │
│  OR ReAct loop if tools detected               │
└────────────────────────────────────────────────┘
┌─ MEDIUM (3 passes) ───────────────────────────┐
│  1. Understand (non-streaming, temp=0.3)       │
│  2. Execute (streaming, temp=0.7)              │
│  3. Critique (non-streaming, temp=0.3)         │
│     → If score < 7: Refine pass               │
└────────────────────────────────────────────────┘
┌─ COMPLEX (5 passes) ──────────────────────────┐
│  1. Understand → 2. Plan → 3. Execute          │
│  4. Critique → 5. Refine (if score < 7, 2x)   │
└────────────────────────────────────────────────┘

Token overhead per complex question: ~4,000 tokens of pipeline infrastructure
Latency: 3-5x slower than single-pass
Self-critique effectiveness: UNPROVEN (research says ineffective without external verification)
```

### 1.7 Dependency Graph — What Imports What

```
config.py ←─────────────────────────────────────────────────┐
    ├──→ tools.py (CODE_EXECUTION_ENABLED)                  │
    ├──→ react_loop.py (REACT_MAX_ITERATIONS, REACT_NATIVE_TOOLS, QWEN3_*)
    ├──→ agent.py (REACT_ENABLED, MULTI_MODEL_*)            │
    └──→ generate.py (20+ constants)                        │
                                                            │
agent_prompts.py (ZERO project deps — cleanest file)        │
    ├──→ agent.py (all builders + parsers + dataclasses)    │
    └──→ react_loop.py (REACT_SYSTEM_PROMPT, TOOL_PROMPT_SECTION)
                                                            │
complexity.py                                               │
    ├──→ tools.py (detect_tools_needed)                     │
    └──→ agent.py (ComplexityLevel, analyze_question, get_pass_count)
                                                            │
tools.py ←── config.py                                      │
    ├──→ complexity.py (detect_tools_needed)                 │
    ├──→ react_loop.py (parse/extract functions, ToolResult) │
    └──→ agent.py (detect_tools_needed)                      │
                                                            │
react_loop.py ←── config, agent_prompts, tools, code_executor
    └──→ agent.py (ReactLoop)                                │
                                                            │
code_executor.py ←── config.py                              │
    └──→ react_loop.py (_run_tools → execute_tool)           │
                                                            │
generate.py (route layer — entry point)                     │
    ├──→ config, middleware/*, routes/shared, storage        │
    ├──→ services/agent.py (AgentPipeline)                   │
    ├──→ services/complexity.py (classify_complexity)        │
    ├──→ services/memory.py (build_enhanced_context)         │
    ├──→ services/vector_store.py (get_user_vector_store)    │
    ├──→ services/graph/ (execute_graph, should_use_langgraph) ← DELETE
    ├──→ services/parallel.py (get_parallel_pipeline)        ← DELETE
    └──→ services/experiments.py + middleware/ab_test.py      ← DELETE

inference_server.py (app init)
    ├──→ services/graph (LangGraph detection)                ← DELETE
    ├──→ services/voting (V4_VOTING_AVAILABLE)               ← DELETE
    └──→ All V4 feature flags → app.config
```

---

## 2. Phase 1: Dead Code Removal

**Goal:** Remove ~2,000 lines of unused code and ~100MB of Python packages. Make the codebase readable before rebuilding.

**Estimated effort:** 2-4 hours
**Risk:** Low (deleting unused code)
**Rollback:** `git revert` to pre-Phase-1 commit

### 1.1 Delete LangGraph Pipeline

**Files to delete entirely:**

```bash
rm -rf backend/services/graph/          # 7 files: __init__.py, agents.py, edges.py, graph.py, llm.py, nodes.py, state.py
rm -f backend/services/parallel.py       # ~200+ lines — parallel execution
rm -f backend/services/experiments.py    # ~150+ lines — A/B test definitions
rm -f backend/middleware/ab_test.py      # ~100+ lines — A/B middleware
```

**Files to edit — remove references:**

**`backend/routes/generate.py`:**
- Delete the entire `/generate/langgraph` route function (L512-L737, ~225 lines)
- Delete the `/generate/simple/stream` route function (L270-L320, ~50 lines)
- Remove any lazy imports of `services.graph`, `services.parallel`, `middleware.ab_test`, `services.experiments`

**`backend/inference_server.py`:**
- Delete LangGraph detection block (L107-L114):
  ```python
  # DELETE THIS BLOCK:
  LANGGRAPH_AVAILABLE = False
  try:
      from services.graph import execute_graph
      from services.graph.edges import should_use_langgraph
      LANGGRAPH_AVAILABLE = True
      logger.info("✅ LangGraph multi-agent system: ENABLED")
  except Exception as e:
      logger.warning(f"⚠️ LangGraph not available: {e}")
  ```
- Delete `app.config["LANGGRAPH_AVAILABLE"] = LANGGRAPH_AVAILABLE` (L168)

**`backend/routes/admin.py`:**
- Delete the 4 experiment endpoints (L15-L76): `get_experiments_status`, `enable_experiment_endpoint`, `disable_experiment_endpoint`, `get_experiment_assignments`
- These use lazy `from services.experiments import ...` — the ImportError catch would return 503 anyway, but cleaner to remove

**`backend/requirements.txt`:**
- Delete these 3 lines:
  ```
  langgraph==0.2.62
  langchain-core==0.3.29
  langchain-community==0.3.14
  ```

### 1.2 Delete Voting Module

**File to delete:**
```bash
rm -f backend/services/voting.py         # ~270 lines
```

**`backend/inference_server.py`:**
- Delete voting detection block (L85-L89):
  ```python
  # DELETE:
  try:
      from services.voting import V4_VOTING_AVAILABLE
      logger.info(f"✅ voting: V4_VOTING_AVAILABLE={V4_VOTING_AVAILABLE}")
  except Exception as e:
      ...
  ```
- Delete `"voting": V4_VOTING_AVAILABLE` from `app.config["V4_FEATURES"]` dict (L165)

### 1.3 Delete Dead Code in agent.py

**`backend/services/agent.py` — delete these methods/functions:**

| Item | Approximate Lines | Why |
|------|-------------------|-----|
| `init_multi_model_config()` | L136-L153 (~18 lines) | Multi-model disabled, never called |
| `OllamaClient._get_model_for_pass()` | L208-L230 (~23 lines) | Multi-model routing, always returns `self.model` |
| `AgentPipeline.process()` (non-streaming) | L559-L668 (~110 lines) | Only called from deleted `/generate/langgraph` |
| Any `enable_voting` parameter handling | Various | Voting deleted |

### 1.4 Delete Native Tool Calling Dead Code

**`backend/services/tools.py` — delete these functions:**

| Function | Approximate Lines | Why |
|----------|-------------------|-----|
| `model_supports_native_tools()` | L316-L319 (~4 lines) | Always returns False in practice |
| `get_native_tool_definitions()` | L322-L359 (~38 lines) | Converts to Ollama JSON format — never used |
| `extract_native_tool_calls()` | L362-L396 (~35 lines) | Parses native response — never used |
| `get_all_tool_definitions()` | L404-L418 (~15 lines) | Merges local + MCP tools — MCP client disabled |

**`backend/services/react_loop.py` — delete/simplify:**

| Item | Lines | Change |
|------|-------|--------|
| `_should_use_native()` | L98-L105 | Delete — always returns False |
| `_is_qwen3()` | L93-L96 | Delete — only used by `_should_use_native` |
| Native tool calling branches in `execute()` and `execute_streaming()` | Various `if self.use_native_tools:` | Replace with XML-only path |

### 1.5 Clean config.py

**Delete these sections from `backend/config.py`:**

| Section | Lines | Variables |
|---------|-------|-----------|
| Multi-model | L146-L157 | `FAST_MODEL`, `SMART_MODEL`, `REASONING_MODEL`, `MULTI_MODEL_ENABLED` |
| Native tools | L196 | `REACT_NATIVE_TOOLS` |
| Qwen3 thinking | L201-L204 | `QWEN3_THINKING_MODE`, `QWEN3_THINKING_BUDGET` |
| MCP client | L214-L217 | `MCP_CLIENT_ENABLED`, `MCP_SERVERS_CONFIG` |
| Self-consistency voting | L220-L224 | `VOTING_CANDIDATES`, `VOTING_TEMPERATURES`, `VOTING_MIN_COMPLEXITY` |

**Keep:** `REACT_ENABLED`, `REACT_MAX_ITERATIONS`, `MCP_SERVER_ENABLED`, `MEMORY_TOOLS_ENABLED`, `CODE_EXECUTION_ENABLED`

### 1.6 Phase 1 Verification Checklist

```bash
cd /Users/gduby/Documents/Trinity/Trinity

# 1. No dangling imports (Python syntax check)
find backend -name "*.py" -not -path "*.bak" -exec python3 -c "import ast; ast.parse(open('{}').read())" \;

# 2. No references to deleted modules
grep -rn "from services.graph\|from services.parallel\|from services.experiments\|from middleware.ab_test\|from services.voting" backend/ --include="*.py" | grep -v ".bak"
# Expected: ZERO matches

# 3. No references to deleted config
grep -rn "MULTI_MODEL\|FAST_MODEL\|SMART_MODEL\|REASONING_MODEL\|REACT_NATIVE_TOOLS\|QWEN3_THINKING\|VOTING_CANDIDATES\|VOTING_TEMPERATURES\|MCP_CLIENT_ENABLED\|MCP_SERVERS_CONFIG" backend/ --include="*.py" | grep -v ".bak" | grep -v "config.py"
# Expected: ZERO matches

# 4. No langchain imports
grep -rn "langgraph\|langchain" backend/ --include="*.py" | grep -v ".bak" | grep -v "requirements"
# Expected: ZERO matches

# 5. Docker build succeeds
cd deploy/docker && docker build -t trinity-test -f Dockerfile ../../backend && cd ../..

# 6. Container starts and health check passes
docker run --rm -d --name trinity-test -p 5001:5001 trinity-test
sleep 15
curl -s http://localhost:5001/health | python3 -m json.tool
docker stop trinity-test

# 7. Line count comparison
find backend -name "*.py" -not -path "*.bak" -not -path "*__pycache__*" | xargs wc -l | tail -1
# Record: _____ lines (expected: ~1,500-2,000 fewer than before)

# 8. Deleted files don't exist
test ! -d backend/services/graph && echo "PASS: graph/ deleted"
test ! -f backend/services/parallel.py && echo "PASS: parallel.py deleted"
test ! -f backend/services/experiments.py && echo "PASS: experiments.py deleted"
test ! -f backend/middleware/ab_test.py && echo "PASS: ab_test.py deleted"
test ! -f backend/services/voting.py && echo "PASS: voting.py deleted"
```

---

## 3. Phase 2: Pipeline Simplification

**Goal:** Replace 5-pass Understand→Plan→Execute→Critique→Refine with single-pass + ReAct. Remove complexity classification entirely.

**Estimated effort:** 4-6 hours
**Risk:** Medium (changing core generation logic)
**Rollback:** `git revert` to Phase 1 commit

### 2.1 Delete Complexity Classifier

**Delete entire file:**
```bash
rm -f backend/services/complexity.py    # 401 lines
```

**Update imports** — all files that reference complexity:

| File | Reference | Action |
|------|-----------|--------|
| `agent.py` | `from .complexity import ComplexityLevel, analyze_question, get_pass_count` | Delete import, remove complexity-based branching |
| `generate.py` | `from services.complexity import classify_complexity` (lazy import in `/generate/langgraph`) | Already deleted in Phase 1 |

### 2.2 Replace Multi-Pass with Single-Pass in agent.py

**Delete these methods from `AgentPipeline`:**

| Method | Lines | Purpose | Replacement |
|--------|-------|---------|-------------|
| `_pass_understand()` | ~L945-L963 | Non-streaming classify | None |
| `_pass_plan()` | ~L965-L981 | Non-streaming plan | None |
| `_pass_execute()` | ~L983-L1022 | Non-streaming execute | None |
| `_pass_execute_simple()` | ~L1024-L1053 | Simple execute | Merged into new `process_streaming()` |
| `_pass_critique()` | ~L1055-L1084 | Non-streaming self-critique | None — research proven ineffective |
| `_pass_refine()` | ~L1086-L1102 | Streaming refinement | None |
| Multi-pass orchestration in `process_streaming()` | ~L670-L939 | if/elif for simple/medium/complex | Replace with single-pass logic |

**New `process_streaming()` pseudocode:**

```python
def process_streaming(self, question, context_messages, user_memory,
                      semantic_context=None, principal_id=None):
    """Single-pass agent: build prompt → detect tools → stream or ReAct."""

    # 1. Format user memory (fixed — no more dict rendering)
    user_memory_text = format_user_memory(user_memory)

    # 2. Detect if tools are needed (keep existing heuristic from tools.py)
    tools_needed = detect_tools_needed(question)

    # 3. Build system prompt — dynamic tool injection
    if tools_needed:
        system_prompt = build_system_prompt_with_tools(
            user_memory=user_memory_text,
            semantic_context=semantic_context
        )
    else:
        system_prompt = build_system_prompt(
            user_memory=user_memory_text,
            semantic_context=semantic_context
        )

    # 4. Build messages array
    messages = [{"role": "system", "content": system_prompt}]
    for msg in context_messages:
        messages.append({"role": msg["role"], "content": msg["content"][:2000]})
    messages.append({"role": "user", "content": question})

    # 5. Route: tools → ReAct loop, otherwise → direct stream
    if tools_needed:
        react = self._get_react_loop(principal_id)
        yield from react.execute_streaming(messages)
    else:
        yield from self.client.chat_stream(messages, max_tokens=MAX_TOKENS)
```

**Target agent.py size after Phase 2:** ~300-400 lines (down from ~1,150)

### 2.3 Simplify Prompt Templates

**`backend/services/agent_prompts.py` — delete these templates and parsers:**

| Item | Lines | Action |
|------|-------|--------|
| `UNDERSTAND_PROMPT` | ~L103-L113 | **DELETE** |
| `PLAN_PROMPT` | ~L120-L131 | **DELETE** |
| `EXECUTE_PROMPT_WITH_PLAN` | ~L138-L161 | **DELETE** |
| `CRITIQUE_PROMPT` | ~L185-L206 | **DELETE** |
| `REFINE_PROMPT` | ~L213-L225 | **DELETE** |
| `UnderstandingResult` dataclass | ~L232-L240 | **DELETE** |
| `PlanResult` dataclass | ~L243-L248 | **DELETE** |
| `CritiqueResult` dataclass | ~L251-L258 | **DELETE** |
| `parse_understanding()` | ~L312-L338 | **DELETE** |
| `parse_plan()` | ~L341-L351 | **DELETE** |
| `parse_critique()` | ~L354-L370 | **DELETE** |
| `build_understand_prompt()` | ~L377-L391 | **DELETE** |
| `build_plan_prompt()` | ~L394-L408 | **DELETE** |
| `build_critique_prompt()` | ~L493-L497 | **DELETE** |
| `build_refine_prompt()` | ~L500-L513 | **DELETE** |

**Keep and refactor:**

| Item | Action |
|------|--------|
| `EXECUTE_PROMPT_SIMPLE` | **RENAME** → `SYSTEM_PROMPT` — becomes primary |
| `REACT_SYSTEM_PROMPT` | **KEEP** — used by ReAct loop |
| `TOOL_PROMPT_SECTION` | **KEEP** — injected dynamically when tools needed |
| `parse_xml_tag()` | **KEEP** — used by ReAct for tool call parsing |
| `parse_numbered_list()` | **KEEP** — general utility |
| `build_execute_prompt()` | **REFACTOR** → `build_system_prompt()` — simplified |

**New prompt structure (2 prompts only):**

```python
SYSTEM_PROMPT = """You are Trinity, a helpful AI assistant.

{user_memory_section}

{semantic_context_section}

Respond directly and concisely. Use markdown for formatting.
Use LaTeX ($$...$$ or $...$) for math equations."""

# Token cost: ~100-200 tokens (before memory/context injection)
# Compare to current: 3,000-5,000 tokens

SYSTEM_PROMPT_WITH_TOOLS = """You are Trinity, a helpful AI assistant with tools.

{user_memory_section}

{semantic_context_section}

## Available Tools
{tool_definitions}

## Tool Protocol
To use a tool, output exactly:
<tool_call name="tool_name">
<param_name>value</param_name>
</tool_call>

Wait for the result before continuing. Provide your final answer directly when done.

Respond directly and concisely. Use markdown for formatting.
Use LaTeX ($$...$$ or $...$) for math equations."""

# Token cost: ~400-600 tokens (before memory/context injection)
```

**Critical change:** No more anti-XML instructions ("NEVER use `<tool_call>` in your final answer"). These paradoxically teach the model about XML syntax.

### 2.4 Dynamic Tool Injection

**Current behavior:** Tool definitions (~600 tokens) included in EVERY prompt, regardless of whether tools are needed.

**New behavior:** `detect_tools_needed()` from `tools.py` (existing function, ~80 lines of regex) determines if tools are likely needed. Tool definitions only injected when the heuristic returns non-empty.

**Impact:** ~600 tokens saved per non-tool query. At 70%+ of queries being non-tool, this is significant.

### 2.5 Update Frontend — Remove Multi-Pass Handling

Search `trinity-icp/src/` for any handling of:

| Pattern | Purpose | Action |
|---------|---------|--------|
| `{"clear": true}` SSE event | Refinement signal — erase and re-stream | **REMOVE** handling |
| `pass: "understand"` | Phase update indicator | **REMOVE** handling |
| `pass: "plan"` | Phase update indicator | **REMOVE** handling |
| `pass: "critique"` | Phase update indicator | **REMOVE** handling |
| `pass: "refine"` | Phase update indicator | **REMOVE** handling |
| `pipeline` or `complexity` in request body | Force complexity routing | **REMOVE** from request |

After Phase 2, the frontend expects: tokens stream in → display them → `{"done": true}` → done.

### 2.6 Merge `/generate/agent` into `/generate/stream`

After simplification, there's no reason for two streaming endpoints. The `/generate/stream` endpoint should incorporate the agent pipeline (which is now just single-pass + optional ReAct).

**Before:** Frontend must choose between `/generate/stream` (direct Ollama) and `/generate/agent` (agent pipeline)
**After:** `/generate/stream` always uses the agent pipeline (which is now lightweight enough to be the default)

### 2.7 Phase 2 Verification Checklist

```bash
# 1. No complexity references
grep -rn "complexity\|ComplexityLevel\|classify_complexity\|analyze_question\|get_pass_count\|SIMPLE_PATTERNS\|COMPLEX_PATTERNS\|MEDIUM_PATTERNS" backend/ --include="*.py" | grep -v ".bak"
# Expected: ZERO matches

# 2. No multi-pass references
grep -rn "UNDERSTAND_PROMPT\|PLAN_PROMPT\|CRITIQUE_PROMPT\|REFINE_PROMPT\|_pass_understand\|_pass_plan\|_pass_critique\|_pass_refine\|UnderstandingResult\|PlanResult\|CritiqueResult" backend/ --include="*.py" | grep -v ".bak"
# Expected: ZERO matches

# 3. Prompt token count verification
python3 -c "
prompt = '''You are Trinity, a helpful AI assistant. Respond directly and concisely.'''
print(f'Base prompt: ~{len(prompt.split())} words / ~{len(prompt)//4} tokens')
"
# Target: <200 tokens base, <600 tokens with tools

# 4. Streaming works end-to-end
# Open browser → send message → verify tokens stream smoothly without gaps
# No more "Understanding..." → "Planning..." → "Executing..." phase indicators

# 5. ReAct still works
# Send: "What is 42 * 17?"
# Verify: calculator tool is called, result (714) is returned

# 6. Latency comparison
# Time a complex query with both old (git stash) and new pipelines
# Expected: 3-5x faster (1 LLM call vs 3-5 LLM calls)

# 7. File count
test ! -f backend/services/complexity.py && echo "PASS: complexity.py deleted"
find backend -name "*.py" -not -path "*.bak" -not -path "*__pycache__*" | xargs wc -l | tail -1
# Record: _____ lines (expected: ~800-1,000 fewer than Phase 1)
```

---

## 4. Phase 3: Memory System Overhaul

**Goal:** Fix all 8 bugs, unify 4 memory layers into 3, increase context window 6→20.

**Estimated effort:** 6-8 hours
**Risk:** Medium-High (data format migration, multiple interacting systems)
**Rollback:** `git revert` to Phase 2 commit

### 3.1 Fix B1 + B8: User Memory Dict Rendering

**Root cause analysis:**

Facts stored by `memory_tools.py tool_save_memory()` have schema:
```python
{
    "text": "User's name is Greg",
    "category": "personal",
    "importance": 4,
    "embedding": [0.0123, 0.0456, ...],  # 384 floats!
    "created_at": 1707700000
}
```

When `_format_user_memory()` does `f"- {fact}"`, Python calls `dict.__repr__()`, producing:
```
- {'text': "User's name is Greg", 'category': 'personal', 'importance': 4, 'embedding': [0.0123, 0.0456, 0.0789, ...384 more floats...], 'created_at': 1707700000}
```

This pollutes the prompt with hundreds of tokens of garbage.

**Fix — new `_format_user_memory()` in agent.py:**

```python
def _format_user_memory(user_memory):
    """Format user memory facts for prompt injection."""
    if not user_memory or not isinstance(user_memory, dict):
        return ""

    facts = user_memory.get("facts", [])
    if not facts:
        return ""

    lines = []
    for fact in facts[:10]:  # Cap at 10 facts
        if isinstance(fact, dict):
            text = fact.get("text") or fact.get("fact") or ""
            if not text:
                continue
            category = fact.get("category", "")
            if category and category != "general":
                lines.append(f"- [{category}] {text}")
            else:
                lines.append(f"- {text}")
        elif isinstance(fact, str):
            lines.append(f"- {fact}")

    if not lines:
        return ""

    return "## What you know about this user\n" + "\n".join(lines)
```

**Same pattern must be applied in `agent_prompts.py build_execute_prompt()`** (B8) — or, after Phase 2 simplification, there's only one prompt injection point.

**Verification test:**
```python
# Both fact formats render cleanly
facts = {"facts": [
    {"text": "User's name is Greg", "category": "personal", "importance": 4,
     "embedding": [0.1]*384, "created_at": 1707700000},
    {"fact": "Prefers dark mode", "addedAt": 1707700000},
    "Plain string fact"
]}
result = _format_user_memory(facts)
assert "embedding" not in result
assert "0.1" not in result       # No embedding floats
assert "Greg" in result
assert "dark mode" in result
assert "Plain string" in result
assert len(result) < 500          # Reasonable size
```

### 3.2 Fix B2: Vector Indexing Missing Parameters

**Current broken call in `generate.py` ~L493:**
```python
vector_store.add_message_embedding(content=user_prompt, role="user", timestamp=time.time())
# Missing: chat_id, message_index — SQLite INSERT will fail
```

**Fix:** Add the required parameters. The frontend must send `chat_id` (already available as `State.currentChatId`):

**Backend fix (`generate.py`):**
```python
# After receiving complete response, index BOTH messages
chat_id = data.get("chat_id", "default")
msg_count = len(context_memory)  # Approximate message index

# Index user message
vector_store.add_message_embedding(
    chat_id=chat_id,
    message_index=msg_count,
    role="user",
    content=user_prompt[:2000],  # Truncate for embedding
    embedding=embed_text(user_prompt[:2000])
)

# Index assistant response (after streaming completes)
vector_store.add_message_embedding(
    chat_id=chat_id,
    message_index=msg_count + 1,
    role="assistant",
    content=full_response[:2000],
    embedding=embed_text(full_response[:2000])
)
```

**Frontend fix — send chat_id in request body:**
```javascript
// In the streaming request body construction
const requestBody = {
    prompt: userMessage,
    context_messages: contextMessages,
    principal: principal,
    chat_id: State.currentChatId,       // ADD THIS
    message_index: State.chatHistory.length,  // ADD THIS
    // ...existing fields
};
```

### 3.3 Fix B3: `build_enhanced_context()` Return Type

**Current broken code in `generate.py` ~L466:**
```python
enhanced_context, semantic_context = build_enhanced_context(
    principal_id=principal, query=user_prompt, recent_messages=context_memory
)
# This crashes: build_enhanced_context() returns a str, not a tuple
```

**Fix — update `memory.py` to return a NamedTuple:**

```python
from typing import NamedTuple, List, Optional

class EnhancedContext(NamedTuple):
    """Result of semantic memory retrieval."""
    full_context: List[dict]        # Messages with semantic context prepended
    semantic_summary: Optional[str]  # Formatted semantic matches for logging

def build_enhanced_context(principal_id, query, recent_messages=None):
    """Build context enhanced with semantic memory retrieval."""
    recent_messages = recent_messages or []

    try:
        sem_memory = get_semantic_memory(principal_id)
        context = sem_memory.retrieve_context(query, chat_id=None)
        semantic_text = sem_memory.format_context_for_prompt(context)

        if semantic_text:
            enhanced = [{"role": "system", "content": f"## Relevant past context\n{semantic_text}"}]
            enhanced.extend(recent_messages)
            return EnhancedContext(full_context=enhanced, semantic_summary=semantic_text)
    except Exception as e:
        logger.warning(f"Semantic retrieval failed: {e}")

    return EnhancedContext(full_context=recent_messages, semantic_summary=None)
```

**Update caller in `generate.py`:**
```python
result = build_enhanced_context(principal_id=principal, query=user_prompt, recent_messages=context_memory)
enhanced_context = result.full_context
semantic_context = result.semantic_summary
```

### 3.4 Fix B4: Fact Format Inconsistency

**Two incompatible schemas exist:**

| Source | Schema | Has Embedding? |
|--------|--------|----------------|
| REST API (`POST /user/memory/fact`) | `{"fact": "...", "addedAt": N, "fromChatId": "...", "category": "..."}` | **NO** |
| Tool call (`save_memory`) | `{"text": "...", "category": "...", "importance": N, "embedding": [...], "created_at": N}` | **YES** |

**Fix: Normalize at REST API save time (`backend/routes/chat.py`):**

```python
@chat_bp.route("/user/memory/fact", methods=["POST"])
@require_auth
def save_user_memory_fact(principal):
    data = request.get_json()
    fact_text = data.get("fact", "").strip()

    if not fact_text:
        return jsonify({"error": "Missing 'fact' field"}), 400

    # Generate embedding for semantic search compatibility
    try:
        from services.embeddings import embed_text
        embedding = embed_text(fact_text)
        embedding_list = embedding.tolist() if embedding is not None else None
    except Exception:
        embedding_list = None

    # Normalized schema (matches tool-created facts)
    normalized_fact = {
        "text": fact_text,
        "category": data.get("category", "general"),
        "importance": data.get("importance", 3),
        "embedding": embedding_list,
        "created_at": int(time.time()),
    }

    # Load, append, save
    memory = load_user_memory(principal)
    if "facts" not in memory:
        memory["facts"] = []
    memory["facts"].append(normalized_fact)
    save_user_memory(principal, memory)

    return jsonify({"status": "saved", "fact": fact_text})
```

**Migration for existing old-format facts:**

```python
def migrate_legacy_facts(principal_id):
    """One-time migration: convert {"fact": "..."} → {"text": "..."} format."""
    from services.embeddings import embed_text

    memory = load_user_memory(principal_id)
    facts = memory.get("facts", [])
    migrated_count = 0

    for i, fact in enumerate(facts):
        if isinstance(fact, dict) and "fact" in fact and "text" not in fact:
            text = fact["fact"]
            try:
                embedding = embed_text(text)
                embedding_list = embedding.tolist() if embedding is not None else None
            except Exception:
                embedding_list = None

            facts[i] = {
                "text": text,
                "category": fact.get("category", "general"),
                "importance": fact.get("importance", 3),
                "embedding": embedding_list,
                "created_at": fact.get("addedAt", int(time.time())),
            }
            migrated_count += 1
        elif isinstance(fact, str):
            # Plain string fact — normalize
            try:
                embedding = embed_text(fact)
                embedding_list = embedding.tolist() if embedding is not None else None
            except Exception:
                embedding_list = None

            facts[i] = {
                "text": fact,
                "category": "general",
                "importance": 3,
                "embedding": embedding_list,
                "created_at": int(time.time()),
            }
            migrated_count += 1

    if migrated_count > 0:
        memory["facts"] = facts
        save_user_memory(principal_id, memory)
        logger.info(f"Migrated {migrated_count} legacy facts for {principal_id[:8]}...")

    return migrated_count
```

**Call migration lazily** on first user memory access per session (not at startup — embedding model may not be ready).

### 3.5 Fix B5: Increase Context Window 6 → 20

**`trinity-icp/src/state/store.js`:**
```javascript
// Change from:
CONTEXT_WINDOW_SIZE: 6,
// To:
CONTEXT_WINDOW_SIZE: 20,
```

**Impact analysis:**
- 20 messages × ~400 tokens avg = ~8,000 tokens context
- 32K context window budget: 1,000 (system prompt) + 8,000 (context) + 23,000 (response) = 32,000 ✓
- 16K context window budget: 1,000 + 8,000 + 7,000 = 16,000 ✓ (still works, shorter responses)
- **This is the single highest-impact change in the entire overhaul**

### 3.6 Fix B6: Conversation Summary Persistence

**Decision:** Disable summarization entirely.

**Rationale:**
- With 20-message context window, compression is unnecessary for most conversations
- The same model doing compression is lossy and loses critical details
- Removes ~65 lines of code and one LLM call per 15 messages
- If sessions exceed 20 messages, semantic memory (now fixed) provides cross-session context

**`trinity-icp/src/state/contextMemory.js`:**
```javascript
// Disable by setting interval beyond any realistic conversation length
SUMMARY_INTERVAL: 999,
```

**Alternative (if research team disagrees):** Keep summarization but:
1. Increase `SUMMARY_INTERVAL` to 40 (double the context window)
2. Persist summary in autosave payload
3. Restore summary on chat load

### 3.7 Wire Semantic Memory Into All Paths

After Phase 2, there's one streaming endpoint. Ensure it always attempts semantic retrieval:

```python
# In the unified /generate/stream handler:

# 1. Always try semantic retrieval (no feature flag check)
try:
    result = build_enhanced_context(principal, user_prompt, context_messages)
    context_messages = result.full_context
    semantic_context = result.semantic_summary
    if semantic_context:
        logger.info(f"Semantic memory: retrieved relevant past context")
except Exception as e:
    logger.debug(f"Semantic retrieval skipped: {e}")
    semantic_context = None

# 2. Always try user memory (with migration)
try:
    user_memory = load_user_memory(principal)
    migrate_legacy_facts(principal)  # Idempotent — skips if already migrated
except Exception:
    user_memory = None

# 3. Always index messages after exchange completes
# (deferred to after streaming finishes — see B2 fix)
```

### 3.8 Memory Architecture — Before vs After

**Before (4 layers, 8 bugs, inconsistent):**
```
Frontend Layer 1: contextMemory (6 messages) — TOO SMALL
Frontend Layer 2: conversationSummary (lossy, lost on refresh) — BROKEN
Backend Layer 3:  Semantic Memory (broken indexing, broken return type) — DEAD CODE
Backend Layer 4:  User Memory (dual schemas, renders as dicts) — BROKEN
```

**After (3 layers, unified, working):**
```
Frontend: contextMemory (20 messages — sufficient for most sessions)
Backend:  Semantic Memory (working indexing, cross-chat retrieval, always active)
Backend:  User Memory (normalized schema, clean rendering, migration for legacy)
Summarization: DISABLED (20-message window makes it unnecessary)
```

### 3.9 Phase 3 Verification Checklist

```bash
# 1. User memory renders correctly
# Create a fact via REST API:
curl -X POST https://api.dubya.ai/user/memory/fact \
  -H "Content-Type: application/json" \
  -d '{"fact": "Test user prefers Python", "category": "preferences"}'
# Send a chat message, check backend logs for prompt content
# Should see: "- [preferences] Test user prefers Python"
# Should NOT see: "{'text': ..., 'embedding': [0.1, ...]}"

# 2. Vector indexing works
# Send 5+ messages in conversation
# Check that SQLite DB exists:
ls -la /var/lib/trinity/chats/*/vectors.db
# Check that it has rows:
sqlite3 /var/lib/trinity/chats/*/vectors.db "SELECT COUNT(*) FROM message_embeddings"
# Should be > 0

# 3. Context window
# Send 15 messages in a row, message #1 = "The secret word is BANANA"
# Message #15: "What was the secret word I mentioned at the start?"
# Should correctly answer "BANANA" (within 20-message window)

# 4. Semantic retrieval
# In chat A: discuss "Python decorators"
# In chat B: ask "What did we discuss about Python?"
# Semantic memory should retrieve relevant context from chat A

# 5. Fact format migration
# Check logs for "Migrated N legacy facts" on first access
# Verify old-format facts are now searchable via recall_memory tool

# 6. Memory tool round-trip
# Ask: "Remember that my favorite language is Rust"
# Start new chat, ask: "What's my favorite programming language?"
# Should retrieve "Rust" via recall_memory or user memory injection
```

---

## 5. Phase 4: Model Upgrade

**Goal:** Switch from `qwen2.5:14b` to `qwen2.5-coder:32b` for significantly better code intelligence.

**Estimated effort:** 2-4 hours (mostly deployment/testing time)
**Risk:** Medium (GPU memory, cold start time)
**Rollback:** Change `MODEL_NAME` env var back

### 4.1 Benchmark Comparison

| Metric | qwen2.5:14b (current) | qwen2.5-coder:32b (target) | Delta |
|--------|----------------------|----------------------------|-------|
| Aider code editing | ~55% | 72.9% | **+18%** |
| HumanEval pass@1 | ~70% | 92.7% | **+23%** |
| VRAM (Q4_K_M) | ~10GB | ~20GB | Fits 24GB GPU |
| Context window | 32K | 32K | Same |
| Speed (tokens/sec) | ~30 tok/s | ~15 tok/s | ~2x slower |
| Training focus | General | **Code-specialized** | Better for coding |

**Analysis:** 18-23% improvement on coding benchmarks is transformative. The model is ~2x slower but the single-pass pipeline (Phase 2) gives back 3-5x latency, net result is still faster than current multi-pass + 14B.

### 4.2 Configuration Changes

**`backend/config.py`:**
```python
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5-coder:32b")
```

**`backend/config.py` — token limits (smarter model, more concise):**
```python
DEFAULT_MAX_TOKENS = 8000           # Keep (smarter model respects limits better)
DEFAULT_MAX_TOKENS_STREAM = 4000    # Keep
```

**`deploy/docker/Dockerfile`:**
```dockerfile
# Update model pull
RUN ollama pull qwen2.5-coder:32b
```

**`deploy/akash/` SDL:**
- GPU requirement: ≥24GB VRAM
- Recommended GPUs: RTX 3090 (24GB), RTX 4090 (24GB), A5000 (24GB)

### 4.3 Quantization Decision

| Quantization | VRAM | Quality Loss | Speed | Fits 24GB + 32K ctx? |
|-------------|------|-------------|-------|----------------------|
| FP16 | ~64GB | None | Baseline | NO |
| Q8_0 | ~34GB | Negligible | +10% | NO |
| Q6_K | ~26GB | Minimal | +15% | TIGHT |
| **Q4_K_M** | **~20GB** | **Small** | **+25%** | **YES** |
| Q4_0 | ~18GB | Moderate | +30% | YES (margin) |

**Decision:** Q4_K_M. Best balance of quality and VRAM for 24GB GPUs.

**Context window VRAM budget:**
- Model weights (Q4_K_M): ~20GB
- KV cache (32K context, 32B model): ~2-3GB
- Total: ~22-23GB → fits 24GB GPU

**Fallback if VRAM issues:**
```python
NUM_CTX = 16384  # Reduce from 32768 — still supports 20-message context window
```

### 4.4 Tier Detection Update

**`backend/config.py`:**
```python
tier_names = {
    # Legacy models
    "tinyllama:1.1b": 1,
    "llama3.1:8b": 2,
    "qwen2.5:72b": 3,
    "qwen2.5:14b": 2,
    "qwen2.5:32b": 3,
    # Coder models
    "qwen2.5-coder:7b": 2,
    "qwen2.5-coder:14b": 2,
    "qwen2.5-coder:32b": 3,    # ADD THIS
    # Qwen3 models
    "qwen3:1.7b": 1,
    "qwen3:8b": 2,
    "qwen3:32b": 3,
}
```

### 4.5 Phase 4 Verification Checklist

```bash
# 1. Model shows in health check
curl -s https://api.dubya.ai/health | python3 -m json.tool
# Should show: "model": "qwen2.5-coder:32b"

# 2. VRAM usage (if SSH access available)
nvidia-smi
# Should show: ~20-23GB VRAM used

# 3. IQ test suite
cd backend/eval && bash run_iq_tests_v3.sh
# Compare scores — should be significantly higher on coding questions

# 4. Coding quality comparison
# Send: "Write a Python function to find the longest palindromic substring using Manacher's algorithm"
# Compare: old model output vs new model output
# The new model should produce more correct, idiomatic code

# 5. Latency sanity check
time curl -X POST https://api.dubya.ai/generate/stream -d '{"prompt":"Hello, introduce yourself briefly"}'
# Should complete within 30 seconds (32B is slower but single-pass compensates)
```

---

## 6. Phase 5: Agentic Scaffolding

**Goal:** Add filesystem tools, code execution, and structured context for Claude Code-level capabilities.

**Estimated effort:** 2-3 weeks
**Risk:** High (security implications)
**Rollback:** Feature flags per tool

### 5.1 New Tool Definitions

Add to `backend/services/tools.py`:

| Tool | Parameters | Return | Security |
|------|-----------|--------|----------|
| `read_file` | `path: str`, `start_line?: int`, `end_line?: int` | File content (max 500 lines) | Sandboxed to `/workspace` |
| `write_file` | `path: str`, `content: str` | Success/failure message | Sandboxed to `/workspace`, max 5MB |
| `list_directory` | `path: str`, `recursive?: bool` | File tree (max depth 3) | Sandboxed to `/workspace` |
| `search_codebase` | `query: str`, `file_pattern?: str` | Grep results (max 50 matches) | Sandboxed to `/workspace` |
| `run_command` | `command: str` | stdout + stderr + exit code | **Allowlist only**: `python`, `pytest`, `node`, `npm test` |

**Security model:**
```python
WORKSPACE_ROOT = "/workspace"

def validate_path(path: str) -> str:
    """Resolve path and ensure it's within workspace."""
    resolved = os.path.realpath(os.path.join(WORKSPACE_ROOT, path))
    if not resolved.startswith(WORKSPACE_ROOT):
        raise SecurityError(f"Path traversal blocked: {path}")
    return resolved

COMMAND_ALLOWLIST = {
    "python": ["python3", "-c"],
    "pytest": ["python3", "-m", "pytest"],
    "node": ["node", "-e"],
    "npm_test": ["npm", "test"],
}
```

### 5.2 Code Execution with Reflexion Pattern

The Reflexion paper (NeurIPS 2023) shows self-critique works **when grounded in external feedback** (compiler errors, test output). Implement this:

```
Model writes code
     ↓
Execute in sandbox → capture stdout/stderr/exit_code
     ↓
If exit_code != 0:
     Inject error as observation in ReAct loop
     Model analyzes error → fixes code → re-execute
     Max 3 retry attempts
     ↓
If exit_code == 0:
     Return success output
```

This transforms self-critique from "theater" (model evaluating its own prose) to "grounded verification" (model seeing actual error messages).

### 5.3 Increase ReAct Iterations

```python
# config.py
REACT_MAX_ITERATIONS = 15  # Was 5
```

**Add cost guard:**
```python
# react_loop.py
MAX_TOTAL_TOKENS = 24000  # 75% of context window

def execute_streaming(self, messages):
    total_tokens = sum(len(m["content"].split()) for m in messages)

    for iteration in range(REACT_MAX_ITERATIONS):
        if total_tokens > MAX_TOTAL_TOKENS:
            yield {"type": "warning", "content": "Approaching context limit, finalizing..."}
            yield from self._force_final_answer(messages)
            return

        # ... normal ReAct iteration ...
        total_tokens += new_tokens_this_iteration
```

### 5.4 Repo Map — V1 (Regex-Based)

Start simple. 80% of value for 10% of effort.

```python
# backend/services/repo_map.py (~100 lines)

import os
import re

def generate_repo_map(workspace_path: str, max_depth: int = 3) -> str:
    """Generate a compact structural overview using grep for signatures."""
    output = []

    for root, dirs, files in os.walk(workspace_path):
        depth = root.replace(workspace_path, "").count(os.sep)
        if depth >= max_depth:
            dirs.clear()
            continue

        indent = "  " * depth
        folder = os.path.basename(root) or os.path.basename(workspace_path)
        output.append(f"{indent}{folder}/")

        for filename in sorted(files):
            if not filename.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                continue

            filepath = os.path.join(root, filename)
            output.append(f"{indent}  {filename}")

            # Extract function/class signatures
            try:
                with open(filepath, "r") as f:
                    for line in f:
                        line = line.rstrip()
                        if re.match(r"\s*(def |class |function |const \w+ = |export )", line):
                            output.append(f"{indent}    {line.strip()}")
            except Exception:
                pass

    return "\n".join(output[:500])  # Cap at 500 lines
```

**Injection:** When a user uploads a project or references files, generate repo map and include as context:
```python
system_prompt += f"\n\n## Project Structure\n```\n{repo_map}\n```"
```

### 5.5 Episodic Memory (Research Phase — Not Implemented Yet)

**Concept:** Store successful multi-turn tool sequences as reusable few-shot examples.

```json
{
    "task_type": "bug_fix",
    "trigger_pattern": "fix.*bug|debug|error in",
    "successful_sequence": [
        {"step": 1, "tool": "read_file", "reasoning": "Read the file mentioned by user"},
        {"step": 2, "tool": "search_codebase", "reasoning": "Find related usages"},
        {"step": 3, "tool": "write_file", "reasoning": "Apply the fix"},
        {"step": 4, "tool": "run_command", "reasoning": "Run tests to verify"}
    ],
    "success_rate": 0.8,
    "times_used": 5,
    "source_conversations": ["chat_abc123", "chat_def456"]
}
```

**Decision:** Defer to after Phase 5.1-5.4 are validated. Requires:
1. Working filesystem tools (5.1)
2. Working code execution (5.2)
3. Enough usage data to identify successful patterns
4. Research team input on retrieval strategy

### 5.6 Phase 5 Verification Checklist

```bash
# 1. File tools work
# Ask: "What files are in this project?"
# Agent should: call list_directory → return tree

# 2. Code reading works
# Ask: "Show me the main function in src/main.py"
# Agent should: call read_file → display code

# 3. Code editing works
# Ask: "Add a docstring to the main function"
# Agent should: call read_file → analyze → call write_file → show diff

# 4. Code execution works
# Ask: "Run the tests for this project"
# Agent should: call run_command("pytest") → show results

# 5. Reflexion error recovery works
# Ask: "Write a function that sorts a list and test it"
# Agent should: write code → execute → if error → fix → re-execute

# 6. ReAct doesn't infinite loop
# Send complex multi-step query → verify terminates within 15 iterations
# Check that cost guard prevents context window overflow

# 7. Repo map generates correctly
# Upload a Python project → verify structural overview is accurate
# Function signatures should appear, not just filenames

# 8. Security
# Attempt path traversal: "Read /etc/passwd"
# Should be blocked with security error
# Attempt disallowed command: "Run rm -rf /"
# Should be blocked — only allowlisted commands permitted
```

---

## 7. Verification Matrix

| Phase | Test | Method | Expected Result | Blocking? |
|-------|------|--------|-----------------|-----------|
| 1 | No dangling imports | `find + python3 -c "ast.parse()"` | No SyntaxError | YES |
| 1 | No dead references | `grep -r "langgraph\|langchain\|ab_test"` | Zero matches | YES |
| 1 | Docker build | `docker build` | Exit 0 | YES |
| 1 | Health check | `curl /health` | 200 OK | YES |
| 1 | Line reduction | `wc -l` | ~1,500-2,000 fewer | NO |
| 2 | No complexity refs | `grep -r "complexity\|UNDERSTAND_PROMPT"` | Zero matches | YES |
| 2 | Streaming works | Browser test | Tokens stream smoothly | YES |
| 2 | ReAct works | "What is 42 * 17?" | Calculator returns 714 | YES |
| 2 | Latency | `time curl /generate` | 3-5x faster | NO |
| 2 | Prompt size | Token count check | <200 base, <600 with tools | NO |
| 3 | Memory renders | Log inspection | Clean text, no dicts | YES |
| 3 | Vector indexing | SQLite count check | Rows > 0 after 5 messages | YES |
| 3 | Context window | 15-message test | Message #1 referenced at #15 | YES |
| 3 | Semantic retrieval | Cross-chat test | Relevant context retrieved | NO |
| 3 | Fact migration | Log check | Legacy facts migrated | NO |
| 3 | Memory round-trip | Save→new chat→recall | Fact retrieved | YES |
| 4 | New model | `curl /health` | Shows qwen2.5-coder:32b | YES |
| 4 | VRAM | `nvidia-smi` | ~20-23GB used | YES |
| 4 | IQ test | `run_iq_tests_v3.sh` | Score ≥ previous | NO |
| 4 | Code quality | Manual comparison | Visibly better code | NO |
| 5 | File tools | "List files" query | Directory tree returned | YES |
| 5 | Code execution | "Run tests" query | Test output shown | YES |
| 5 | Error recovery | Bug fix task | Fix→re-run succeeds | NO |
| 5 | Security | Path traversal attempt | Blocked | YES |

---

## 8. Risk Register

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Phase 2 breaks streaming | Medium | High | Git revert to Phase 1; test streaming incrementally per function |
| Phase 3 migration corrupts user data | Low | Critical | Backup all user_memory.json before deploy; migration is additive only |
| Phase 4 model doesn't fit GPU | Medium | Medium | Fall back to Q4_0 or reduce NUM_CTX to 16384 |
| Phase 4 model is significantly slower | High | Low | Expected ~2x slower, but single-pass compensates; net latency similar |
| Phase 5 sandbox escape | Low | Critical | Path traversal prevention; command allowlist; Docker isolation layer |
| Phase 5 ReAct infinite loop | Medium | Medium | Hard limit at 15 iterations + token budget guard at 75% context |
| Removing multi-pass reduces quality | Low | Medium | Run IQ test suite before/after; keep old code in git history for comparison |
| Frontend breaks on simplified SSE | Low | Medium | Frontend already handles simple streaming; just remove dead branches |
| Cold start latency increases with 32B | Medium | Low | Expected: 30-60 seconds for first request; mention in docs |
| `detect_tools_needed()` false negatives | Medium | Low | User can still explicitly trigger tools; heuristic is a hint not a gate |

---

## 9. Decisions Log

| # | Decision | Rationale | Alternative Considered | Why Rejected |
|---|----------|-----------|----------------------|--------------|
| D1 | Single-pass over multi-pass | Stechly et al. (arXiv:2310.12397): "LLMs are no better at verifying than generating." 3-5x latency improvement. | Keep multi-pass with better prompts | Same model can't meaningfully critique itself without external signal |
| D2 | Context window 20 over 6 | 6 messages = 3 exchanges. Coding sessions need 10+ exchanges. 20 fits easily in 32K context. | 10 messages (compromise) | No reason to compromise — 20 × 400 tokens = 8K, leaves 24K for response |
| D3 | Disable summarization | With 20-message window, lossy compression adds code complexity for marginal benefit. | Keep with increased interval (30) | Same model compressing = lossy; adds dynamic import coupling; lost on refresh |
| D4 | qwen2.5-coder:32b | +18% Aider, +23% HumanEval, code-specialized training. Fits same GPU (Q4_K_M). | qwen2.5:32b (general) | Coder variant specifically trained for Trinity's primary use case |
| D5 | Delete LangGraph entirely | Complete parallel pipeline, 100MB+ deps, never enabled in production, no proven benefit. | Keep as optional feature flag | Dead code is a liability; 7 extra files, 3 extra packages, maintenance burden |
| D6 | Delete voting entirely | Never called from any active code path. Self-consistency voting needs multiple identical models. | Keep for future multi-model | Premature; design it when multi-model is actually deployed |
| D7 | Keep ReAct, kill Understand/Plan/Critique/Refine | ReAct (iterative tool loop) validated by SWE-Agent, Aider, Claude Code, OpenHands. Multi-pass is unvalidated. | Keep Critique only (lightweight check) | Critique without ground truth (tests/linter) is "mostly theater" per research |
| D8 | XML tools over native Ollama tools | Native produces empty content with Qwen3. XML is portable across models. | Fix native tools for Qwen2.5-Coder | Model-specific; XML is debuggable and works everywhere |
| D9 | Dynamic tool injection | Saves ~600 tokens/request (70%+ of queries don't need tools). Models perform better without irrelevant instructions. | Always include tools | Unnecessary overhead; cleaner prompts = better responses |
| D10 | V1 repo map (regex) over V2 (tree-sitter) | 80% value for 10% effort. Regex catches `def`/`class`/`function` signatures adequately. | Start with tree-sitter | Over-engineering; prove concept first, upgrade incrementally |
| D11 | Reflexion (external feedback) over pure self-critique | Reflexion paper: 91% pass@1 with test feedback vs 80% without. Grounded in real errors, not self-evaluation. | Pure self-critique (current approach) | Research clear: external verification is what makes self-improvement work |

---

## Appendix A: Files Modified/Deleted Per Phase

### Phase 1 — Deletions (~2,000 lines removed)

| Action | Path |
|--------|------|
| DELETE DIR | `backend/services/graph/` (7 files) |
| DELETE FILE | `backend/services/parallel.py` |
| DELETE FILE | `backend/services/experiments.py` |
| DELETE FILE | `backend/services/voting.py` |
| DELETE FILE | `backend/middleware/ab_test.py` |
| EDIT | `backend/routes/generate.py` — remove langgraph + simple/stream endpoints |
| EDIT | `backend/routes/admin.py` — remove experiment endpoints |
| EDIT | `backend/requirements.txt` — remove langgraph/langchain deps |
| EDIT | `backend/services/agent.py` — remove multi-model, non-streaming process() |
| EDIT | `backend/services/react_loop.py` — remove native tool code |
| EDIT | `backend/services/tools.py` — remove native tool functions |
| EDIT | `backend/config.py` — remove dead config sections |
| EDIT | `backend/inference_server.py` — remove LangGraph/voting detection |

### Phase 2 — Simplifications (~1,000 lines removed)

| Action | Path |
|--------|------|
| DELETE FILE | `backend/services/complexity.py` |
| EDIT | `backend/services/agent.py` — replace multi-pass with single-pass |
| EDIT | `backend/services/agent_prompts.py` — keep 2 prompts, delete 6 + parsers |
| EDIT | `backend/routes/generate.py` — merge agent into stream endpoint |
| EDIT | `trinity-icp/src/features/generate.js` — remove critique/refine handling |

### Phase 3 — Fixes (~150 lines net added)

| Action | Path |
|--------|------|
| EDIT | `backend/services/agent.py` — fix `_format_user_memory()` |
| EDIT | `backend/services/agent_prompts.py` — fix user memory injection |
| EDIT | `backend/routes/generate.py` — fix vector indexing, semantic retrieval |
| EDIT | `backend/services/memory.py` — fix return type (NamedTuple) |
| EDIT | `backend/routes/chat.py` — normalize fact schema + embed at save |
| EDIT | `backend/services/memory_tools.py` — add migration function |
| EDIT | `trinity-icp/src/state/store.js` — CONTEXT_WINDOW_SIZE = 20 |
| EDIT | `trinity-icp/src/state/contextMemory.js` — disable summarization |
| EDIT | `trinity-icp/src/features/generate.js` — send chat_id + message_index |

### Phase 4 — Model (config changes only)

| Action | Path |
|--------|------|
| EDIT | `backend/config.py` — MODEL_NAME, tier detection |
| EDIT | `deploy/docker/Dockerfile` — model pull command |
| EDIT | `deploy/akash/*.yml` — GPU requirements |

### Phase 5 — New Features (~500 lines added)

| Action | Path |
|--------|------|
| NEW FILE | `backend/services/repo_map.py` (~100 lines) |
| EDIT | `backend/services/tools.py` — add 5 filesystem/execution tools |
| EDIT | `backend/services/code_executor.py` — sandboxed execution |
| EDIT | `backend/config.py` — REACT_MAX_ITERATIONS = 15 |
| EDIT | `backend/services/react_loop.py` — token budget guard |

## Appendix B: Estimated Line Count Impact

| Phase | Lines Removed | Lines Added | Net Change |
|-------|--------------|-------------|------------|
| Phase 1 | ~2,000 | ~0 | **-2,000** |
| Phase 2 | ~1,000 | ~100 | **-900** |
| Phase 3 | ~50 | ~200 | **+150** |
| Phase 4 | ~10 | ~10 | **0** |
| Phase 5 | ~0 | ~500 | **+500** |
| **Total** | **~3,060** | **~810** | **-2,250** |

The codebase gets **2,250 lines smaller** while becoming significantly more capable.

## Appendix C: Research References

| Paper/Tool | Key Finding | Phase Applied |
|------------|-------------|---------------|
| Stechly et al. (arXiv:2310.12397) | LLMs no better at verifying than generating | Phase 2 — remove self-critique |
| Reflexion (arXiv:2303.11366, NeurIPS 2023) | Self-reflection works WITH external feedback (tests, errors) | Phase 5 — code execution with error feedback |
| Self-Contrast (arXiv:2401.02009, ACL 2024) | Multi-perspective > single self-evaluation | Future — multi-model evaluation |
| CoALA (arXiv:2309.02427) | Cognitive architecture taxonomy for language agents | Phase 3 — memory layer design |
| SWE-Agent (NeurIPS 2024) | Simple 100-line agent matches complex pipelines | Phase 2 — simplification rationale |
| Aider leaderboards | qwen2.5-coder:32b = 72.9% (matches GPT-4o) | Phase 4 — model selection |
| LangGraph Deep Agents | Filesystem-backed context for long sessions | Phase 5 — repo map |
| Aider repo map | Tree-sitter AST map with PageRank relevance | Phase 5 — structured context |

---

*This document was generated February 12, 2026. Commit to `docs/OVERHAUL-REFERENCE.md` and reference from all sessions working on the overhaul.*
