# Trinity — Intelligence, Routing & Decision-Making

> Last updated: February 2026

## Overview

When a user sends a message, Trinity doesn't just forward it to a language model. It goes through an **intelligent pipeline** that decides:

1. Does this query need tools (web search, code execution, file access)?
2. If yes, which tools? And how should they be orchestrated?
3. What context should be assembled (memory, search results, documents)?
4. Should the response self-correct if tool execution fails?

This document explains how that decision-making works end-to-end.

---

## The Two Paths

Every message takes one of two paths:

```
User message arrives at POST /generate/agent
│
├── detect_tools_needed(prompt)
│   Heuristic regex scan of the user's message
│
├── Tools detected? ─── YES ──> ReAct Loop (iterative tool calling)
│                                │
│                                ├── Think → Act → Observe → Think → ...
│                                ├── Up to 15 iterations
│                                ├── 48,000 token budget
│                                └── Self-correction on errors (Reflexion)
│
└── Tools detected? ─── NO ───> Direct Chat (single LLM call)
                                 │
                                 └── Stream response directly from Ollama
```

Both paths:
- Include user memory in the system prompt
- Include semantic context (relevant past messages)
- Stream results back to the frontend via SSE
- Index the response into semantic memory after completion

---

## Step 1: Tool Detection

**File:** `services/tools.py` → `detect_tools_needed(prompt)`

Before calling the LLM, the system scans the user's message with regex patterns to determine if tools will be needed:

| Pattern | Detected Tool | Example Triggers |
|---------|--------------|-----------------|
| Math expressions (`\d+\s*[+\-*/^]\s*\d+`) | `calculator` | "What is 25 * 4?" |
| "search", "look up", "find info" | `web_search` | "Search for the latest Python release" |
| "is it true", "verify", "fact check" | `fact_check` | "Is it true that Python 4 was released?" |
| Code fences, "write code", "function" | `code_display` | "Write a sorting function in Python" |
| "remember", "save this", "note that" | `save_memory` | "Remember that I prefer dark mode" |
| "what do you know about me" | `recall_memory` | "What do you know about my projects?" |
| "read file", "show me the file" | `read_file` | "Read the config.py file" |
| "write to", "create file" | `write_file` | "Create a hello.py file" |
| "list files", "show directory" | `list_directory` | "List files in the workspace" |
| "search codebase", "find in code" | `search_codebase` | "Search the codebase for auth functions" |
| "run", "execute" | `run_command` | "Run the test suite" |

If **any** pattern matches, the message is routed to the ReAct loop with full tool capabilities. Otherwise, it goes to direct chat.

> **Note:** This is a heuristic, not an LLM classification. It's fast (microseconds) but imperfect — some queries that would benefit from tools may be missed, and some that don't need them may trigger tool mode unnecessarily. In practice, it works well because the ReAct loop can simply choose not to use tools even when they're available.

---

## Step 2: Context Assembly

**File:** `services/agent.py` → `AgentPipeline.process_streaming()`

Before the LLM is called, context is assembled from multiple sources:

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONTEXT ASSEMBLY                            │
│                                                                  │
│  ┌── From Frontend ─────────────────────────────────────────┐   │
│  │  context_messages: last 20 messages (sliding window)      │   │
│  │  user_memory: persistent facts + preferences              │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌── From Semantic Memory ──────────────────────────────────┐   │
│  │  Working memory: last 5 messages from current chat        │   │
│  │  Semantic memory: top 8 relevant past messages            │   │
│  │  (weighted: 70% similarity + 30% recency)                 │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌── Auto-Detected ─────────────────────────────────────────┐   │
│  │  Web search results (if query contains search keywords)   │   │
│  │  Document context (if documents uploaded)                  │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  All assembled into system prompt by build_system_prompt():      │
│                                                                  │
│  ┌── System Prompt ─────────────────────────────────────────┐   │
│  │  1. Trinity identity + formatting guidelines              │   │
│  │  2. User memory facts (if any)                            │   │
│  │  3. Semantic context from past conversations              │   │
│  │  4. Search results (if auto-searched)                     │   │
│  │  5. Tool documentation (if tools path)                    │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Step 3a: Direct Chat (No Tools)

When no tools are detected, the system makes a single streaming call to Ollama:

```
OllamaClient.chat_stream(
    messages=[
        {role: "system", content: assembled_system_prompt},
        ...context_messages,
        {role: "user", content: prompt}
    ],
    model="qwen3:32b",
    options={num_ctx: 65536},
    think=False  # Suppress Qwen3 <think> blocks
)

→ Yields SSE events: {token: "..."} for each generated token
→ Final event: {done: true, done_reason: "stop"|"length"}
```

**Agent-Level Overrides:** `MAX_TOKENS = 16384` (set in `agent.py`, overrides config's `DEFAULT_MAX_TOKENS = 8000`). Context messages are capped to 10 messages × 2000 chars each to prevent prompt bloat.

---

## Step 3b: ReAct Loop (With Tools)

**File:** `services/react_loop.py` → `ReactLoop.execute_streaming()`

The ReAct (Reasoning + Acting) pattern is an iterative loop where the LLM thinks, decides on an action, observes the result, and repeats.

### Qwen3 `think=False` Requirement

All Ollama LLM calls in the ReAct loop pass `think=False` to suppress Qwen3's `<think>` reasoning blocks. Without this:
- The model generates lengthy `<think>...</think>` blocks that consume tokens but are stripped from output
- Responses appear empty after stripping
- Token budget is exhausted faster, causing timeouts

`think=False` is set on all 4 LLM call sites in `react_loop.py` (lines 272, 370, 422, 532).

### Response Content Extraction

`_get_response_content()` in `react_loop.py` performs defensive post-processing:
1. Strips `<think>...</think>` blocks via regex
2. Strips residual `<tool_call>` XML tags (prevents XML leak to user)
3. If stripping produces empty content, falls back to text inside think blocks (model put its answer there)

### The Loop

```
Iteration 1:
│
├── LLM generates response (streaming)
│   ├── <think>I need to search for the latest data...</think>
│   └── <tool_call name="web_search">{"query": "Python 3.13 release date"}</tool_call>
│
├── parse_tool_calls(response)
│   → [ToolCall(name="web_search", arguments={"query": "..."})]
│
├── execute_tool(tool_call, principal, ...)
│   → ToolResult(name="web_search", result="Python 3.13 was released...", success=true)
│
├── Format observation:
│   "## Tool Result: web_search\nPython 3.13 was released on October 1, 2024..."
│
├── Append to conversation as assistant message
│
└── Continue to next iteration...

Iteration 2:
│
├── LLM sees the tool result in context
│   ├── <think>Now I have the information. Let me compose the answer.</think>
│   └── <final_answer>Python 3.13 was released on October 1, 2024...</final_answer>
│
└── Loop terminates → stream final answer to user
```

### Termination Conditions

The loop stops when any of these occur:

| Condition | What Happens |
|-----------|-------------|
| `<final_answer>` tag detected | LLM is done — stream the answer |
| Max iterations reached (15) | Force a final answer generation |
| Token budget exhausted (48,000) | Force a final answer generation |
| No tool calls and no final answer for 2 iterations | Treat the response as the final answer |

### SSE Events During ReAct

The frontend receives different event types during a ReAct execution:

```
{phase: "thinking", message: "Analyzing your question..."}
{phase: "searching", message: "Searching the web..."}
{token: "Based on "}                          ← streaming tokens
{token: "my research, "}
{phase: "tool_execution", message: "Running calculator..."}
{phase: "tool_result", message: "Result: 42"}
{token: "The answer is "}
{token: "42."}
{done: true, response: {answer: "...", total_time_seconds: 3.5}}
```

The frontend's `TypingIndicator` component shows phase-appropriate animations during tool execution.

---

## The 15 Tools

**File:** `services/tools.py` (definitions), `services/code_executor.py` (execution)

| # | Tool | Category | What It Does |
|---|------|----------|-------------|
| 1 | `calculator` | Math | AST-based safe math evaluation (no eval()) |
| 2 | `web_search` | Information | Brave Search API query → formatted results |
| 3 | `fact_check` | Information | Dual web search (claim + verification) → evidence |
| 4 | `document_search` | Information | Search uploaded temporary documents |
| 5 | `code_display` | Code | Format code as copyable/downloadable blocks |
| 6 | `save_memory` | Memory | Save a fact about the user (with deduplication) |
| 7 | `recall_memory` | Memory | Retrieve relevant facts by semantic similarity |
| 8 | `search_memory` | Memory | Search facts by exact match, semantic, or hybrid |
| 9 | `update_memory` | Memory | Update an existing fact with new information |
| 10 | `forget_memory` | Memory | Soft-delete a fact (preserved in exports) |
| 11 | `read_file` | Filesystem | Read file contents (sandboxed to workspace) |
| 12 | `write_file` | Filesystem | Create/write files (sandboxed to workspace) |
| 13 | `list_directory` | Filesystem | List directory contents (recursive, depth-limited) |
| 14 | `search_codebase` | Filesystem | Glob-based code search |
| 15 | `run_command` | Execution | Run restricted commands (python, pytest, node only) |

### Tool Call Format

The LLM generates tool calls as XML:

```xml
<tool_call name="web_search">
{"query": "Python 3.13 new features"}
</tool_call>
```

The `parse_tool_calls()` function extracts these using a 4-tier regex fallback:

1. **Strict:** `<tool_call name="...">...</tool_call>` — well-formed XML with name attribute
2. **Lenient:** Allows missing `</tool_call>` closing tag
3. **Nameless:** `<tool_call>...</tool_call>` without name attribute — infers tool from child XML tags via `_TAG_TO_TOOL` mapping (e.g., `<expression>` → calculator, `<query>` → web_search)
4. **Bare:** Tool name followed by parameter tags without `<tool_call>` wrapper

### Tool Execution Dispatch

**File:** `services/code_executor.py` → `execute_tool()`

```
execute_tool(tool_call, principal, ...)
│
├── tool_call.name == "calculator"
│   └── evaluate_math_expression(expr)
│       AST-based: whitelist of operators, no eval()
│
├── tool_call.name == "web_search"
│   └── search.search_web(query)
│       Brave Search API → formatted results
│
├── tool_call.name == "fact_check"
│   └── fact_check.fact_check(claim)
│       Two searches: claim + "is it true that {claim}"
│
├── tool_call.name == "document_search"
│   └── Search document_store (in-memory, 1hr TTL)
│
├── tool_call.name == "code_display"
│   └── format_code_display(code, language)
│       Returns formatted markdown code block
│
├── tool_call.name in ["save_memory", "recall_memory", "search_memory"]
│   └── memory_tools.tool_save/recall/search_memory(principal, ...)
│
├── tool_call.name == "read_file"
│   └── _execute_read_file(args)
│       Path sandboxed to WORKSPACE_ROOT, optional line ranges
│
├── tool_call.name == "write_file"
│   └── _execute_write_file(args)
│       Path sandboxed to WORKSPACE_ROOT
│
├── tool_call.name == "list_directory"
│   └── _execute_list_directory(args)
│       Recursive with depth limit (default 3)
│
├── tool_call.name == "search_codebase"
│   └── _execute_search_codebase(args)
│       Glob-based file search
│
├── tool_call.name == "run_command"
│   └── Restricted execution:
│       Only: python, python3, pytest, node
│       Timeout: 10 seconds
│       Sandboxed to WORKSPACE_ROOT
│
└── Unknown tool name
    └── Try MCP client (external tool servers)
        └── If no MCP client: return error
```

### Filesystem Sandboxing

All filesystem tools are sandboxed to `WORKSPACE_ROOT` (default: `/workspace`):

```python
def _resolve_sandbox_path(path):
    resolved = Path(WORKSPACE_ROOT, path).resolve()
    if not str(resolved).startswith(str(Path(WORKSPACE_ROOT).resolve())):
        raise ValueError("Path traversal detected")
    return resolved
```

This prevents the AI from reading `/etc/passwd` or writing to system directories.

### Command Restriction

The `run_command` tool only allows specific executables:

```python
ALLOWED_COMMANDS = {"python", "python3", "pytest", "node"}
```

Any other command (e.g., `rm`, `curl`, `bash`) is rejected before execution.
Arguments are parsed with `shlex.split(...)` and executed with `subprocess.run(..., shell=False)`, so shell metacharacters are not interpreted.

---

## Reflexion (Self-Correction)

**File:** `services/react_loop.py`

When certain tools return errors, the ReAct loop can self-correct using **Reflexion** — feeding the error back as context and letting the LLM try again.

### Which Tools Trigger Reflexion

| Tool | Reflexion? | Why |
|------|-----------|-----|
| `code_display` | Yes | Code might have syntax errors |
| `run_command` | Yes | Command might fail, need different approach |
| `write_file` | Yes | File write might fail (permissions, path) |
| All others | No | Errors are informational, not correctable |

### Reflexion Flow

```
ReAct Iteration N:
│
├── LLM generates: <tool_call name="run_command">{"command": "python test.py"}</tool_call>
│
├── execute_tool() → ToolResult(success=false, result="ModuleNotFoundError: numpy")
│
├── reflexion_retries < 3? (REFLEXION_MAX_RETRIES)
│   │
│   ├── YES: Inject error as context message:
│   │   "## Tool Error (attempt 1/3)\nModuleNotFoundError: numpy\n
│   │    Please fix the error and try again."
│   │
│   │   increment reflexion_retries
│   │   continue loop → LLM sees error, generates corrected tool call
│   │
│   └── NO: Give up, include error in final answer
│       "I tried 3 times but couldn't resolve the error..."
```

---

## Token Budget Management

Each ReAct execution has a token budget to prevent runaway costs:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `REACT_TOKEN_BUDGET` | 48,000 tokens | Total budget for all iterations |
| Token estimation | ~4 chars per token | Approximate counting |

```
At each iteration:
│
├── Estimate tokens consumed so far:
│   consumed = sum(len(text) / 4 for text in all_messages)
│
├── If consumed > REACT_TOKEN_BUDGET:
│   ├── Stop iterating
│   ├── Force a final_answer generation:
│   │   "Based on what I've gathered so far, here's my answer..."
│   └── Include note that budget was reached
│
└── Otherwise: continue loop
```

---

## System Prompts

**Files:** `services/prompts.py`, `services/agent_prompts.py`

### Core Identity Prompt (`TRINITY_SYSTEM_PROMPT`)

Defines Trinity's personality, capabilities, and formatting guidelines. Includes:
- Identity and traits
- Markdown formatting rules
- LaTeX/KaTeX math rendering instructions
- Code block formatting

### ReAct System Prompt (`REACT_SYSTEM_PROMPT`)

Used when tools are available. Includes:
- The core identity
- ReAct pattern instructions (Think → Act → Observe → Repeat)
- Tool documentation for all 15 tools
- `<final_answer>` tag usage
- Error handling instructions

### Direct System Prompt (`SYSTEM_PROMPT`)

Used for direct chat (no tools). Simpler version without tool documentation.

### Prompt Assembly

```python
def build_system_prompt(context, memory, search_results, tools):
    prompt = TRINITY_SYSTEM_PROMPT

    if memory and memory.get('facts'):
        prompt += "\n## What You Know About This User\n"
        for fact in memory['facts']:
            prompt += f"- {fact['text']}\n"

    if context:
        prompt += "\n## Relevant Context\n"
        prompt += context

    if search_results:
        prompt += "\n## Search Results\n"
        prompt += search_results

    if tools:
        prompt += TOOL_PROMPT_SECTION      # 15 tool docs
        prompt += REACT_SYSTEM_PROMPT      # ReAct instructions

    return prompt
```

---

## Streaming Architecture

### Server-Side (Backend)

The backend uses Server-Sent Events (SSE) to stream responses in real-time:

```python
def generate():
    for event in pipeline.process_streaming(prompt, ...):
        yield f"data: {json.dumps(event)}\n\n"

    return Response(generate(), mimetype='text/event-stream')
```

### Event Types

| Event | Fields | When |
|-------|--------|------|
| Phase update | `{phase, message}` | Agent enters new phase (thinking, searching, etc.) |
| Token | `{token}` | Each generated text chunk |
| Tool result | `{phase: "tool_result", message}` | Tool execution completed |
| Done | `{done: true, response: {...}}` | Generation complete |
| Error | `{error: "..."}` | Something went wrong |

### Client-Side (Frontend)

The `streamSSE()` utility in `utils/sse.ts` parses the event stream:

```typescript
async function* streamSSE(response: Response, signal: AbortSignal): AsyncGenerator<SSEEvent> {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = JSON.parse(line.slice(6));
                yield data;
            }
        }
    }
}
```

### Cloudflare Worker Passthrough

The Cloudflare Worker detects SSE streams by path (`/generate/agent`, `/generate/stream`) and passes through the `text/event-stream` content type without buffering.

---

## Web Search Integration

**File:** `services/search.py`

When the prompt contains search-related keywords, the agent can trigger web searches:

### Brave Search API

```
search_web(query, count=5, timeout=10)
│
├── POST to https://api.search.brave.com/res/v1/web/search
│   Headers: X-Subscription-Token: BRAVE_SEARCH_API_KEY
│
├── Parse results: [SearchResult(title, url, snippet, source)]
│
└── Format for LLM context:
    "## Web Search Results for: '{query}'\n
     1. **Title** (url)\n   snippet\n
     2. ..."
```

### Fact Checking

```
fact_check(claim)
│
├── search_web(claim)               → supporting evidence
├── search_web("is it true " + claim) → verification evidence
│
└── Format both as structured evidence for the LLM to evaluate
```

---

## MCP Integration (Model Context Protocol)

Trinity implements both sides of the MCP standard:

### As an MCP Server

**File:** `services/mcp_server.py`

Exposes Trinity's 15 tools via the MCP JSON-RPC 2.0 protocol:
- HTTP endpoint: `POST /mcp`
- Stdio transport: `mcp_stdio_server.py` (for Claude Desktop)

### As an MCP Client

**File:** `services/mcp_client.py`

Can connect to external MCP servers to access their tools:
- Tools are prefixed with server name: `servername:toolname`
- Currently disabled (no external servers configured)

---

## Structured Output

**File:** `services/structured.py`

For cases where the LLM needs to produce valid JSON (not just freeform text), Trinity uses the Outlines library for constrained generation:

| Schema | Purpose |
|--------|---------|
| `understanding` | Structured problem understanding |
| `plan` | Step-by-step plan |
| `critique` | Self-assessment |
| `tool_call` | Structured tool invocation |

This ensures the output always conforms to the JSON schema, preventing parsing errors.

---

## Request Tracing

**File:** `services/tracing.py`

Every request through the agent pipeline is traced for debugging and quality monitoring:

### Trace Structure

```
RequestTrace:
├── request_id: unique identifier
├── started_at: timestamp
├── finished_at: timestamp
├── total_duration_ms: wall-clock time
├── classification: { tools_detected, direct_chat }
├── phases: [
│     PhaseTrace(name, duration_ms, tokens, model, result, error),
│     PhaseTrace(...),
│     ...
│   ]
└── quality_metrics: { error_rate, avg_duration, token_efficiency }
```

### Trace Store

A ring buffer holds the last 500 traces in memory:

| Method | Purpose |
|--------|---------|
| `get_recent(n)` | Last N traces |
| `get_trace(id)` | Specific trace by ID |
| `get_stats()` | Aggregate statistics |
| `get_quality_report()` | Self-assessment: error rates, slow responses, token efficiency |

---

## Performance Characteristics

| Metric | Typical Value | Notes |
|--------|--------------|-------|
| Direct chat latency | 2-15 seconds | Depends on response length |
| Tool detection | < 1 ms | Regex-based, no LLM call |
| ReAct single iteration | 3-10 seconds | One LLM call + one tool execution |
| Full ReAct loop | 5-60 seconds | Depends on number of iterations |
| Embedding computation | 10-50 ms | Per text, cached after first computation |
| Memory retrieval | 5-20 ms | Depends on vector store size |
| Cold start (first request) | 20-30 seconds | Model loading into GPU memory |

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `REACT_MAX_ITERATIONS` | 15 | Maximum Think→Act→Observe cycles |
| `REACT_TOKEN_BUDGET` | 48,000 | Total token budget per request |
| `REFLEXION_MAX_RETRIES` | 3 | Self-correction attempts on tool errors |
| `NUM_CTX` | 65,536 | Ollama context window size |
| `DEFAULT_MAX_TOKENS` | 8,000 | Max tokens per response |
| `CODE_EXECUTION_ENABLED` | `False` | Whether sandboxed code execution is active |
| `CODE_EXECUTION_TIMEOUT` | 5 seconds | Python sandbox timeout |
| `MAX_DOCUMENT_CONTEXT_CHARS` | 60,000 | Max document context in prompt |
| `WORKSPACE_ROOT` | `/workspace` | Filesystem sandbox root |

---

## Key Files

| File | Role |
|------|------|
| `services/agent.py` | `AgentPipeline` — main orchestrator, `OllamaClient` |
| `services/agent_prompts.py` | System prompts + tool documentation |
| `services/react_loop.py` | `ReactLoop` — iterative tool calling + Reflexion |
| `services/tools.py` | Tool definitions, parsing, detection |
| `services/code_executor.py` | Tool dispatch + sandboxed execution |
| `services/search.py` | Brave Search API integration |
| `services/fact_check.py` | Dual-search fact verification |
| `services/structured.py` | Constrained JSON generation |
| `services/tracing.py` | Request tracing + quality reports |
| `services/loading_messages.py` | Phase-aware loading messages |
| `routes/generate.py` | `/generate` and `/generate/agent` endpoints |
