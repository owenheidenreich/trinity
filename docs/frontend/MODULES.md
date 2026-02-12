# Trinity Frontend Modules

> **Last Updated:** February 10, 2026  
> **Location:** [trinity-icp/src/](../../trinity-icp/src/)  
> **Framework:** Vanilla JavaScript + Zustand state management
> **See also:** [CODEBASE-MAP.md](../ai-context/CODEBASE-MAP.md) for full project reference

---

## Overview

The frontend is a single-page application deployed to ICP (Internet Computer Protocol).
After refactoring, `app.js` is a 266-line orchestrator that imports modular code from `core/`, `features/`, `auth/`, `state/`, `storage/`, and `ui/`.

```
trinity-icp/src/
├── index.html              # Entry point
├── styles.css              # Global styles (dark theme, 1897 lines)
├── app.js                  # Application orchestrator (266 lines)
├── config.js               # Environment configuration
├── tools.js                # Tool definitions
├── core/                   # Infrastructure modules
│   ├── api.js              # HTTP client, signed requests, streaming (564 lines)
│   ├── environment.js      # Endpoint detection, version check (87 lines)
│   └── logger.js           # Structured logging utility (43 lines)
├── features/               # Feature modules (extracted from app.js)
│   ├── auth.js             # Login/logout UI flow (180 lines)
│   ├── generate.js         # Message send, streaming, stop (377 lines)
│   ├── chatManagement.js   # Load/delete/new chat, sidebar (378 lines)
│   └── memory.js           # User memory CRUD modal (175 lines)
├── auth/                   # Authentication (4 modules)
├── state/                  # State management (2 modules)
├── storage/                # Persistence (3 modules)
├── ui/                     # UI components (9 modules)
├── api/                    # API clients (1 module)
├── utils/                  # Utilities (3 modules)
└── backend_canister/       # ICP canister integration
```

---

## State Management

### state/store.js

Zustand store for centralized state.

**⚠️ CRITICAL:** Zustand uses read-only getters. Direct assignments fail silently!

```javascript
// ❌ WRONG - fails silently
State.isAuthenticated = true;
State.chatHistory = [...];

// ✅ CORRECT - use setter methods
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

**State Shape:**
```javascript
{
    // Chat State
    chatStarted: false,
    chatHistory: [],
    currentChatId: null,
    allChats: [],
    archivedChats: [],
    
    // Authentication
    isAuthenticated: false,
    principal: null,
    authenticatedSince: null,
    
    // User Memory
    userMemory: { facts: [], preferences: {} },
    
    // Context Memory (last 6 messages for LLM)
    contextMemory: [],
    CONTEXT_WINDOW_SIZE: 6,
    
    // Conversation Summary (compressed older messages)
    conversationSummary: null,
    lastSummaryAt: 0,
    SUMMARY_INTERVAL: 15,  // Summarize every 15 messages
    
    // Autosave
    autosaveStatus: 'idle' | 'saving' | 'saved' | 'error',
    unsavedChanges: false,
    
    // UI State
    isGenerating: false,
    isLoadingChat: false
}
```

**Key Actions:**
```javascript
State.reset()                    // New chat
State.addMessage(role, content)  // Add message
State.setChatHistory(messages)   // Replace history
State.setAuthenticated(principal, timestamp)
State.setAutosaveStatus(status)
State.loadChat(chatData)
```

---

### state/contextMemory.js

Manages the sliding context window sent to the LLM.

**Purpose:** Keep only recent messages to fit context window while preserving conversation coherence.

**Functions:**
```javascript
function updateContextMemory(messages) {
    // Keep last 6 messages
    // Older messages go to conversationSummary
}

function getContextForLLM() {
    // Returns: { contextMemory: [...], summary: "..." }
}

function triggerSummarization() {
    // Every 15 messages, compress older context
}
```

---

## Authentication

### auth/authManager.js

Ed25519 keypair and signature management.

**Methods:**
```javascript
AuthManager.initialize()
    // Load ICP auth bundle, restore saved identity

AuthManager.createIdentity()
    // Generate new Ed25519 keypair

AuthManager.signRequest(method, path, body)
    // Create signed headers for API request
    // Returns: { 'ICP-Principal', 'ICP-Timestamp', 'ICP-Signature', 'ICP-PublicKey', 'ICP-Nonce' }

AuthManager.getPrincipal()
    // Get current principal ID

AuthManager.logout()
    // Clear identity from localStorage
```

**Storage:**
- Private key: `localStorage['trinity_identity_key']` (encrypted)
- Principal: `localStorage['trinity_principal']`

---

### auth/icp-auth.js

ICP-specific authentication utilities.

**Functions:**
```javascript
function derivePrincipal(publicKey)
    // Convert Ed25519 public key to ICP principal ID
    // Format: "xxxxx-xxxxx-xxxxx-xxxxx-cai"

function verifySignature(message, signature, publicKey)
    // Verify Ed25519 signature (for testing)
```

---

### auth/auth-entry.js

Authentication entry point and flow coordinator.

**Exports:**
```javascript
async function initializeAuth()
    // Initialize AuthManager, check for existing identity

async function authenticateUser()
    // Full authentication flow with UI feedback

function isAuthenticated()
    // Check current auth state
```

---

### auth/keyExportModal.js

UI for exporting/importing identity keys.

**Functions:**
```javascript
function showExportModal()
    // Display modal with:
    // - Download private key as JSON
    // - Copy to clipboard
    // - QR code for mobile

function importKey(keyData)
    // Restore identity from exported key
```

---

## Storage

### storage/autosave.js

Automatic chat persistence with debouncing.

**Configuration:**
- Debounce: 2 seconds after last change
- Retry: 5 attempts with exponential backoff
- Endpoint: `POST /chat/autosave`

**Functions:**
```javascript
function scheduleAutosave()
    // Debounce and queue save

async function performAutosave()
    // Encrypt and send to backend

function cancelAutosave()
    // Cancel pending save (e.g., on logout)
```

**Flow:**
1. User sends message
2. `scheduleAutosave()` called
3. Wait 2 seconds (debounce)
4. Encrypt chat with principal ID as password
5. POST to `/chat/autosave`
6. Update `autosaveStatus` in store

---

### storage/lighthouse.js

IPFS archival via Lighthouse.

**Functions:**
```javascript
async function archiveChat(chatId)
    // Upload encrypted chat to IPFS
    // Returns CID

async function recoverFromIPFS(cid)
    // Download and decrypt archived chat

async function listArchives()
    // Get all user's IPFS uploads

async function checkDealStatus(cid)
    // Check Filecoin deal status (alias: checkFilecoinDealStatus)
```

---

### storage/indexedDB.js

Local browser storage for offline support.

**Functions:**
```javascript
async function saveToLocal(chatId, data)
    // Save to IndexedDB

async function loadFromLocal(chatId)
    // Load from IndexedDB

async function getAllLocalChats()
    // List locally stored chats

async function syncWithServer()
    // Merge local and server chats
```

---

## UI Components

### ui/index.js

UI module exports and initialization.

```javascript
import { Messages } from './messages.js';
import { Sidebar } from './sidebar.js';
import { Modals } from './modals.js';
import { Notifications } from './notifications.js';
// ... etc

export function initializeUI() {
    Messages.init();
    Sidebar.init();
    Modals.init();
    // ...
}
```

---

### ui/messages.js

Chat message rendering and interactions.

**Functions:**
```javascript
Messages.render(messages)
    // Render message list with KaTeX math

Messages.addMessage(role, content)
    // Append single message with animation

Messages.showTypingIndicator()
Messages.hideTypingIndicator()

Messages.renderMarkdown(content)
    // Parse markdown + KaTeX
```

**Features:**
- Live KaTeX math rendering (`$inline$` and `$$block$$`)
- Code syntax highlighting
- Copy code button
- Message timestamps

---

### ui/sidebar.js

Chat list and navigation.

**Functions:**
```javascript
Sidebar.render(chats)
    // Render chat list

Sidebar.selectChat(chatId)
    // Load and display chat

Sidebar.newChat()
    // Create new conversation

Sidebar.deleteChat(chatId)
    // Delete with confirmation

Sidebar.searchChats(query)
    // Filter chat list
```

---

### ui/modals.js

Modal dialogs.

**Modals:**
```javascript
Modals.showSettingsModal()
Modals.showKeyExportModal()
Modals.showIPFSModal(cid)
Modals.showIPFSStorageModal()
Modals.showDeleteConfirmModal(chatId, onConfirm)
Modals.showErrorModal(title, message)
Modals.close()
```

---

### ui/notifications.js

Toast notifications.

**Functions:**
```javascript
Notifications.show(message, type)
    // type: 'success' | 'error' | 'warning' | 'info'
    // Auto-dismiss after 3 seconds

Notifications.showPersistent(message, type)
    // Requires manual dismiss
```

---

### ui/editMessage.js

Inline message editing (129 lines).

**Functions:**
```javascript
function enableEditMode(messageElement)
    // Replace message content with editable textarea
    // Show save/cancel buttons

function saveEdit(messageElement, newContent)
    // Update message in state
    // Re-render with markdown/KaTeX
    // Trigger autosave

function cancelEdit(messageElement)
    // Restore original content
```

---

### ui/loadingMessages.js

Loading state messages during inference.

**Function:**
```javascript
function getRandomLoadingMessage()
    // Returns random message like:
    // "Thinking deeply..."
    // "Consulting the neural networks..."
    // "Processing your request..."
```

---

### ui/rainbowBorder.js

Rainbow gradient border animations.

**Functions:**
```javascript
function startRainbowAnimation(element)
function stopRainbowAnimation(element)
function applyRainbowWave()  // During autosave
```

**Usage:** Applied to buttons on hover, input field during focus.

---

### ui/domCache.js

DOM element caching for performance.

**Usage:**
```javascript
import { DOM } from './domCache.js';

// Cached lookups
DOM.chatContainer
DOM.messageInput
DOM.sendButton
DOM.sidebar

// Refresh cache after DOM changes
DOM.refresh()
```

---

## Core Modules

### core/api.js

HTTP client with authentication, streaming, and error handling (564 lines).

**Key Functions:**
```javascript
API.authenticatedRequest(path, options)
    // Send request with Ed25519 signed headers
    // Handles auth errors, retries, JSON parsing

API.streamRequest(path, body, onChunk, onDone)
    // Streaming inference with chunk callbacks
    // Handles ReadableStream, SSE parsing

API.request(path, options)
    // Unauthenticated request (for /generate, /health)

API.healthCheck()
    // Check backend availability
```

**Usage pattern:**
```javascript
// Authenticated request
const chats = await API.authenticatedRequest('/chat/list');

// Streaming
await API.streamRequest('/generate/stream', { prompt }, 
    (chunk) => appendToUI(chunk),
    (full) => finalize(full)
);
```

---

### core/environment.js

Endpoint detection and version checking (87 lines).

**Functions:**
```javascript
Environment.detectEndpoint()
    // Auto-detect API URL based on hostname
    // dubya.ai → api.dubya.ai
    // localhost → localhost:8000

Environment.checkVersion()
    // Compare local vs server version
```

---

### core/logger.js

Structured logging utility (43 lines).

**Functions:**
```javascript
Logger.info(module, message, data)
Logger.warn(module, message, data)
Logger.error(module, message, data)
Logger.debug(module, message, data)
```

**Usage:** `Logger.info('Auth', 'Login successful', { principal })`

---

## Feature Modules

### features/auth.js

Authentication UI flow (180 lines). Handles login button, identity creation, and logout.

**Functions:**
```javascript
function handleLogin()
    // Create or restore Ed25519 identity
    // Update UI: hide login, show chat area
    // Trigger autosave sync

function handleLogout()
    // Clear identity, reset state
    // Show login screen

function showAuthStatus(principal)
    // Display truncated principal in header
```

---

### features/generate.js

Message sending and AI response handling (377 lines).

**Functions:**
```javascript
async function sendMessage(content)
    // Add user message to state
    // Build context (last 6 msgs + summary)
    // Stream response from /generate/stream
    // Schedule autosave on completion

function stopGeneration()
    // Abort in-flight request
    // Update UI state

function handleStreamChunk(chunk)
    // Append chunk to assistant message
    // Live KaTeX rendering during stream
```

---

### features/chatManagement.js

Chat CRUD and sidebar management (378 lines).

**Functions:**
```javascript
async function loadChat(chatId)
    // Fetch from /chat/<id>, decrypt, render
    // Add edit buttons to loaded messages

async function deleteChat(chatId)
    // DELETE /chat/<id> with confirmation
    // Remove from sidebar, reset if active

function newChat()
    // Reset state, clear UI
    // Focus message input

function renderSidebar(chats)
    // Render chat list with titles and dates
    // Highlight active chat
```

---

### features/memory.js

User memory management modal (175 lines).

**Functions:**
```javascript
async function showMemoryModal()
    // Fetch user memory from /user/memory
    // Display facts list with delete buttons

async function addFact(fact)
    // POST to /user/memory/fact

async function deleteFact(index)
    // DELETE /user/memory/fact/<index>
```

---

## API

### api/canister-client.js

ICP backend canister integration (350 lines).

Currently all traffic routes through Cloudflare Worker to Akash backend.

```javascript
// USE_CANISTER controlled by config
async function callCanister(method, args) {
    // HTTP API fallback when canister disabled
}
```

---

## Main Application

### app.js

Application orchestrator (266 lines). Thin entry point that imports and composes all modules.

**Structure:**
```javascript
// 1. Import all modules
import { State } from './state/store.js';
import { API } from './core/api.js';
import * as UI from './ui/index.js';
import * as Features from './features/*.js';

// 2. Compose Actions object
const Actions = {
    sendMessage: Features.generate.sendMessage,
    loadChat: Features.chatManagement.loadChat,
    login: Features.auth.handleLogin,
    // ... maps data-action attributes to feature functions
};

// 3. init() — app startup
async function init() {
    // Version check, UI init, environment detection
    // Sidebar render, auth gate
    // Event delegation (all data-action clicks)
    // Mobile keyboard handling
}

// 4. Export globals
export { State, API, UI, Actions };
window.State = State;  // Legacy compat
```

**Event delegation:** All interactive elements use `data-action="actionName"` attributes, routed through a single click handler to the `Actions` object.

---

### config.js

Environment configuration.

```javascript
export const Config = {
    // API endpoints
    API_BASE_URL: 'https://api.dubya.ai',
    
    // ICP canisters
    FRONTEND_CANISTER_ID: 'zc67k-kiaaa-aaaal-qtmiq-cai',
    BACKEND_CANISTER_ID: 'au5zq-2qaaa-aaaal-qtowa-cai',
    
    // Feature flags
    USE_CANISTER: false,  // Use HTTP API instead
    ENABLE_IPFS: true,
    ENABLE_DEBUG: false,
    
    // Limits
    MAX_MESSAGE_LENGTH: 32000,
    CONTEXT_WINDOW_SIZE: 6
};
```

---

### tools.js

Tool definitions for agentic features.

```javascript
export const Tools = {
    webSearch: {
        name: 'web_search',
        description: 'Search the web',
        endpoint: '/tools/search'
    },
    browse: {
        name: 'browse',
        description: 'Fetch webpage content',
        endpoint: '/tools/browse'
    },
    // ...
};
```

---

## Styling

### styles.css

Global styles with dark theme.

**Design System:**
```css
/* Colors */
--bg-primary: #1a1a1a;
--bg-secondary: #2a2a2a;
--text-primary: #ffffff;
--text-secondary: #888888;
--accent: #4a9eff;

/* Borders */
--border-radius: 6px;
--border-radius-lg: 8px;

/* Rainbow gradient (on hover) */
background: linear-gradient(135deg, #ff6b6b, #ffa500, #ffff00, #00ff00, #00bfff, #8a2be2);
```

**Key Classes:**
- `.message-user` / `.message-assistant`
- `.sidebar-chat-item`
- `.modal-overlay` / `.modal-content`
- `.rainbow-border` (animated)
- `.saving-indicator`

---

## Build & Deploy

**Build:**
```bash
cd trinity-icp
npm run build
```

**Deploy to ICP:**
```bash
dfx deploy --network ic
```

**Local Development:**
```bash
npm run dev  # Vite dev server on localhost:5173
```

---

## Testing

**Status:** No frontend tests currently exist.

**Recommended:**
- Add Vitest for unit tests
- Add Playwright for E2E tests

**Priority test targets:**
1. `state/store.js` — State mutations
2. `auth/authManager.js` — Key generation, signing
3. `storage/autosave.js` — Debouncing, retry logic
