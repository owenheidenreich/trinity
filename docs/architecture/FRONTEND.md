# Trinity — Frontend Architecture

> Last updated: February 19, 2026 · Covers React frontend v3.0.0 (`src-react/`)

## Overview

Trinity's frontend is a React 19 single-page application built with TypeScript and Vite. It runs as a canister on the Internet Computer (ICP), meaning the frontend code itself is hosted on a decentralized blockchain — not a traditional CDN or web server.

There are **two frontends** in the repository:

| Frontend | Directory | Status | Version |
|----------|-----------|--------|---------|
| React / TypeScript | `trinity-icp/src-react/` | **Active** (default build) | 3.0.0 |
| Vanilla JavaScript | `trinity-icp/src/` | Legacy (still buildable via `npm run build:legacy`) | 2.8.0 |

This document covers the active React frontend. The legacy frontend shares the same ICP auth bundle and Zustand store contract but uses imperative DOM manipulation instead of components.

---

## Component Tree

```
App
├── ToastProvider                       ← Global toast notification stack
└── AppShell                            ← Main layout orchestrator
    │
    ├── AuthModal                       ← Shown when not authenticated (gates everything)
    │   └── KeyExportModal              ← Shows private key for backup (shown once)
    │
    ├── Sidebar                         ← Chat list, connection status, identity controls
    │   ├── ChatItem (internal)         ← Per-chat row: load, pin, export, delete
    │   └── MemoryPanel                 ← Raw JSON display of stored facts, fact count
    │
    ├── EmptyState                      ← Welcome screen (shown before first message)
    │
    ├── MessageList                     ← Scrollable message container
    │   ├── Message                     ← Rendered user or assistant message
    │   │   ├── MarkdownRenderer        ← Splits HTML into text + CodeBlock segments
    │   │   │   └── CodeBlock           ← Collapsible, copyable, downloadable code
    │   │   ├── DownloadCards           ← File download cards for code blocks
    │   │   └── CopyAllButton           ← Copy entire message text
    │   │
    │   ├── StreamingMessage            ← Active AI response during streaming
    │   │   ├── MemoizedMarkdown        ← Completed blocks (never re-renders)
    │   │   ├── MarkdownRenderer        ← Tail prose (re-renders each tick)
    │   │   ├── StreamingCodeCard       ← In-progress code block
    │   │   └── TypingIndicator         ← Phase-aware thinking animation
    │   │
    │   └── ContinueButton             ← Shown when response was truncated
    │
    ├── MessageInput                    ← Text input, send/stop, file attachment
    │
    ├── ConfirmModal                    ← Generic confirmation dialog
    ├── InfoModal                       ← Rich info modals (About, Akash, ICP, Model, IPFS)
    └── AutosaveIndicator               ← Save status badge
```

---

## File Structure

```
src-react/
├── App.tsx                     # App root (wraps AppShell in ToastProvider)
├── main.tsx                    # React entry point (createRoot)
├── config.ts                   # Environment config (API URL, version, feature flags)
├── index.html                  # HTML shell (loads icp-auth.js bundle)
│
├── components/
│   ├── chat/
│   │   ├── CodeBlock.tsx       # Collapsible code block with copy/download
│   │   ├── ContinueButton.tsx  # "Continue generating" for truncated responses
│   │   ├── CopyAllButton.tsx   # Copy entire message content
│   │   ├── DownloadCards.tsx    # File download cards extracted from code
│   │   ├── MarkdownRenderer.tsx# Splits rendered HTML into text + CodeBlock segments
│   │   ├── MathBlock.tsx       # KaTeX math rendering component
│   │   ├── Message.tsx         # Static rendered message (user or assistant)
│   │   ├── MessageInput.tsx    # Chat input textarea + controls
│   │   ├── MessageList.tsx     # Scrollable message container + streaming
│   │   └── StreamingMessage.tsx# Live typing animation for AI responses
│   │
│   ├── layout/
│   │   ├── AppShell.tsx        # Main layout + all hook orchestration
│   │   └── EmptyState.tsx      # Welcome screen before first message
│   │
│   ├── modals/
│   │   ├── AuthModal.tsx       # Login/import key/generate identity
│   │   ├── ConfirmModal.tsx    # Generic yes/no confirmation
│   │   ├── InfoModal.tsx       # Rich info about infrastructure
│   │   ├── KeyExportModal.tsx  # Private key display + copy + warnings
│   │   ├── PassphraseModal.tsx # Passphrase setup/unlock flow
│   │   └── WelcomeModal.tsx    # First-time user welcome
│   │
│   ├── notifications/
│   │   ├── AutosaveIndicator.tsx  # Save status badge (saving/saved/error)
│   │   └── ToastProvider.tsx      # Global toast notification stack
│   │
│   └── sidebar/
│       ├── Sidebar.tsx         # Chat list, connection, identity controls
│       └── MemoryPanel.tsx     # Collapsible memory facts display
│
├── hooks/
│   ├── useAuth.ts              # Ed25519 identity management
│   ├── useAutosave.ts          # Debounced save to IndexedDB + cloud
│   ├── useChat.ts              # SSE streaming, send/stop/continue
│   ├── useConnection.ts       # Backend health polling
│   └── usePassphrase.ts       # Passphrase lock/unlock management
│
├── services/
│   └── canister.ts             # ICP canister interaction
│
├── store/
│   ├── index.ts                # Zustand store implementation
│   └── types.ts                # Store state + action type definitions
│
├── types/
│   ├── api.ts                  # Request/response interfaces
│   ├── auth.ts                 # Auth-related interfaces
│   ├── index.ts                # Re-exports
│   └── message.ts              # ChatMessage, SSEEvent, AgentPhase
│
├── utils/
│   ├── codeParser.ts           # Code block extraction + streaming detection
│   ├── crypto.ts               # Browser-side AES-GCM encryption for localStorage
│   ├── indexedDB.ts            # Local-first chat persistence
│   ├── lighthouse.ts           # IPFS gateway utilities
│   ├── logger.ts               # Structured logging utility
│   ├── markdown.ts             # Markdown + math rendering pipeline
│   └── sse.ts                  # Server-Sent Events stream parser
│
└── styles/                     # CSS Modules (11 .module.css files + global)
    ├── tokens.css              # Design tokens (colors, spacing, radii)
    └── global.css              # Base resets and global styles
```

---

## State Management (Zustand)

All application state flows through a single Zustand store. Components subscribe to specific slices using selectors, and state is never mutated directly.

### Store Shape

```typescript
interface StoreState {
  // Chat state
  chatStarted: boolean;                    // Whether a conversation has begun
  chatHistory: ChatMessage[];              // Full conversation (all messages)
  currentChatId: string | null;            // Active chat identifier
  currentUserId: string | null;            // User ID (persisted in localStorage)
  allChats: ChatListItem[];                // Sidebar chat list

  // Auth state
  isAuthenticated: boolean;
  principal: string | null;                // ICP principal text
  username: string | null;
  authenticatedSince: number | null;

  // Memory
  userMemory: UserMemory | null;           // Persistent facts + preferences
  contextMemory: ChatMessage[];            // Sliding window for LLM context
  CONTEXT_WINDOW_SIZE: number;             // Max context messages (default: 50)

  // Autosave
  autosaveStatus: 'idle' | 'saving' | 'saved' | 'error';
  unsavedChanges: boolean;
  lastActivityTime: number | null;

  // UI state
  isGenerating: boolean;                   // AI is streaming
  isLoadingChat: boolean;                  // Chat is being loaded from server
}
```

### Key Actions

| Action | What It Does |
|--------|-------------|
| `reset()` | Starts a new chat — clears history, generates new chat ID |
| `addMessage(role, content)` | Appends to both `chatHistory` and `contextMemory`, marks unsaved |
| `updateContextMemory(message)` | Adds to context window, trims to `CONTEXT_WINDOW_SIZE` |
| `getContextForLLM()` | Returns context snapshot for the API request |
| `setAuthenticated(principal, timestamp)` | Sets auth state |
| `removeLastMessage()` | Removes last message from both history and context |

### Critical Rule

> **Zustand uses setter methods, not direct assignment.** Direct property writes (`State.isAuthenticated = true`) fail silently. Always use setters (`State.setAuthenticated(principal, timestamp)`).

---

## Hooks

### `useAuth` — Identity Management

Manages the Ed25519 keypair lifecycle for self-custody authentication using **deterministic identity derivation**.

```
┌─ useAuth ───────────────────────────────────────────────────────┐
│                                                                  │
│  State:                                                          │
│  ├── isAuthenticated: boolean                                    │
│  ├── principal: string | null                                    │
│  ├── username: string | null                                     │
│  └── authenticatedSince: number | null                           │
│                                                                  │
│  Identity (useRef):                                              │
│  └── Ed25519Identity object (keypair + signing)                  │
│                                                                  │
│  Actions:                                                        │
│  ├── initialize()    → Restore from encrypted localStorage       │
│  ├── register(user, pass) → Derive keypair + register on ICP    │
│  ├── signIn(user, pass) → Derive keypair + verify on-chain      │
│  ├── logout()        → Clear identity + localStorage             │
│  ├── exportKey()     → Return private key hex + principal        │
│  ├── signMessage()   → Ed25519 sign arbitrary data               │
│  └── buildAuthHeaders(endpoint) → 5-header auth set              │
│                                                                  │
│  Auto-behavior:                                                  │
│  └── useEffect on mount → initialize() (restore saved session)   │
└──────────────────────────────────────────────────────────────────┘
```

**Deterministic identity derivation:** No random keypairs. Same username + password always produces the same Ed25519 keypair:
- `deriveIdentitySeed(password, username)` → Argon2id KDF → 32-byte seed
- `Ed25519KeyIdentity.fromSecretKey(seed)` → deterministic keypair
- Private key encrypted with `password + username` via AES-256-GCM → stored in localStorage
- On sign-in: re-derive keypair, compare principal against on-chain registration
- **Export/Import:** `exportKey()` returns private key hex + principal for backup/migration

### `useChat` — Message Streaming

Handles sending messages and processing the streaming response.

```
┌─ useChat ────────────────────────────────────────────────────────┐
│                                                                   │
│  State:                                                           │
│  ├── tokens: string         (accumulated response text)           │
│  ├── isStreaming: boolean    (stream active)                       │
│  ├── phase: AgentPhase      (thinking, searching, tool_use, etc.) │
│  ├── error: Error | null                                          │
│  └── agentResponse: AgentResponse | null (metadata on completion) │
│                                                                   │
│  Actions:                                                         │
│  ├── send(prompt, buildAuthHeaders)                               │
│  │   1. POST to /generate/agent with auth headers                 │
│  │   2. Process SSE stream via streamSSE() utility                │
│  │   3. Accumulate tokens, update phase, detect completion        │
│  │                                                                │
│  ├── continueGeneration(buildAuthHeaders)                         │
│  │   Send continuation prompt with last 200 chars of context      │
│  │                                                                │
│  └── stop()                                                       │
│      Abort via AbortController                                    │
│                                                                   │
│  Key detail: tokens stored in useRef to avoid stale closures      │
│  getTokens() provides current value at any point                  │
└───────────────────────────────────────────────────────────────────┘
```

### `useAutosave` — Persistent Save

```
┌─ useAutosave ────────────────────────────────────────────────────┐
│                                                                   │
│  scheduleAutosave(buildAuthHeaders)                               │
│  └── Debounces for 2 seconds, then calls executeSave()            │
│                                                                   │
│  executeSave(buildAuthHeaders)                                    │
│  ├── 1. Save to IndexedDB immediately (local-first)              │
│  ├── 2. POST to /chat/autosave with auth headers                 │
│  ├── 3. On success: mark synced, set status 'saved'              │
│  └── 4. On failure: queue for later sync, retry up to 5x         │
│         with exponential backoff (1s × 2^n)                       │
│                                                                   │
│  retryPendingSync(buildAuthHeaders)                               │
│  └── Iterates all pending items, retries up to 10 attempts each   │
└───────────────────────────────────────────────────────────────────┘
```

### `useConnection` — Health Monitoring

Polls the backend `/health` endpoint every 30 seconds. Tracks connection status, model name, GPU type, and provider info. Initial check fires after 100ms.

---

## Rendering Pipeline

How a message goes from raw text to rendered HTML with syntax highlighting and math.

### Static Messages (committed to chat history)

```
Raw text from LLM
      │
      ▼
preprocessToolCalls()          Strip XML tool calls, convert code_display to fences
      │
      ▼
protectMath()                  Normalize LaTeX delimiters, replace with placeholders
      │                        \[...\] → $$...$$    \(...\) → $...$
      ▼                        Math → %%MATH_BLOCK_n%% / %%MATH_INLINE_n%%
marked.parse()                 GFM Markdown → HTML (with highlight.js for code)
      │
      ▼
DOMPurify.sanitize()           Strip XSS vectors
      │
      ▼
restoreMath()                  Replace placeholders with KaTeX-rendered HTML
      │
      ▼
MarkdownRenderer               Split HTML into text segments + <pre><code> blocks
      │
      ├── Text segments        → dangerouslySetInnerHTML
      └── Code blocks          → CodeBlock component (collapsible, copyable)
```

### Streaming Messages (during active generation)

```
SSE tokens arriving in real-time
      │
      ▼
Accumulated in tokensRef (useRef, avoids re-render storms)
      │
      ▼
Typing animation (4 chars every 12ms from accumulated buffer)
      │
      ▼
splitAtCompletedBlocks()       Find last completed ``` fence
      │
      ├── Stable text          → MemoizedMarkdown (React.memo, never re-renders)
      │                          Already-completed code blocks stay frozen
      │
      ├── Tail text            → MarkdownRenderer (re-renders each tick)
      │                          Current prose being typed
      │
      └── Unclosed fence       → StreamingCodeCard (live code block)
                                 Shows language + growing code content
```

This architecture prevents the entire message from re-rendering on every character. Only the small "tail" after the last completed block re-renders, while everything above it is memoized.

---

## Authentication Flow

### First-Time User (Registration)

```
┌─ WelcomeModal ───────────────────────────────────────────┐
│                                                           │
│   User enters username + password                         │
│           │                                               │
│           ▼                                               │
│   deriveIdentitySeed(password, username) → Argon2id       │
│           │                                               │
│           ▼                                               │
│   Ed25519KeyIdentity.fromSecretKey(seed)                  │
│           │                                               │
│           ▼                                               │
│   Register principal on ICP canister                      │
│           │                                               │
│           ▼                                               │
│   Encrypt private key with AES-256-GCM (key=pass+user)   │
│           │                                               │
│           ▼                                               │
│   localStorage: trinity_identity_key (encrypted, base64)  │
│   localStorage: trinity_principal (plaintext)             │
│   localStorage: trinity_username (plaintext)              │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Returning User (Sign-In)

1. User enters username + password in WelcomeModal
2. `deriveIdentitySeed(password, username)` → same deterministic seed
3. Reconstruct Ed25519Identity from seed
4. Lookup username on-chain → compare principals
5. If match → encrypt key, store locally, set authenticated state
6. If mismatch → error (wrong password)

### Auto-Restore (Same Browser)

On page load, `useAuth.initialize()` automatically:
1. Reads encrypted key from localStorage
2. If encrypted → requires password re-entry via PassphraseModal
3. Decrypts and reconstructs Ed25519Identity
4. Sets authenticated state

### Request Signing

Every authenticated API call includes 5 headers:

```
ICP-Principal:   <principal text>
ICP-Timestamp:   <Date.now() in milliseconds>
ICP-Nonce:       <16 random bytes, hex encoded>
ICP-PublicKey:   <raw 32-byte public key, hex> (DER[12:], skip prefix)
ICP-Signature:   <Ed25519 sign("<principal>:<timestamp>:<endpoint>:<nonce>"), hex>
```

---

## Data Flow: Sending a Message

```
1. User types in MessageInput, presses Enter
                │
2. AppShell.handleSend()
   ├── Read attached file (if any), prepend to prompt
   ├── store.addMessage('user', prompt)  →  chatHistory + contextMemory updated
   ├── Generate chatId if needed
   └── chat.send(prompt, auth.buildAuthHeaders)
                │
3. useChat.send()
   ├── Create AbortController
   ├── Set isStreaming=true, clear tokens/phase/error
   ├── Build request body: { prompt, principal, context_messages, chat_id, ... }
   ├── POST to /generate/agent with auth headers
   ├── Handle 429 (rate limit) → show error
   └── Iterate streamSSE(response) async generator
                │
4. streamSSE() parses SSE lines → yields SSEEvent objects
   ├── { token: "Hello" }         → append to tokensRef
   ├── { phase: "searching" }     → update phase state
   ├── { done: true, response }   → set agentResponse
   └── { error: "..." }           → set error state
                │
5. Back in AppShell
   ├── chat.getTokens() gets final accumulated text
   ├── store.addMessage('assistant', finalText)
   ├── autosave.scheduleAutosave(auth.buildAuthHeaders)
   └── Refresh chat list in sidebar
```

---

## IndexedDB Storage (Local-First)

The frontend uses IndexedDB as a local-first cache. All chats are saved locally before attempting cloud sync.

```
Database: TrinityChats (v1)
│
├── Object Store: "chats"
│   ├── keyPath: chatId
│   ├── Indexes: principal, lastUpdated
│   └── Record: { chatId, principal, title, messages[], metadata, lastUpdated }
│
└── Object Store: "pendingSync"
    ├── keyPath: chatId
    ├── Index: timestamp
    └── Record: { chatId, chatData, timestamp, retryCount }
```

**Sync strategy:**
1. Save locally to IndexedDB (instant)
2. Attempt cloud sync to `/chat/autosave`
3. If cloud fails → queue in `pendingSync` store
4. On next successful save or app reload → retry all pending items

### Feb 16, 2026 chat persistence fixes

- Autosave now reads the latest Zustand state at execution time (prevents stale chat ID/history writes).
- New chats reliably generate and retain distinct chat IDs before send/autosave.
- Continue-generation updates now patch the active conversation safely.
- Combined with backend artifact filtering, this resolved:
  - false blank "Recovered Chat" entries on fresh accounts,
  - sidebar chat overwrite on "New Chat",
  - partial history saves where only the latest message was persisted.

---

## Sidebar & Chat Management

The sidebar displays all user chats sorted with pinned items first, then by most recent.

```
┌─ Sidebar ──────────────────────────────────────┐
│                                                 │
│  [+ New Chat]                                   │
│                                                 │
│  Connection: 🟢 Connected                       │
│  Model: qwen3:32b                      │
│                                                 │
│  📌 Pinned Chat Title               🗑️         │
│  Recent Chat Title                   🗑️         │
│  Another Chat Title                  🗑️         │
│                                                 │
│  ─────────────────────────────────              │
│  ICP | Akash | IPFS | Model  ← Info badges      │
│  Chats: 5/20                                    │
│                                                 │
│  [Export Key]  [Logout]                         │
└─────────────────────────────────────────────────┘
```

**Actions wired through AppShell:**

| Sidebar Action | AppShell Handler | Backend Call |
|----------------|-----------------|--------------|
| New Chat | `store.reset()` | None |
| Load Chat | Fetch `/chat/:id`, update store | `GET /chat/:id` (auth required) |
| Delete Chat | ConfirmModal → `DELETE /chat/:id` | `DELETE /chat/:id` (auth required) |
| Pin Chat | `POST /chat/:id/pin` | `POST /chat/:id/pin` (auth required) |
| Export Chat | Fetch chat → format as Markdown → download `.md` | `GET /chat/:id` |
| Export Key | Show KeyExportModal | None (local operation) |
| Logout | `auth.logout()` → clear store + localStorage | None |

---

## Build & Deployment

### Build Commands

```bash
npm run dev          # Start React dev server (Vite, port 5173)
npm run build        # Production build → dist/
npm run dev:legacy   # Start legacy vanilla JS dev server
npm run build:legacy # Build legacy frontend → dist/
```

### Build Configuration (Vite)

The React frontend uses `vite.config.react.ts`:
- React plugin for JSX transform
- CSS Modules for scoped styles
- Output to `dist/` directory
- ICP auth bundle (`icp-auth.js`) copied to `dist/` post-build

### ICP Deployment

```bash
dfx deploy --ic trinity_frontend   # Deploy to Internet Computer mainnet
```

Canister ID: `zc67k-kiaaa-aaaal-qtmiq-cai` (or as configured in `canister_ids.json`)

Both the React and legacy builds deploy to the same canister — only one is active at a time depending on which `npm run build` variant was used.

---

## Design System

| Token | Value | Used For |
|-------|-------|----------|
| Background | `#1a1a1a` | App background |
| Text | `#ffffff` | Primary text |
| Border radius | `6px` (elements), `8px` (modals) | Rounded corners |
| Accent | Rainbow gradient on hover | Interactive element borders |
| Labels | Text-only (no emojis) | UI labels and buttons |

Styling uses CSS Modules (`.module.css` files) for component-scoped styles, with `tokens.css` defining shared design tokens and `global.css` for base resets.

---

## Key TypeScript Interfaces

### ChatMessage
```typescript
interface ChatMessage {
  id: number;                    // negative temp ID until persisted
  chatId: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;             // milliseconds
  status: 'pending' | 'persisted';
  timestamp?: number;            // legacy alias
}
```

### AuthHeaders
```typescript
type AuthHeaders = Record<string, string> & {
  'Content-Type': string;
  'ICP-Principal': string;
  'ICP-Signature': string;
  'ICP-Timestamp': string;
  'ICP-PublicKey': string;
  'ICP-Nonce': string;
};
```

### SSEEvent
```typescript
interface SSEEvent {
  type?: 'session';
  chat_id?: string;
  token?: string;
  done?: boolean;
  done_reason?: 'stop' | 'length';
  assistant_message_id?: number;
  phase?: string;
  message?: string;
  error?: string;
  response?: AgentResponse;
}
```

### ConnectionStatus
```typescript
interface ConnectionStatus {
  connected: boolean;
  model: string | null;
  lastChecked: number | null;
  error: string | null;
  gpuType: string | null;
  provider: string | null;
}
```

See [types/](../../trinity-icp/src-react/types/) for the complete type definitions.
