# Trinity Chat System Architecture

> **Last Updated:** February 25, 2026
> **Status:** Canonical — reflects production codebase

## Overview

Every user message travels through a composable pipeline of focused modules:

```
Frontend (React 19)  →  /generate/agent (SSE)
                              │
                    context_loader.load_context()      ← classify + load all context once
                              │
                    prompt_assembler.assemble()         ← token-budgeted prompt
                              │
                    StreamingPipeline.process_streaming()
                              │
                    ┌─────────┴─────────┐
                    │   ReAct Loop      │   (tools needed)
                    │   Direct chat     │   (no tools)
                    └─────────┬─────────┘
                              │
                        execute_tool()  (code_executor.py)
                              │
                        llama-server (qwen3:32b)
```

The former 1086-line `agent.py` god module was refactored into: `context_loader.py`, `query_classifier.py`, `prompt_assembler.py`, `pipeline.py`, and `think_filter.py`. Legacy callers still work via `AgentPipeline` (thin wrapper).

All responses stream as **Server-Sent Events (SSE)**. There is no REST request/response pair — the single inference endpoint `/generate/agent` is the sole path for user-facing LLM output.

---

## 1. Frontend: Sending a Message

**File:** `trinity-icp/src-react/hooks/useChat.ts`

```
user types message
       │
  send(text)
       │
  ensureCanonicalChatId()        ← creates chat via POST /chat/start if needed
       │
  addMessage("user", text)       ← Zustand optimistic update (no wait for server)
       │
  POST /generate/agent           ← {message, chat_id, principal_id, context_memory[]}
       │
  EventSource loop               ← processEvents() generator
       │
  ┌────┴──────────────────────────────────┐
  │  event type          action           │
  │  {type:"session"}    setCurrentChatId │
  │  {phase:"..."}       (status display) │
  │  {token:"..."}       append to buffer │
  │  {done:true}         finalize message │
  │  {error:"..."}       show error       │
  └───────────────────────────────────────┘
       │
  fetchPersistedChat()           ← GET /chat/{chat_id} after done to sync messages
```

**Key rules:**
- `context_memory[]` is a sliding window of recent messages sent in every request (frontend-side context, not the server's DB context)
- `<think>` blocks are stripped server-side by `think_filter.py` before tokens reach the frontend
- `continueGeneration()` re-sends with `"continue"` message when `done_reason === "length"`

---

## 2. Backend Entry Point: `/generate/agent`

**File:** `backend/routes/generate.py`

```
POST /generate/agent
       │
  @require_auth (Ed25519 sig, 60s window)
       │
  context_loader.load_context(store, knowledge_store, prompt, chat_id, principal_id)
       │
  ┌────┴──────────────────────────────────────────────────────┐
  │  Every query gets full context:                           │
  │  25 msgs + summary + 20 semantic results + query embedding│
  │  + tool detection (ByteTransformer + regex fallback)      │
  │  + temperature routing (code→0.1, tools→0.3, else→0.7)   │
  └────────────────────────────────────────────────────────────┘
       │
  prompt_assembler.assemble(question, context, knowledge_items, ...)
       │ → token-budgeted messages array
       │
  store.append_message(user)     ← persist user message
  enqueue_ingestion(user)        ← async: index + extract + summarize
       │
  StreamingPipeline.process_streaming() → SSE generator
       │
  store.append_message(assistant) ← persist final response
  enqueue_ingestion(assistant)    ← async ingestion
```

---

## 3. Routing Decision Tree

**File:** `backend/services/pipeline.py` (extracted from former agent.py)

```
StreamingPipeline.process_streaming(question, messages, principal_id, tools_needed, ...)
       │
  tools_needed?  ──YES──→  optional web_search pre-fetch
       │                    → ReactLoop.execute_streaming()
       │ NO
  chat_stream() (direct, single-pass) + tool-call rescue
       │
  think_filter.filter_think_blocks(stream) → strip <think>…</think>
       │
  yield {done: true, response_mode, done_reason}
```

Note: All classification (smalltalk, disclosure, code intent) is done **once** in `context_loader.load_context()` via `query_classifier.py` — not re-evaluated in the pipeline.

### Tool Detection (3-Tier)

`detect_tools_needed()` in `backend/services/tools.py` uses a 3-tier system:

1. **ByteTransformer** `detect_tools()` — neural classifier (<1ms, ~50K params)
2. **Confirmation gate** — suppresses false positives when confidence < 0.92 unless regex agrees
3. **Regex fallback** — `_regex_detect_tools()` catches tools the classifier missed

| Trigger Pattern | Tool(s) Activated |
|---|---|
| `calculate`, `\d+\s*[+\-*/]`, `sqrt`, `sin(`, … | `calculator` |
| `search the web`, `look up`, `latest news`, … | `web_search` |
| `fact.check`, `verify`, `is it true`, … | `fact_check` |
| `remember`, `save.*fact`, `store.*memory`, … | `save_memory` |
| `recall`, `what do you know about me`, … | `recall_memory` |
| `run`, `execute`, `write code`, explicit file path | `code_display` / `run_command` |
| `read file`, `list directory`, `search codebase` | filesystem tools |

Returns a `list[str]` of tool names. **Empty list → direct chat (with tool-call rescue). Non-empty → ReAct loop.**

`code_display` additionally requires `CODE_EXECUTION_ENABLED=true` AND explicit execution/fix intent or a concrete filesystem path.

---

## 4. ReAct Loop

**File:** `backend/services/react_loop.py`

```
ReactLoop.execute_streaming(question, context_messages, ...)
       │
  _build_messages():
    [system: REACT_SYSTEM_PROMPT + TOOL_PROMPT_SECTION + repo_map + user_memory]
    [context: last 20 messages, capped at 4000 chars each]
    [user: question]
       │
  for iteration in range(REACT_MAX_ITERATIONS):
       │
    client.chat(messages)                      ← non-streaming; avoids SSE gaps
       │
    parse_tool_calls(response)
       │
    ┌──┴─────────────────────────────────────────────┐
    │  no tool calls?                                │
    │    strip <think> blocks                        │
    │    yield {token: chunk} × N  (4-char chunks)   │
    │    yield {react_done, tools_used, iterations}  │
    │    return                                      │
    └────────────────────────────────────────────────┘
       │ (tool call found)
    execute first tool only (one tool per iteration)
       │
    yield {phase:"tool_execution", message:"Using X..."}
    execute_tool(tc.name, tc.params, context)
    yield {phase:"tool_result",    message:"X: done|error"}
       │
    messages.append({role:"assistant", content})
    messages.append({role:"user",      content: observation})
       │
    Reflexion? (code_display / run_command / write_file + error):
      retry_count ≤ REFLEXION_MAX_RETRIES?
        → self-correction prompt injected as observation
      retry_count > max?
        → "max retries reached" prompt, continue to final answer
       │
    _estimate_tokens(messages) > REACT_TOKEN_BUDGET?
      → break (force final answer)
       │
  (max iterations or token budget exhausted)
  inject "give your final answer" user message
  client.chat_stream() → collect all tokens → strip <think> → yield {token:} chunks
  yield {react_done, tools_used, iterations: max_iterations}
```

### ReAct Configuration

| Config Key | Default | Description |
|---|---|---|
| `REACT_MAX_ITERATIONS` | 5 | Max tool-calling rounds |
| `REACT_TOKEN_BUDGET` | 48000 | Estimated token cap before forcing final answer |
| `REFLEXION_MAX_RETRIES` | 3 | Self-correction retries for failed code/write/run tools |

### One Tool Per Turn

The loop **always executes only `tool_calls[0]`** — the first detected tool call per iteration. The model observes the result and decides whether to use another tool or answer. This avoids unpredictable parallel side-effects.

### Reflexion (Self-Correction)

Applies to: `code_display`, `run_command`, `write_file`

On error: the observation message includes the error text and a directive to analyze and fix it. On next iteration the model re-calls the tool with corrected parameters.

---

## 5. Tool Execution Dispatch

**File:** `backend/services/code_executor.py`

`execute_tool(tool_name, params, context)` routes to the appropriate handler:

```
execute_tool()
    │
    ├── "calculator"        evaluate_math_expression()    (AST eval, no Python exec)
    ├── "code_display"      format_code_display()         (RestrictedPython sandbox)
    ├── "current_datetime"  datetime.now(UTC)
    ├── "web_search"        _execute_web_search()         (Brave Search API)
    ├── "fact_check"        _execute_fact_check()         (dual web searches)
    ├── "save_memory"  ┐
    ├── "recall_memory"│
    ├── "search_memory"├── _execute_memory_tool()        (memory_tools.py)
    ├── "update_memory"│
    ├── "forget_memory"┘
    ├── "read_file"         _execute_read_file()          (sandboxed)
    ├── "write_file"        _execute_write_file()         (sandboxed)
    ├── "list_directory"    _execute_list_directory()     (sandboxed)
    ├── "search_codebase"   _execute_search_codebase()    (sandboxed)
    └── "run_command"       _execute_run_command()        (allowlist only)
```

### Calculator

Uses Python `ast.parse()` + recursive `eval_node()`. No `eval()` or `exec()`. Safe math functions only (`sin`, `cos`, `log`, `sqrt`, `pi`, …). Returns formatted result or error string.

### Code Display / Execution

- Always formats code as a fenced markdown block
- Python execution only if `CODE_EXECUTION_ENABLED=true` **and** `execute=true` param
- Uses **RestrictedPython**: no imports, no file I/O, no network, no `os`/`subprocess`
- Runs in a separate daemon thread with `CODE_EXECUTION_TIMEOUT` second limit

### Filesystem Sandbox

All file/directory/search/command tools call `_resolve_sandbox_path()` first:

```
user_path  →  (WORKSPACE_ROOT / user_path).resolve()
                      │
             starts with WORKSPACE_ROOT?
               YES → proceed
               NO  → "Access denied: path traversal blocked"
```

- `read_file`: max `WORKSPACE_MAX_FILE_SIZE`, line-range support, truncated at 500 lines
- `write_file`: creates parent dirs automatically
- `list_directory`: skips `.git`, `__pycache__`, `node_modules`; depth capped at `WORKSPACE_MAX_DEPTH`
- `search_codebase`: substring search, skips binary/large files, max `WORKSPACE_MAX_SEARCH_RESULTS`
- `run_command`: `shlex.split()` (no shell), executable must be in `WORKSPACE_ALLOWED_COMMANDS`; `subprocess.run(shell=False)`, timeout = `WORKSPACE_COMMAND_TIMEOUT`

### Memory Tools

Delegated to `backend/services/memory_tools.py`. All require `principal_id` in context (injected by `ReactLoop` from `generate.py`'s `context` dict).

| Tool | Action |
|---|---|
| `save_memory` | `store.create_fact()` with embedding |
| `recall_memory` | `store.list_facts()` filtered by category/query |
| `search_memory` | semantic search via embeddings |
| `update_memory` | `store.update_fact()` |
| `forget_memory` | `store.soft_delete_fact()` |

---

## 6. Tool Call XML Format

**File:** `backend/services/tools.py`

The model emits tool calls as XML:

```xml
<tool_call name="calculator">
  <expression>sqrt(144) + 2^8</expression>
</tool_call>
```

`parse_tool_calls()` has **four fallback strategies** to handle model formatting drift:

1. **Strict** — `<tool_call name="...">...</tool_call>` with named attribute
2. **Lenient** — unclosed or malformed tag with `name=` attribute
3. **Nameless** — `<tool_call>` with inner tags; tool name inferred from tag via `_TAG_TO_TOOL` dict
4. **Bare** — plain tool name followed by XML params; no outer `tool_call` wrapper

`replace_tool_calls_with_results()` replaces the raw XML in the final answer with:
- Success: `[Tool Result]\n{output}`
- Failure: `[Tool Error: {error}]`

### All 14 Tools

| Tool | Category | Description |
|---|---|---|
| `calculator` | Math | AST-safe expression evaluator |
| `code_display` | Code | Format + optionally execute Python (sandbox) |
| `web_search` | Web | Brave Search API, top 5 results |
| `fact_check` | Web | Dual web searches to verify a claim |
| `save_memory` | Memory | Persist a fact to the user's profile |
| `recall_memory` | Memory | Retrieve facts by category or query |
| `search_memory` | Memory | Semantic search over facts |
| `update_memory` | Memory | Edit an existing fact |
| `forget_memory` | Memory | Soft-delete a fact |
| `read_file` | Filesystem | Read a file in WORKSPACE_ROOT |
| `write_file` | Filesystem | Write a file in WORKSPACE_ROOT |
| `list_directory` | Filesystem | List directory contents |
| `search_codebase` | Filesystem | Substring grep across workspace files |
| `run_command` | Filesystem | Run an allowlisted shell command |

---

## 7. SSE Event Protocol

**Endpoint:** `POST /generate/agent` (streaming response)

```
data: {"type": "session", "chat_id": "...", "message_id": 42}

data: {"phase": "tool_execution", "message": "Using web_search..."}
data: {"phase": "tool_result",    "message": "web_search: done"}

data: {"token": "The "}
data: {"token": "answer "}
data: {"token": "is..."}

data: {"done": true, "assistant_message_id": 43,
       "done_reason": "stop", "response_mode": "react"}
```

| Event Field | Values | Notes |
|---|---|---|
| `type: "session"` | — | First event; establishes chat/message IDs |
| `phase` | `"tool_execution"`, `"tool_result"`, `"thinking"`, `"searching"` | Status display only |
| `token` | string chunk | Streamed answer text (4-char chunks from ReAct, native from direct stream) |
| `done` | true | Terminal event |
| `done_reason` | `"stop"`, `"length"`, `"tool_limit"` | `"length"` → frontend calls `continueGeneration()` |
| `response_mode` | `"react"`, `"direct"` | Metadata |
| `error` | string | Terminal error event |

---

## 8. Prompt Architecture

**File:** `backend/services/prompt_assembler.py` (new), `backend/services/agent_prompts.py`

### Prompt Assembly (New)

```
prompt_assembler.assemble(question, context_messages, knowledge_items, tools_needed, ...)
  │
  ├── Token budget allocation:
  │   55% for conversation history (~2200 tokens)
  │   Remaining for knowledge items (~1800 tokens)
  │   Safety margin: 2000 tokens
  │
  ├── Auto-generated tool section from TOOL_DEFINITIONS (single source of truth)
  │   (replaces hand-written TOOL_PROMPT_SECTION string)
  │
  → [
      {role: "system",    content: identity + knowledge items + tool_section},
      {role: "user",      content: conversation_summary},     ← if exists
      {role: "assistant", content: "I understand..."},        ← summary anchor
      ... last N unsummarized messages (capped at 20) ...
      {role: "user",      content: question}
    ]
```

### ReAct Path

Uses `REACT_SYSTEM_PROMPT` from `agent_prompts.py`, with tool definitions auto-generated by `prompt_assembler.get_tool_prompt_section()`.

Context messages: last 20, capped at 4000 chars each.

---

## 9. Chat & Memory CRUD API

**Files:** `backend/routes/chat.py`, `backend/routes/memory.py`, `backend/routes/user.py`

All routes require `@require_auth` (Ed25519). Write routes also apply `@storage_rate_limit`.

**Chat routes** (`routes/chat.py`):
| Method | Route | Action |
|---|---|---|
| `POST` | `/chat/start` | Create chat; `chat_id` optionally client-supplied |
| `GET` | `/chat/list` | List all chats (active + archived) |
| `GET` | `/chat/<chat_id>` | Paginated messages (`before_message_id`, `limit` 1–200) |
| `PATCH` | `/chat/<chat_id>` | Update `title`, `pinned`, `archived` |
| `DELETE` | `/chat/<chat_id>` | Hard delete chat + messages |
| `POST` | `/chat/<chat_id>/pin` | Toggle pin state |
| `POST` | `/chat/<chat_id>/archive` | Archive to IPFS |
| `GET` | `/chat/recover-archives` | List IPFS archives |
| `GET` | `/chat/archive/status/<cid>` | Check archive status |

**Memory routes** (`routes/memory.py`):
| Method | Route | Action |
|---|---|---|
| `GET` | `/user/memory` | Full memory dump: facts + summaries + recent jobs |
| `POST` | `/user/memory/fact` | Create fact (auto-embeds) |
| `PATCH` | `/user/memory/fact/<id>` | Edit fact text/category/importance (re-embeds) |
| `DELETE` | `/user/memory/fact/<id>` | Soft-delete fact |

**User routes** (`routes/user.py`):
| Method | Route | Action |
|---|---|---|
| `GET` | `/user/status` | User account status |
| `GET` | `/user/export` | Full data export (chats metadata + memory) |
| `GET` | `/user/stats` | Aggregate stats (chat count, fact count, encryption info) |

**Pagination:** `GET /chat/<chat_id>?before_message_id=100&limit=50` — returns messages with `message_id < 100`, newest-first, max 200 per page. `has_more: true` when returned count equals limit.

---

## 10. Full Request Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND                                                           │
│                                                                     │
│  user types → send() → optimistic addMessage() → POST /generate    │
│                                                                     │
│  SSE loop:  session → phase events → tokens → done                 │
│             → fetchPersistedChat() → sync UI from DB               │
└─────────────────────────────────────────────────────────────────────┘
          │                              ▲
          ▼                              │ SSE stream
┌─────────────────────────────────────────────────────────────────────┐
│  /generate/agent  (generate.py)                                     │
│                                                                     │
│  Auth → mode detection → DB read (25 msgs) → memory load           │
│  → store user msg → enqueue ingestion → AgentPipeline              │
│  → stream response → store assistant msg → enqueue ingestion       │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  StreamingPipeline.process_streaming()  (pipeline.py)                │
│                                                                     │
│  tools?     → ReactLoop.execute_streaming()                        │
│  direct?    → client.chat_stream() + think_filter + tool-call rescue│
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ReactLoop  (react_loop.py)                            [if tools]   │
│                                                                     │
│  iteration 1..N:                                                    │
│    client.chat() → parse_tool_calls()                              │
│    no calls? → stream final answer → react_done event              │
│    call?     → execute_tool() → inject observation → repeat        │
│                                                                     │
│  reflexion: code/run/write errors → self-correction up to 3×       │
│  token budget: ~48k tokens → force final answer                    │
│  max iterations: force chat_stream() final answer                  │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  execute_tool()  (code_executor.py)                                 │
│                                                                     │
│  calculator    → AST eval (no exec)                                │
│  code_display  → RestrictedPython sandbox + timeout thread         │
│  web_search    → Brave API                                         │
│  memory tools  → memory_tools.py → state.db                       │
│  filesystem    → sandboxed to WORKSPACE_ROOT                       │
│  run_command   → allowlist + subprocess (shell=False)              │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  llama-server  (port 8081, qwen3:32b)                               │
│                                                                     │
│  OpenAI-compatible API: POST /v1/chat/completions                  │
│  max_tokens=16384, timeout=600s, think blocks stripped by filter   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 11. `<think>` Block Handling

**File:** `backend/services/think_filter.py` (extracted from agent.py)

Qwen3 emits `<think>…</think>` blocks containing internal reasoning. Trinity strips them via:

**`think_filter.filter_think_blocks(token_stream, accumulator)`** — streaming generator that strips `<think>...</think>` in real-time as tokens arrive from llama-server.

**Safety:** ~20k token think-block limit triggers flush (prevents unbounded buffering).

**Fallback:** If stripping leaves empty content but think-block text exists, `_get_response_content()` extracts the think-block text and uses it as the answer (the model put its answer inside `<think>`).

---

## 12. Code Response Contract

`_finalize_response_contract()` in `agent.py` sets the SSE `done` event metadata:

| Field | Values |
|---|---|
| `response_mode` | `"react"` (tool path), `"direct"` (single-pass), `"smalltalk"` |
| `done_reason` | `"stop"` (complete), `"length"` (truncated — triggers `continueGeneration()`), `"tool_limit"` (hit max iterations) |

When `done_reason === "length"`, `useChat.ts` automatically calls `continueGeneration()` which re-sends `"continue"` to `/generate/agent`.

---

## 13. Key Files

| Purpose | File |
|---|---|
| SSE inference route | `backend/routes/generate.py` |
| Context loading (single path) | `backend/services/context_loader.py` |
| Query classification | `backend/services/query_classifier.py` |
| Token-budgeted prompts | `backend/services/prompt_assembler.py` |
| Streaming pipeline | `backend/services/pipeline.py` |
| Think-block filtering | `backend/services/think_filter.py` |
| Agent pipeline (compat wrapper) | `backend/services/agent.py` |
| Prompt templates | `backend/services/agent_prompts.py` |
| ReAct loop | `backend/services/react_loop.py` |
| Tool execution dispatch | `backend/services/code_executor.py` |
| Tool definitions & XML parser | `backend/services/tools.py` |
| Memory tool implementations | `backend/services/memory_tools.py` |
| Knowledge retrieval | `backend/services/knowledge_store.py` |
| Background ingestion | `backend/services/ingestion_worker.py` |
| Chat CRUD routes | `backend/routes/chat.py` |
| Persistent storage | `backend/services/state_store/` |
| Frontend SSE hook | `trinity-icp/src-react/hooks/useChat.ts` |
| Frontend orchestration | `trinity-icp/src-react/components/layout/AppShell.tsx` |
| Zustand store | `trinity-icp/src-react/store/index.ts` |

---

## 14. Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `REACT_MAX_ITERATIONS` | 5 | Max ReAct tool-calling rounds |
| `REACT_TOKEN_BUDGET` | 48000 | Estimated token threshold — force answer |
| `REFLEXION_MAX_RETRIES` | 3 | Self-correction retries for code/run/write errors |
| `CODE_EXECUTION_ENABLED` | false | Enable Python sandbox execution |
| `CODE_EXECUTION_TIMEOUT` | 10 | Python sandbox timeout (seconds) |
| `WORKSPACE_ROOT` | `/workspace` | Filesystem tool sandbox root |
| `WORKSPACE_MAX_DEPTH` | 4 | Recursive directory listing depth |
| `WORKSPACE_MAX_FILE_SIZE` | 10MB | Max file size for read/write |
| `WORKSPACE_MAX_SEARCH_RESULTS` | 50 | Max grep results per search |
| `WORKSPACE_COMMAND_TIMEOUT` | 30 | `run_command` subprocess timeout (seconds) |
| `WORKSPACE_ALLOWED_COMMANDS` | `["python","python3","pip","git","ls","cat"]` | `run_command` allowlist |
| `LLAMA_SERVER_CHAT_PORT` | `8081` | Chat llama-server port |
| `LLAMA_SERVER_INGEST_PORT` | `8082` | Ingest llama-server port |
| `MODEL_NAME` | `qwen3:32b` | Primary model |
