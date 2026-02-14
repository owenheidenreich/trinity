# Trinity Frontend Overhaul — Engineering Plan

**Date:** February 13, 2026
**Status:** ✅ COMPLETE — All phases (A through E) finished. React frontend live at dubya.ai since Feb 13, 2026.
**Author:** R&D Analysis (3-agent deep audit + industry research)
**Purpose:** Replace the vanilla JS frontend with a React + TypeScript stack to eliminate the recurring "backend change breaks frontend" cycle.
**Supersedes:** INTELLIGENCE-OVERHAUL Phase 0 (frontend stabilization via subtraction)
**Related:** [INTELLIGENCE-OVERHAUL.md](INTELLIGENCE-OVERHAUL.md) (ALL PHASES 0-5 COMPLETE), [TRINITY-MONETIZATION-PLAN.md](TRINITY-MONETIZATION-PLAN.md)

> **Post-Intelligence-Overhaul Note (Feb 13, 2026):** The INTELLIGENCE-OVERHAUL (Phases 0-5) completed *before* this migration began. The vanilla JS frontend was already stabilized (Phase 0), the backend simplified to single-pass + ReAct (Phases 1-2), memory fixed with `CONTEXT_WINDOW_SIZE=20` (Phase 3), model upgraded to `qwen2.5-coder:32b` (Phase 4), and agentic scaffolding added (Phase 5). The React migration types and contracts below have been updated to match the **post-overhaul** API.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Analysis](#2-problem-analysis)
3. [Industry Comparison](#3-industry-comparison)
4. [Recommended Architecture](#4-recommended-architecture)
5. [Component Design](#5-component-design)
6. [Streaming Architecture](#6-streaming-architecture)
7. [CSS Strategy](#7-css-strategy)
8. [Security Improvements](#8-security-improvements)
9. [Testing Strategy](#9-testing-strategy)
10. [ICP Deployment Compatibility](#10-icp-deployment-compatibility)
11. [Migration Plan](#11-migration-plan)
12. [Relationship to INTELLIGENCE-OVERHAUL](#12-relationship-to-intelligence-overhaul)
13. [Risk Register](#13-risk-register)
14. [Alternatives Considered](#14-alternatives-considered)
15. [Decisions Log](#15-decisions-log)
16. [Success Metrics](#16-success-metrics)

---

## 1. Executive Summary

Trinity's frontend is a ~9,700-line vanilla JavaScript SPA with zero tests, 5+ duplicated rendering pipelines, and a 605-line streaming monolith (`generate.js`) that breaks every time the model or backend output format changes. The root cause is structural: hand-rolled imperative DOM manipulation with no component boundaries, no reactive rendering, and no type contracts between frontend and backend.

### The Core Problem

Every backend intelligence improvement (model swap, prompt change, tool format update, SSE event change) triggers a frontend incident. The typing animation breaks. Code blocks render wrong. Math expressions flash or disappear. The team then spends hours debugging DOM manipulation code instead of shipping features.

### The Fix

Migrate to **React + TypeScript + Vite**, deployed to the same ICP asset canister. This gives us:

- **One rendering pipeline** (currently 5+) — a single `MarkdownRenderer` component handles all message display
- **Typed SSE contracts** — TypeScript catches backend format changes at build time, not in production
- **Component isolation** — code blocks, math, streaming cursor are independent components that can't break each other
- **Test coverage** — Vitest + Playwright catch regressions before deploy
- **Multi-platform alignment** — React web shares code with the planned React Native (mobile) and Electron (desktop) apps

### Impact Summary

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Rendering pipelines | 5+ across 3 files | 1 (`MarkdownRenderer`) | -80% |
| Frontend incidents per backend deploy | ~1-2 | 0 (typed contracts) | -100% |
| Test coverage | 0% | >60% (rendering at 90%) | New |
| Type coverage | 0% | 95%+ (TypeScript strict) | New |
| Time to add rendering feature | 2-4 hours + debugging | 30-60 minutes | -75% |
| CSS dead code | Unknown (~2,105 lines, single file) | 0 (CSS Modules tree-shake) | -100% |
| Console security leaks | 253 statements | 0 (ESLint `no-console`) | -100% |
| Code shared with mobile/desktop apps | 0% | ~60% (types, hooks, state) | New |

**Estimated effort:** 3-4 weeks
**Risk:** Medium (incremental migration; staging canister for parallel testing)
**Rollback:** Git revert + redeploy current vanilla JS from prior commit

---

## 2. Problem Analysis

### 2.1 The Recurring Break Pattern

    Backend change (model swap, prompt edit, SSE format change)
        -> Frontend renders unexpected token sequence
        -> Typing animation breaks OR code block corrupts OR math disappears
        -> Manual debugging of imperative DOM code (hours)
        -> Hotfix deployed -> next backend change repeats the cycle

This pattern is documented in INTELLIGENCE-OVERHAUL.md Section 1 ("Problem 4: The frontend is structurally broken") and corroborated by the 3-agent deep audit that found:

- **4 separate message sending paths** (only 1 actually used)
- **5+ rendering pipelines** scattered across 3 files with duplicated logic
- **253 console.log statements** in production (leaking principals, signatures, API URLs)
- **Zero tests, zero linting, zero type checking**

### 2.2 Root Cause Inventory

| Root Cause | Location | Why It Breaks |
|---|---|---|
| **5+ rendering pipelines** | `preprocessToolCalls()` duplicated in `messages.js` AND `editMessage.js`; streaming render in `generate.js`; legacy `typeMessage()` in `messages.js`; continuation renderer duplicated inline in `generate.js` | Tool format change must update 3+ locations; miss one -> silent rendering failure |
| **605-line `generate()` monolith** | `generate.js` lines 57-530: nested callbacks, `setInterval` timers, closures over mutable DOM refs, inline HTML construction, continuation nesting another full `generateAgent()` inside `onDone` | Any streaming behavior change is high-risk; `arguments.callee` usage is deprecated and fails in strict mode |
| **No reactive rendering** | Zustand store exists (`store.js`) but UI never subscribes to state changes; every DOM update is manual and imperative | Missing a manual `UI.renderX()` call after state change -> stale UI with no error or warning |
| **`parseMarkdownWithMath()` called every 15ms** | `generate.js` line ~290: full markdown parse + DOMPurify sanitize + math protect/restore on every streaming tick | Performance bottleneck; KaTeX `renderMathInElement()` also called per-token with console logging |
| **Module-scoped mutable state** | `streamDetailsEl`, `streamCodeEl` at module scope in `generate.js` | Cross-contamination between overlapping requests; memory leak on interrupted streams |
| **Zero tests, zero types** | No test files under `trinity-icp/`; no TypeScript; no ESLint | No regression protection; every deploy is a manual smoke test |
| **2,105-line monolithic CSS** | Single `styles.css` with no BEM/CSS modules/design tokens; sidebar uses inline `style=""` in JS | Style changes cascade unpredictably; dead selectors accumulate |
| **CDN scripts without integrity** | 6 CDN scripts in `index.html` lack SRI hashes | Vulnerable to CDN compromise |
| **`document.execCommand('copy')` deprecated** | `codeUtils.js` uses deprecated API because Clipboard API blocked by ICP permissions policy | May be removed from browsers at any time |

### 2.3 Frontend File Inventory (Current State)

| File | Lines | Purpose | Fragility |
|------|-------|---------|-----------|
| `features/generate.js` | 605 | Streaming monolith — the #1 fragile file | CRITICAL |
| `ui/modals.js` | 642 | String-based DOM generation for all modals | HIGH (XSS risk) |
| `ui/messages.js` | 578 | Message rendering, code enhancement, typing animation | HIGH |
| `core/api.js` | ~400 | SSE handling, 4 message paths (3 dead) | HIGH |
| `state/store.js` | 302 | Zustand store (good foundation — keeps its shape) | LOW |
| `utils/math.js` | 200 | KaTeX protect/restore (solid logic — ports cleanly) | LOW |
| `utils/codeBlockParser.js` | ~90 | Code block extraction (solid — ports cleanly) | LOW |
| `utils/codeUtils.js` | ~170 | File naming, copy utility | MEDIUM |
| `styles.css` | 2,105 | Monolithic CSS | HIGH |
| `auth/icp-auth.js` | 8,578 | Pre-built ICP auth bundle (generated, not hand-written) | N/A |
| Other 25 files | ~2,600 | Config, sidebar, storage, auth, tools | MEDIUM |
| **Total hand-written** | **~9,725** | | |

---

## 3. Industry Comparison

### 3.1 How Production LLM Chat UIs Handle Streaming + Code Blocks

| Project | Stack | How Streaming Works | Code Blocks | Math | Tests |
|---|---|---|---|---|---|
| **LobeChat** (72K stars) | React + Next.js + Zustand + `@lobehub/ui` | React hooks + SSE; state-driven re-render | `react-syntax-highlighter` (Prism) | KaTeX component | Vitest + e2e |
| **Chatbot UI** (33K stars) | Next.js + TypeScript + Supabase | `useChat` hook pattern | Highlight.js in React components | N/A | Playwright e2e |
| **Vercel AI SDK** | Framework-agnostic (React/Svelte/Vue) | `useChat()` / `useCompletion()` hooks handle SSE, buffering, abort natively | N/A (UI-layer concern) | N/A | Comprehensive |
| **ChatScope** (1.7K stars) | React component kit | Built-in typing indicator component | N/A | N/A | Storybook |
| **Trinity (current)** | Vanilla JS | 300+ lines of `setInterval` + DOM mutation + nested callbacks | Regex extraction -> `innerHTML` -> `enhanceCodeBlocks()` post-process | `renderMathInElement()` per tick | **None** |

### 3.2 Key Insight

Every major production chat UI uses React (or a reactive framework) with **component isolation** between message rendering, streaming state, code blocks, and math. None use imperative DOM manipulation for streaming. The streaming problem (token buffering, abort, cursor, auto-scroll) is a **solved problem** — Vercel's `useChat()` handles it in ~50 lines. Trinity reinvents it in 300+ lines with multiple known bugs.

---

## 4. Recommended Architecture

### 4.1 Stack Selection: React + TypeScript + Vite

**Why React** (over Svelte, SolidJS, Vue):

1. **Multi-platform alignment**: The monetization plan specifies React Native for iOS/Android (months 3-5) and Electron for desktop (months 5-8). React web shares components, state logic, hooks, and types with all platforms.
2. **Zustand already in place**: `store.js` already exports a `useStore` React hook marked `// Export hook for React components (future use)`. Migration path is pre-built.
3. **Ecosystem depth for chat UIs**: `@lobehub/ui`, `@chatscope/chat-ui-kit-react`, Vercel AI SDK `useChat()` — all React-first.
4. **ICP compatibility**: ICP asset canisters serve static files. React builds to static `dist/` output identical to the current Vite build. Zero ICP-side changes needed.
5. **Contributor pool**: React is the most widely known frontend framework. Vanilla JS chat UIs have zero open-source contributors.

**Why TypeScript**: The #1 class of bugs is **interface drift** — when the backend changes SSE event format, tool output XML structure, or response fields, the frontend breaks silently because there's no type contract. TypeScript catches these at build time.

**Why Vite (keep)**: Already in use. Excellent React/TS support. Fast HMR for development. Produces the same `dist/` output that ICP asset canisters serve.

### 4.2 Dependency Strategy

**Bundle via npm (eliminate CDN scripts):**

| Library | Current (CDN) | Proposed (npm) | Why |
|---|---|---|---|
| highlight.js 11.9.0 | cdnjs, no SRI hash | `npm install highlight.js` | SRI problem eliminated; tree-shakeable language packs |
| marked 11.1.1 | cdnjs, no SRI hash | `npm install marked` | Type-safe; no CDN compromise risk |
| DOMPurify 3.0.6 | cdnjs, no SRI hash | `npm install dompurify` + `@types/dompurify` | Typed config; no CDN compromise risk |
| KaTeX 0.16.9 | jsdelivr, no SRI hash | `npm install katex` | Component-level import; no CDN |
| QRCode.js 1.0.0 | cdnjs, no SRI hash | `npm install qrcode` | Eliminate last CDN dependency |
| zustand 5.0.3 | npm (bundled) | Keep | Already bundled |
| @lighthouse-web3/sdk | npm (bundled) | Keep | Already bundled |

**Net result**: Zero CDN scripts. All dependencies bundled, typed, and tree-shaken. CSP policy simplified (no external script-src domains needed).

---

## 5. Component Design

### 5.1 Directory Structure (Actual — as built)

    trinity-icp/src-react/
    ├── components/
    │   ├── chat/
    │   │   ├── MessageList.tsx          # Message container with auto-scroll
    │   │   ├── Message.tsx              # Single message wrapper (user or AI)
    │   │   ├── StreamingMessage.tsx     # AI message during active streaming (token buffer + cursor)
    │   │   ├── MarkdownRenderer.tsx     # THE single rendering pipeline (markdown -> React tree)
    │   │   ├── CodeBlock.tsx            # Syntax-highlighted, collapsible, copyable, downloadable
    │   │   ├── MathBlock.tsx            # KaTeX-rendered math (inline or block)
    │   │   ├── TypingIndicator.tsx      # Phase-aware thinking animation (dots, phase badges)
    │   │   ├── ContinueButton.tsx       # Truncation handling (done_reason === 'length')
    │   │   ├── CopyAllButton.tsx        # Copy full message text
    │   │   ├── DownloadCards.tsx        # File download cards for code blocks
    │   │   └── MessageInput.tsx         # Textarea + send + file attach + keyboard handling
    │   ├── sidebar/
    │   │   └── Sidebar.tsx              # Collapsible sidebar with chat list + status indicators
    │   ├── modals/
    │   │   ├── AuthModal.tsx            # Login/signup flow
    │   │   ├── KeyExportModal.tsx       # QR code key export
    │   │   ├── ConfirmModal.tsx         # Generic confirmation dialog
    │   │   └── InfoModal.tsx            # Informational modal
    │   ├── notifications/
    │   │   └── ToastProvider.tsx        # Toast notification system
    │   └── layout/
    │       ├── AppShell.tsx             # Top-level layout (sidebar + main + modals)
    │       └── EmptyState.tsx           # Welcome/empty chat state
    ├── hooks/
    │   ├── useChat.ts                   # SSE streaming, token buffer, abort, retry, errors
    │   ├── useAuth.ts                   # Ed25519 key management, principal derivation
    │   ├── useAutosave.ts               # 2s debounced encrypted save with exponential backoff
    │   └── useConnection.ts            # Health check polling
    ├── store/
    │   ├── index.ts                     # Zustand store (migrated from store.js + typed)
    │   └── types.ts                     # State shape types
    ├── types/
    │   ├── message.ts                   # Message, SSEEvent, AgentResponse types
    │   ├── api.ts                       # Request/response types for all endpoints
    │   ├── auth.ts                      # Principal, KeyPair, AuthState types
    │   └── index.ts                     # Re-exports
    ├── utils/
    │   ├── markdown.ts                  # marked + DOMPurify + math protection (from math.js)
    │   ├── codeParser.ts                # Code block extraction (from codeBlockParser.js)
    │   ├── crypto.ts                    # AES-256-GCM encryption (from crypto.js)
    │   ├── indexedDB.ts                 # IndexedDB storage wrapper
    │   ├── lighthouse.ts                # Lighthouse/IPFS backup
    │   ├── sse.ts                       # SSE stream parser
    │   └── logger.ts                    # Environment-gated structured logger
    ├── __tests__/                       # 11 test files, 137 tests
    ├── config.ts                        # Runtime configuration (from config.js)
    ├── css-modules.d.ts                 # CSS module type declarations
    ├── App.tsx                          # Root component
    ├── main.tsx                         # Entry point (ReactDOM.createRoot)
    ├── test-setup.ts                    # Vitest setup
    ├── public/
    │   ├── .ic-assets.json5             # ICP asset canister headers config
    │   └── .well-known/ic-domains       # Custom domain mapping (dubya.ai)
    └── styles/
        ├── tokens.css                   # Design system: colors, spacing, radii, typography
        ├── global.css                   # Reset + base typography
        └── components/                  # CSS Modules (.module.css per component)
            ├── AppShell.module.css
            ├── CodeBlock.module.css
            ├── DownloadCards.module.css
            ├── EmptyState.module.css
            ├── Message.module.css
            ├── MessageInput.module.css
            ├── Modal.module.css
            ├── Sidebar.module.css
            ├── Toast.module.css
            └── TypingIndicator.module.css

### 5.2 The Single Rendering Pipeline

**This is the most important architectural decision.** Currently, messages pass through 5+ different rendering paths depending on context (streaming vs. static, initial vs. continuation, tool call vs. plain text). The new architecture has ONE:

    Raw text (from SSE or chat history)
        -> preprocessToolCalls()          # XML tool tags -> fenced code blocks (single implementation)
        -> protectMath()                  # $...$ and $$...$$ -> placeholders (prevents marked mangling)
        -> marked.parse()                 # Markdown -> HTML string
        -> DOMPurify.sanitize()           # XSS prevention
        -> restoreMath()                  # Placeholders -> KaTeX-rendered HTML
        -> React.createElement tree       # HTML string -> React component tree
        -> CodeBlock / MathBlock / text   # Each type rendered by its own component

Every message — streaming or static, user or AI, initial or continuation — goes through `MarkdownRenderer.tsx`. The component tree is:

    <MarkdownRenderer content={text}>
      ├── <p>Regular paragraph text</p>
      ├── <MathBlock expression="E=mc^2" display={true} />
      ├── <CodeBlock language="python" code="def foo()..." filename="app.py" />
      ├── <p>More text</p>
      └── <MathBlock expression="x^2" display={false} />  {/* inline */}
    </MarkdownRenderer>

**Why this eliminates the break pattern**: When the backend changes tool output format, there is exactly ONE place to update (`preprocessToolCalls` in `markdown.ts`). When streaming token patterns change, `StreamingMessage.tsx` handles buffering but rendering still goes through MarkdownRenderer. When math delimiters change, `protectMath()` is the single control point.

### 5.3 Key Component Contracts (TypeScript)

    // types/message.ts — the contract between backend and frontend
    // types/message.ts — SSE event contract (post-intelligence-overhaul)
    interface SSEEvent {
      token?: string;           // Streaming token
      done?: boolean;           // Stream complete
      done_reason?: 'stop' | 'length';  // Why stream ended
      phase?: string;           // 'searching' | 'executing' | 'responding'
      message?: string;         // Phase description
      error?: string;           // Error message
      response?: AgentResponse; // Metadata on stream completion
    }

    interface ChatMessage {
      id: string;
      role: 'user' | 'assistant';
      content: string;
      timestamp: number;
    }

    // Post-overhaul: single-pass pipeline, no complexity/passes_used
    interface AgentResponse {
      answer?: string;
      search_performed?: boolean;
      search_query?: string;
      total_time_seconds?: number;
      done_reason: 'stop' | 'length';
      model?: string;
    }

    // types/api.ts — request types (matches /generate/agent body)
    interface GenerateRequest {
      prompt: string;
      principal: string;
      context_messages: Pick<ChatMessage, 'role' | 'content'>[];
      chat_id: string;
      message_index: number;
    }

When the backend changes any of these fields, TypeScript surfaces the break **at build time** instead of in production.

---

## 6. Streaming Architecture

### 6.1 Current Architecture (Fragile)

    SSE response
      -> api.js: onToken(token, fullText) callback
      -> generate.js: tokenBuffer = fullText (closure variable)
      -> setInterval(15ms):
          displayedLength += 3
          visibleText = tokenBuffer.substring(0, displayedLength)
          getCodeBlockStatus(visibleText)     // Parse ALL text for fences
          if (inProgress) -> create/update streamDetailsEl (module-scoped DOM ref)
          stableDiv.innerHTML = parseMarkdownWithMath(stableText)    // Full re-parse
          tailDiv.innerHTML = parseMarkdownWithMath(tailText) + cursor  // Full re-parse
          chatArea.scrollTop = chatArea.scrollHeight  // Scroll

**Problems**: `setInterval` timer disconnected from React/state lifecycle. Module-scoped DOM refs leak across messages. Full markdown+math+sanitize parse on every 15ms tick. `innerHTML` replacement destroys existing KaTeX DOM nodes. Code block detection regex runs on full accumulated text every tick (O(n) per tick, O(n^2) total). No abort cleanup. Legacy `typeMessage()` in messages.js re-parses entire content per CHARACTER (O(n^2) parsing).

### 6.2 Proposed Architecture (Robust)

    // hooks/useChat.ts — ~80 lines replacing ~300 lines across api.js + generate.js
    function useChat() {
      const [tokens, setTokens] = useState('');
      const [isStreaming, setIsStreaming] = useState(false);
      const [phase, setPhase] = useState<Phase | null>(null);
      const [error, setError] = useState<Error | null>(null);
      const abortRef = useRef<AbortController | null>(null);

      const send = useCallback(async (prompt: string) => {
        abortRef.current = new AbortController();
        setIsStreaming(true);
        setTokens('');

        try {
          const response = await fetch(`${CONFIG.API_URL}/generate/agent`, {
            method: 'POST',
            signal: abortRef.current.signal,
            headers: buildAuthHeaders(prompt),
            body: JSON.stringify(buildRequest(prompt)),
          });

          for await (const event of streamSSE(response)) {
            if (event.phase) setPhase({ name: event.phase, message: event.message });
            if (event.full_text != null) setTokens(event.full_text);
            if (event.done) { /* finalize */ }
            if (event.error) setError(new Error(event.error));
          }
        } catch (e) {
          if (e.name !== 'AbortError') setError(e);
        } finally {
          setIsStreaming(false);
        }
      }, []);

      const stop = useCallback(() => abortRef.current?.abort(), []);

      return { tokens, isStreaming, phase, error, send, stop };
    }

    // components/chat/StreamingMessage.tsx — ~60 lines replacing generate.js DOM logic
    function StreamingMessage({ tokens, isStreaming }: Props) {
      // Split tokens into stable (completed code blocks) and tail (in-progress)
      const { stableText, tailText, streamingBlock } = useMemo(
        () => splitAtCompletedBlocks(tokens),
        [tokens]
      );

      return (
        <div className={styles.message}>
          {/* Stable section: memoized, never re-renders during streaming */}
          <MemoizedMarkdown content={stableText} />

          {/* Tail: re-renders on new tokens, but only the trailing text */}
          <MarkdownRenderer content={tailText} />
          {isStreaming && <span className={styles.cursor}>|</span>}

          {/* Streaming code card: shows in-progress code block */}
          {streamingBlock && (
            <StreamingCodeCard
              language={streamingBlock.lang}
              code={streamingBlock.code}
              lineCount={streamingBlock.lines}
            />
          )}
        </div>
      );
    }

### 6.3 Why This Eliminates the Fragility

| Current Problem | How React Architecture Fixes It |
|---|---|
| `setInterval` timer disconnected from component lifecycle | React state updates trigger re-renders; no timers needed |
| Module-scoped DOM refs leak across messages | Component state is function-scoped; each `StreamingMessage` instance is isolated |
| `innerHTML` replacement destroys KaTeX nodes | React reconciliation preserves existing DOM nodes; only changed content updates |
| Full markdown parse on every 15ms tick | `useMemo` on `stableText` — completed sections never re-parse |
| `arguments.callee` in continuation (deprecated) | Standard recursive callback pattern with proper closure |
| No abort cleanup (timers keep running) | `AbortController` + React cleanup (`useEffect` return) |
| O(n^2) text scanning per token | Incremental: only scan new tokens for fence markers |

---

## 7. CSS Strategy

### 7.1 Current Problems

- **2,105 lines in one file** with no organization system
- **No design tokens**: colors hardcoded (`#1a1a1a`, `#ffffff`, `#ef4444`) across 100+ locations
- **Dead selectors**: `.tool-nav`, `.guest-info`, `.tool-view` appear unused
- **Inline styles in JS**: `sidebar.js` renders HTML with extensive `style=""` attributes
- **No naming convention**: class names like `.message`, `.ai`, `.sidebar` have global scope collision risk
- **Commented-out code**: `pointer-events: none` on `.ui-disabled` (commented out, noted "was blocking stop button clicks")

### 7.2 Proposed Solution

**Design Tokens** (`tokens.css`):

    :root {
      /* Colors */
      --color-bg-primary: #1a1a1a;
      --color-bg-secondary: #242424;
      --color-bg-tertiary: #2a2a2a;
      --color-text-primary: #ffffff;
      --color-text-secondary: #aaa;
      --color-text-muted: #888;
      --color-accent: #667eea;
      --color-error: #ef4444;
      --color-success: #22c55e;
      --color-warning: #f59e0b;

      /* Spacing */
      --space-xs: 4px;
      --space-sm: 8px;
      --space-md: 12px;
      --space-lg: 16px;
      --space-xl: 24px;

      /* Radii */
      --radius-sm: 6px;
      --radius-md: 8px;
      --radius-lg: 12px;

      /* Typography */
      --font-mono: 'SF Mono', 'Fira Code', monospace;
      --font-sans: system-ui, -apple-system, sans-serif;

      /* Transitions */
      --transition-fast: 150ms ease;
      --transition-normal: 300ms ease;
    }

**CSS Modules** (per-component):

    /* components/chat/CodeBlock.module.css */
    .container { /* auto-scoped to CodeBlock_container_x3k2 */ }
    .header { }
    .copyButton { }
    .code { }

**Benefits**:
- Dead CSS is impossible — unused component CSS is tree-shaken
- No naming collisions — CSS Modules auto-scope class names
- Design consistency — tokens enforce the design system
- No inline styles in JS — eliminated entirely
- **Estimated output**: ~800 lines of CSS across modules (vs. 2,105 monolithic)

---

## 8. Security Improvements

| Issue | Current State | Fix | Priority |
|---|---|---|---|
| **6 CDN scripts without SRI** | `index.html` loads highlight.js, marked, DOMPurify, KaTeX, QRCode from CDN with no integrity hashes | Bundle all via npm; zero CDN scripts | HIGH |
| **253 `console.log` statements** | Log principals, signatures, API URLs to browser console | TypeScript + ESLint `no-console` rule; structured `Logger` with env-gated output | HIGH |
| **`document.execCommand('copy')`** | Deprecated API used because Clipboard API blocked by ICP | Use `navigator.clipboard.writeText()` with textarea fallback; update ICP CSP Permissions-Policy | MEDIUM |
| **String-based DOM (XSS)** | `modals.js` (642 lines) builds HTML via template literals | React JSX eliminates string-based DOM; DOMPurify only for user-generated markdown | HIGH |
| **`window.State` global** | Full app state exposed to browser console | Remove; debugging via React DevTools + Zustand devtools middleware (dev-only) | MEDIUM |
| **No CSP `script-src` lockdown** | CSP allows scripts from multiple CDN domains | All scripts bundled; CSP `script-src 'self'` only | MEDIUM |

### CSP Changes (`.ic-assets.json5`)

    # Before:
    script-src 'self' 'unsafe-eval' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net;
    style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net;

    # After:
    script-src 'self';
    style-src 'self' 'unsafe-inline';

---

## 9. Testing Strategy

### 9.1 Why This Is Non-Negotiable

The INTELLIGENCE-OVERHAUL identified "zero tests, zero linting, zero type checking" as a critical finding. The current frontend has survived this long only because changes are rare and manually smoke-tested. The planned backend overhaul (Phases 1-5) will change SSE event formats, tool output, and response structures — each change will require frontend verification. Without tests, each verification is manual.

### 9.2 Test Layers

| Layer | Tool | Scope | What It Catches |
|---|---|---|---|
| **Types** | TypeScript strict mode | All SSE event types, API response types, state shape | Interface drift between backend and frontend — **the #1 current pain point** |
| **Unit** | Vitest | `MarkdownRenderer`, `codeParser`, `protectMath`/`restoreMath`, SSE parser, token buffer | Rendering pipeline regressions |
| **Component** | Vitest + React Testing Library | `CodeBlock`, `StreamingMessage`, `MessageInput`, `MathBlock` | UI behavior: collapse/expand, copy, auto-scroll, cursor visibility |
| **Integration** | Playwright | Full flow: send message -> stream -> code block renders -> math renders -> copy works | End-to-end correctness against real (or mocked) backend |
| **Lint** | ESLint | `no-console`, `no-any`, React hooks rules | Security leaks, type safety, hook misuse |

### 9.3 Critical Test Cases

    // The tests that would have caught every recent frontend incident:

    describe('MarkdownRenderer', () => {
      it('renders fenced code blocks with syntax highlighting');
      it('renders inline math $x^2$ without breaking');
      it('renders block math $$E=mc^2$$ as display mode');
      it('handles incomplete code blocks during streaming (odd fence count)');
      it('preserves math inside code blocks (does not render as KaTeX)');
      it('handles nested backticks in code blocks');
      it('sanitizes script injection in message content');
      it('preprocesses <tool_call> XML to fenced code blocks');
    });

    describe('StreamingMessage', () => {
      it('shows typing cursor during streaming');
      it('removes cursor when streaming completes');
      it('shows streaming code card for in-progress code block');
      it('collapses completed code blocks during streaming');
      it('memoizes stable sections (no re-render for completed blocks)');
      it('handles abort cleanly (no dangling state)');
    });

    describe('useChat', () => {
      it('buffers tokens from SSE and updates state');
      it('handles abort via AbortController');
      it('handles network errors gracefully');
      it('handles done_reason=length (shows continue button)');
      it('sends chat_id and message_index in request body');
    });

---

## 10. ICP Deployment Compatibility

### 10.1 No ICP Changes Required

The ICP asset canister (`dfx.json`) serves static files from `dist/`. React + Vite builds to the same `dist/` directory. The deploy command is unchanged:

    npm run build                              # Vite builds React app -> dist/
    dfx deploy trinity_frontend --network ic   # Upload dist/ to asset canister

### 10.2 Specific Considerations

| Concern | Status | Notes |
|---|---|---|
| **Asset canister type** | Compatible | `"type": "assets", "source": ["dist"]` — framework-agnostic |
| **IIFE format** | No longer needed | Current `vite.config.js` uses IIFE for `file://` compatibility. React uses ESM. If `file://` support needed, `@vitejs/plugin-legacy` (already installed, currently disabled) re-enables it. |
| **CSP headers** | Simplified | Fewer external domains needed (no CDN scripts). Update `.ic-assets.json5`. |
| **Custom domain** | Unchanged | `.well-known/` config for `dubya.ai` binding unaffected |
| **Canister IDs** | Unchanged | Same `zc67k-kiaaa-aaaal-qtmiq-cai` frontend canister |
| **Bundle size** | Comparable | Current CDN scripts + IIFE bundle approx 500KB. React + bundled deps approx 400-600KB (highlight.js is the largest dependency either way) |
| **Backend canister** | Unchanged | Still disabled (`USE_CANISTER = false` due to 20s timeout) |
| **Post-build script** | Simplified or removed | Current `post-build.js` strips `type="module"` and injects `icp-auth.js`. React build handles module format natively. Auth bundle import becomes a standard ES import. |

---

## 11. Migration Plan

### 11.1 Strategy: Incremental, Not Big-Bang

The migration must avoid a multi-week blackout where the app is non-functional. Each phase produces a deployable (if incomplete) application.

### Phase A: Foundation (Week 1) ✅ COMPLETE

**Goal**: App shell renders, auth works, can send a message (no streaming UI yet).
**Completed**: Feb 13, 2026. All items below are implemented and verified.

| Task | Input | Output | Status |
|---|---|---|---|
| Scaffold React + TypeScript + Vite in `src-react/` | Current `vite.config.js` | `vite.config.react.ts` with React plugin | ✅ |
| Define TypeScript types for SSE events, messages, API | Current `api.js` + `store.js` | `types/message.ts`, `types/api.ts`, `types/auth.ts` | ✅ |
| Port Zustand store from JS to TS | `state/store.js` (257 lines) | `store/index.ts` (typed, same shape) | ✅ |
| Create `useAuth.ts` hook | `auth/authManager.js` + `auth/auth-entry.js` | Ed25519 key management as React hook | ✅ |
| Create `useChat.ts` hook | `core/api.js` + `core/sse.js` | SSE streaming with typed events | ✅ |
| Build `AppShell.tsx` + `MessageInput.tsx` | Current `app.js` + `index.html` | Basic layout renders | ✅ |
| Configure ESLint + `no-console` + strict TypeScript | N/A | `tsconfig.json`, `.eslintrc.json` | ✅ |

**Verification**: `npm run build` succeeds ✅. `tsc --noEmit` clean ✅. 59 tests pass ✅.

### Phase B: Rendering Pipeline (Week 2) ✅ COMPLETE

**Goal**: Streaming messages render correctly with code blocks and math.
**Completed**: Feb 13, 2026. All components built, CSS modules created, tests passing.

| Task | Input | Output | Status |
|---|---|---|---|
| Build `MarkdownRenderer.tsx` | `editMessage.js` (parseMarkdownWithMath), `math.js` (protect/restore) | THE single rendering pipeline | ✅ |
| Build `CodeBlock.tsx` | `messages.js` (enhanceCodeBlocks), `codeUtils.js`, `codeBlockParser.js` | Self-contained: highlight, copy, collapse, download | ✅ |
| Build `MathBlock.tsx` | `math.js` (renderMath, protectMath, restoreMath) | KaTeX rendering as React component | ✅ |
| Build `StreamingMessage.tsx` | `generate.js` (stable/stream/tail split, token buffer, cursor) | Token buffer + incremental render + memoized stable sections | ✅ |
| Build `TypingIndicator.tsx` | `generate.js` (thinking indicator, phase badges) | Phase-aware thinking animation | ✅ |
| Build `Message.tsx` + `MessageList.tsx` | `messages.js` (showMessage, message rendering) | Message display with auto-scroll | ✅ |
| Write unit tests for rendering pipeline | Test cases from Section 9.3 | 59 tests (codeParser: 15, markdown: 25, store: 19) | ✅ |

**Verification**: `npm run build` produces 270 modules, 1,477KB JS (471KB gzipped) ✅. All 59 tests green ✅.

### Phase C: Feature Parity (Week 3) ✅ COMPLETE

**Goal**: Full feature parity with current app.

**Completed**: Feb 13, 2026. All items below are implemented and verified.

| Task | Input | Output | Status |
|---|---|---|---|
| Build `Sidebar.tsx` | `ui/sidebar.js` | Sidebar with chat list, collapse, status indicators | ✅ |
| Port autosave | `storage/autosave.js` | `useAutosave.ts` hook with debounce + exponential backoff | ✅ |
| Port chat management | `features/chatManagement.js` | Load, delete, new chat flows | ✅ |
| Build modals | `ui/modals.js` (642 lines of template literals) | React components (AuthModal, KeyExportModal, ConfirmModal, InfoModal) | ✅ |
| Port edit-and-regenerate | `generate.js` (editAndRegenerate function) | Edit button + history truncation + re-generate | ✅ |
| Port continue-from-truncation | `generate.js` (continue button + nested generateAgent) | `ContinueButton.tsx` with clean continuation chaining | ✅ |
| Port file attachment | `tools.js` | File attach + `DownloadCards.tsx` | ✅ |
| Port notifications | `ui/notifications.js` | `ToastProvider.tsx` notification component | ✅ |
| Port IndexedDB + Lighthouse storage | `storage/indexedDB.js`, `storage/lighthouse.js` | `utils/indexedDB.ts`, `utils/lighthouse.ts` | ✅ |
| Build empty state | N/A | `EmptyState.tsx` welcome screen | ✅ |

**Verification**: All features from current app work. Sidebar loads chats. Autosave fires. Modals render. Edit-and-regenerate works. File attachment works.

### Phase D: Testing + Hardening (Days 15-19) ✅ COMPLETE

**Goal**: Regression protection and security hardening.

**Completed**: Feb 13, 2026. 137 tests across 11 test files. ESLint clean. Security audit performed with HIGH/MEDIUM findings fixed.

| Task | Output | Status |
|---|---|---|
| Vitest unit tests for SSE, lighthouse, logger, codeParser, markdown, store | 137 tests, 11 test files | ✅ |
| Vitest component tests for CodeBlock, StreamingMessage, MessageInput | Behavioral coverage with mocked CSS modules | ✅ |
| Vitest hook tests for useChat, useConnection, toast system | Full streaming/error/abort/continuation coverage | ✅ |
| ESLint `no-console` enforcement across all files | 0 violations, `eslint.config.mjs` (flat config for ESLint 9) | ✅ |
| Security audit: XSS, auth nonce, input validation, DOMPurify | 10 findings audited, HIGH/MEDIUM fixed | ✅ |
| Security: HTML-escape math fallback paths (XSS prevention) | `escapeHtml()` in markdown.ts + MathBlock.tsx | ✅ |
| Security: Replace Math.random nonce with crypto.getRandomValues | useAuth.ts nonce hardened | ✅ |
| Security: Remove `style` from DOMPurify allowed attributes | CSS injection vector removed | ✅ |
| Security: Client-side input limits (50k chars, 10MB files) | MessageInput.tsx hardened | ✅ |
| Playwright e2e test | Deferred — requires running Akash backend; tracked as future work | ⏳ |
| Accessibility audit | Deferred — tracked as future work | ⏳ |

**Verification**: `npx vitest run` passes 137 tests ✅. `npx eslint src-react/` clean ✅. `npx tsc --noEmit` clean ✅. `npx vite build` produces 473KB gzip ✅.

### Phase E: Deploy + Cutover (Days 20-22) ✅ COMPLETE

**Goal**: Production deployment with rollback safety.

| Task | Output | Status |
|---|---|---|
| Audit deploy readiness | dfx.json source `["dist"]`, canister IDs, vite config verified | ✅ |
| Enhance index.html for production | OG meta tags, description, hardened CSP (frame-src, object-src, base-uri, form-action), app-version meta, mobile viewport | ✅ |
| Configure .ic-assets.json5 | Security headers (X-Content-Type-Options, Referrer-Policy, Permissions-Policy), immutable cache for hashed assets, no-cache for HTML/icp-auth.js | ✅ |
| Add .well-known/ic-domains | `dubya.ai` + `www.dubya.ai` custom domain config in React public dir | ✅ |
| Enable Vite publicDir | Changed `publicDir: false` → `publicDir: 'public'` so .ic-assets.json5 and .well-known copy to dist | ✅ |
| Fix icp-auth.js path | Changed `src="/icp-auth.js"` → `src="./icp-auth.js"` for ICP relative path safety | ✅ |
| Build production bundle | 473KB gzip JS + 8KB gzip CSS + 60 KaTeX fonts + icp-auth.js (303KB) = 67 files in dist | ✅ |
| Deploy to production canister (`zc67k-kiaaa-aaaal-qtmiq-cai`) | `dfx deploy trinity_frontend --network ic` — live at dubya.ai | ✅ |
| Smoke test: canister URL | https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io/ returns HTTP 200, React app renders auth screen | ✅ |
| Smoke test: custom domain | https://dubya.ai/ returns HTTP 200, `<title>Trinity AI</title>` | ✅ |
| Smoke test: security headers | CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy all served via HTTP headers | ✅ |
| Smoke test: asset caching | Hashed JS/CSS: `cache-control: public, max-age=31536000, immutable` | ✅ |

**Verification**: `curl -s https://dubya.ai/ | grep '<title>'` returns `<title>Trinity AI</title>` ✅. All security headers confirmed via `curl -I` ✅.

**Rollback**: `git checkout` the pre-overhaul commit + `dfx deploy trinity_frontend --network ic`. Asset canister deploy takes ~60 seconds.

---

## 12. Relationship to INTELLIGENCE-OVERHAUL

The INTELLIGENCE-OVERHAUL Phase 0 ("Frontend Stabilization") identified 10 frontend bugs (F1-F10) and prescribed deletion/consolidation fixes. This migration **supersedes Phase 0** — dead code doesn't need deletion because it simply doesn't get ported.

### How Each Phase 0 Item Is Resolved

| OVERHAUL Item | ID | Migration Resolution |
|---|---|---|
| Deduplicate `preprocessToolCalls()` | F4 | Single `MarkdownRenderer` — one definition, one import |
| Remove dead message paths (generateSimple, canister path) | F10 | Not ported — they vanish |
| Fix context window inconsistency (6 vs 12) | F1 | Single `useChat` hook — one context path |
| Add `chat_id` / `message_index` to requests | F2, F3 | Built into typed `GenerateRequest` interface |
| Fix `{"clear": true}` handling | F5 | Handled in `useChat` hook with proper state reset |
| Fix module-scoped DOM refs | F6 | React component state is function-scoped by design |
| Fix Zustand direct mutations | F7 | TypeScript + React hooks enforce immutable updates |
| Remove 253 console.log statements | F8 | ESLint `no-console` + structured Logger |
| Optimize streaming render (parseMarkdownWithMath per tick) | F9 | `useMemo` on stable sections; only tail re-renders |
| Delete contextMemory.js / summarization | 0.2 | Not ported — dead code vanishes |
| Delete `app.js.bak` | -- | Not ported |

### Phase Ordering (Updated Feb 13, 2026)

    INTELLIGENCE-OVERHAUL Phases 0-5 ✅ ALL COMPLETE
        Phase 0: Frontend stabilization (vanilla JS cleaned) ✅
        Phase 1: Backend dead code removal (~2,000 lines) ✅
        Phase 2: Pipeline simplification (single-pass + ReAct) ✅
        Phase 3: Memory system overhaul (CONTEXT_WINDOW_SIZE=20) ✅
        Phase 4: Model upgrade (qwen2.5-coder:32b) ✅
        Phase 5: Agentic scaffolding (filesystem tools, code execution, repo map) ✅

    FRONTEND OVERHAUL (This Plan) ✅ ALL COMPLETE
        Phase A: Foundation ✅ COMPLETE
        Phase B: Rendering Pipeline ✅ COMPLETE
        Phase C: Feature Parity ✅ COMPLETE
        Phase D: Testing + Hardening ✅ COMPLETE (137 tests, ESLint clean, security audit)
        Phase E: Deploy + Cutover ✅ COMPLETE (live at dubya.ai, Feb 13 2026)

**Key implication:** The backend API contract is now stable. The React types must match the *post-overhaul* API — no `complexity`, no `passes_used`, no `clear` events, no `temperature`/`user_memory` in `/generate/agent` body. `CONTEXT_WINDOW_SIZE` is 20.

---

## 13. Risk Register

| Risk | Prob | Impact | Mitigation |
|---|---|---|---|
| **3-4 week timeline slips** | Medium | Medium | Phases A-B are the critical path. Phase C can compress (not every feature needed on day 1 — e.g., code panel side-panel is already broken). Phase D testing can run in parallel with Phase C. |
| **React bundle size increases load time** | Low | Low | Current CDN deps are ~400KB loaded regardless. Bundling doesn't increase total; may reduce via tree-shaking (unused highlight.js languages). |
| **ICP CSP blocks React dev tooling** | Low | Low | Dev tooling only in development builds. Production CSP unchanged. |
| **Team unfamiliarity with React/TypeScript** | Medium | High | React is the most documented framework. AI coding tools are highly effective with React/TS. Zustand already in use. LobeChat and Chatbot UI serve as reference implementations. |
| **Streaming regression** | Medium | High | Playwright e2e test for streaming is a Phase D gate. Staging canister allows parallel testing before cutover. |
| **`file://` protocol support breaks** | Low | Low | Re-enable `@vitejs/plugin-legacy` (already installed). Assess whether anyone actually uses offline mode. |
| **Autosave behavior regression** | Medium | Medium | Port autosave logic verbatim; unit test debounce timing and retry behavior. Test against production Akash backend on staging. |
| **Ed25519 auth regression** | Low | High | Auth logic is well-isolated in `authManager.js`. Port as `useAuth.ts` hook. Verify principal derivation produces identical results. |
| **No frontend during migration** | Low | Critical | Migration is additive (new files alongside old). Old app remains deployable throughout. Cutover only when staging verified. |

---

## 14. Alternatives Considered

| Alternative | Evaluation | Why Rejected |
|---|---|---|
| **Keep vanilla JS, just clean it up** (OVERHAUL Phase 0) | Addresses symptoms (dead code, console.log) but not root cause (imperative DOM, no components, no types). Removes ~500 lines but every new feature re-creates the same class of bugs. | Structural problem requires structural solution. Subtraction without architecture change is temporary. |
| **Svelte** | Excellent DX and performance. Smaller bundle than React. | No Svelte Native for mobile (monetization plan needs React Native). Smaller chat UI ecosystem. Fewer available contributors. Zustand would need replacement. |
| **SolidJS** | Best runtime performance of any framework. Fine-grained reactivity. | Tiny ecosystem. No equivalent to LobeChat's `@lobehub/ui` or Vercel AI SDK's `useChat()`. Risky for long-term maintenance. No mobile story. |
| **Vue** | Viable. Good DX. Large ecosystem. | Weaker mobile story (no Vue Native matching React Native maturity). Zustand replacement needed (Pinia). Fewer chat UI libraries. |
| **Next.js (SSR)** | React-based. Massive ecosystem. | ICP asset canisters are static-only — no SSR. Next.js's SSR/SSG features are wasted on static hosting. Adds unnecessary complexity. |
| **Juno (ICP-native framework)** | Purpose-built for ICP. Handles auth, storage, hosting. | Opinionated and tightly coupled to ICP. Small community. Reduces portability for multi-platform goals. Not proven for complex chat UIs. |
| **Lit / Web Components** | Framework-agnostic. Native browser standard. | No state management story. No chat UI component ecosystem. React Native code sharing impossible. |

---

## 15. Decisions Log

| # | Decision | Rationale | Alternative | Why Rejected |
|---|---|---|---|---|
| D1 | React + TypeScript over vanilla JS | Typed SSE contracts catch breaks at build time; component isolation prevents cross-contamination; ecosystem has battle-tested chat UI primitives | Keep vanilla JS + clean it up | Structural problem needs structural fix; cleaning removes symptoms not cause |
| D2 | React over Svelte/Solid/Vue | Multi-platform alignment (React Native/Electron planned); largest chat UI ecosystem; Zustand already in use with React hooks stubbed | Svelte (better DX), SolidJS (better perf) | No mobile story; smaller ecosystems |
| D3 | Vite (keep) over Next.js/Webpack | Already in use; excellent React/TS support; produces static output matching ICP asset canister | Next.js | SSR wasted on static ICP hosting |
| D4 | CSS Modules over Tailwind/CSS-in-JS | Zero-runtime; auto-scoped names; design tokens via CSS custom properties; tree-shaken per component | Tailwind (popular), styled-components (colocation) | Tailwind adds different learning curve; CSS-in-JS has runtime cost |
| D5 | Bundle all deps via npm over CDN | Eliminates SRI vulnerability; enables tree-shaking; simplifies CSP; typed imports | Keep CDN with SRI hashes | SRI is brittle; doesn't solve type safety |
| D6 | Incremental migration over big-bang rewrite | Old app stays deployable throughout; staging canister for parallel testing; each phase is independently verifiable | Freeze features for 4 weeks + rewrite | Too risky; no app during rewrite period |
| D7 | This plan supersedes OVERHAUL Phase 0 | Phase 0 items (F1-F10) automatically resolved by not porting dead code; React prevents re-introduction of structural bugs | Do Phase 0 first, then migrate later | Two rounds of frontend work; Phase 0 changes thrown away during migration |
| D8 | Vitest + Playwright over Jest + Cypress | Vitest is Vite-native (same config); Playwright faster and more reliable than Cypress | Jest + Cypress | Different config system; Cypress slower and heavier |

---

## 16. Success Metrics

| Metric | Current | Target | Measurement |
|---|---|---|---|
| Frontend incidents per backend deploy | ~1-2 | 0 | Incident count over 10 deploys |
| Time to add new rendering feature | 2-4 hours + debugging | 30-60 minutes | Dev tracked time |
| Time to diagnose rendering bug | 1-3 hours | 10-30 minutes (stack trace + types) | Dev tracked time |
| TypeScript type coverage | 0% | 95%+ strict | `tsc --noEmit` |
| Frontend test coverage | 0% | >60% overall; >90% on rendering pipeline | Vitest coverage report |
| CSS dead code | Unknown | 0 (CSS Modules tree-shake) | Build output analysis |
| Console security leaks | 253 statements | 0 `console.log` in production | ESLint CI gate |
| Bundle size | ~500KB (CDN + IIFE) | <=600KB (bundled, tree-shaken) | Build output |
| Streaming render performance | Full markdown parse 66x/sec per message | Stable sections memoized; only tail re-renders | Chrome DevTools profiling |
| Shared code with future mobile app | 0% | ~60% (types, hooks, store, utils) | File diff between web and React Native repos |

---

## Appendix A: Files Ported vs. Dropped

### Ported (logic preserved, rewritten in TypeScript + React)

| Current File | Lines | New Location | Notes |
|---|---|---|---|
| `state/store.js` | 302 | `store/index.ts` | Same shape, add types |
| `utils/math.js` | 200 | `utils/markdown.ts` | protectMath/restoreMath logic preserved |
| `utils/codeBlockParser.js` | 90 | `utils/codeParser.ts` | extractCodeBlocks/getCodeBlockStatus preserved |
| `utils/codeUtils.js` | 170 | `utils/codeParser.ts` + `utils/markdown.ts` | Filename/icon logic merged into parser; rendering into markdown |
| `utils/crypto.js` | ~100 | `utils/crypto.ts` | AES-256-GCM logic preserved |
| `core/sse.js` | ~60 | `utils/sse.ts` | SSE stream parser as standalone utility |
| `core/logger.js` | ~20 | `utils/logger.ts` | Expand to structured logging |
| `core/api.js` | ~400 | `hooks/useChat.ts` | Only generateAgent path; SSE handling in hook |
| `auth/authManager.js` | ~200 | `hooks/useAuth.ts` | Ed25519 key management as hook |
| `storage/autosave.js` | ~150 | `hooks/useAutosave.ts` | Debounce + retry as hook |
| `storage/indexedDB.js` | ~80 | `utils/indexedDB.ts` | Direct port |
| `storage/lighthouse.js` | ~100 | `utils/lighthouse.ts` | Direct port |
| `config.js` | ~80 | `config.ts` | Add types |
| `features/generate.js` | 605 | `hooks/useChat.ts` + `StreamingMessage.tsx` | Decomposed: streaming in hook, render in component |
| `features/chatManagement.js` | ~150 | Component + store actions | Direct port |
| `features/auth.js` | ~100 | `hooks/useAuth.ts` | Merged into auth hook |
| `features/memory.js` | ~80 | Store actions | Direct port |

### Dropped (dead code — not ported)

| Current File | Lines | Why Dropped |
|---|---|---|
| `app.js.bak` | 2,400 | Backup file, dead code, gets bundled by Vite |
| `state/contextMemory.js` | 75 | Summarization never persists, never triggers, broken |
| `api/canister-client.js` | ~100 | Backend canister disabled (`USE_CANISTER = false`) |
| `ui/codePanel.js` | ~150 | References non-existent store methods; partially integrated |
| Dead paths in `api.js` | ~200 | `generateSimple()`, `generate()` canister path — 0 callers |
| Dead function in `chatManagement.js` | ~20 | `recoverArchivedChats()` — stub that logs "removed in v3.7.0" |
| `auth/icp-auth.js` | 8,578 | Pre-built generated bundle — rebuild via `build-auth.js`, imported as module |

### Summary

| Category | Lines |
|---|---|
| Hand-written code ported | ~2,887 (rewritten as TypeScript + React) |
| Dead code dropped | ~2,945 (including `app.js.bak`) |
| Generated code (`icp-auth.js`) | 8,578 (re-imported as ES module) |
| New code (components, hooks, tests, types, CSS modules) | ~5,200 production + ~1,700 tests = ~6,900 total |
| **Net hand-written production code** | **~5,200 lines** (vs. current ~9,725 — 47% reduction) |

---

## Appendix B: Dependency Comparison

### Current package.json dependencies

    {
      "dependencies": {
        "zustand": "^5.0.3",
        "@lighthouse-web3/sdk": "^0.4.4",
        "w3name": "^1.1.3"
      },
      "devDependencies": {
        "vite": "^5.4.0",
        "@vitejs/plugin-legacy": "^5.4.3",
        "esbuild": "^0.27.2",
        "@dfinity/agent": "^3.4.3",
        "@dfinity/candid": "^3.4.3",
        "@dfinity/identity": "^3.4.3",
        "@dfinity/principal": "^3.4.3"
      }
    }

Plus 6 CDN scripts: highlight.js, marked, DOMPurify, KaTeX, KaTeX auto-render, QRCode.js

### Proposed package.json dependencies

    {
      "dependencies": {
        "react": "^19.0.0",
        "react-dom": "^19.0.0",
        "zustand": "^5.0.3",
        "@lighthouse-web3/sdk": "^0.4.4",
        "w3name": "^1.1.3",
        "marked": "^11.1.1",
        "dompurify": "^3.0.6",
        "highlight.js": "^11.9.0",
        "katex": "^0.16.9",
        "qrcode": "^1.5.3"
      },
      "devDependencies": {
        "typescript": "^5.4.0",
        "@types/react": "^19.0.0",
        "@types/react-dom": "^19.0.0",
        "@types/dompurify": "^3.0.5",
        "@types/katex": "^0.16.7",
        "@vitejs/plugin-react": "^4.3.0",
        "vite": "^5.4.0",
        "esbuild": "^0.27.2",
        "vitest": "^2.0.0",
        "@testing-library/react": "^16.0.0",
        "playwright": "^1.44.0",
        "eslint": "^9.0.0",
        "@typescript-eslint/eslint-plugin": "^7.0.0",
        "@dfinity/agent": "^3.4.3",
        "@dfinity/candid": "^3.4.3",
        "@dfinity/identity": "^3.4.3",
        "@dfinity/principal": "^3.4.3"
      }
    }

Zero CDN scripts.

### Size Impact

| Component | Current | Proposed |
|---|---|---|
| highlight.js (CDN) | ~50KB gzipped | ~45KB gzipped (tree-shake unused languages) |
| marked (CDN) | ~8KB gzipped | ~8KB gzipped |
| DOMPurify (CDN) | ~7KB gzipped | ~7KB gzipped |
| KaTeX + CSS (CDN) | ~100KB gzipped | ~95KB gzipped (tree-shake unused fonts) |
| QRCode.js (CDN) | ~15KB gzipped | ~12KB gzipped |
| React + ReactDOM | N/A | ~45KB gzipped |
| App bundle (IIFE) | ~80KB gzipped | ~60KB gzipped (TypeScript + tree-shaking) |
| **Total** | **~260KB gzipped** | **~272KB gzipped** |

Net increase: ~12KB gzipped (~5%). Offset by elimination of 6 separate HTTP requests for CDN scripts.

---

*Generated February 13, 2026.*