# Handoff: Memory Research Fork — Fixing Trinity's Broken Tools & Internet Access

**Date:** February 17, 2026  
**Context:** Analysis of live user conversation with Trinity revealing critical gaps  
**Priority:** P0 — Core features (web search, file upload) are non-functional  
**Branch:** Fork from `main` at commit `8363fe0`

---

## The Problem (User Conversation Analysis)

A real conversation between a user and Trinity (attached: `chat between trinity and me.md`) reveals **five critical failures**:

### Failure 1: Trinity Claims It Can't Search the Internet
**User says:** "search the internet to find out. utilize all tools"  
**Trinity says:** "I cannot search the internet in real time because I don't have access to live data"

**Root cause:** Multi-layered.
1. **Tool detection regex gap.** The `detect_tools_needed()` function in `backend/services/tools.py` (line 360+) uses pattern-matching for search triggers like `current price`, `latest news`, `right now`. But the phrase **"search the internet"** matches NONE of these patterns. The user explicitly asked Trinity to search, and the heuristic missed it entirely.
2. **Model doesn't know it has tools.** When tool detection fails, the query goes to the *direct chat* path (no ReAct loop). The direct chat system prompt does NOT include tool documentation, so the model responds as a generic LLM: "I can't access the internet."
3. **The live deployment is running `qwen3:8b` (TEST tier),** not `qwen3:32b` (production). The 8B model is weaker at following tool-calling instructions even when tools are detected.

### Failure 2: Hallucinated Bitcoin Price
**User says:** "what is the price of bitcoin right now?"  
**Trinity says:** "$68,870.66" (a training-data hallucination from ~Oct 2023)

**Root cause:** Despite this query matching search patterns (`price of`, `bitcoin`, `right now`), the tool detection likely fired BUT the 8B model ignored the tool documentation and answered from training data instead of calling `web_search`. The search WAS available (confirmed: `web_search: true` in `/health` response, Brave API key is deployed and 31 chars long).

### Failure 3: Wrong Date
**User says:** "what day is it?"  
**Trinity says:** "October 25, 2023"

**Root cause:** No `current_date` tool exists. The model hallucinates from training data. This is a **missing tool** — Trinity has no way to know the current date/time.

### Failure 4: Duplicate Response
**Two different user messages returned:** "Yo, what's up? You good?"

**Root cause:** Likely the model generating the same low-effort response for casual messages, or possibly a caching issue with semantic response cache (cosine similarity >0.95 threshold treating different casual messages as identical).

### Failure 5: File Upload Doesn't Work
**User reports (out-of-band):** Upload files doesn't work.

**Root cause:** The frontend has an "Attach file" button that reads the file as text and **inlines it into the prompt** as `[Attached file: name]\n\n{content}\n\n{message}`. It does NOT call the backend's `/tools/documents/upload` API endpoint. This means:
- Large files blow past prompt limits (100K chars max)
- Binary files (PDF, images) fail silently — `file.text()` returns garbage
- The `document_search` tool can't query uploaded files because nothing is in the `document_store`
- The backend document upload/query infrastructure exists but is completely disconnected from the frontend

---

## Current System State

| Component | Status | Evidence |
|-----------|--------|----------|
| Brave Search API Key | ✅ Deployed (31 chars) | `.env` has key, `/health` shows `web_search: true` |
| Web search backend code | ✅ Working | `search.py` uses Brave API, returns results |
| Tool detection for "search" | ❌ Gaps | Explicit "search the internet" not matched |
| Tool detection for "bitcoin price" | ✅ Should match | `price of`, `bitcoin`, `right now` patterns exist |
| ReAct loop | ✅ Code works | Verified with smoke tests (5/5 pass on 32B model) |
| Direct chat path | ⚠️ No tool awareness | System prompt doesn't mention tools when `tools_needed=False` |
| Model (production) | ❌ Wrong model deployed | Health shows `qwen3:8b`, should be `qwen3:32b` |
| File upload frontend | ❌ Not wired to backend API | Inlines text into prompt instead |
| File upload backend | ✅ API exists | `/tools/documents/upload` endpoint works |
| Document query backend | ✅ API exists | `/tools/documents/query` endpoint works |
| Current date/time tool | ❌ Missing | No tool provides real-time date |

---

## Quickest Fixes (Ranked by Impact ÷ Effort)

### Fix 1: Deploy Production Model (5 minutes) — **HIGHEST IMPACT**
The live deployment is running `qwen3:8b` (TEST tier), not `qwen3:32b`. The 8B model is too small to reliably follow tool-calling instructions. 

```bash
./scripts/trinity-deploy-production.sh production
```

This single fix would likely resolve Failures 1, 2, and 4 because the 32B model follows tool instructions much better. **No code changes needed.**

### Fix 2: Expand Tool Detection Patterns (15 minutes)
Add explicit "search" verb patterns to `detect_tools_needed()` in `backend/services/tools.py`:

```python
# Add to search_patterns list (~line 360):
r"\bsearch\b.*(internet|web|online|for)",  # "search the internet"
r"(look|search)\s+(it\s+)?(up|for)",        # "look it up", "search for"
r"(find|get)\s+(me\s+)?(info|information|data|details)\s+(on|about)",
r"(google|bing|browse)\b",                  # explicit search engine refs
r"what('?s| is) the (current|latest|today)",  # "what's the current..."
```

### Fix 3: Add `current_datetime` Tool (30 minutes)
Add a new tool that returns the current date/time:

**In `tools.py` TOOL_DEFINITIONS:**
```python
"current_datetime": {
    "description": "Get the current date and time. Use when the user asks what day/time it is.",
    "parameters": {},
    "examples": ['<tool_call name="current_datetime"></tool_call>'],
}
```

**In `code_executor.py` execute_tool():**
```python
elif tool_name == "current_datetime":
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return True, f"Current date/time: {now.strftime('%A, %B %d, %Y at %H:%M:%S UTC')}"
```

**In `tools.py` detect_tools_needed():**
```python
datetime_patterns = [
    r"what (day|date|time) is it",
    r"what('?s| is) today",
    r"current (date|time|day)",
    r"today'?s date",
]
```

### Fix 4: Wire Up File Upload Frontend → Backend (2-4 hours)
Replace the inline-text approach with actual API upload:

1. **In `AppShell.tsx` `handleSend()`:**
   - If attachment exists, POST to `/tools/documents/upload` with base64 content
   - Store the returned `session_id` 
   - Pass `session_id` in the `/generate/agent` request so the ReAct loop can query it via `document_search`

2. **In `MessageInput.tsx`:**
   - Support PDF/docx (extract text via a library or send raw and let backend parse)
   - Show upload progress indicator
   - Validate supported file types

3. **Backend already supports this** — the `/tools/documents/upload` and `/tools/documents/query` endpoints work. The `document_search` tool in the ReAct loop will query the `document_store` if a session_id is available.

### Fix 5: Add Search Fallback in Direct Chat Path (30 minutes)
When `tools_needed=False` but the direct chat path detects search keywords, it already does a background search. However, the keyword list is too narrow:

```python
# In agent.py ~line 623, expand search_keywords:
search_keywords = [
    "latest", "current", "today", "news", "price", "weather",
    "recent", "update", "2024", "2025", "2026", "who won", "score",
    "search", "look up", "find out", "what day", "what time",  # ADD THESE
    "right now", "happening", "bitcoin", "stock", "crypto",     # ADD THESE
]
```

---

## API Keys & Memberships Needed

| Service | Status | Cost | How to Get |
|---------|--------|------|------------|
| **Brave Search API** | ✅ Already have key | Free tier: 2,000 queries/mo. Pro: $5/mo (unlimited) | [brave.com/search/api](https://brave.com/search/api/) |
| **Lighthouse (IPFS)** | ✅ Already have key | Free tier: 1GB. Paid: $0.001/MB | [lighthouse.storage](https://www.lighthouse.storage/) |
| **OpenAI API** (optional) | ❌ Not needed | N/A | Trinity uses self-hosted Ollama |
| **Google Search API** (alternative) | ❌ Not configured | $5/1000 queries | [programmablesearchengine.google.com](https://programmablesearchengine.google.com/) |

**Bottom line:** No new API keys or memberships are needed. The Brave Search key is already deployed and working. The issue is that the code doesn't route queries to it properly.

---

## Deployment Architecture Issue

The current live deployment is running the **wrong tier:**

| Expected | Actual |
|----------|--------|
| `qwen3:32b` (production) | `qwen3:8b` (test) |
| `trinity-production-qwen3-32b` | `trinity-test-qwen3-8b` |
| GPU: A100/A6000/RTX4090 | Unknown (likely smaller GPU) |

This was likely caused by deploying the test tier for smoke-testing and never switching back to production, or the production deployment (DSEQ 25567678 on RTX 4090) was closed and replaced with a test deployment.

**Fix:** Redeploy production tier:
```bash
./scripts/trinity-deploy-production.sh production
```

---

## Recommended Fix Order

| # | Fix | Time | Impact | Dependencies |
|---|-----|------|--------|--------------|
| 1 | Redeploy production model (32B) | 5 min | **Critical** | Akash wallet funded |
| 2 | Expand tool detection patterns | 15 min | **High** | None |
| 3 | Add `current_datetime` tool | 30 min | **Medium** | Docker rebuild + redeploy |
| 4 | Expand direct-chat search keywords | 30 min | **Medium** | Docker rebuild + redeploy |
| 5 | Wire up file upload frontend→backend | 2-4 hrs | **High** | Frontend + backend changes |

Fixes 2-4 can be combined into a single Docker build + deploy cycle.

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/services/tools.py` | Add search patterns, add `current_datetime` tool definition |
| `backend/services/code_executor.py` | Add `current_datetime` execution handler |
| `backend/services/agent.py` | Expand direct-chat search keywords |
| `trinity-icp/src-react/components/layout/AppShell.tsx` | Wire file upload to `/tools/documents/upload` API |
| `trinity-icp/src-react/components/chat/MessageInput.tsx` | Add PDF/docx support, upload progress |
| `deploy/akash/deploy-production.yaml` | Verify correct image tag for production |

---

## Test Plan

After fixes, re-run the conversation from the attached chat to verify:

1. **"search the internet to find out"** → Trinity should call `web_search` tool via ReAct loop
2. **"what is the price of bitcoin right now?"** → Trinity should call `web_search`, return real current price
3. **"what day is it?"** → Trinity should call `current_datetime` tool, return real date
4. **"what up!"** / casual messages → Should get unique, contextual responses (no duplicates)
5. **File attachment** → Should upload via API, queryable via `document_search` tool

Additionally, run existing test suites:
```bash
cd backend && python -m pytest tests/ -x -q                    # 976 unit tests
python scripts/smoke_test.py https://api.dubya.ai               # 5 smoke tests
python scripts/live_integration_test.py https://api.dubya.ai    # 25 integration tests
```

---

## Memory Research Fork Specific Notes

This fork should focus on investigating:

1. **Why the model "forgets" it has tools** — Even with tool documentation in the system prompt, the 8B model ignores it. Is this a prompt engineering issue, a model capability issue, or both?

2. **Semantic response cache interference** — The duplicate "Yo, what's up?" response may indicate the semantic cache (cosine similarity >0.95) is too aggressive for short casual messages. All short greetings embed similarly.

3. **Context window utilization** — With `NUM_CTX=65536` and `MAX_TOKENS=16384`, is the model actually using the full context? The conversation shows Trinity "forgetting" earlier statements within the same chat.

4. **Tool-calling reliability by model size** — Comparative analysis: how reliably do 8B vs 32B models follow XML tool-calling instructions? What's the minimum model size for reliable ReAct execution?

5. **Memory persistence across conversations** — The user memory system (MemGPT tools) exists but wasn't triggered in this conversation. How often does auto-extraction actually fire? Are facts being saved and recalled across sessions?
