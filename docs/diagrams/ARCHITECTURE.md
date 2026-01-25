# Trinity Architecture

**Complete system design overview for AI assistants**

---

## 🎯 High-Level Overview

Trinity is a **fully decentralized AI chat application**:
- Frontend hosted on Internet Computer (ICP)
- Backend on Akash Network (decentralized cloud)
- Storage on Filecoin (permanent IPFS)
- Self-custody authentication (Ed25519 keypairs)

**No central server. No password database. User owns everything.**

---

## 🌐 Network Topology

```
User Browser
    ↓ HTTPS
Cloudflare CDN (trinityai.cc)
    ├→ trinity-frontend-proxy → ICP Canister bkyz2-fmaaa-aaaaa-qaaaq-cai
    │                             └→ index.html, app.js, styles.css
    │
    └→ trinity-api-proxy → Akash Network efe65t...
                             └→ Flask Backend → Ollama → Llama 70B
```

### Domain Routing

| URL | Destination | Purpose |
|-----|-------------|---------|
| `https://trinityai.cc/*` | ICP Frontend | HTML/CSS/JS assets |
| `https://api.trinityai.cc/*` | Akash Backend | API endpoints |

### Development Mode (file://)

```
User Browser (file:///.../index.html)
    ↓
app.js detects environment
    ├→ localhost:8000 (if available) → TinyLlama 1.1B
    └→ Akash Production (fallback) → Llama 70B
```

---

## 🏗️ Component Architecture

### 1. Frontend (ICP Canister)

**Technology**: Vanilla JavaScript (no framework)

**Files**:
- `index.html` (68 lines) - HTML structure
- `app.js` (2226 lines) - Main application logic
- `styles.css` (639 lines) - Responsive styling
- `icp-auth.js` (296KB bundled) - ICP authentication libraries

**Modules in app.js**:
```javascript
// 1. CONFIG - Environment detection & API URLs
const CONFIG = {
    TEST_MODE: false,
    API_URL: 'http://efe65t...', // Auto-detected
    switchEnvironment(env) { ... },
    _availableEnvironments: { local, production }
};

// 2. State - Centralized application state
const State = {
    chatHistory: [],
    currentChatId: null,
    isAuthenticated: false,
    principal: null,
    contextMemory: [], // Last 6 messages
    conversationSummary: null
};

// 3. Auth - ICP Identity & Ed25519
const Auth = {
    identity: null, // Ed25519KeyIdentity
    async login() { ... },
    async signMessage(msg) { ... },
    getPublicKeyHex() { ... }
};

// 4. API - Backend communication
const API = {
    async generate(prompt) { ... },
    async autosave(chatData) { ... },
    async archiveChat(chatId) { ... }
};

// 5. UI - DOM manipulation
const UI = {
    elements: {}, // Cached DOM references
    showMessage(type, content) { ... },
    renderSidebar() { ... },
    showEnvironmentSwitcher() { ... }
};

// 6. Actions - Business logic
const Actions = {
    async generate() { ... },
    async checkHealth() { ... },
    async loadChats() { ... }
};

// 7. Autosave - Background persistence
const Autosave = {
    scheduleAutosave(data) { ... },
    executeAutosave() { ... }
};

// 8. Archive - Filecoin storage
const Archive = {
    async initiateArchive(chatId) { ... },
    async recoverFromArchive() { ... }
};
```

**Key Features**:
- Single-page application (no routing)
- Environment auto-detection (file:// vs https://)
- Real-time connection status
- Environment switcher (development mode only)
- Responsive design (mobile + desktop)

**Deployment**:
```bash
cd trinity-icp
dfx deploy --network ic
```

---

### 2. Backend (Akash Network)

**Technology**: Python Flask + Ollama

**Main Files**:
- `inference_server.py` (1014 lines) - Flask API server
- `icp_auth.py` (210 lines) - Ed25519 signature verification

**API Endpoints**:

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | No | Health check + model info |
| `/generate` | POST | No | LLM inference (for now) |
| `/chat/autosave` | POST | ✅ | Save encrypted chat |
| `/chat/list` | GET | ✅ | List user's chats |
| `/chat/<id>` | GET | ✅ | Load specific chat |
| `/chat/<id>` | DELETE | ✅ | Delete chat |
| `/chat/<id>/archive` | POST | ✅ | Archive to Filecoin |
| `/chat/archive-recover/<cid>` | GET | ✅ | Recover from archive |

**Authentication Flow**:
```python
@require_auth  # Decorator on protected endpoints
def protected_route():
    # 1. Extract headers
    x_principal = request.headers.get('X-Principal')
    x_timestamp = request.headers.get('X-Timestamp')
    x_signature = request.headers.get('X-Signature')
    x_public_key = request.headers.get('X-Public-Key')
    
    # 2. Verify signature
    message = f"{x_principal}:{x_timestamp}"
    verify_signature(message, x_signature, x_public_key)
    
    # 3. Check timestamp (5-minute window)
    if abs(time.time() - x_timestamp) > 300:
        abort(401, "Timestamp expired")
    
    # 4. Proceed with request
    return handle_request(x_principal)
```

**Ollama Integration**:
```python
import ollama

response = ollama.generate(
    model='llama3.1:70b',
    prompt=user_message,
    context=recent_messages  # Last 6 messages
)
```

**Storage**:
- Chats saved to `~/.trinity/chats/<principal>/<chat_id>.json`
- AES-256-GCM encryption with PBKDF2 key derivation
- Passphrase derived from user's Principal ID

**Deployment**:
- Docker container on Akash Network
- 2x NVIDIA A100 80GB GPUs
- Ubuntu 22.04 base image
- Ollama + Python Flask

---

### 3. Storage Architecture

#### Layer 1: Active Storage (Akash Backend)

```
User sends message
    ↓
Autosave triggers (2-second debounce)
    ↓
Frontend → /chat/autosave → Backend
    ↓
Encrypt with AES-256-GCM
    ↓
Save to ~/.trinity/chats/{principal}/{chatId}.json
```

**Chat File Format**:
```json
{
  "chatId": "chat-1737484532000-abc123",
  "principal": "abc123...xyz",
  "messages": [
    {
      "id": "msg-1737484532123-xyz",
      "role": "user",
      "content": "Hello!",
      "timestamp": 1737484532123
    },
    {
      "id": "msg-1737484535456-abc",
      "role": "assistant",
      "content": "Hi! How can I help?",
      "timestamp": 1737484535456
    }
  ],
  "metadata": {
    "title": "Hello!",
    "createdAt": 1737484532000,
    "updatedAt": 1737484535456
  }
}
```

**Encryption**:
- Algorithm: AES-256-GCM
- Key Derivation: PBKDF2 (100,000 iterations)
- Salt: Random 16 bytes (stored with ciphertext)
- Passphrase: User's Principal ID

#### Layer 2: Archive Storage (Filecoin/IPFS)

```
User clicks "Archive" button
    ↓
Frontend → /chat/{id}/archive → Backend
    ↓
Read encrypted chat file
    ↓
Upload to Pinata (Filecoin gateway)
    ↓
Get CID (Content Identifier)
    ↓
Return CID to user
    ↓
User saves CID for recovery
```

**Pinata API**:
```python
headers = {
    'Authorization': f'Bearer {PINATA_JWT}',
    'Content-Type': 'application/json'
}

payload = {
    'pinataContent': chat_data,
    'pinataMetadata': {
        'name': f'trinity-chat-{chat_id}',
        'keyvalues': {
            'principal': principal,
            'timestamp': timestamp
        }
    }
}

response = requests.post(
    'https://api.pinata.cloud/pinning/pinJSONToIPFS',
    headers=headers,
    json=payload
)

cid = response.json()['IpfsHash']
```

**Recovery**:
```
User provides CID
    ↓
Frontend → /chat/archive-recover/{cid} → Backend
    ↓
Try multiple IPFS gateways (30s timeout each):
    1. cloudflare-ipfs.com
    2. ipfs.io
    3. dweb.link
    4. gateway.pinata.cloud
    ↓
Download encrypted chat
    ↓
Decrypt with user's Principal-derived key
    ↓
Return chat data to frontend
    ↓
Load into active chat (read-only mode)
```

---

## 🔐 Authentication Architecture

### Self-Custody System

**No passwords. No email. User owns private keys.**

**Key Generation**:
```javascript
// In browser (app.js)
import { Ed25519KeyIdentity } from '@dfinity/identity';

// Generate new identity
const identity = Ed25519KeyIdentity.generate();

// Derive Principal ID
const principal = identity.getPrincipal().toText();
// Example: "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz"

// Export private key
const privateKey = identity.getKeyPair().secretKey;
const privateKeyHex = Array.from(privateKey)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
```

**Storage**:
- Private key stored in browser `localStorage`
- User shown export modal on first login
- User responsible for backing up key

**Message Signing**:
```javascript
// Sign request
const message = `${principal}:${timestamp}`;
const messageBytes = new TextEncoder().encode(message);
const signature = await identity.sign(messageBytes);
const signatureHex = Array.from(signature)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

// Send to backend
headers: {
    'X-Principal': principal,
    'X-Timestamp': timestamp,
    'X-Signature': signatureHex,
    'X-Public-Key': publicKeyHex
}
```

**Backend Verification**:
```python
from cryptography.hazmat.primitives.asymmetric import ed25519

# Parse public key
public_key_bytes = bytes.fromhex(public_key_hex)
public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

# Verify signature
message_bytes = f"{principal}:{timestamp}".encode('utf-8')
signature_bytes = bytes.fromhex(signature_hex)

try:
    public_key.verify(signature_bytes, message_bytes)
    # ✅ Signature valid
except Exception:
    # ❌ Signature invalid
    abort(401, "Invalid signature")
```

---

## 🧠 Context Memory & Summarization

### Sliding Window (Short-Term Memory)

```javascript
const State = {
    contextMemory: [], // Last 6 messages
    CONTEXT_WINDOW_SIZE: 6,
    
    updateContextMemory(message) {
        this.contextMemory.push(message);
        if (this.contextMemory.length > this.CONTEXT_WINDOW_SIZE) {
            this.contextMemory.shift(); // Remove oldest
        }
    }
};
```

**Sent to LLM**:
```json
{
  "prompt": "User's new message",
  "contextMemory": [
    {"role": "user", "content": "Message 1"},
    {"role": "assistant", "content": "Response 1"},
    {"role": "user", "content": "Message 2"},
    {"role": "assistant", "content": "Response 2"},
    {"role": "user", "content": "Message 3"},
    {"role": "assistant", "content": "Response 3"}
  ]
}
```

### Conversation Summarization (Long-Term Memory)

**Triggered every 15 messages**:

```javascript
async compressContext() {
    // Extract messages 0 to (length - 6)
    const messagesToSummarize = this.chatHistory.slice(
        this.lastSummaryAt,
        this.chatHistory.length - 6
    );
    
    // Build summary prompt
    const summaryPrompt = `
        Analyze this conversation and extract key facts:
        - Numbers, dates, values mentioned
        - User preferences or requirements
        - Technical specifications
        - Names of files/functions discussed
        - Decisions made
        
        ${conversationText}
    `;
    
    // Request summary from LLM (no context)
    const summary = await API.generate(summaryPrompt, 0.7, true);
    
    // Update state
    this.conversationSummary = summary;
    this.lastSummaryAt = this.chatHistory.length;
}
```

**Sent to LLM after summarization**:
```json
{
  "prompt": "User's new message",
  "contextMemory": [
    {
      "role": "system",
      "content": "Earlier conversation summary:\n- User is building a React app\n- Database is PostgreSQL\n- API uses REST\n..."
    },
    {"role": "user", "content": "Recent message 1"},
    {"role": "assistant", "content": "Recent response 1"},
    {"role": "user", "content": "Recent message 2"},
    {"role": "assistant", "content": "Recent response 2"},
    {"role": "user", "content": "Recent message 3"},
    {"role": "assistant", "content": "Recent response 3"}
  ]
}
```

**Benefits**:
- Keeps token usage low
- Maintains long-term context
- No conversation length limit
- Automatic compression

---

## 🔄 Data Flow Diagrams

### Message Generation Flow

```
User types message → Click send
    ↓
Actions.generate()
    ├→ State.addMessage('user', content)
    ├→ UI.showMessage('user', content)
    └→ API.generate(prompt, contextMemory)
        ↓
    Flask Backend receives POST /generate
        ├→ Extract prompt & context
        └→ ollama.generate(model, prompt, context)
            ↓
        Ollama → Llama 70B inference
            ↓
        Stream response tokens
            ↓
    Flask returns response JSON
        ↓
    Actions.generate() receives response
        ├→ State.addMessage('assistant', response)
        ├→ UI.showMessage('assistant', response, animate=true)
        └→ Autosave.scheduleAutosave()
```

### Autosave Flow

```
Message added to State
    ↓
Autosave.scheduleAutosave(chatData)
    ├→ Clear existing timeout
    ├→ Set new 2-second timeout
    └→ UI.showAutosaveIndicator('saving')
        ↓
    [2 seconds later]
        ↓
    Autosave.executeAutosave()
        ├→ Build payload: {chatId, messages, metadata}
        └→ API.autosave(payload)
            ↓
        POST /chat/autosave
            ├→ @require_auth (verify signature)
            ├→ Encrypt chat with AES-256-GCM
            ├→ Save to ~/.trinity/chats/{principal}/{chatId}.json
            └→ Return {success: true}
                ↓
        Autosave.executeAutosave() receives response
            ├→ UI.showAutosaveIndicator('success')
            ├→ UI.renderSidebar() (refresh chat list)
            └→ Hide indicator after 2 seconds
```

### Archive Flow

```
User clicks "📦 Archive" in sidebar
    ↓
Archive.initiateArchive(chatId)
    ├→ UI.showConfirmDialog("Archive this chat?")
    └→ [User confirms]
        ↓
    API.archiveChat(chatId)
        ↓
    POST /chat/{chatId}/archive
        ├→ @require_auth
        ├→ Read encrypted chat file
        ├→ Upload to Pinata API
        ├→ Get CID (Filecoin identifier)
        └→ Return {success: true, filepointId: cid}
            ↓
    Archive.showRecoveryIdDialog(cid)
        ├→ Display modal with CID
        ├→ "Copy to Clipboard" button
        └→ Warning: "Save this ID to recover later"
```

---

## 📊 Performance Characteristics

### Frontend

| Metric | Value | Notes |
|--------|-------|-------|
| Initial Load | ~500ms | HTML + CSS + JS |
| Environment Detection | ~2 seconds | Checks localhost + Akash |
| Auth Init | ~1 second | Load ICP libraries |
| Message Render | Instant | DOM manipulation |
| Sidebar Render | ~50ms | Max 50 chats |

### Backend (LOCAL - TinyLlama 1.1B)

| Metric | Value | Notes |
|--------|-------|-------|
| Cold Start | N/A | Always running |
| Token Generation | 50-80 tokens/sec | M1 Mac performance |
| Memory Usage | ~2GB | TinyLlama model size |
| First Token Latency | ~200ms | Almost instant |

### Backend (AKASH - Llama 70B)

| Metric | Value | Notes |
|--------|-------|-------|
| Cold Start | 20-30 seconds | First request after idle |
| Token Generation | 50-100 tokens/sec | 2x A100 performance |
| Memory Usage | ~140GB | Llama 70B model size |
| First Token Latency | 3-5 seconds | Including network |

### Storage

| Operation | Latency | Notes |
|-----------|---------|-------|
| Autosave | ~100ms | Local disk write |
| Load Chat | ~50ms | Local disk read |
| List Chats | ~200ms | Scan directory |
| Archive Upload | ~5 seconds | Upload to Pinata |
| Archive Download | ~10 seconds | IPFS gateway retrieval |

---

## 🔧 Technology Stack

### Frontend
- **Language**: Vanilla JavaScript (ES6+)
- **Libraries**:
  - `@dfinity/identity` - Ed25519 keypairs
  - `@dfinity/principal` - Principal ID derivation
  - `marked.js` - Markdown rendering
  - `highlight.js` - Code syntax highlighting
  - `DOMPurify` - XSS protection

### Backend
- **Language**: Python 3.10
- **Framework**: Flask (lightweight)
- **Dependencies**:
  - `ollama` - LLM inference
  - `cryptography` - Ed25519 verification
  - `flask-cors` - CORS handling
  - `requests` - Pinata API calls
  - `pycryptodome` - AES encryption

### Infrastructure
- **Frontend Hosting**: Internet Computer (ICP)
- **Backend Compute**: Akash Network
- **Storage**: Filecoin (via Pinata)
- **CDN**: Cloudflare
- **Container**: Docker

---

## 🎓 Design Principles

1. **Decentralization First**: No single point of failure
2. **Self-Custody**: User owns keys and data
3. **Privacy by Design**: Encryption at rest
4. **Graceful Degradation**: Works offline (local mode)
5. **Progressive Enhancement**: Environment auto-detection
6. **Simplicity**: Vanilla JS, no complex frameworks
7. **Cost Efficiency**: Local dev free, production optimized
8. **Developer Experience**: Fast iteration, instant feedback

---

## 📚 Related Documentation

- **Development**: [DEVELOPMENT.md](DEVELOPMENT.md)
- **Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Network Diagram**: [diagrams/trinity-network-architecture.md](diagrams/trinity-network-architecture.md)
- **Storage Diagram**: [diagrams/trinity-storage-architecture.md](diagrams/trinity-storage-architecture.md)

---

**Trinity: Decentralized AI, owned by users, built on open protocols.**
