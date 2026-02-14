# Trinity Frontend Modules

> **Last Updated:** February 2026
> **Active Frontend:** React 19 + TypeScript in `trinity-icp/src-react/` (v3.0.0)
> **Legacy Frontend:** Vanilla JS in `trinity-icp/src/` (v2.8.0, still buildable via `npm run build:legacy`)
>
> For the complete frontend architecture, see [architecture/01-FRONTEND.md](../architecture/01-FRONTEND.md).

---

## React Frontend (`trinity-icp/src-react/` — ACTIVE)

Fully typed TypeScript rewrite using React 19, Zustand, Vite, and CSS Modules.

### Component Tree

```
App
├── ToastProvider                       ← Global toast notification stack
└── AppShell                            ← Main layout orchestrator
    ├── AuthModal → KeyExportModal      ← Identity gate
    ├── Sidebar                         ← Chat list, connection, identity
    ├── EmptyState                      ← Welcome screen
    ├── MessageList                     ← Message container
    │   ├── Message → MarkdownRenderer → CodeBlock
    │   ├── StreamingMessage (live typing, MemoizedMarkdown)
    │   └── ContinueButton
    ├── MessageInput                    ← Text input + send/stop
    ├── ConfirmModal, InfoModal         ← Dialogs
    └── AutosaveIndicator               ← Save status badge
```

### Custom Hooks

| Hook | Purpose |
|------|---------|
| `useAuth` | Ed25519 identity: generate, import, export, sign, build auth headers |
| `useChat` | SSE streaming: send, continue, stop, phase tracking |
| `useAutosave` | Debounced 2s save → IndexedDB (local-first) + cloud sync |
| `useConnection` | `/health` polling every 30s, connection status |

### State Management (Zustand)

```typescript
// CRITICAL: Use setter methods, not direct assignment
State.setAuthenticated(principal, timestamp);  // ✅
State.isAuthenticated = true;                  // ❌ Fails silently
```

**Key state:** `chatHistory`, `contextMemory` (window: 20), `isAuthenticated`, `principal`, `userMemory`, `allChats`, `autosaveStatus`, `isGenerating`

### File Structure

```
src-react/
├── App.tsx, main.tsx, config.ts
├── components/
│   ├── chat/          # CodeBlock, Message, MessageInput, MessageList,
│   │                  # StreamingMessage, MarkdownRenderer, MathBlock,
│   │                  # CopyAllButton, ContinueButton, DownloadCards
│   ├── layout/        # AppShell, EmptyState
│   ├── modals/        # AuthModal, ConfirmModal, InfoModal, KeyExportModal
│   ├── notifications/ # AutosaveIndicator, ToastProvider
│   └── sidebar/       # Sidebar
├── hooks/             # useAuth, useChat, useAutosave, useConnection
├── store/             # Zustand store (index.ts, types.ts)
├── types/             # api.ts, auth.ts, message.ts
├── utils/             # crypto, markdown, sse, indexedDB, lighthouse, codeParser, logger
└── styles/            # CSS Modules + tokens.css + global.css
```

---

## Legacy Vanilla JS Frontend (`trinity-icp/src/`)

Imperative DOM manipulation app. Still buildable but no longer the default.

### Key Differences from React

| Aspect | Legacy | React |
|--------|--------|-------|
| State access | `State.chatHistory` (proxy) | `useStore((s) => s.chatHistory)` |
| Auth | Singleton `AuthManager` | `useAuth()` hook |
| Streaming | `setInterval` typing + DOM construction | `useChat()` hook + `StreamingMessage` |
| Rendering | `marked.parse()` → `innerHTML` | `parseMarkdownWithMath()` → components |
| Sidebar | HTML string template | `<Sidebar>` component |
| Styling | Single `styles.css` | CSS Modules |
| Types | None | Full TypeScript |

### File Structure

```
src/
├── app.js                   # Orchestrator (event delegation)
├── config.js                # API endpoints, feature flags
├── core/                    # api.js, sse.js, environment.js, logger.js
├── features/                # generate.js, auth.js, chatManagement.js, memory.js
├── auth/                    # authManager.js, icp-auth.js, keyExportModal.js
├── state/                   # store.js (Zustand, same shape as React)
├── storage/                 # autosave.js, indexedDB.js, lighthouse.js
├── ui/                      # messages.js, sidebar.js, modals.js, codePanel.js, etc.
└── styles.css               # Single global stylesheet
```

---

## Build & Deploy

```bash
# React (active)
cd trinity-icp && npm run dev         # Dev server (port 5173)
cd trinity-icp && npm run build       # Production build → dist/

# Legacy vanilla JS
cd trinity-icp && npm run dev:legacy
cd trinity-icp && npm run build:legacy

# Deploy to ICP
dfx deploy trinity_frontend --network ic
```

Both builds output to `dist/` and deploy to the same ICP canister.
