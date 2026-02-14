# Trinity Post-Overhaul — Senior QA Handoff

**Date:** February 13, 2026
**Prepared by:** Automated code audit
**Scope:** INTELLIGENCE-OVERHAUL (Phases 0-5) + FRONTEND-OVERHAUL (Phases A-E)
**System:** React 19 frontend on ICP → Cloudflare Worker → Flask backend on Akash with Ollama (qwen2.5-coder:32b)

---

## Executive Summary

Two major engineering proposals were executed back-to-back in a single sprint:

1. **INTELLIGENCE-OVERHAUL** — Gutted the backend pipeline: deleted ~2,700 lines (multi-pass, LangGraph, voting, complexity classifier), replaced with single-pass ReAct, fixed memory bugs, upgraded model from qwen3:8b to qwen2.5-coder:32b, added filesystem/code-execution tools, expanded context window 6→20.

2. **FRONTEND-OVERHAUL** — Replaced entire vanilla JavaScript frontend (~9,700 lines) with React 19 + TypeScript (~5,200 lines). New rendering pipeline, SSE streaming, CSS modules, 137 unit tests. Deployed to ICP asset canister.

Both proposals claim "COMPLETE." This audit found **4 confirmed bugs**, **3 latent risks**, and **2 integration gaps** that require verification before confidence is warranted.

---

## Severity Classification

- **P0-BLOCKER**: Feature will not work at all. User-visible failure on first use.
- **P1-HIGH**: Feature degrades or fails under specific conditions.
- **P2-MEDIUM**: Incorrect behavior but doesn't block primary use.
- **P3-LOW**: Cosmetic, cleanup, or future risk.

---

## Section 1: Confirmed Bugs

### BUG-1: Autosave sends wrong field name (P0-BLOCKER)

| Detail | |
|---|---|
| **Location** | [useAutosave.ts line 45](trinity-icp/src-react/hooks/useAutosave.ts#L45) |
| **What happens** | Frontend sends `chat_id` (snake_case) |
| **What backend expects** | `chatId` (camelCase) — [chat.py line 114](backend/routes/chat.py#L114) |
| **Impact** | Every autosave request returns 400 "Missing chatId". **No chats are saved to the cloud.** Users lose all conversations on page refresh. |
| **Evidence** | Backend: `chat_id = data.get("chatId")` — no fallback to `chat_id` |
| **Verification** | Open app → authenticate → send message → wait 2s → check network tab for 400 on `/chat/autosave` |
| **Fix** | Change `chat_id` to `chatId` in useAutosave.ts line 45 |

### BUG-2: User memory renders as raw dict in non-tool prompts (P1-HIGH)

| Detail | |
|---|---|
| **Location** | [agent_prompts.py line 212](backend/services/agent_prompts.py#L212) |
| **What happens** | `build_system_prompt()` does `f"- {fact}"` on raw fact objects |
| **What should happen** | Facts should be formatted like `_format_user_memory()` in [agent.py line 56](backend/services/agent.py#L56) |
| **Impact** | When no tools are needed (direct generation path, line 464 of agent.py), user memory facts render as `- {'text': 'User likes Python', 'embedding': [0.123, 0.456, ...], 'category': 'preferences'}` — polluting the model's context with 384-float arrays. This is **the same bug as B1** from the INTELLIGENCE-OVERHAUL, partially fixed in agent.py but not in agent_prompts.py. |
| **Evidence** | agent.py line 453 calls `_format_user_memory(user_memory)` for ReAct path, but line 464 passes raw `user_memory` dict to `build_system_prompt()` which does the naive formatting |
| **Verification** | Save a memory fact → send a simple non-tool query → inspect backend logs for system prompt content |
| **Fix** | Either: (a) call `_format_user_memory()` before passing to `build_system_prompt()`, or (b) make `build_system_prompt()` use the same dict-safe formatting |

### BUG-3: Only user messages are semantically indexed (P2-MEDIUM)

| Detail | |
|---|---|
| **Location** | [generate.py line 301](backend/routes/generate.py#L301) |
| **What happens** | `sem_memory.index_message(chat_id, idx, "user", user_prompt)` — only the user's prompt is indexed |
| **What should happen** | Both user message AND assistant response should be indexed for semantic retrieval |
| **Impact** | Cross-chat semantic search only finds user questions, not assistant answers. If you ask "What did we discuss about Python?" and the assistant gave a thorough answer about Python in a prior chat, the semantic search won't find it because only "tell me about Python decorators" (the user question) was indexed. ~50% of conversation content is invisible to semantic memory. |
| **Verification** | Chat A: ask about topic X, get detailed response → Chat B: ask "What did we discuss about X?" → check if semantic context includes the assistant's response |

### BUG-4: Stale LangGraph references in observability (P3-LOW)

| Detail | |
|---|---|
| **Location** | [observability.py line 354](backend/middleware/observability.py#L354) |
| **What happens** | Prometheus metric `PARALLEL_EXECUTIONS` still has `langgraph` as a label value. 5 test assertions in test_observability.py reference `"langgraph"` routing. |
| **Impact** | Dead metric labels consume cardinality. Test assertions validate a pipeline that no longer exists — if labels are ever cleaned, tests will fail. |
| **Verification** | `grep -rn "langgraph" backend/ --include="*.py"` — should be 0 matches but returns ~6 |

---

## Section 2: Integration Gaps (Untested Paths)

### GAP-1: Frontend ↔ Backend have NEVER been tested together post-overhaul

**This is the most critical finding.** Both overhauls were developed and tested in isolation:

- Backend: tested via pytest (unit tests with mocks, no real Ollama)
- Frontend: tested via vitest (unit tests with mocked fetch, no real backend)
- The Akash backend has been offline during the entire frontend overhaul
- The ICP deploy was verified to load the auth screen, but no message was sent

**No integration test has occurred.** The first real test will be when the Akash backend boots.

### GAP-2: Continuation flow may produce incoherent results

[useChat.ts lines 170-235](trinity-icp/src-react/hooks/useChat.ts#L170-L235) handles `done_reason === 'length'` by sending a new `/generate/agent` request with `"Continue from where you left off..."`. This sends the truncation context as a new user prompt, which means:
- The model processes it as a fresh request, not a continuation
- The system prompt is regenerated (including tool injection logic)
- The model may not seamlessly continue — it may introduce new introductions or repeat content

The old vanilla JS had the same behavior, so this is **not a regression**, but it's worth noting that "continue" is a prompt hack, not a real continuation protocol.

---

## Section 3: Latent Risks

### RISK-1: Context window discrepancy between prompt builder and hook

The React frontend sends up to 20 context messages (CONTEXT_WINDOW_SIZE = 20 in [store/index.ts line 30](trinity-icp/src-react/store/index.ts#L30)), but `build_system_prompt()` in [agent_prompts.py line 203](backend/services/agent_prompts.py#L203) truncates to `context_messages[-6:]`. This means:

- Frontend dutifully sends 20 messages
- `build_system_prompt()` silently discards 14 of them
- Only the last 6 messages appear in the system prompt for the **non-tool path**
- The ReAct path (tool-using queries) may handle this differently

**Impact**: The "CONTEXT_WINDOW_SIZE = 20" fix from Phase 3 may only be effective when tools are triggered. Simple Q&A conversations may still have a 6-message effective window.

**Verification**: Send 10 messages in a conversation, reference something from message #1 in message #10 (without triggering tools). Does the model remember?

### RISK-2: Code execution is disabled by default

`CODE_EXECUTION_ENABLED` defaults to `false` in [config.py](backend/config.py). The Phase 5 agentic tools (run_command, code execution with Reflexion) exist in code but won't execute in production unless the env var is explicitly set to `true` in the Akash deployment YAML.

**Verification**: Check `deploy/akash/*.yml` for `CODE_EXECUTION_ENABLED=true`. If absent, Phase 5's code execution is dead.

### RISK-3: The old vanilla frontend is still deployable but out of sync

The vanilla JS code in `trinity-icp/src/` still exists. If someone runs the old `build:legacy` command or reverts, the vanilla frontend would deploy — but it has NOT been updated for the post-intelligence-overhaul API contract. It still references:
- `CONTEXT_WINDOW_SIZE = 6`
- Old SSE event handling
- Dead code paths (generateSimple, etc.)

The rollback plan ("git checkout + dfx deploy") would restore the vanilla JS which is incompatible with the overhauled backend.

---

## Section 4: Verification Matrix

### Tier 1: Must-Pass (Block release if any fail)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| T1 | Health check | `curl https://api.dubya.ai/health` | 200 OK, `"model": "qwen2.5-coder:32b"` | UNTESTED |
| T2 | Auth flow | Open dubya.ai → Create new identity | Principal ID displayed, keys in localStorage | UNTESTED |
| T3 | Send message | Authenticate → type "Hello" → send | Tokens stream in, response completes | UNTESTED |
| T4 | Autosave fires | Send message → wait 3s → check network | POST /chat/autosave returns 200 (**EXPECTED TO FAIL — BUG-1**) | UNTESTED |
| T5 | Chat list loads | Sidebar → check if chats appear | Previously saved chats listed | UNTESTED |
| T6 | Load saved chat | Click a chat in sidebar | Messages render with markdown/code/math | UNTESTED |
| T7 | Code block renders | Ask "Write a Python hello world" | Syntax-highlighted code block with copy button | UNTESTED |
| T8 | Math renders  | Ask "What is the quadratic formula?" | KaTeX-rendered math (not raw LaTeX) | UNTESTED |
| T9 | Tool use works | Ask "What is 42 * 17?" | Calculator tool invoked, returns 714 | UNTESTED |
| T10 | Stop button | During streaming → click stop | Stream aborts cleanly, partial response visible | UNTESTED |

### Tier 2: Should-Pass (Degraded but not blocked)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| T11 | User memory save | "Remember that I like Rust" | Memory saved confirmation | UNTESTED |
| T12 | User memory recall | New chat → "What language do I like?" | "Rust" mentioned | UNTESTED |
| T13 | Context window | 15-msg conversation, reference msg #1 at msg #15 | Model recalls early context | UNTESTED |
| T14 | Continue button | Ask for very long response → truncation | "Continue" button appears, continuation works | UNTESTED |
| T15 | Edit and regenerate | Click edit on sent message → modify → re-send | History truncated, new response generated | UNTESTED |
| T16 | File tools | "List the files in /workspace" | Directory listing returned | UNTESTED |
| T17 | Delete chat | Sidebar → delete a chat → confirm | Chat removed from list | UNTESTED |
| T18 | Key export | Auth menu → export key → QR code | QR code displayed with private key | UNTESTED |
| T19 | Key import | Import key from QR/text → authenticate | Same principal restored | UNTESTED |
| T20 | Sidebar collapse | Click hamburger → sidebar collapses | Chat area expands, sidebar hides | UNTESTED |

### Tier 3: Edge Cases

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| T21 | Network error | Kill backend → send message | Error toast, not crash | UNTESTED |
| T22 | Double-send prevention | Click send rapidly | Only one request fires | UNTESTED |
| T23 | Long message | Paste 5,000 chars → send | Accepted (under 50k limit) | UNTESTED |
| T24 | Overlimit message | Paste 51,000 chars → send | Rejected with error | UNTESTED |
| T25 | Page refresh mid-stream | Streaming → refresh page | Stream lost, no crash on reload | UNTESTED |
| T26 | Multiple tabs | Open 2 tabs with same identity | Both work independently | UNTESTED |
| T27 | Cold start | First request after Akash deploy | Responds within 60s (model loading) | UNTESTED |
| T28 | Mobile viewport | Open on mobile browser | Responsive layout, input usable | UNTESTED |
| T29 | Security headers | `curl -I https://dubya.ai/` | CSP, X-Content-Type-Options, Referrer-Policy present | VERIFIED |
| T30 | Asset caching | `curl -I .../assets/main-*.js` | `cache-control: public, max-age=31536000, immutable` | VERIFIED |

---

## Section 5: What Both Proposals Claim vs. Reality

### INTELLIGENCE-OVERHAUL

| Phase | Claim | Verdict | Evidence |
|---|---|---|---|
| 0 | Frontend stabilized | **SUPERSEDED** | React migration replaced vanilla JS entirely |
| 1 | ~2,000 lines dead code removed | **PARTIALLY VERIFIED** | Files deleted, but stale langgraph labels in observability (BUG-4) |
| 2 | Single-pass + ReAct | **VERIFIED** | No multi-pass code remains. agent.py is 525 lines, 3 prompt templates |
| 3 | All memory bugs fixed | **PARTIALLY VERIFIED** | B1 fixed in agent.py but NOT in agent_prompts.py (BUG-2). B5 context window = 20 but silently truncated to 6 in prompt builder (RISK-1). B2 only indexes user messages (BUG-3) |
| 4 | qwen2.5-coder:32b | **VERIFIED** | config.py, Dockerfile, Akash YAML all reference qwen2.5-coder:32b |
| 5 | Filesystem tools, code execution, repo map | **VERIFIED** | All files exist. Code execution disabled by default (RISK-2) |

### FRONTEND-OVERHAUL

| Phase | Claim | Verdict | Evidence |
|---|---|---|---|
| A | Foundation — types, store, hooks, ESLint | **VERIFIED** | 62 source files, tsc clean, ESLint clean |
| B | Rendering pipeline — single MarkdownRenderer | **VERIFIED** | One pipeline, code blocks, math, streaming all working in unit tests |
| C | Feature parity — sidebar, modals, autosave, etc. | **PARTIALLY VERIFIED** | All components exist, but autosave has BUG-1 (wrong field name) |
| D | Testing + hardening — 137 tests, security audit | **VERIFIED** | 137/137 tests pass, ESLint clean, security findings addressed |
| E | Deployed to ICP production | **VERIFIED** | Live at dubya.ai, HTTP 200, security headers confirmed |

---

## Section 6: Action Items for QA

### Immediate (Before declaring "it works")

1. **Fix BUG-1** (autosave chat_id → chatId) — this is a showstopper
2. **Run Tier 1 tests** (T1-T10) once Akash backend is up
3. **Verify BUG-2** — check if user memory renders as dicts in non-tool prompts
4. **Verify RISK-1** — test if context window is truly 20 or silently 6 for simple queries

### Short-term (Within 1-2 days)

5. Run Tier 2 tests (T11-T20)
6. Fix BUG-2 (dual formatting path in agent_prompts.py)
7. Verify CODE_EXECUTION_ENABLED is set in Akash deployment
8. Clean up BUG-4 (stale langgraph labels)

### Medium-term (Within 1 week)

9. Run Tier 3 edge case tests (T21-T30)
10. Fix BUG-3 (index assistant responses too)
11. Fix RISK-1 (remove the `[-6:]` truncation in `build_system_prompt()`)
12. Consider whether the vanilla JS in `src/` should be archived to a branch

### Deferred (Tracked but not blocking)

13. Playwright e2e tests (noted as deferred in both proposals)
14. Accessibility audit  
15. Model selection UI
16. Rollback plan needs updating — vanilla JS is no longer compatible with overhauled backend

---

## Section 7: Architecture Quick Reference

```
User Browser (dubya.ai)
  │
  ├── React 19 + TypeScript (ICP asset canister zc67k-kiaaa-aaaal-qtmiq-cai)
  │     ├── Auth: Ed25519 keys in localStorage (icp-auth.js bundle)
  │     ├── State: Zustand store (CONTEXT_WINDOW_SIZE=20)
  │     ├── Storage: IndexedDB (local-first) + autosave to Akash
  │     └── Streaming: SSE via fetch + AbortController
  │
  ├── HTTPS
  │
  ├── Cloudflare Worker (SSL termination + proxy)
  │
  ├── HTTPS
  │
  └── Akash Backend (Flask + Ollama)
        ├── /health — no auth
        ├── /generate/agent — SSE streaming, single-pass or ReAct
        ├── /chat/autosave — Ed25519 auth required
        ├── /chat/list — Ed25519 auth required
        ├── /chat/<id> — Ed25519 auth required
        ├── /user/memory — Ed25519 auth required
        ├── Model: qwen2.5-coder:32b (Q4_K_M, ~20GB VRAM)
        ├── Tools: calculator, web_search, save/recall/search_memory,
        │          read_file, write_file, list_directory, search_codebase, run_command
        └── Storage: encrypted JSON on disk + Lighthouse IPFS backup
```

---

## Appendix: Files Changed in This Overhaul

### Backend (INTELLIGENCE-OVERHAUL)

- **Deleted**: services/graph/ (7 files), services/parallel.py, services/experiments.py, services/voting.py, services/complexity.py, middleware/ab_test.py
- **Major rewrites**: services/agent.py (single-pass), services/agent_prompts.py (3 prompts), routes/generate.py (2 routes)
- **New**: services/repo_map.py, services/code_executor.py (expanded)
- **Production Python**: ~12,900 lines  |  **Test Python**: ~9,300 lines

### Frontend (FRONTEND-OVERHAUL)

- **New directory**: trinity-icp/src-react/ (62 files)
- **Old directory**: trinity-icp/src/ (still exists, no longer deployed)
- **Production TS/TSX/CSS**: ~5,200 lines  |  **Test TS**: ~1,700 lines  |  **Tests**: 137 across 11 files
- **Build**: 473KB gzip JS + 8KB gzip CSS + 303KB icp-auth.js + 60 KaTeX fonts = 67 files

---

*This document should be reviewed alongside the actual test execution. No integration test has been performed — all findings above are from static code analysis only.*
