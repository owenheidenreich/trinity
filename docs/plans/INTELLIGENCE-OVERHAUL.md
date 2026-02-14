# Trinity Intelligence Overhaul — Definitive Engineering Plan

**Date:** February 12, 2026
**Status:** Pre-implementation — approved for Phase 0 execution
**Sources:** Team A Research Analysis, Team B Engineering Specification, Deep Frontend Audit (3 agents)
**Purpose:** Single source of truth for the complete overhaul. Supersedes all prior planning documents.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Team Synthesis](#2-team-synthesis)
3. [Bug Registry](#3-bug-registry)
4. [Phase 0: Frontend Stabilization](#4-phase-0-frontend-stabilization)
5. [Phase 1: Backend Dead Code Removal](#5-phase-1-backend-dead-code-removal)
6. [Phase 2: Pipeline Simplification](#6-phase-2-pipeline-simplification)
7. [Phase 3: Memory System Overhaul](#7-phase-3-memory-system-overhaul)
8. [Phase 4: Model Upgrade](#8-phase-4-model-upgrade)
9. [Phase 5: Agentic Scaffolding](#9-phase-5-agentic-scaffolding)
10. [Decisions Log](#10-decisions-log)
11. [Verification Matrix](#11-verification-matrix)
12. [Risk Register](#12-risk-register)
13. [Research References](#13-research-references)
14. [Appendices](#14-appendices)

---

## 1. Executive Summary

Trinity's intelligence is bottlenecked by **four** architectural problems, ordered by severity:

### Problem 1: The multi-pass pipeline is actively degrading quality

A 14B model critiquing its own output is self-reinforcement, not quality assurance. Every successful coding tool in production (Aider, SWE-Agent, OpenHands, Claude Code, Cursor) uses single-pass + external feedback. The 5-7 sequential LLM calls add 15-30s latency and ~1,400 tokens of template overhead per complex query — with no measurable quality improvement. Academic research (Stechly et al., arXiv:2310.12397) confirms: "LLMs are no better at verifying than generating."

### Problem 2: The 6-message context window is catastrophically small

After 3 back-and-forth exchanges, the model has zero memory of what was discussed. This is the single biggest user-visible intelligence problem. Claude Code maintains full conversation history (200K tokens). Aider uses repository maps. Trinity loses everything after 3 exchanges.

### Problem 3: The model is wrong

Generic `qwen3:8b` is a general-purpose chat model. Coding-specialized `qwen2.5-coder:32b` scores 72.9% on Aider benchmarks (matches GPT-4o) vs ~45% estimated for Qwen3:8b. This is free intelligence — just swap the model.

### Problem 4: The frontend is structurally broken (NEW)

Neither team adequately scoped the frontend. A deep 3-agent audit revealed:
- **4 separate message sending paths** (only 1 actually used)
- **5+ rendering pipelines** scattered across 3 files with duplicated logic
- **253 console.log statements** in production (leaking principals, signatures, API URLs)
- **Zero tests, zero linting, zero type checking**
- **Broken summarization** that never persists and rarely triggers
- **Inconsistent context window** (6 in some paths, 12 in others)

Every time backend intelligence improves, the frontend breaks because there is no single rendering pipeline, no shared preprocessing, and no test coverage. **Phase 0 must stabilize the frontend before any backend changes.**

### The Fix Is Subtraction

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Backend Python lines | ~8,000 | ~4,500 | -44% |
| Frontend JS lines (active) | ~5,000 | ~3,000 | -40% |
| Message sending paths | 4 | 1 | -75% |
| Rendering pipelines | 5+ | 2 | -60% |
| Pipeline LLM calls (complex) | 5-7 | 1 | -80% |
| Latency (complex query) | 20-40s | 3-10s | -75% |
| Context messages | 6 | 20 | +233% |
| Coding benchmark score | ~45% | ~73% | +62% |
| Python dependencies | 26 | 23 | -100MB Docker |

---

## 2. Team Synthesis

### 2.1 Where Both Teams Agree (Core of the Plan)

These items are settled — no further debate needed:

| Decision | Team A | Team B | Confidence |
|----------|--------|--------|------------|
| Delete multi-pass pipeline → single-pass ReAct | Yes | Yes | Very High |
| Delete complexity classifier (401 lines) | Yes | Yes | Very High |
| Delete LangGraph pipeline (~800 lines, 100MB deps) | Yes | Yes | Very High |
| Delete voting module (~270 lines) | Yes | Yes | Very High |
| Delete experiments + A/B testing modules | Yes | Yes | Very High |
| Context window 6 → 20 messages | Yes | Yes | Very High |
| qwen2.5-coder:32b at Q4_K_M on 24GB GPU | Yes | Yes | High |
| Keep XML tool calling (for now) | Yes | Yes | High |
| Dynamic tool injection (save ~275-600 tokens) | Yes | Yes | High |
| Keep ReAct loop, kill understand/plan/critique/refine | Yes | Yes | Very High |
| Fix all memory bugs before adding features | Yes | Yes | High |
| Phase order: strip → simplify → fix memory → model → agentic | Yes | Yes | High |

### 2.2 Disagreements and Resolutions

| Issue | Team A | Team B | Deep Audit | Resolution |
|-------|--------|--------|------------|------------|
| **Phase count** | 6 (benchmarks separate) | 5 (verification per-phase) | Frontend needs dedicated phase | **6 phases: 0-5**. Add Phase 0 (frontend). Fold benchmarks into phases. |
| **/generate/simple** | Delete endpoint | Keep (frontend uses it) | `generateSimple()` is dead code — 0 callers | **Delete both** endpoint AND frontend function. Neither team checked actual call sites. |
| **Summarization** | Persist in autosave | Disable entirely | Never persists, rarely triggers, broken when it does | **Delete entirely**. Code is dead weight. With 20-message window, unnecessary. |
| **Repo map** | tree-sitter (full AST) | regex V1 (80/10 rule) | N/A | **Team B** — regex first, prove concept, upgrade later. |
| **MCP client config** | Not addressed | Delete config vars | N/A | **Team B** — dead config, clean it. |
| **Qwen3 thinking config** | Not addressed | Delete config vars | N/A | **Team B** — switching to qwen2.5-coder, not Qwen3. |
| **Frontend scope** | "Update a few values" (store.js, contextMemory.js) | "Send chat_id, increase window" (3 file edits) | 4 msg paths, 5 render pipelines, 253 console.log, 0 tests, structural rot | **Much larger than either team scoped**. Dedicated Phase 0 required. |

### 2.3 Where Team A Was Stronger

- Academic research grounding (ReAct, Reflexion, ToT, MemGPT, CoALA citations)
- SOTA comparison matrix (5 tools analyzed side-by-side)
- Strategic reasoning about WHY each decision is correct
- Quantization impact analysis with VRAM budgets
- Model benchmark data (HumanEval+, Aider, MBPP+)

### 2.4 Where Team B Was Stronger

- Implementation specificity (exact line numbers, file paths, code to delete)
- Phase verification checklists (runnable bash commands)
- Bug enumeration (8 vs 5, more thorough)
- Dependency and import graph analysis
- Decisions log with alternatives and rejection rationale
- Pseudocode for every fix
- Endpoint consolidation strategy
- Frontend file-level change specifications

### 2.5 What Neither Team Caught (Frontend Audit)

| Finding | Severity | Impact |
|---------|----------|--------|
| `CONTEXT_WINDOW_SIZE` used as 6 AND 12 (`*2`) depending on code path | CRITICAL | Backend receives unpredictable context size |
| `generateSimple()` is dead code (0 callers) | MEDIUM | Team B wrong to keep `/generate/simple` |
| 4 separate message sending paths | HIGH | Backend changes break 50% of the time |
| 5+ rendering pipelines across 3 files | HIGH | Tool format changes cause silent failures |
| 253 console.log statements leaking auth data | HIGH | Security + performance issue |
| Zero test framework (no jest/vitest/eslint) | HIGH | No regression protection |
| Summarization never persists (not in autosave, not in IndexedDB) | CRITICAL | Feature is complete fiction |
| `{"clear": true}` SSE event not handled in UI | MEDIUM | Refinement signal reaches API layer but never clears display |
| `preprocessToolCalls()` in 3 places (messages.js, editMessage.js, imported by generate.js) | HIGH | Tool format changes must update 3 locations |
| Zustand reactivity bypassed via `window.State = State` + direct mutations | MEDIUM | State changes don't trigger re-renders |
| `modals.js` is 642 lines of string-based DOM generation | LOW | Unmaintainable, XSS risk |
| Circular import: contextMemory.js → dynamic import app.js → API | MEDIUM | Fragile initialization order |

---

## 3. Bug Registry

### 3.1 Backend Bugs (B1-B8, from Team B)

| ID | Location | Description | Impact | Fix Phase |
|----|----------|-------------|--------|-----------|
| **B1** | `agent.py L107-115` | `_format_user_memory()` does `f"- {fact}"` on dict objects → renders as `"- {'text': '...', 'embedding': [0.1, ...]}"` | 384-float arrays pollute prompt | Phase 3 |
| **B2** | `generate.py L493` | `add_message_embedding()` called without `chat_id` and `message_index` | SQLite INSERT fails — semantic memory never indexed | Phase 3 |
| **B3** | `generate.py L466` | `build_enhanced_context()` returns `str` but caller destructures as `(enhanced_context, semantic_context)` tuple | TypeError crash → V4 semantic memory is dead | Phase 3 |
| **B4** | `memory_tools.py` vs `chat.py` | Two incompatible fact schemas: API creates `{"fact": "..."}`, tools create `{"text": "...", "embedding": [...]}` | `recall_memory` can't find API-created facts; prompt formatting crashes on tool-created facts | Phase 3 |
| **B5** | `store.js L27` | `CONTEXT_WINDOW_SIZE = 6` — only 6 messages in sliding window | Model forgets everything beyond 3 exchanges | Phase 3 |
| **B6** | `contextMemory.js` | `conversationSummary` stored only in Zustand (client RAM) | Summary disappears on page refresh — feature is fiction | Phase 0 (delete) |
| **B7** | `react_loop.py` | Native tool calling code paths exist but `REACT_NATIVE_TOOLS = "never"` permanently | Dead code branches add complexity | Phase 1 |
| **B8** | `agent_prompts.py L470` | Same dict-as-string rendering as B1, different code path (`build_execute_prompt`) | Duplicate of B1 — both must be fixed | Phase 3 |

### 3.2 Frontend Bugs (F1-F10, from Deep Audit)

| ID | Location | Description | Impact | Fix Phase |
|----|----------|-------------|--------|-----------|
| **F1** | `store.js` + `api.js` | `CONTEXT_WINDOW_SIZE` used as 6 in `addMessage()` but `CONTEXT_WINDOW_SIZE * 2` (12) in `generateStream()` / `generateAgent()` | Backend receives inconsistent context (6 or 12 messages depending on path) | Phase 0 |
| **F2** | `api.js L352` | `chat_id` never sent in `/generate/agent` requests | Backend cannot correlate requests to conversations | Phase 0 |
| **F3** | Entire frontend | `message_index` never sent in any request | Backend cannot track message position | Phase 0 |
| **F4** | `editMessage.js` + `messages.js` + `generate.js` | `preprocessToolCalls()` duplicated in 3 places (2 definitions, 1 import) | Tool format changes must update multiple files; divergence causes rendering bugs | Phase 0 |
| **F5** | `api.js L426-429` | `{"clear": true}` SSE event sets `fullText = ''` in API scope but never clears UI's `tokenBuffer` | Refinement clears in backend but UI keeps rendering old tokens | Phase 0 |
| **F6** | `generate.js L169-176` | Module-scoped DOM refs (`streamDetailsEl`, `streamCodeEl`) shared across all calls | If messages overlap, refs cross-contaminate; memory leak on interrupted streams | Phase 0 |
| **F7** | `generate.js L449-456` | Direct array mutation (`lastMsg.content = combined`) bypasses Zustand reactivity | State changes not detected by subscribers; UI may not update | Phase 0 |
| **F8** | Entire frontend | 253 `console.log/warn/error` statements in production | Logs principals, signatures, API URLs; performance bloat | Phase 0 |
| **F9** | `generate.js L301-302` | `parseMarkdownWithMath()` called every 15ms tick on `tailDiv` | 300+ full markdown+math+sanitize parses per response | Phase 0 |
| **F10** | `api.js`, `generate.js`, `contextMemory.js` | 4 message paths (simple/HTTP/canister/agent), only agent is used | Dead code confuses developers; changes to wrong path cause silent breaks | Phase 0 |

---

## 4. Phase 0: Frontend Stabilization

**Goal:** Make the frontend resilient to backend changes. Stop the cycle of "intelligence upgrade → frontend breaks."

**Estimated effort:** 3-5 hours
**Risk:** Low-Medium (mostly deletion and consolidation)
**Rollback:** `git revert` to pre-Phase-0 commit
**Rollback Hash**
- 3ac050a0fa484c96224bdb2b268f3b02a2f97db8	
- 2026-02-12 23:17:10	
- docs: complete engineering spec for Trinity agentic overhaul

### 0.1 Deduplicate preprocessToolCalls()

**Current state:** Defined in `editMessage.js:14-51` (exported) AND `messages.js:14-51` (local, never exported). `generate.js:16` imports from `editMessage.js`. `messages.js` uses its own local copy internally.

**Fix:**
1. Keep the definition in `editMessage.js` (already exported)
2. In `messages.js`, delete the local `preprocessToolCalls()` function (lines 14-51)
3. Add import at top of `messages.js`: `import { preprocessToolCalls } from './editMessage.js';`
4. Verify `parseMarkdownWithMath()` in `messages.js` calls the imported version

**Verification:** `grep -rn "function preprocessToolCalls" trinity-icp/src/` → exactly 1 match.

### 0.2 Remove Dead Message Paths

**Delete from `api.js`:**
- `generateSimple()` (lines 127-149) — 0 callers in entire frontend
- ICP canister conditional in `generate()` (lines 177-192) — `USE_CANISTER: false` hardcoded

**Delete from `contextMemory.js`:**
- Entire file (75 lines) — summarization never persists, rarely triggers, broken when it does
- Remove all references to `ContextMemory.compressContext()` from `generate.js`
- Remove `conversationSummary`, `lastSummaryAt`, `SUMMARY_INTERVAL` from `store.js`

**Delete from `chatManagement.js`:**
- `recoverArchivedChats()` — stub that logs "feature removed in v3.7.0"

**Delete backend endpoint:**
- `/generate/simple/stream` from `routes/generate.py` — frontend never calls it

**Verification:** `grep -rn "generateSimple\|compressContext\|USE_CANISTER\|recoverArchived\|SUMMARY_INTERVAL" trinity-icp/src/` → 0 matches.

### 0.3 Fix Context Window Inconsistency (F1)

**Current:** `addMessage()` truncates to `CONTEXT_WINDOW_SIZE` (6), but `generateStream()` and `generateAgent()` use `CONTEXT_WINDOW_SIZE * 2` (12).

**Fix:** Remove the `* 2` multiplier. The context window size should mean what it says.

**In `api.js` (generateStream and generateAgent):**
```javascript
// Change from:
const contextMessages = State.contextMemory.slice(-State.CONTEXT_WINDOW_SIZE * 2);
// To:
const contextMessages = State.contextMemory.slice(-State.CONTEXT_WINDOW_SIZE);
```

**Note:** This will temporarily reduce context from 12 to 6 messages. Phase 3 increases it to 20, which is the actual fix.

### 0.4 Add chat_id and message_index to Requests (F2, F3)

**In `api.js` — generateAgent() request body:**
```javascript
const body = {
    prompt: prompt.trim(),
    temperature,
    principal: State.principal,
    context_messages: contextMessages,
    user_memory: State.userMemory || {},
    chat_id: State.currentChatId,                    // ADD
    message_index: State.chatHistory.length,          // ADD
};
```

### 0.5 Fix `{"clear": true}` Handling (F5)

**In `api.js` — generateAgent() SSE handler:**
```javascript
if (data.clear) {
    console.log('🔄 Clearing for refinement');
    fullText = '';
    if (onClear) onClear();  // ADD: notify UI
}
```

**Add `onClear` callback parameter** to `generateAgent()` signature. In `generate.js`, pass callback that resets `tokenBuffer`, `displayedLength`, and `messageDiv.innerHTML`.

### 0.6 Fix Module-Scoped State (F6, F7)

**Move DOM refs inside the generate function closure:**
```javascript
// BEFORE (module scope — leaks across messages):
let streamDetailsEl = null;
let streamCodeEl = null;

// AFTER (function scope — isolated per message):
export async function generate(prompt, ...) {
    let streamDetailsEl = null;
    let streamCodeEl = null;
    // ... rest of function
}
```

**Fix Zustand mutations (F7):**
```javascript
// BEFORE (direct mutation):
const history = State.chatHistory;
const lastMsg = history[history.length - 1];
lastMsg.content = combined;  // MUTATES IN PLACE
State.setChatHistory([...history]);

// AFTER (immutable):
const history = [...State.chatHistory];
const lastMsg = { ...history[history.length - 1], content: combined };
history[history.length - 1] = lastMsg;
State.setChatHistory(history);
```

### 0.7 Remove Console Statements (F8)

Replace all 253 `console.log/warn/error` with a conditional logger:

**Create `trinity-icp/src/core/logger.js` (~20 lines):**
```javascript
const DEBUG = localStorage.getItem('trinity_debug') === 'true';

export const Logger = {
    debug: (...args) => DEBUG && console.log(...args),
    info: (...args) => DEBUG && console.info(...args),
    warn: (...args) => console.warn(...args),  // Keep warnings
    error: (...args) => console.error(...args), // Keep errors
};
```

Then find/replace across all files. Keep `console.error` for actual errors; replace all `console.log` and `console.warn` with `Logger.debug` / `Logger.warn`.

**Critical:** Remove any statements that log `State.principal`, signatures, API keys, or auth headers.

### 0.8 Unify SSE Handling

**Current:** 3 separate SSE implementations with duplicated `TextDecoder` / `reader.read()` / line-splitting logic in `generateStream()`, `generateAgent()`, and continuation code.

**Fix:** Extract shared SSE reader:

**Create `trinity-icp/src/core/sse.js` (~60 lines):**
```javascript
export async function* streamSSE(response, signal) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        yield JSON.parse(line.slice(6));
                    } catch {}
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}
```

Refactor `generateStream()` and `generateAgent()` to use `for await (const data of streamSSE(response))`.

### 0.9 Phase 0 Verification Checklist

```bash
# 1. Single preprocessToolCalls definition
grep -rn "function preprocessToolCalls" trinity-icp/src/
# Expected: 1 match (editMessage.js only)

# 2. No dead code references
grep -rn "generateSimple\|USE_CANISTER\|compressContext\|SUMMARY_INTERVAL\|recoverArchived" trinity-icp/src/
# Expected: 0 matches

# 3. No console.log in production (except Logger)
grep -rn "console\.log" trinity-icp/src/ | grep -v "logger.js" | grep -v "node_modules"
# Expected: 0 matches

# 4. chat_id sent in requests
grep -rn "chat_id" trinity-icp/src/core/api.js
# Expected: >= 1 match in generateAgent body

# 5. Context window consistent
grep -rn "CONTEXT_WINDOW_SIZE \* 2" trinity-icp/src/
# Expected: 0 matches

# 6. Build succeeds
cd trinity-icp && npm run build
# Expected: exit 0, no errors

# 7. Manual smoke test
# Open app → send message → verify tokens stream → verify tool call renders → verify code block renders
```

---

## 5. Phase 1: Backend Dead Code Removal

**Goal:** Remove ~2,000 lines of unused code and ~100MB of Python packages.

**Estimated effort:** 2-4 hours
**Risk:** Low
**Rollback:** `git revert`

### 1.1 Delete Entire Modules

```bash
rm -rf backend/services/graph/          # 7 files (~800 lines) — LangGraph pipeline
rm -f backend/services/parallel.py       # ~200 lines — parallel execution
rm -f backend/services/experiments.py    # ~150 lines — A/B test definitions
rm -f backend/middleware/ab_test.py      # ~100 lines — A/B middleware
rm -f backend/services/voting.py         # ~270 lines — self-consistency voting
```

### 1.2 Clean Import References

**`backend/routes/generate.py`:**
- Delete `/generate/langgraph` route (~225 lines)
- Delete `/generate/simple/stream` route (~50 lines)
- Remove lazy imports of `services.graph`, `services.parallel`, `middleware.ab_test`, `services.experiments`

**`backend/inference_server.py`:**
- Delete LangGraph detection block (~8 lines)
- Delete voting detection block (~5 lines)
- Delete `app.config["LANGGRAPH_AVAILABLE"]` and `app.config["V4_FEATURES"]["voting"]`

**`backend/routes/admin.py`:**
- Delete 4 experiment endpoints (~60 lines)

### 1.3 Delete Native Tool Calling Dead Code (B7)

**`backend/services/tools.py` — delete:**
- `model_supports_native_tools()` (~4 lines)
- `get_native_tool_definitions()` (~38 lines)
- `extract_native_tool_calls()` (~35 lines)
- `get_all_tool_definitions()` (~15 lines) — MCP client disabled

**`backend/services/react_loop.py` — delete:**
- `_should_use_native()` (~8 lines)
- `_is_qwen3()` (~4 lines)
- All `if self.use_native_tools:` branches

### 1.4 Delete Dead agent.py Methods

- `init_multi_model_config()` (~18 lines)
- `OllamaClient._get_model_for_pass()` (~23 lines)
- `AgentPipeline.process()` non-streaming (~110 lines)
- Any `enable_voting` parameter handling

### 1.5 Clean config.py

**Delete sections:**
- Multi-model: `FAST_MODEL`, `SMART_MODEL`, `REASONING_MODEL`, `MULTI_MODEL_ENABLED`
- Native tools: `REACT_NATIVE_TOOLS`
- Qwen3 thinking: `QWEN3_THINKING_MODE`, `QWEN3_THINKING_BUDGET`
- MCP client: `MCP_CLIENT_ENABLED`, `MCP_SERVERS_CONFIG`
- Voting: `VOTING_CANDIDATES`, `VOTING_TEMPERATURES`, `VOTING_MIN_COMPLEXITY`

**Keep:** `REACT_ENABLED`, `REACT_MAX_ITERATIONS`, `MCP_SERVER_ENABLED`, `MEMORY_TOOLS_ENABLED`, `CODE_EXECUTION_ENABLED`

### 1.6 Clean requirements.txt

Delete:
```
langgraph==0.2.62
langchain-core==0.3.29
langchain-community==0.3.14
```

**Net savings:** ~100MB from Docker image.

### 1.7 Phase 1 Verification

```bash
# 1. No dangling imports
find backend -name "*.py" -not -path "*__pycache__*" -exec python3 -c "import ast; ast.parse(open('{}').read())" \;

# 2. No references to deleted modules
grep -rn "from services.graph\|from services.parallel\|from services.experiments\|from middleware.ab_test\|from services.voting" backend/ --include="*.py"
# Expected: 0 matches

# 3. No dead config references
grep -rn "MULTI_MODEL\|FAST_MODEL\|SMART_MODEL\|REASONING_MODEL\|REACT_NATIVE_TOOLS\|QWEN3_THINKING\|VOTING_CANDIDATES\|MCP_CLIENT_ENABLED" backend/ --include="*.py" | grep -v config.py
# Expected: 0 matches

# 4. No langchain imports
grep -rn "langgraph\|langchain" backend/ --include="*.py"
# Expected: 0 matches

# 5. Docker build
cd deploy/docker && docker build --platform linux/amd64 -t trinity-test -f Dockerfile ../../backend

# 6. Deleted files don't exist
test ! -d backend/services/graph && echo "PASS"
test ! -f backend/services/parallel.py && echo "PASS"
test ! -f backend/services/voting.py && echo "PASS"

# 7. Line count
find backend -name "*.py" -not -path "*__pycache__*" | xargs wc -l | tail -1
# Record: _____ (expect ~1,500-2,000 fewer)
```

---

## 6. Phase 2: Pipeline Simplification

**Goal:** Replace 5-pass understand→plan→execute→critique→refine with single-pass + ReAct.

**Estimated effort:** 4-6 hours
**Risk:** Medium
**Rollback:** `git revert` to Phase 1

### 2.1 Delete Complexity Classifier

```bash
rm -f backend/services/complexity.py    # 401 lines
```

Remove all imports of `ComplexityLevel`, `analyze_question`, `get_pass_count`, `classify_complexity`.

### 2.2 Replace Multi-Pass in agent.py

**Delete methods:**
- `_pass_understand()`, `_pass_plan()`, `_pass_execute()`, `_pass_execute_simple()`
- `_pass_critique()`, `_pass_refine()`
- Multi-pass orchestration in `process_streaming()` (~270 lines of if/elif)

**New `process_streaming()` (~50 lines):**
```python
def process_streaming(self, question, context_messages, user_memory,
                      semantic_context=None, principal_id=None):
    """Single-pass: build prompt → detect tools → stream or ReAct."""
    user_memory_text = format_user_memory(user_memory)
    tools_needed = detect_tools_needed(question)

    if tools_needed:
        system_prompt = build_system_prompt_with_tools(
            user_memory=user_memory_text, semantic_context=semantic_context)
    else:
        system_prompt = build_system_prompt(
            user_memory=user_memory_text, semantic_context=semantic_context)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in context_messages:
        messages.append({"role": msg["role"], "content": msg["content"][:2000]})
    messages.append({"role": "user", "content": question})

    if tools_needed:
        react = self._get_react_loop(principal_id)
        yield from react.execute_streaming(messages)
    else:
        yield from self.client.chat_stream(messages, max_tokens=MAX_TOKENS)
```

**Target `agent.py` size:** ~300-400 lines (from ~1,150)

### 2.3 Simplify Prompts

**Delete from `agent_prompts.py`:**
- `UNDERSTAND_PROMPT`, `PLAN_PROMPT`, `EXECUTE_PROMPT_WITH_PLAN`, `CRITIQUE_PROMPT`, `REFINE_PROMPT`
- `UnderstandingResult`, `PlanResult`, `CritiqueResult` dataclasses
- `parse_understanding()`, `parse_plan()`, `parse_critique()`
- `build_understand_prompt()`, `build_plan_prompt()`, `build_critique_prompt()`, `build_refine_prompt()`

**Keep and refactor:**
- `EXECUTE_PROMPT_SIMPLE` → rename to `SYSTEM_PROMPT` (primary)
- `REACT_SYSTEM_PROMPT` → keep
- `TOOL_PROMPT_SECTION` → keep (injected conditionally)
- `parse_xml_tag()` → keep

**New prompt structure (2 prompts only):**
```python
SYSTEM_PROMPT = """You are Trinity, a helpful AI assistant.

{user_memory_section}

{semantic_context_section}

Respond directly and concisely. Use markdown for formatting.
Use LaTeX ($$...$$ or $...$) for math equations."""
# ~100-200 tokens (vs current 3,000-5,000)

SYSTEM_PROMPT_WITH_TOOLS = SYSTEM_PROMPT + """

## Available Tools
{tool_definitions}

## Tool Protocol
To use a tool, output exactly:
<tool_call name="tool_name">
<param_name>value</param_name>
</tool_call>

Wait for the result before continuing."""
# ~400-600 tokens with tools
```

**Critical:** No more anti-XML instructions ("NEVER use `<tool_call>`"). These paradoxically teach the model about XML syntax.

### 2.4 Merge /generate/agent into /generate/stream

After simplification, the agent pipeline is lightweight enough to be the default. One streaming endpoint handles everything.

### 2.5 Remove Multi-Pass Frontend Handling

**In `generate.js`:**
- Remove `{"clear": true}` handling (already broken, now unnecessary)
- Remove phase indicator display for understand/plan/critique/refine
- Remove any `pass:` handling in SSE events

### 2.6 Phase 2 Verification

```bash
# 1. No complexity references
grep -rn "complexity\|ComplexityLevel\|classify_complexity" backend/ --include="*.py"
# Expected: 0 matches

# 2. No multi-pass references
grep -rn "UNDERSTAND_PROMPT\|PLAN_PROMPT\|CRITIQUE_PROMPT\|REFINE_PROMPT\|_pass_understand\|_pass_plan\|_pass_critique\|_pass_refine" backend/ --include="*.py"
# Expected: 0 matches

# 3. Streaming works
# Browser test: send message → tokens stream smoothly → no phase gaps

# 4. ReAct works
# Send "What is 42 * 17?" → calculator returns 714

# 5. File counts
test ! -f backend/services/complexity.py && echo "PASS"
find backend -name "*.py" -not -path "*__pycache__*" | xargs wc -l | tail -1
# Record: _____ (expect ~800-1,000 fewer than Phase 1)
```

---

## 7. Phase 3: Memory System Overhaul

**Goal:** Fix all memory bugs, unify layers, increase context 6→20.

**Estimated effort:** 6-8 hours
**Risk:** Medium-High
**Rollback:** `git revert` to Phase 2

### 3.1 Fix B1 + B8: User Memory Dict Rendering

**New `_format_user_memory()` in agent.py:**
```python
def _format_user_memory(user_memory):
    if not user_memory or not isinstance(user_memory, dict):
        return ""
    facts = user_memory.get("facts", [])
    if not facts:
        return ""
    lines = []
    for fact in facts[:10]:
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

After Phase 2 simplification, there's only one prompt injection point (no more B8 duplicate).

### 3.2 Fix B2: Vector Indexing

Add `chat_id` and `message_index` to `add_message_embedding()` calls in `generate.py`. Frontend now sends `chat_id` (fixed in Phase 0).

### 3.3 Fix B3: build_enhanced_context() Return Type

Return a NamedTuple instead of bare string:
```python
class EnhancedContext(NamedTuple):
    full_context: List[dict]
    semantic_summary: Optional[str]
```

### 3.4 Fix B4: Fact Format Normalization

Normalize at REST API save time. All facts stored as:
```python
{"text": str, "category": str, "importance": int, "embedding": list, "created_at": int}
```

Add lazy migration for existing old-format facts (idempotent).

### 3.5 Fix B5: Context Window 6 → 20

**`store.js`:**
```javascript
CONTEXT_WINDOW_SIZE: 20,
```

**Impact:** 20 messages × ~400 tokens = ~8,000 tokens context. Fits comfortably in both 32K (current) and 128K (Phase 4) context windows.

**This is the single highest-impact change in the entire overhaul.**

### 3.6 Memory Architecture After Phase 3

**Before (4 layers, 8+ bugs):**
```
Frontend Layer 1: contextMemory (6 messages, inconsistently applied) — BROKEN
Frontend Layer 2: conversationSummary (never persists, rarely triggers) — DEAD CODE
Backend Layer 3:  Semantic Memory (broken indexing, broken return type) — CRASHED
Backend Layer 4:  User Memory (dual schemas, renders as dicts) — BROKEN
```

**After (2 layers, working):**
```
Frontend: contextMemory (20 messages — sufficient for most sessions)
Backend:  User Memory (normalized schema, clean rendering, embeddings on all facts)
Backend:  Semantic Memory (working indexing, cross-chat retrieval, always active)
Summarization: DELETED (20-message window makes it unnecessary)
```

### 3.7 Phase 3 Verification

```bash
# 1. Memory renders correctly
# Create fact via REST, send chat message, check logs for prompt
# Should see "- [preferences] Test fact" NOT "{'text': ..., 'embedding': [0.1, ...]}"

# 2. Context window
# Send 15 messages, message #1 = "The secret word is BANANA"
# Message #15: "What was the secret word?"
# Should answer "BANANA"

# 3. Semantic retrieval
# Chat A: discuss "Python decorators"
# Chat B: ask "What did we discuss about Python?"
# Should retrieve context from Chat A

# 4. Memory round-trip
# Ask: "Remember that my favorite language is Rust"
# New chat: "What's my favorite language?"
# Should retrieve "Rust"
```

---

## 8. Phase 4: Model Upgrade

**Goal:** Switch to `qwen2.5-coder:32b` for ~30% better coding intelligence.

**Estimated effort:** 2-4 hours
**Risk:** Medium (GPU memory)
**Rollback:** Change `MODEL_NAME` env var

### 4.1 Benchmark Comparison

| Metric | Current (qwen3:8b) | Target (qwen2.5-coder:32b) | Delta |
|--------|--------------------|-----------------------------|-------|
| Aider benchmark | ~45%* | 72.9% | **+28%** |
| HumanEval+ | ~55%* | ~79% | **+24%** |
| VRAM (Q4_K_M) | ~6GB | ~20GB | Fits 24GB |
| Context window | 32K | 128K | **4x** |
| Speed (tok/s) | ~40 | ~15 | ~2.5x slower |
| Training focus | General chat | **Code-specialized** | Better for coding |

*Estimated for general chat model on coding tasks.

**Net result:** 2.5x slower per token BUT single-pass pipeline (Phase 2) removed 3-5x latency overhead. Net latency is **faster** than current multi-pass + 8B.

### 4.2 Configuration Changes

**`config.py`:**
```python
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5-coder:32b")
```

**`config.py` — tier detection:**
```python
tier_names = {
    # ... existing ...
    "qwen2.5-coder:32b": 3,    # ADD
}
```

**`deploy/docker/Dockerfile`:**
```dockerfile
RUN ollama pull qwen2.5-coder:32b
```

**`deploy/akash/*.yml`:** GPU ≥ 24GB VRAM (RTX 3090, RTX 4090, A5000).

### 4.3 Quantization: Q4_K_M

| Quantization | VRAM | Quality Loss | Fits 24GB + 32K ctx? |
|-------------|------|-------------|----------------------|
| FP16 | ~64GB | None | NO |
| Q8_0 | ~34GB | Negligible | NO |
| **Q4_K_M** | **~20GB** | **Small (~5-8%)** | **YES** |
| Q4_0 | ~18GB | Moderate | YES (margin) |

**Fallback if VRAM tight:** `NUM_CTX = 16384` (still supports 20-message window).

### 4.4 Phase 4 Verification

```bash
# 1. Health check shows new model
curl -s https://api.dubya.ai/health | python3 -m json.tool
# "model": "qwen2.5-coder:32b"

# 2. VRAM usage
nvidia-smi
# ~20-23GB used

# 3. Coding quality
# Ask: "Write a Python function to find the longest palindromic substring using Manacher's algorithm"
# Compare quality with old model output

# 4. Latency check
time curl -X POST https://api.dubya.ai/generate/stream -d '{"prompt":"Hello"}'
# Should complete within 30s (32B is slower but single-pass compensates)
```

---

## 9. Phase 5: Agentic Scaffolding

**Goal:** Add filesystem tools, code execution, repo map for Claude Code-level capabilities.

**Estimated effort:** 2-3 weeks
**Risk:** High (security implications)
**Rollback:** Feature flags per tool

### 5.1 New Filesystem Tools

| Tool | Parameters | Security |
|------|-----------|----------|
| `read_file` | `path`, `start_line?`, `end_line?` | Sandboxed to `/workspace` |
| `write_file` | `path`, `content` | Sandboxed, max 5MB |
| `list_directory` | `path`, `recursive?` | Sandboxed, max depth 3 |
| `search_codebase` | `query`, `file_pattern?` | Sandboxed, max 50 matches |
| `run_command` | `command` | **Allowlist only**: python, pytest, node |

### 5.2 Code Execution with Reflexion

The Reflexion pattern (NeurIPS 2023) — self-critique works ONLY with **external feedback**:

```
Model writes code → Execute in sandbox → Capture stdout/stderr/exit_code
  → If error: inject error as observation in ReAct loop → model fixes → re-execute
  → If success: return output
  Max 3 retry attempts
```

This transforms self-critique from "theater" (model evaluating its own prose) to "grounded verification" (model seeing actual errors).

### 5.3 Increase ReAct Iterations

```python
REACT_MAX_ITERATIONS = 15  # Was 5
```

Add token budget guard:
```python
MAX_TOTAL_TOKENS = 24000  # 75% of context window
# Force final answer if approaching limit
```

### 5.4 Repo Map V1 (Regex-Based)

~100 lines. Extracts `def`/`class`/`function`/`const` signatures from workspace files. Injected into context when user references a project.

80% of tree-sitter's value for 10% of the effort. Upgrade to tree-sitter later based on usage data.

### 5.5 Phase 5 Verification

```bash
# 1. File tools: "What files are in this project?" → list_directory
# 2. Code reading: "Show me main.py" → read_file
# 3. Code execution: "Run pytest" → run_command, show results
# 4. Error recovery: write buggy code → execute → fix → re-execute
# 5. Security: "Read /etc/passwd" → blocked
# 6. Iteration limit: complex task → terminates within 15 iterations
```

---

## 10. Decisions Log

| # | Decision | Rationale | Alternative | Why Rejected |
|---|----------|-----------|-------------|--------------|
| D1 | Single-pass over multi-pass | Stechly et al.: "LLMs no better at verifying than generating." 3-5x latency improvement. No production tool uses multi-pass self-critique. | Keep multi-pass with better prompts | Same model can't meaningfully critique itself without external signals |
| D2 | Context window 20 over 6 | 6 = 3 exchanges. Coding needs 10+. 20×400 tokens = 8K, leaves 24K for response in 32K window. | 10 (compromise) | No reason to compromise — 8K context is affordable |
| D3 | Delete summarization entirely | Audit proved: never persists, rarely triggers, broken when it does. 20-message window makes it unnecessary. | Persist in autosave (Team A) | Why save broken code? Delete and ship the context window increase. |
| D4 | qwen2.5-coder:32b | +28% Aider, +24% HumanEval, code-specialized, fits 24GB GPU (Q4_K_M), 128K context. | qwen2.5:32b (general), qwen3:8b (current) | Coder variant specifically trained for Trinity's primary use case |
| D5 | Delete LangGraph entirely | 7 files, 100MB deps, never enabled in production, duplicate pipeline. | Keep as optional | Dead code is a liability — maintenance burden with zero benefit |
| D6 | Delete voting entirely | Never called from any active path. Self-consistency needs multiple identical models. | Keep for future multi-model | Premature; design when multi-model actually deployed |
| D7 | Keep ReAct, kill multi-pass | ReAct (iterative tool loop) validated by SWE-Agent, Aider, Claude Code. Multi-pass is unvalidated. | Keep Critique as lightweight check | Critique without ground truth (tests/linter) is "mostly theater" |
| D8 | XML tools over native Ollama | Native produces empty content with Qwen3. XML is portable, debuggable. | Fix native for qwen2.5-coder | Model-specific; XML works everywhere |
| D9 | Dynamic tool injection | Saves ~600 tokens/request for 70%+ of queries. Cleaner prompts = better responses. | Always include tools | Unnecessary overhead |
| D10 | Regex repo map V1 | 80% value, 10% effort. Prove concept first. | Start with tree-sitter | Over-engineering; upgrade incrementally |
| D11 | Reflexion (external feedback) | Reflexion paper: 91% pass@1 with test feedback vs 80% without. | Pure self-critique | Research clear: external verification makes self-improvement work |
| D12 | Frontend Phase 0 before backend | Every backend change breaks frontend. Stabilize first, then change safely. | Fix frontend alongside backend | Audit shows frontend is too broken for incremental fixes |
| D13 | Delete /generate/simple | Audit: 0 callers in entire frontend. Dead code. | Keep (Team B) | Team B didn't check actual call sites |
| D14 | Delete conversationSummary system | Audit: never persists to disk, never sent to backend, lost on every refresh. | Fix and persist (Team A) | Feature is complete fiction — no value in fixing dead code |

---

## 11. Verification Matrix

| Phase | Test | Method | Expected | Blocking? |
|-------|------|--------|----------|-----------|
| 0 | Single preprocessToolCalls | `grep "function preprocessToolCalls"` | 1 match | YES |
| 0 | No dead frontend code | `grep "generateSimple\|USE_CANISTER"` | 0 matches | YES |
| 0 | No console.log | `grep "console\.log" \| grep -v logger` | 0 matches | YES |
| 0 | chat_id in requests | `grep "chat_id" api.js` | ≥1 match | YES |
| 0 | Frontend builds | `npm run build` | Exit 0 | YES |
| 1 | No dangling imports | `python3 -c "ast.parse(...)"` | No errors | YES |
| 1 | No dead references | `grep "langgraph\|langchain\|ab_test"` | 0 matches | YES |
| 1 | Docker builds | `docker build --platform linux/amd64` | Exit 0 | YES |
| 1 | Health check | `curl /health` | 200 OK | YES |
| 2 | No complexity refs | `grep "complexity\|UNDERSTAND_PROMPT"` | 0 matches | YES |
| 2 | Streaming works | Browser test | Smooth token stream | YES |
| 2 | ReAct works | "What is 42 * 17?" | Returns 714 | YES |
| 2 | Latency | `time curl /generate` | 3-5x faster | NO |
| 3 | Memory renders clean | Log inspection | No dicts in prompt | YES |
| 3 | Vector indexing | SQLite count check | Rows > 0 | YES |
| 3 | Context window | 15-message test | Msg #1 recalled at #15 | YES |
| 3 | Memory round-trip | Save → new chat → recall | Fact retrieved | YES |
| 4 | New model loaded | `curl /health` | qwen2.5-coder:32b | YES |
| 4 | VRAM | `nvidia-smi` | 20-23GB | YES |
| 5 | File tools | "List files" query | Directory tree | YES |
| 5 | Code execution | "Run tests" query | Test output | YES |
| 5 | Security | Path traversal attempt | Blocked | YES |

---

## 12. Risk Register

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Phase 0 frontend changes break rendering | Medium | High | Manual smoke test after each change; Phase 0 is all deletion/consolidation (low risk) |
| Phase 2 single-pass reduces quality on some queries | Low | Medium | Benchmark before/after; can add lightweight planning prompt for explicit "design" queries |
| Phase 3 memory migration corrupts user data | Low | Critical | Backup all user_memory.json before deploy; migration is additive only |
| Phase 4 model doesn't fit GPU | Medium | Medium | Fall back to Q4_0 or reduce NUM_CTX to 16384 |
| Phase 4 model is ~2.5x slower | High | Low | Expected; single-pass compensates; net latency similar or better |
| Phase 5 sandbox escape | Low | Critical | Path traversal prevention; command allowlist; Docker isolation |
| Phase 5 ReAct infinite loop | Medium | Medium | Hard limit at 15 iterations + token budget at 75% context |
| Removing multi-pass reduces quality | Low | Medium | Keep old code in git history; run IQ test before/after |
| Frontend breaks on simplified SSE | Low | Medium | Phase 0 stabilization makes this safe |
| Cold start latency with 32B model | Medium | Low | Expected 30-60s first request; document in deployment notes |
| `detect_tools_needed()` false negatives | Medium | Low | User can explicitly trigger tools; heuristic is hint not gate |
| No frontend test coverage | High | Medium | Phase 0 doesn't add tests (scope control); future improvement |

---

## 13. Research References

| Paper/Tool | Key Finding | Phase Applied |
|------------|-------------|---------------|
| Stechly et al. (arXiv:2310.12397) | LLMs no better at verifying than generating | Phase 2 — delete self-critique |
| Reflexion (arXiv:2303.11366, NeurIPS 2023) | Self-reflection works WITH external feedback | Phase 5 — code execution |
| Self-Contrast (arXiv:2401.02009, ACL 2024) | Multi-perspective > single self-evaluation | Future — multi-model |
| CoALA (arXiv:2309.02427) | Cognitive architecture taxonomy for agents | Phase 3 — memory design |
| SWE-Agent (NeurIPS 2024) | Simple 100-line agent matches complex pipelines | Phase 2 — simplification |
| Aider leaderboards | qwen2.5-coder:32b = 72.9% (matches GPT-4o) | Phase 4 — model selection |
| ReAct (Yao et al., 2022) | Interleaving reasoning + actions beats pure reasoning | Phase 2 — keep ReAct loop |
| Tree of Thoughts (Yao et al., 2023) | Branching helps ONLY with clear eval functions | Phase 5 — code execution eval |
| MemGPT (Packer et al., 2023) | LLM-managed memory for persistent facts | Phase 3 — fix, don't expand |

---

## 14. Appendices

### Appendix A: Files Modified/Deleted Per Phase

#### Phase 0 — Frontend (~500 lines removed)
| Action | Path |
|--------|------|
| NEW FILE | `trinity-icp/src/core/logger.js` (~20 lines) |
| NEW FILE | `trinity-icp/src/core/sse.js` (~60 lines) |
| DELETE FILE | `trinity-icp/src/state/contextMemory.js` (75 lines) |
| EDIT | `trinity-icp/src/ui/messages.js` — delete local preprocessToolCalls, import from editMessage |
| EDIT | `trinity-icp/src/core/api.js` — delete generateSimple, canister path, unify SSE, add chat_id |
| EDIT | `trinity-icp/src/features/generate.js` — fix module scope, remove console.log, remove clear/phase handling |
| EDIT | `trinity-icp/src/state/store.js` — remove summary state, fix context window |
| EDIT | `trinity-icp/src/features/chatManagement.js` — remove recoverArchivedChats |
| EDIT | All frontend files — replace console.log with Logger |

#### Phase 1 — Backend Deletions (~2,000 lines removed)
| Action | Path |
|--------|------|
| DELETE DIR | `backend/services/graph/` (7 files) |
| DELETE FILE | `backend/services/parallel.py` |
| DELETE FILE | `backend/services/experiments.py` |
| DELETE FILE | `backend/services/voting.py` |
| DELETE FILE | `backend/middleware/ab_test.py` |
| EDIT | `backend/routes/generate.py` — remove langgraph + simple/stream |
| EDIT | `backend/routes/admin.py` — remove experiment endpoints |
| EDIT | `backend/requirements.txt` — remove langgraph/langchain |
| EDIT | `backend/services/agent.py` — remove multi-model, non-streaming |
| EDIT | `backend/services/react_loop.py` — remove native tool code |
| EDIT | `backend/services/tools.py` — remove native tool functions |
| EDIT | `backend/config.py` — remove dead sections |
| EDIT | `backend/inference_server.py` — remove LangGraph/voting detection |

#### Phase 2 — Simplifications (~1,000 lines removed)
| Action | Path |
|--------|------|
| DELETE FILE | `backend/services/complexity.py` |
| EDIT | `backend/services/agent.py` — single-pass replacement |
| EDIT | `backend/services/agent_prompts.py` — keep 2 prompts, delete rest |
| EDIT | `backend/routes/generate.py` — merge agent into stream |

#### Phase 3 — Memory Fixes (~150 lines net added)
| Action | Path |
|--------|------|
| EDIT | `backend/services/agent.py` — fix _format_user_memory() |
| EDIT | `backend/routes/generate.py` — fix vector indexing, semantic retrieval |
| EDIT | `backend/services/memory.py` — fix return type |
| EDIT | `backend/routes/chat.py` — normalize fact schema |
| EDIT | `backend/services/memory_tools.py` — add migration |
| EDIT | `trinity-icp/src/state/store.js` — CONTEXT_WINDOW_SIZE = 20 |

#### Phase 4 — Model (config changes only)
| Action | Path |
|--------|------|
| EDIT | `backend/config.py` — MODEL_NAME, tier detection |
| EDIT | `deploy/docker/Dockerfile` — model pull |
| EDIT | `deploy/akash/*.yml` — GPU requirements |

#### Phase 5 — New Features (~500 lines added)
| Action | Path |
|--------|------|
| NEW FILE | `backend/services/repo_map.py` (~100 lines) |
| EDIT | `backend/services/tools.py` — add 5 filesystem tools |
| EDIT | `backend/services/code_executor.py` — sandboxed execution |
| EDIT | `backend/config.py` — REACT_MAX_ITERATIONS = 15 |
| EDIT | `backend/services/react_loop.py` — token budget guard |

### Appendix B: Line Count Impact

| Phase | Lines Removed | Lines Added | Net Change |
|-------|--------------|-------------|------------|
| Phase 0 | ~500 | ~80 | **-420** |
| Phase 1 | ~2,000 | ~0 | **-2,000** |
| Phase 2 | ~1,000 | ~100 | **-900** |
| Phase 3 | ~50 | ~200 | **+150** |
| Phase 4 | ~10 | ~10 | **0** |
| Phase 5 | ~0 | ~500 | **+500** |
| **Total** | **~3,560** | **~890** | **-2,670** |

The codebase gets **2,670 lines smaller** while becoming significantly more capable, more reliable, and more maintainable.

### Appendix C: Answers to Research Questions

**Q1: Is the pipeline helping or hurting?**
Hurting. No production tool uses multi-pass self-critique. Research requires external feedback for self-reflection to work. Delete understand/plan/critique/refine. Keep single-pass ReAct.

**Q2: What memory architecture works?**
Full context + MemGPT for cross-session. Fix the bugs (B1-B4), increase window (B5), delete summarization (B6). RAG for cross-session only.

**Q3: Model selection?**
qwen2.5-coder:32b at Q4_K_M. Single model, no routing. Fits 24GB. 128K context. Matches GPT-4o on coding.

**Q4: Is Trinity ready for agentic use?**
Not yet. Need: code execution sandbox, filesystem tools, more ReAct iterations (5→15). Phase 5.

**Q5: Is the system prompt harmful?**
Partially. Tool definitions waste 275 tokens when no tools needed. Anti-XML instructions paradoxically teach XML syntax. Fix: dynamic injection, shorter prompts.

**Q6: The rendering problem?**
XML works. Don't change format now. Fix the frontend rendering pipeline first (Phase 0), then backend changes won't break it.

---

*This document supersedes TEAM-A-ANALYSIS.md, TEAM-B-ANALYSIS.md, and OVERHAUL-REFERENCE.md. All sessions working on the overhaul should reference this document.*

*Generated February 12, 2026.*
