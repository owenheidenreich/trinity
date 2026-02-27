# Trinity Pivot: Single-User Private Instance

## Context

The original pivot plan (`trinity-pivot-plan.md`) was designed for a multi-tenant cloud product — provider CRUD endpoints, workspace sessions with TTL, per-user learning pipelines, GPU job scheduling. But Trinity can't compete with frontier AI companies on user acquisition and infrastructure. They have hundreds of millions of users and the infrastructure to support them.

The new direction: **Trinity is a private AI assistant you download and run on your own hardware.** One user, one instance, full control. This changes everything about what's possible and what's unnecessary.

---

## What the Original Plan Gets Wrong

### 1. BYO Provider with CRUD endpoints — wrong abstraction

The original plan proposes 4 new endpoints, encrypted key storage, and a provider registry. For a single local user, this is a settings file. The user edits `.env` to point at a different OpenAI-compatible URL. No API needed.

### 2. Workspace sessions with scoped permissions — unnecessary

The original plan proposes session models, TTL, scope enforcement, and `WORKSPACE_ALLOWED_ROOTS`. For a private instance on your own machine, **you own the filesystem**. The user mounts their project directory and Trinity reads it directly. No session, no scope negotiation, no TTL.

### 3. Continuous learning pipeline — premature

The original plan proposes learning events, feedback endpoints, consent tracking, nightly retraining, deploy gates. The classifiers are 50K-param byte-level transformers that train in seconds on CPU. There's no feedback data yet. Build the feedback UI first, collect data for months, then decide if automated retraining is worth it.

### 4. GPU job scheduler — no problem to solve

Single user = single GPU = no contention. The P0/P1/P2 priority lanes solve a multi-tenant scheduling problem that doesn't exist when one person owns the whole machine.

### 5. Audio transcription and image generation — scope creep

These require either shipping Whisper/SD models (massive download) or calling external APIs (defeats the "private instance" story). Neither builds on what makes Trinity different.

---

## What Single-User Unlocks

These are things that are **impossible or impractical** in multi-tenant but become free in single-user:

### Memory & Knowledge
- **No fact limit**: Currently `PROFILE_MAX_FACTS=25` to control per-user token budgets. Single user can load ALL facts into context.
- **Always-on state store**: No LRU eviction (currently `MAX_STATE_STORES=100`). Keep the SQLite connection open permanently with WAL mode for better performance.
- **Aggressive background indexing**: Ingestion worker currently throttles to avoid starving other users. Single user can use 100% of idle compute for fact extraction, embedding, summarization.
- **Cross-conversation memory**: Currently scoped per-principal. Single user means ALL chats feed into ONE knowledge base — Trinity learns from everything.

### Compute
- **Full GPU utilization**: No need to reserve headroom for other users' requests.
- **Larger context windows**: `NUM_CTX=40960` is conservative for shared GPU. Single user on A100 can push to 65K+ easily, or use the model's full 128K native context.
- **No token quotas**: Remove `TOKEN_QUOTA_DAILY=100000` entirely. Your GPU, your tokens.
- **Longer timeouts**: Current 60s Akash hard limit gone. Let complex ReAct chains run for minutes if needed.

### Filesystem
- **Direct project access**: Mount your actual project directory. Trinity's `read_file`, `write_file`, `search_codebase`, `run_command` tools operate on your real codebase — no upload, no sandbox, no copy.
- **Expand command whitelist**: Currently restricted to `["python", "python3", "pytest", "node"]`. On your own machine, you can allow `git`, `npm`, `cargo`, `make`, etc.
- **Remove 5MB file limit**: `WORKSPACE_MAX_FILE_SIZE` is a shared-resource protection. Your machine, your files.

### Privacy
- **Zero network traffic**: All inference local. No prompts ever leave your machine.
- **Simpler encryption**: Don't need Argon2id KDF (64MB memory cost) for local-only storage. A local passphrase with SQLCipher is sufficient.
- **No ICP dependency**: Auth becomes a local password or nothing at all.

---

## What to Strip Out (~850+ lines)

### Auth System (eliminate)
- `backend/middleware/icp_auth.py` — 375 lines of Ed25519 signature verification, nonce tracking, principal derivation
- Replace with: Simple bearer token or local password check (~20 lines)

### Multi-tenant Isolation (eliminate)
- Per-principal directory logic in `backend/services/state_store/_base.py` — `_user_dir_for_principal()`, LRU eviction, OrderedDict tracking (~80 lines)
- `principal_id` parameter threading through 21 service modules (274 occurrences) — hardcode to `"default"`
- `backend/services/session_manager.py` — per-principal passphrase dict (48 lines) → single global passphrase

### Rate Limiting (simplify)
- `backend/middleware/rate_limit.py` — per-user token quota tracking, IP-based limiting (~200 lines of quota logic)
- Keep: Basic request rate limiting for DoS prevention (if exposed to network), but default to no limits for localhost

### Anonymous Access (eliminate)
- `require_auth_or_anonymous` decorator, synthetic `anon-{ip_hash}` principal generation, `is_anonymous` checks in routes (~50 lines)

### ICP/Blockchain (make optional)
- `backend/routes/passphrase.py` — Lighthouse canary upload (228 lines, keep file but skip upload)
- `trinity-icp/src-react/services/canister.ts` — ICP username registry calls
- `trinity-icp/src-react/hooks/useAuth.ts` — Replace Ed25519 derivation with simple password auth

---

## What to Build

### Phase 0: Docker Packaging (the actual product)

**Goal**: `docker-compose up` starts everything.

**docker-compose.yml**:
- `llama-server` container (chat, port 8081) — pulls GGUF model on first run
- `llama-server` container (ingest, port 8082) — same model, smaller context
- `trinity-backend` container — Flask API, mounts `~/.trinity/` for data persistence
- `trinity-frontend` — pre-built React app served by backend or nginx

**User-facing config** (`.env`):
```
MODEL_NAME=qwen3:8b          # or 32b, 4b, 1.7b
PROJECT_DIR=~/my-project      # mounted into Trinity for code tools
TRINITY_PASSWORD=             # optional, for local auth
BRAVE_SEARCH_API_KEY=         # optional, enables web search
```

**Files to create/modify**:
- New: `docker-compose.yml` (root level)
- New: `deploy/docker/Dockerfile.local` (simplified, no Akash-specific layers)
- New: `startup-local.sh` (model download + service orchestration)
- Modify: `backend/config.py` — local-first defaults
- Modify: `trinity-icp/src-react/config.ts` — default to `localhost:8000`

### Phase 1: Strip Multi-Tenant Overhead

**Goal**: Remove code that only exists for multi-user scenarios.

- Replace `icp_auth.py` with simple local auth middleware (~20 lines)
- Hardcode principal to `"default"` throughout services
- Flatten state store to single `~/.trinity/state.db` (no per-principal dirs)
- Remove token quotas, keep optional rate limiting
- Remove `session_manager.py` (single user = single passphrase)
- Remove anonymous/guest code paths

### Phase 2: Unlock Single-User Power

**Goal**: Remove artificial limits that existed for shared resource protection.

**Memory unlocks** (context_loader.py, prompt_assembler.py):
- Raise `PROFILE_MAX_FACTS` from 25 → 100+
- Raise `SEMANTIC_MEMORY_SIZE` from 8 → 20+
- Raise `WORKING_MEMORY_SIZE` from 5 → 15+
- Keep token budgeting but increase allocations

**Compute unlocks** (config.py):
- Remove `TOKEN_QUOTA_DAILY` / `TOKEN_QUOTA_HOURLY`
- Raise `NUM_CTX` based on detected GPU VRAM
- Raise `DEFAULT_MAX_TOKENS` from 16384 → 32768
- Raise ReAct timeout from 300s → 600s+
- `REACT_MAX_ITERATIONS` from 5 → 10

**Filesystem unlocks** (code_executor.py):
- `WORKSPACE_ROOT` = user's mounted project directory
- Expand `WORKSPACE_ALLOWED_COMMANDS` to include `git`, `npm`, `cargo`, `make`, `pip`, etc.
- Remove `WORKSPACE_MAX_FILE_SIZE` limit (or raise to 50MB)
- Remove `WORKSPACE_MAX_DEPTH=3` limit
- Remove `WORKSPACE_MAX_SEARCH_RESULTS=50` cap

### Phase 3: Frontend for Single-User

**Goal**: Simplify the frontend — no registration flow, no ICP, direct to chat.

- Replace `WelcomeModal` (username+password → Ed25519) with optional local password prompt
- Remove ICP canister calls from `useAuth`
- Remove infrastructure badges (ICP, Akash, IPFS) — not relevant for local
- Add settings panel: model selection, project directory, API keys
- Keep: `MemoryPanel` (fact viewing/editing), `MarkdownRenderer`, `CodeBlock`, chat UI

### Phase 4: Polish for Distribution

- Write "3-step setup" README
- Create GitHub release with tagged versions
- Add auto-update check (compare local version to GitHub releases)
- Add first-run setup wizard (select model based on detected hardware)

---

## What to Keep From the Original Plan

| Original Item | Keep? | Why |
|---|---|---|
| Charts/graph rendering | **Yes** | Frontend-only, visible value, no backend changes |
| BYO provider (simplified) | **Yes** | As a `.env` setting, not CRUD endpoints |
| Feedback collection | **Yes** | Thumbs up/down → state.db. No retraining pipeline yet |
| Continuous learning pipeline | **No** | Premature. Collect feedback data first |
| GPU job scheduler | **No** | No multi-user contention to solve |
| Audio transcription | **No** | Scope creep |
| Image generation | **No** | Scope creep |
| Workspace sessions | **No** | Mount the directory directly |

---

## Hardware Requirements

| Model | RAM | GPU VRAM | Inference Speed | Download Size |
|-------|-----|----------|-----------------|---------------|
| qwen3:1.7b | 4GB | 0 (CPU-only) | ~30-60s/response | ~2GB |
| qwen3:4b | 8GB | 2GB+ | ~15-20s/response | ~4GB |
| qwen3:8b | 16GB | 4GB+ | ~5-10s/response | ~8GB |
| qwen3:32b | 32GB | 20GB+ | ~2-5s/response | ~20GB |

---

## Verification Plan

1. **Packaging**: `docker-compose up` on a fresh machine (with GPU) downloads model and starts all services within 10 minutes
2. **Auth**: Navigate to `localhost:3000`, see chat UI directly (no ICP registration)
3. **Memory**: Send messages, verify facts extracted and recalled in subsequent conversations
4. **Code tools**: Mount a project, ask Trinity to read/search/modify files, verify it works on real filesystem
5. **Persistence**: Stop and restart containers, verify all chats and memory preserved in `~/.trinity/`
6. **Offline**: Disconnect from internet, verify all core features still work (web search gracefully fails)
7. **Tests**: Existing 934+ unit tests still pass (with principal_id hardcoded to "default")
