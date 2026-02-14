# Trinity Frontend Modules

> **Last Updated:** February 13, 2026
> **Active Frontend:** Vanilla JS in `trinity-icp/src/`
> **New Frontend:** React 19 + TypeScript in `trinity-icp/src-react/` (not yet deployed)

---

## Vanilla JS Frontend (`trinity-icp/src/` — ACTIVE)

Single-page application deployed to ICP. `app.js` is a thin orchestrator that imports modular code.

### State Management (`state/store.js`)

Zustand store. **CRITICAL:** Direct assignments fail silently — use setter methods.

```javascript
// ❌ WRONG
State.isAuthenticated = true;

// ✅ CORRECT
State.setAuthenticated(principal, timestamp);
```

**Key state:**
- `chatHistory`, `currentChatId`, `allChats`
- `isAuthenticated`, `principal`
- `contextMemory` (sliding window, `CONTEXT_WINDOW_SIZE = 20`)
- `userMemory: { facts: [] }`
- `isGenerating`, `isLoadingChat`, `autosaveStatus`

### Streaming Pipeline (`features/generate.js`)

Three-part DOM strategy during streaming:
1. **stableDiv**: Completed code blocks (updated only when new block finishes)
2. **tailDiv**: Trailing prose + cursor (updated every tick)
3. **streamDiv**: In-progress code block (collapsible `<details>`)

If `done_reason === 'length'` → Continue button appears (chains requests).

### Auth (`auth/authManager.js`)

Ed25519 keypair management. Every API request signed with: Principal + Timestamp + Nonce + Signature. Keys stored in `localStorage`.

### Autosave (`storage/autosave.js`)

Rate-limited (debounce 5s). Sends `POST /chat/autosave` with `chatId` (camelCase). IndexedDB for local-first, server for durability.

### File Structure

```
src/
├── app.js                   # Orchestrator (imports modules, event delegation)
├── config.js                # API endpoints, feature flags
├── core/
│   ├── api.js               # HTTP client, signed requests, streaming
│   ├── sse.js               # SSE parser
│   ├── environment.js       # Endpoint detection
│   └── logger.js            # Structured logging
├── features/
│   ├── generate.js          # Streaming (3-part DOM, code blocks, Continue)
│   ├── auth.js              # Login/logout UI
│   ├── chatManagement.js    # Chat CRUD, sidebar
│   └── memory.js            # User memory modal
├── auth/
│   ├── authManager.js       # Ed25519 keypair management
│   ├── icp-auth.js          # Bundled ICP auth (don't edit)
│   └── keyExportModal.js    # Key export/import
├── state/
│   └── store.js             # Zustand store (CONTEXT_WINDOW_SIZE=20)
├── storage/
│   ├── autosave.js          # Rate-limited autosave
│   ├── indexedDB.js         # Local persistence
│   └── lighthouse.js        # IPFS backup
├── ui/
│   ├── messages.js          # Message rendering, markdown, KaTeX
│   ├── sidebar.js           # Chat list
│   ├── modals.js            # Modal dialogs
│   ├── editMessage.js       # Inline editing
│   ├── codePanel.js         # Code display
│   ├── loadingMessages.js   # Loading indicators
│   ├── notifications.js     # Toast notifications
│   └── rainbowBorder.js     # Visual effects
└── utils/
    ├── crypto.js            # AES-GCM encryption
    ├── math.js              # KaTeX rendering
    └── validation.js        # Input validation
```

---

## React 19 Frontend (`trinity-icp/src-react/` — NEW)

Fully typed TypeScript rewrite. Same Zustand store shape for API compatibility.

### Key Differences from Vanilla
- Hooks-first: `useChat`, `useAuth`, `useConnection`, `useAutosave`
- Component-based: `MessageList`, `StreamingMessage`, `CodeBlock`, `MarkdownRenderer`
- Context-based toasts (`ToastProvider`)
- 137 unit tests via Vitest

### Structure

```
src-react/
├── App.tsx                  # Root (AppShell + ToastProvider)
├── main.tsx                 # React 19 entry
├── store/
│   ├── index.ts             # Zustand store (same shape as vanilla)
│   └── types.ts             # TypeScript interfaces
├── components/
│   ├── layout/              # AppShell, EmptyState
│   ├── chat/                # MessageList, MessageInput, StreamingMessage, CodeBlock
│   ├── sidebar/             # Sidebar
│   ├── modals/              # AuthModal, KeyExportModal, ConfirmModal
│   └── notifications/       # ToastProvider
├── hooks/
│   ├── useChat.ts           # Main chat logic (generate, stream)
│   ├── useAuth.ts           # Auth state + signing
│   ├── useConnection.ts     # Health check
│   └── useAutosave.ts       # Rate-limited autosave
├── utils/
│   ├── api.ts, sse.ts, crypto.ts, markdown.ts, logger.ts
│   └── indexedDB.ts, lighthouse.ts
└── __tests__/               # 137 tests
```

---

## Build & Deploy

```bash
# Vanilla JS (active)
cd trinity-icp && npm run build:legacy

# React (new)
cd trinity-icp && npm run build

# Deploy to ICP
dfx deploy trinity_frontend --network ic

# Local dev
npm run dev:legacy    # Vanilla JS
npm run dev           # React
```

---

## API Contract

Both frontends use the same backend endpoints:

| Action | Endpoint | Method |
|--------|----------|--------|
| Generate | `/generate/agent` | POST (SSE stream) |
| Autosave | `/chat/autosave` | POST (`chatId` field) |
| Load chats | `/chat/list` | GET |
| Load chat | `/chat/<id>` | GET |
| Delete chat | `/chat/<id>` | DELETE |
| User memory | `/user/memory` | GET/POST |
| Health | `/health` | GET |
