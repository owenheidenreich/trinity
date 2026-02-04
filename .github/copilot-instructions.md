# Trinity AI Copilot Instructions

## Architecture Overview

Trinity is a **fully decentralized AI chat application** with self-custody authentication, encrypted storage, and live KaTeX math rendering. The system consists of:

- **Frontend**: ICP canister (Internet Computer) hosting vanilla JavaScript app
- **Backend**: Akash Network (decentralized cloud) running Python Flask + Ollama
- **Storage**: Encrypted autosave on Akash disk with IPFS backup via Lighthouse SDK
- **Auth**: Ed25519 keypairs with principal-based access control

### Key Components
- `trinity-icp/src/`: Modular frontend (13 modules, Zustand state management)
- `backend/inference_server.py`: Flask backend with auth decorators
- `deploy/cloudflare-worker/`: Cloudflare Worker for SSL termination
- `backend/icp_auth.py`: Ed25519 signature verification

### Data Flow
```
User Input → Frontend (ICP) → Cloudflare Worker → Akash Backend → Ollama LLM
                                      ↓
                               Autosave (2s debounce) → Encrypted JSON on Akash disk
```

## Critical Developer Workflows

### Deployment (Unified Pipeline)
```bash
./scripts/trinity-deploy-production.sh       # Interactive tier selection
./scripts/trinity-deploy-production.sh 2     # Auto-select Tier 2 (Llama 8B ~$50/mo)
./scripts/trinity-deploy-production.sh 3     # Auto-select Tier 3 (Qwen 72B ~$200/mo)
# Handles: Docker build → Push → Akash CLI deploy → Cloudflare update → ICP deploy → Verify
```

### Testing
```bash
curl https://api.dubya.ai/health  # Backend health check
```

## 🔄 MANDATORY: Workflow Checklists

**BEFORE making ANY change, identify which section is affected and complete the FULL checklist.**

See `docs/CLAUDE.md#workflow-checklists-critical` for complete checklists:
- **DOCKER**: Any backend Python file or `deploy/docker/*` change
- **BACKEND**: Any `backend/inference_server.py` or `backend/services/*` change
- **FRONTEND**: Any `trinity-icp/src/*` change
- **AKASH**: Any deployment or `deploy/akash/*` change
- **ICP**: Any canister deployment
- **CSS/UI**: Any `styles.css` or UI component change
- **MEMORY**: Any context or user memory change
- **STORAGE**: Any autosave or encryption change
- **MODEL**: Any prompt or model config change

**Example: Changing backend code**
1. ☐ Python syntax valid
2. ☐ All imports exist
3. ☐ Dockerfile COPY includes all files/dirs
4. ☐ Docker build passes
5. ☐ Container starts without errors
6. ☐ Push to Docker Hub
7. ☐ Update Akash YAML
8. ☐ Redeploy

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

## Model Tiers

| Tier | Model | RAM | Cost |
|------|-------|-----|------|
| 2 | Llama 3.1 8B | 16GB | ~$50/mo |
| 3 | Qwen2.5 72B | 64GB | ~$200/mo |

## Integration Points

### External Dependencies
- **Ollama**: Model inference on Akash
- **Lighthouse SDK**: IPFS backup storage
- **KaTeX**: Live LaTeX math rendering (via jsdelivr CDN)
- **Cloudflare Workers**: SSL termination and proxy for Akash
- **Akash Network**: Decentralized compute (CLI deployment via `provider-services`)
- **ICP**: Frontend + backend canister hosting (dfx deploy)

### API Endpoints
- `/health`: Status check (no auth)
- `/generate`: AI inference (no auth)
- `/chat/autosave`: Save encrypted chat (Ed25519 required)
- `/chat/list`: List user's chats (Ed25519 required)
- `/chat/<id>`: Load specific chat (Ed25519 required)
- `/chat/<id>` DELETE: Delete chat (Ed25519 required)
- `/user/memory`: User memory CRUD (Ed25519 required)

### File Structure Conventions
- Frontend modules: `trinity-icp/src/` with clear separation (auth/, state/, storage/, ui/)
- Backend: `backend/` with modular structure (services/, middleware/, routes/)
- Deploy configs: `deploy/` with docker/, akash/, local/ subfolders
- Docs: `docs/` with authoritative CLAUDE.md reference (includes workflow checklists)

## Common Pitfalls

### Git Slow Operations
- If `git add` or `git status` takes 5+ minutes, check for build artifacts
- `trinity-icp/target/` (Rust, 70MB+) and `trinity-icp/node_modules/` (18MB+) should NOT be tracked
- Delete with `rm -rf trinity-icp/target trinity-icp/node_modules` - they regenerate on build
- Expected project file count: ~1,500 files (not 20,000+)

### Silent Failures
- Zustand direct state assignments don't throw errors but break functionality
- Always use setter methods: `State.setAuthenticated()`, not `State.isAuthenticated =`

### Environment Confusion
- Local testing shows "storage working" but it's actually broken
- Always test storage features against production Akash backend

### Cold Starts
- First request after Akash deployment takes 20-30 seconds (LLM loading)
- This is expected behavior, not a bug

Reference: `docs/CLAUDE.md#next-steps-analysis`