# Trinity AI Copilot Instructions

## Architecture Overview

Trinity is a **fully decentralized AI chat application** with self-custody authentication, encrypted storage, and permanent Filecoin archival. The system consists of:

- **Frontend**: ICP canister (Internet Computer) hosting vanilla JavaScript app
- **Backend**: Akash Network (decentralized cloud) running Python Flask + Ollama
- **Storage**: Two-tier system - active chats on Akash disk, archives on Filecoin/IPFS via Lighthouse SDK
- **Auth**: Ed25519 keypairs with principal-based access control

### Key Components
- `trinity-icp/src/`: Modular frontend (13 modules, Zustand state management)
- `backend/inference_server.py`: Flask backend with auth decorators
- `cloudflare/workers/`: HTTPS proxies to HTTP backends
- `backend/icp_auth.py`: Ed25519 signature verification

### Data Flow
```
User Input → Frontend (ICP) → Cloudflare Worker → Akash Backend → Ollama LLM
                                      ↓
                               Autosave (2s debounce) → Encrypted JSON on Akash disk
                                      ↓
                               Archive Button → Lighthouse → IPFS + Filecoin Deal
```

## Critical Developer Workflows

### Local Development (TinyLlama 1.1B)
```bash
./dev              # Start local backend + open frontend
# Backend: http://localhost:8000, Model: TinyLlama (free, fast)
# Only tests AI inference - NO storage features available locally
```

### Production Testing (Llama 70B)
```bash
./test-prod        # Test against Akash production backend
# Auto-stops local backend, switches to production URL
# Expect 20-30s cold start for first request
```

### Deployment
```bash
./akash-deploy llama70b  # Build Docker image + prepare Akash YAML
# Then manually deploy via https://console.akash.network
cd trinity-icp && dfx deploy --ic trinity_frontend  # Deploy frontend
```

### Testing
```bash
python3 test/integration/test_filecoin_integration.py  # 4/4 tests should pass
curl https://api.trinityai.cc/health         # Backend health check
```

## Project-Specific Conventions

### State Management (Zustand)
**CRITICAL**: Zustand uses read-only getters. Direct assignments fail silently.

❌ **Wrong**:
```javascript
State.isAuthenticated = true;
State.chatHistory = [...];
```

✅ **Correct**:
```javascript
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

Reference: `trinity-icp/src/state/store.js`

### Authentication
- All `/chat/*` endpoints require Ed25519 signatures
- Backend uses `@require_auth` decorator
- Principal ID derived from public key (base32 encoded)
- 5-minute timestamp window for replay protection

Reference: `backend/icp_auth.py`, `backend/inference_server.py`

### Encryption
- AES-256-GCM with PBKDF2 key derivation
- Principal ID used as password (100k iterations)
- Random salt + nonce per encryption
- Files stored as base64-encoded encrypted content

Reference: `backend/inference_server.py` (EncryptionUtils class)

### Memory System
- **contextMemory**: Last 6 messages sent to LLM
- **conversationSummary**: Compressed older messages (every 15 messages)
- **userMemory**: Persistent facts across all chats (stored in `user_memory.json`)

Reference: `trinity-icp/src/state/contextMemory.js`

### UI Design System
- Dark theme: `#1a1a1a` background, `#ffffff` text
- Rainbow gradient borders on hover for interactive elements
- 6px border radius, 8px for modals
- Text-only labels (no emojis)

Reference: `docs/CLAUDE.md#ui-ux-design-system`

### Autosave
- 2-second debounce after each message
- Exponential backoff retry (5 attempts max)
- Rainbow wave animation during save
- Automatic title generation

Reference: `trinity-icp/src/storage/autosave.js`

## Environment Differences

### Local vs Production
| Feature | Local (TinyLlama) | Production (Akash) |
|---------|-------------------|-------------------|
| AI Inference | ✅ TinyLlama 1.1B | ✅ Llama 3.1 70B |
| Autosave | ❌ Not functional | ✅ Encrypted to disk |
| Filecoin Archive | ❌ No Lighthouse config | ✅ Full archival via Lighthouse |
| Context Memory | ⚠️ Works but not persisted | ✅ Full persistence |
| Cost | Free | ~$50-60/month |

**Testing Rule**: Storage features require Akash deployment. Local environment is for AI inference only.

## Integration Points

### External Dependencies
- **Ollama**: Model inference (local + Akash)
- **Lighthouse SDK**: Direct IPFS + Filecoin storage with verified deals
- **Cloudflare Workers**: HTTPS termination and CORS
- **Akash Network**: Decentralized compute (manual deployment via console)
- **ICP**: Frontend hosting (dfx deploy)

### API Endpoints
- `/health`: Status check (no auth)
- `/generate`: AI inference (no auth)
- `/chat/autosave`: Save encrypted chat (Ed25519 required)
- `/chat/list`: List user's chats (Ed25519 required)
- `/chat/<id>`: Load specific chat (Ed25519 required)
- `/chat/archive/<cid>`: Download archive by CID (no auth)

### File Structure Conventions
- Frontend modules: `trinity-icp/src/` with clear separation (auth/, state/, storage/, ui/)
- Backend: `backend/` for Python production code
- Deploy configs: `deploy/` with docker/, akash/, local/ subfolders
- Tests: `test/` with integration/ and local/ subdirs
- Docs: `docs/` with authoritative CLAUDE.md reference

## Common Pitfalls

### Silent Failures
- Zustand direct state assignments don't throw errors but break functionality
- Always use setter methods: `State.setAuthenticated()`, not `State.isAuthenticated =`

### Environment Confusion
- Local testing shows "storage working" but it's actually broken
- Always test storage features against production Akash backend

### Cold Starts
- First request after Akash deployment takes 20-30 seconds (LLM loading)
- This is expected behavior, not a bug

### Archive Limits
- Maximum 10 archived chats per user
- Archive button moves current chat to read-only and starts new chat

Reference: `docs/CLAUDE.md#next-steps-analysis`