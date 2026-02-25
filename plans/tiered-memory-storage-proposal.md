# Trinity Tiered Memory & Storage Architecture

> **Status:** Proposal  
> **Author:** AI Copilot + gduby  
> **Date:** February 20, 2026  
> **Scope:** Frontend smart loading, backend tier-aware context, KV cache optimization

---

## Executive Summary

Trinity's current memory and storage architecture loads everything eagerly — 200 messages per chat switch, all chat titles on sidebar render, no conversation lifecycle management beyond a boolean archive flag, unbounded state store caching, and flat retrieval scoring that treats a one-off question from three weeks ago the same as an active deep discussion.

This proposal introduces a **2-tier conversation model** (Active / Archived), **smart frontend loading** (paginated messages, virtualized sidebar, tier-grouped UI), **backend tier-aware context** (weighted retrieval, cross-conversation summaries, state store eviction), and **KV cache optimization** (shared system-prompt prefix caching). Each phase delivers standalone value. No data migrations, no schema changes, no breaking API changes.

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Design Philosophy](#2-design-philosophy)
3. [Tier Definitions](#3-tier-definitions)
4. [Phase 1 — Frontend Smart Loading](#4-phase-1--frontend-smart-loading)
5. [Phase 2 — Backend Tier-Aware Context & Eviction](#5-phase-2--backend-tier-aware-context--eviction)
6. [Phase 3 — KV Cache Optimization](#6-phase-3--kv-cache-optimization)
7. [Phase 4 — Future (Deferred)](#7-phase-4--future-deferred)
8. [Architecture Diagram](#8-architecture-diagram)
9. [Hardware Constraints & Budget](#9-hardware-constraints--budget)
10. [File Change Map](#10-file-change-map)
11. [Key Decisions & Rationale](#11-key-decisions--rationale)
12. [Verification Checklist](#12-verification-checklist)

---

## 1. Current State Analysis

### What exists today

| Area | Current Behavior | Problem |
|------|-----------------|---------|
| **Message loading** | Frontend fetches `GET /chat/{id}?limit=200` on every chat switch | 50-500KB per switch, all in JS memory, no pagination wired |
| **Sidebar** | `.map()` renders all chats, all titles decrypted server-side in one call | No virtualization, sluggish at 100+ chats |
| **Archive** | `archived` boolean flag on `chats` table | No behavioral difference — archived chats still load in sidebar, no auto-archival |
| **State stores** | `_state_stores: Dict[str, PrincipalStateStore]` — never evicted | Unbounded open SQLite connections, memory grows linearly with principals |
| **Retrieval scoring** | `similarity × 0.60 + importance × 0.25 + recency × 0.15` | All facts scored equally regardless of source conversation tier |
| **KV cache** | `cache_prompt: true` in API requests (in-memory prefix reuse) | No disk persistence, no per-conversation snapshots, cache lost on restart |
| **Chat data location** | Ephemeral disk at `/var/lib/trinity/chats/` | Survives restarts, not redeployments (IPFS checkpoint is backup) |
| **Context loading** | 25 messages + summary + top 20 knowledge items per request | No cross-conversation awareness, no tier differentiation |
| **Conversation summaries** | Rolling summary every 10 messages via 8B ingest model | Exists but underutilized — not used for cross-conversation context |

### Backend pagination exists but frontend doesn't use it

The `GET /chat/<chat_id>` endpoint already supports cursor-based pagination:

```
GET /chat/{id}?limit=50&before_message_id=123
→ { messages: [...], pagination: { has_more: true, returned: 50 } }
```

The `get_messages()` method in `state_store.py` uses `message_id` (autoincrement) as a stable cursor, orders by `message_id DESC`, applies `LIMIT`, and reverses to chronological. The frontend just never calls it with pagination params.

### Hardware budget

| Resource | Production (A100-40GB) | Tier 3 (A100-80GB) |
|----------|----------------------|---------------------|
| GPU VRAM | 40 GB | 80 GB |
| System RAM | 48 Gi | 64 Gi |
| Ephemeral disk | 10 Gi | 10 Gi |
| Persistent disk (models only) | 80 Gi | 120 Gi |
| Chat model VRAM | ~19 GB (qwen3-32b Q4_K_M) | ~19 GB |
| Ingest model VRAM | ~5 GB (qwen3-8b Q4_K_M) | ~5 GB |
| KV cache per slot (65K ctx, q8_0) | **~8 GB** | **~8 GB** |
| Available for KV after models | ~14 GB (1 slot) | ~54 GB (6 slots) |
| Max concurrent users (SQLite) | ~200-2000 (5-50 MB/user) | Same |

---

## 2. Design Philosophy

Straight from the MicroGPT playbook: **don't over-engineer, don't waste resources, smartly engineer.**

- **Both tiers keep all data.** The difference is how eagerly data is loaded into RAM and LLM context, not what's stored on disk. No data loss, no compression, no deletion.
- **Two tiers, not three.** "Ongoing" and "Current" collapse into "Active." If you touched it this week, it's active. The summary system + fast pagination handle quick switching between any active conversations without needing a middle tier.
- **Each phase delivers standalone value.** Phase 1 (frontend) works without Phase 2 (backend). Phase 2 works without Phase 3 (KV). No phase depends on another.
- **No schema migrations.** All changes use existing columns (`archived`, `updated_at`, `pinned`) and existing APIs. New behavior, same data model.
- **Scalability-aware from day one.** Every design choice is evaluated against "what happens with 100 users." Per-user KV caching at 8 GB/slot doesn't scale on A100-40GB — so we defer it. Shared prefix caching scales to infinite users.

---

## 3. Tier Definitions

| Tier | Definition | Promotion | Demotion |
|------|-----------|-----------|----------|
| **Active** | Current conversation + any conversation touched in the last 7 days | Any message sent/received, or user opens the chat | Untouched for 7+ days AND not pinned → auto-archived |
| **Archived** | Not touched in 7+ days, or explicitly archived by user | User opens it (touch updates `updated_at`, auto-promotes to Active) | N/A (already bottom tier) |

### Behavioral differences by tier

| Behavior | Active | Archived |
|----------|--------|----------|
| Sidebar placement | "Recent" section (expanded) | "Archived" section (collapsed) |
| Message loading | Paginated, 50 per page | Same (paginated, 50 per page) |
| Knowledge retrieval weight | 1.0× | 0.6× |
| Cross-conversation summary injection | Yes (top 2-3 active chats) | No |
| LLM context window | Full (65K) | Reduced (16K) — summary + last 10 messages |
| Auto-archival | Exempt (by definition) | N/A |

### Zero-risk rollout

Opening an archived conversation auto-promotes it to Active (updates `updated_at`). The user sees no difference in capability — they can continue right where they left off. The tier only affects background behavior (retrieval weighting, context budget) until the user actively re-engages.

---

## 4. Phase 1 — Frontend Smart Loading

**Goal:** Reduce client-side memory usage and improve perceived performance. No backend changes needed.

### 4.1 Paginated message loading

**File:** `trinity-icp/src-react/components/layout/AppShell.tsx`

**Current:** `handleLoadChat` fetches `GET /chat/{id}?limit=200`, dumps all messages into `chatHistory`.

**Proposed:**
1. Change initial fetch to `?limit=50` (most recent 50 messages)
2. Store `pagination.has_more` and the smallest `message_id` from the response
3. Wire a "Load earlier messages" trigger (either a button or IntersectionObserver at the top of the message list)
4. On trigger: `GET /chat/{id}?limit=50&before_message_id={oldest_id}`, prepend to `chatHistory`
5. Maintain scroll position after prepending (anchor to the previously-top-visible message)

**Store change:** `trinity-icp/src-react/store/index.ts` — add `prependMessages(messages: ChatMessage[])` action that inserts at the beginning of `chatHistory` and updates `contextMemory` window.

```typescript
// New store action
prependMessages: (messages: ChatMessage[]) => {
  set((state) => ({
    chatHistory: [...messages, ...state.chatHistory],
    contextMemory: [...messages, ...state.chatHistory].slice(-CONTEXT_WINDOW_SIZE),
  }));
},
```

**Wire in AppShell:**
```typescript
// New state for pagination
const [hasMoreMessages, setHasMoreMessages] = useState(false);
const [oldestMessageId, setOldestMessageId] = useState<number | null>(null);

// Modified handleLoadChat
const response = await fetch(`${CONFIG.API_URL}/chat/${chatId}?limit=50`, { headers });
const data = await response.json();
setHasMoreMessages(data.pagination?.has_more ?? false);
if (data.messages?.length) {
  setOldestMessageId(data.messages[0].id);
}

// New loadMoreMessages function
const loadMoreMessages = async () => {
  if (!currentChatId || !oldestMessageId || !hasMoreMessages) return;
  const response = await fetch(
    `${CONFIG.API_URL}/chat/${currentChatId}?limit=50&before_message_id=${oldestMessageId}`,
    { headers }
  );
  const data = await response.json();
  const normalized = normalizeMessages(currentChatId, data.messages ?? []);
  prependMessages(normalized);
  setHasMoreMessages(data.pagination?.has_more ?? false);
  if (data.messages?.length) {
    setOldestMessageId(data.messages[0].id);
  }
};
```

### 4.2 Sidebar virtualization

**File:** `trinity-icp/src-react/components/sidebar/Sidebar.tsx`

**Current:** Flat `.map()` renders all `ChatItem` components. No virtualization.

**Proposed:**
1. Add `@tanstack/react-virtual` dependency (~3KB gzipped)
2. Replace `.map()` with a virtualized list that only renders visible items
3. Each item is ~56px tall (title + date + actions) — calculate overscan accordingly

```bash
cd trinity-icp && npm install @tanstack/react-virtual
```

```typescript
import { useVirtualizer } from '@tanstack/react-virtual';

const parentRef = useRef<HTMLDivElement>(null);
const virtualizer = useVirtualizer({
  count: sortedChats.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 56,
  overscan: 5,
});
```

### 4.3 Tier-grouped sidebar

**File:** `trinity-icp/src-react/components/sidebar/Sidebar.tsx`

**Current:** All chats in one flat list, sorted by pinned then `lastUpdated`.

**Proposed:**
1. Split `sortedChats` into two arrays using `lastUpdated` and `archived` flag:
   - **Recent:** `lastUpdated > now - 7 days` AND `!archived` (or `pinned`)
   - **Archived:** everything else
2. Render two collapsible sections with headers: "Recent" (expanded) and "Archived (#)" (collapsed)
3. Pure frontend logic — uses existing `ChatListItem.lastUpdated` field

```typescript
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const now = Date.now();

const recentChats = sortedChats.filter(
  (c) => c.pinned || (!c.archived && c.lastUpdated > now - SEVEN_DAYS_MS)
);
const archivedChats = sortedChats.filter(
  (c) => !c.pinned && (c.archived || c.lastUpdated <= now - SEVEN_DAYS_MS)
);
```

### 4.4 What this achieves

| Metric | Before | After |
|--------|--------|-------|
| Data per chat switch | 50-500KB (200 msgs) | 10-100KB (50 msgs) |
| JS memory (messages) | All 200 in `chatHistory` | 50 initially, grows on scroll |
| Sidebar render cost | O(n) DOM nodes for n chats | O(visible) DOM nodes |
| Archived chat visibility | Mixed into main list | Collapsed section, out of the way |

---

## 5. Phase 2 — Backend Tier-Aware Context & Eviction

**Goal:** Make the backend tier-aware. Auto-manage conversation lifecycle. Evict stale state. Weight retrieval by tier.

### 5.1 Auto-archival

**File:** `backend/services/state_store.py`

Add method to `PrincipalStateStore`:

```python
def auto_archive_stale_chats(self, days: int = 7) -> int:
    """Archive chats untouched for `days` days. Pinned chats exempt. Returns count archived."""
    cutoff = int((time.time() - days * 86400) * 1000)  # epoch ms
    with self._lock:
        cursor = self._conn.execute(
            """UPDATE chats SET archived = 1 
               WHERE principal_id = ? AND archived = 0 AND pinned = 0 
               AND updated_at < ?""",
            (self._principal_id, cutoff)
        )
        self._conn.commit()
        return cursor.rowcount
```

**Call site:** Add to `list_chats()` with a throttle — run at most once per hour per principal:

```python
# In list_chats(), before the SELECT:
now = time.time()
if now - self._last_archive_check > 3600:  # 1 hour throttle
    self.auto_archive_stale_chats(days=ARCHIVE_AFTER_DAYS)
    self._last_archive_check = now
```

**New constant in `config.py`:**
```python
ARCHIVE_AFTER_DAYS = int(os.getenv("ARCHIVE_AFTER_DAYS", "7"))
```

### 5.2 State store LRU eviction

**File:** `backend/services/state_store.py`

Replace `_state_stores: Dict[str, PrincipalStateStore]` with an LRU cache:

```python
from collections import OrderedDict

MAX_STATE_STORES = int(os.getenv("MAX_STATE_STORES", "100"))

_state_store_lock = threading.Lock()
_state_stores: OrderedDict[str, PrincipalStateStore] = OrderedDict()

def get_state_store(principal_id: str) -> PrincipalStateStore:
    with _state_store_lock:
        store = _state_stores.get(principal_id)
        if store is not None:
            _state_stores.move_to_end(principal_id)  # mark as recently used
            return store
        
        # Evict oldest if at capacity
        while len(_state_stores) >= MAX_STATE_STORES:
            _, evicted = _state_stores.popitem(last=False)
            try:
                evicted.close()  # close SQLite connection
            except Exception:
                pass
        
        store = PrincipalStateStore(principal_id)
        _state_stores[principal_id] = store
        return store
```

**What `close()` does:** Close the SQLite connection, free the `threading.RLock`, allow GC to reclaim the object. The `state.db` file on disk is untouched — the store is re-created on next access.

**New constant in `config.py`:**
```python
MAX_STATE_STORES = int(os.getenv("MAX_STATE_STORES", "100"))
```

### 5.3 Tier-aware retrieval scoring

**File:** `backend/services/knowledge_store.py`

Currently the scoring formula in `search()` is:
```python
combined = similarity * 0.60 + importance_norm * 0.25 + recency * 0.15
```

**Proposed:** Add a `source_weight` multiplier based on whether the source conversation is archived:

```python
# In search(), after computing combined score:
source_chat_id = item.get("chat_id")
if source_chat_id:
    chat_meta = self._store.get_chat(source_chat_id)
    is_archived = chat_meta and chat_meta.get("archived", False)
    source_weight = ARCHIVE_RETRIEVAL_WEIGHT if is_archived else 1.0
    combined *= source_weight
```

This requires facts/embeddings to carry their source `chat_id`. Currently, the `embeddings_messages` table already has `chat_id` via the `messages` foreign key. For `memory_facts`, we need to add the source `chat_id` at ingestion time (tag in the `category` field or add a nullable `source_chat_id` column — prefer the column for cleanliness).

**Schema addition** (backward-compatible, nullable):
```sql
ALTER TABLE memory_facts ADD COLUMN source_chat_id TEXT DEFAULT NULL;
```

Run as part of the schema validation in `_ensure_schema()`. Existing facts get `NULL` source (treated as active weight 1.0).

**New constant in `config.py`:**
```python
ARCHIVE_RETRIEVAL_WEIGHT = float(os.getenv("ARCHIVE_RETRIEVAL_WEIGHT", "0.6"))
```

### 5.4 Cross-conversation summary injection

**File:** `backend/services/context_loader.py`

Currently `load_context()` loads the summary for the **current** conversation only. 

**Proposed:** Also load summaries from the user's other active (non-archived) conversations, inject as lightweight cross-conversation awareness.

```python
# In load_context(), after loading current conversation summary:
cross_summaries = []
if store and principal_id:
    all_summaries = store.list_conversation_summaries()
    active_chats = store.list_chats(include_archived=False, limit=10)
    active_chat_ids = {c["chat_id"] for c in active_chats if c["chat_id"] != chat_id}
    
    for cid in active_chat_ids:
        if cid in all_summaries and all_summaries[cid].get("summary"):
            cross_summaries.append({
                "chat_id": cid,
                "title": next((c["title"] for c in active_chats if c["chat_id"] == cid), ""),
                "summary": all_summaries[cid]["summary"]
            })
    
    # Take top 3 by recency, budget 500 tokens each (max 1500 total)
    cross_summaries.sort(key=lambda s: all_summaries[s["chat_id"]].get("updated_at", 0), reverse=True)
    cross_summaries = cross_summaries[:3]
```

**Inject into prompt via `prompt_assembler.py`** — add a new section after the current conversation summary:

```
## Other Active Conversations (for cross-reference context)
- "Deployment troubleshooting": User is debugging Akash GPU allocation issues...
- "React refactor": User is migrating sidebar components to use virtualization...
```

**Token budget:** Max 1500 tokens for cross-conversation summaries (configurable). Added to the existing token budget calculation.

**New constant in `config.py`:**
```python
CROSS_CONVERSATION_SUMMARY_BUDGET = int(os.getenv("CROSS_CONVERSATION_SUMMARY_BUDGET", "1500"))
CROSS_CONVERSATION_MAX_CHATS = int(os.getenv("CROSS_CONVERSATION_MAX_CHATS", "3"))
```

### 5.5 What this achieves

| Metric | Before | After |
|--------|--------|-------|
| Stale conversations | Accumulate forever in sidebar | Auto-archived after 7 days (pinned exempt) |
| Open SQLite connections | Unbounded, grows with principals | Capped at 100, LRU eviction |
| Retrieval relevance | All facts weighted equally | Active conversations prioritized (1.0× vs 0.6×) |
| Cross-conversation awareness | None — LLM only sees current conversation | Summaries from top 3 active chats injected |
| File descriptor risk | Grows linearly | Bounded at MAX_STATE_STORES |

---

## 6. Phase 3 — KV Cache Optimization

**Goal:** Reduce time-to-first-token and GPU memory pressure through cache management.

### 6.1 Wire `--prompt-cache` for shared system prefix

**File:** `deploy/docker/startup.sh`

The infrastructure already exists — `PROMPT_CACHE_DIR`, directory creation at `/data/kv_cache` — but the flag is never passed to llama-server.

**Change:** Add `--prompt-cache` to the chat server launch command:

```bash
llama-server \
    --host 0.0.0.0 \
    --port ${CHAT_PORT} \
    --model ${CHAT_MODEL_PATH} \
    --ctx-size ${CHAT_CTX} \
    --n-gpu-layers -1 \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --cont-batching \
    --prompt-cache ${CACHE_DIR}/system_prefix.bin \
    ${CHAT_EXTRA_FLAGS}
```

**What this does:** The first request computes KV for the system prompt prefix (~2000 tokens) and saves it to disk. Subsequent requests with the same prefix skip that computation. The system prompt is identical for all users, so every request benefits.

**Savings estimate:** ~250ms prefill time per request (system prompt is ~2000 tokens, prefill runs at ~8000 tok/s on A100).

**Disk cost:** The cache file is ~250 MB for 2000 tokens of KV state (128 KB/token × 2000). This is on ephemeral storage — acceptable since it's rebuilt on restart.

### 6.2 Reduced context for archived conversations

**File:** `backend/services/context_loader.py`, `backend/services/pipeline.py`

When a user opens an archived conversation, they're typically asking "remind me what this was about" or briefly continuing a resolved topic. Full 65K context is overkill.

**Proposed:** Add a `ctx_budget` field to `RequestContext`:

```python
@dataclass
class RequestContext:
    # ... existing fields ...
    ctx_budget: int = NUM_CTX  # default full context

# In load_context():
chat_meta = store.get_chat(chat_id) if store else None
is_archived = chat_meta and chat_meta.get("archived", False)
ctx_budget = 16384 if is_archived else NUM_CTX  # 16K vs 65K
```

**Pipeline passes this to `chat_stream()`:** The reduced budget means fewer messages are packed into the prompt, and the KV cache uses less VRAM for archived conversations — leaving more room for active conversations.

**Note:** If the user sends a message in an archived conversation, that conversation's `updated_at` is refreshed, promoting it to Active. Subsequent messages get full context. This only affects the first interaction after opening an archived chat.

### 6.3 What this achieves

| Metric | Before | After |
|--------|--------|-------|
| System prefix computation | Recomputed every request | Cached on disk, loaded in ~50ms |
| Time-to-first-token | ~250ms longer than necessary | ~250ms saved per request |
| VRAM for archived conversations | Full 8 GB KV slot | ~2 GB KV (16K ctx) |
| Disk usage for cache | 0 | ~250 MB (ephemeral, rebuilt on restart) |

---

## 7. Phase 4 — Future (Deferred)

These items are documented for future consideration. They are not part of the current implementation plan.

### 7.1 Per-user KV cache via `--slot-save-path`

llama-server supports `--slot-save-path DIR` which enables REST API endpoints for saving/restoring KV cache state per slot. This could enable:
- Save KV state when user switches conversations
- Restore KV state when they switch back (instant context reload)
- Per-user KV files on disk

**Why deferred:** At 8 GB per slot (65K ctx, q8_0), this is only viable on A100-80GB/H100-80GB (6 slots available). On A100-40GB (production), there's room for exactly 1 slot after model weights. Disk writes of 8 GB per save are also expensive. The cost/benefit ratio doesn't justify implementation until: (a) running on 80GB GPUs, (b) implementing slot eviction by LRU, (c) potentially compressing saved slots (gzip: 8 GB → ~2-3 GB).

### 7.2 Conversation search (FTS5)

Add a SQLite FTS5 virtual table on decrypted message content for full-text search across all conversations. Populated lazily (index on read, not write, to avoid decryption overhead on every insert). Frontend search bar in sidebar.

### 7.3 Smart conversation grouping

Cluster related conversations by topic using embedding similarity on their summaries. Auto-generate groups like "Deployment," "React refactor," "Memory system." Display as collapsible folder structure in sidebar.

### 7.4 IPFS archive tiering

Instead of keeping archived conversations in local SQLite forever, checkpoint them to IPFS and evict from local ephemeral disk. Restore on demand when user opens an archived chat. This addresses the ephemeral storage limitation — archived data lives permanently on IPFS, freeing local disk for active conversations.

### 7.5 sqlcipher migration

Switch from per-field AES-256-GCM to whole-DB sqlcipher encryption. Infrastructure exists in `backend/services/db.py` but isn't wired. Eliminates per-read decrypt overhead, simplifies code, enables FTS5 on encrypted data (since the whole DB is transparently encrypted).

---

## 8. Architecture Diagram

### Current flow

```
User opens Trinity
    │
    ▼
GET /chat/list → ALL chats, ALL titles decrypted ──→ Flat sidebar list
    │
    ▼
User clicks chat
    │
    ▼
GET /chat/{id}?limit=200 → ALL messages loaded into JS memory
    │
    ▼
User sends message
    │
    ▼
context_loader: 25 messages + summary + 20 knowledge items (flat scoring)
    │
    ▼
prompt_assembler: token budget (55K available)
    │
    ▼
llama-server: recomputes system prefix KV every time
```

### Proposed flow

```
User opens Trinity
    │
    ▼
GET /chat/list → titles + metadata only
    │
    ├── "Recent" section: active chats (expanded, virtualized)
    └── "Archived" section: stale chats (collapsed, count badge)
    │
    ▼
User clicks a chat
    │
    ├── Active: GET /chat/{id}?limit=50 → paginated, scroll-up loads more
    └── Archived: GET /chat/{id}?limit=50 → same API, reduced LLM context
    │
    ▼
User sends message
    │
    ▼
context_loader:
    ├── Current chat: 25 messages + summary + knowledge (full)
    ├── Cross-chat: summaries from top 3 other active chats (~1500 tokens)
    ├── Knowledge scoring: tier-weighted (active 1.0×, archived 0.6×)
    └── Context budget: 65K (active) or 16K (archived, until re-promoted)
    │
    ▼
prompt_assembler: token budget with cross-conversation section
    │
    ▼
llama-server: system prefix KV loaded from disk cache (~50ms vs ~250ms)
```

---

## 9. Hardware Constraints & Budget

### KV cache math (why per-user caching is deferred)

Qwen3-32B: 64 layers, 8 KV heads (GQA), 128 head dim, q8_0 quantization (1 byte/element).

$$\text{Per token} = 8 \times 128 \times 2 \times 64 \times 1\text{B} = 128\text{ KB}$$

| Context Window | KV Cache Size | Use Case |
|---------------|---------------|----------|
| 65,536 (full) | **8 GB** | Active conversations |
| 16,384 (archived) | **2 GB** | Archived conversations |
| 2,048 (system prefix) | **256 MB** | Shared prompt cache |

| GPU | VRAM After Models (~24 GB) | Full Slots | Archived Slots |
|-----|---------------------------|-----------|---------------|
| A100-40GB | ~14 GB | 1 | 7 |
| A6000-48GB | ~22 GB | 2 | 11 |
| A100-80GB | ~54 GB | 6 | 27 |
| H100-80GB | ~54 GB | 6 | 27 |

**Conclusion:** Per-user KV slot management only makes sense on 80GB GPUs. On production A100-40GB, the single slot is shared across all users via `cache_prompt: true` (in-memory prefix reuse). The `--prompt-cache` addition saves the system prefix to disk — scales to infinite users.

### System RAM budget (48 Gi production)

| Component | Estimated Usage |
|-----------|----------------|
| llama-server processes (CPU side) | ~3-6 GB |
| Python/Flask + FastEmbed | ~1-1.5 GB |
| SQLite connections (100 max, LRU) | ~100-400 MB |
| OS + container overhead | ~500 MB |
| **Total** | **~5-8 GB** |
| **Headroom** | **~40 GB** |

System RAM is not the bottleneck. GPU VRAM and ephemeral disk are the real constraints.

### Ephemeral disk budget (10 Gi)

| Data | Estimated Size |
|------|---------------|
| Per-user state.db (200 users × 25 MB avg) | ~5 GB |
| Prompt cache file | ~250 MB |
| Conversation summaries (in state.db) | Included above |
| Logs, temp files | ~500 MB |
| **Total** | **~6 GB** |
| **Headroom** | **~4 GB** |

At 500+ users, ephemeral disk becomes a concern. Phase 4 IPFS archive tiering addresses this.

---

## 10. File Change Map

### Phase 1 (Frontend)

| File | Change | Risk |
|------|--------|------|
| `trinity-icp/src-react/components/layout/AppShell.tsx` | Paginated loading (`?limit=50`), scroll-up trigger, `loadMoreMessages()` | Low — backend API unchanged |
| `trinity-icp/src-react/components/sidebar/Sidebar.tsx` | Virtualization (`@tanstack/react-virtual`), tier grouping (Recent/Archived sections) | Low — visual only |
| `trinity-icp/src-react/store/index.ts` | Add `prependMessages` action | Low — additive |
| `trinity-icp/package.json` | Add `@tanstack/react-virtual` | Low — small dep |

### Phase 2 (Backend)

| File | Change | Risk |
|------|--------|------|
| `backend/services/state_store.py` | `auto_archive_stale_chats()`, LRU eviction via `OrderedDict`, `_last_archive_check` throttle | Medium — state lifecycle change |
| `backend/services/knowledge_store.py` | Tier-weighted scoring (`source_weight` multiplier) | Low — scoring formula adjustment |
| `backend/services/context_loader.py` | Cross-conversation summary injection, `ctx_budget` for archived chats | Medium — prompt assembly change |
| `backend/services/prompt_assembler.py` | New `cross_conversation_summaries` section in prompt | Low — additive section |
| `backend/config.py` | New constants: `ARCHIVE_AFTER_DAYS`, `MAX_STATE_STORES`, `ARCHIVE_RETRIEVAL_WEIGHT`, `CROSS_CONVERSATION_SUMMARY_BUDGET`, `CROSS_CONVERSATION_MAX_CHATS` | Low — env-configurable |

### Phase 3 (KV Cache)

| File | Change | Risk |
|------|--------|------|
| `deploy/docker/startup.sh` | Add `--prompt-cache ${CACHE_DIR}/system_prefix.bin` flag | Low — single flag |
| `backend/services/context_loader.py` | Set `ctx_budget` from chat archive status | Low — already proposed in Phase 2 |
| `backend/services/pipeline.py` | Pass `ctx_budget` through to `chat_stream()` | Low — parameter threading |

---

## 11. Key Decisions & Rationale

### Why two tiers instead of three?

Original proposal: Archived / Ongoing / Current. The "Ongoing" tier was defined as "frequently returned to, long-running." But in practice, the difference between "ongoing" and "current" is simply recency. If you touched it today, it's current. If you touched it three days ago, it's still relevant. The summary system + fast pagination handle quick switching between any active conversations. A third tier adds classification complexity (how do you distinguish "ongoing" from "current"?) without adding capability.

**Two tiers with auto-promotion** gives the same UX: open any conversation → it becomes active → full context → no perceptible difference from "current."

### Why not per-user KV cache now?

Cost-benefit: 8 GB per slot × N users = untenable on A100-40GB (room for 1 slot total). The shared system prefix cache captures the universal benefit (every user's prompt starts the same way). llama-server's `cache_prompt: true` already handles intra-session prefix reuse for the rest of the prompt. The per-user dream requires 80GB GPUs and a slot eviction system — deferred to Phase 4.

### Why 0.6× weight for archived, not 0× or 0.3×?

Facts from archived conversations are still valuable — "User works at Google" doesn't become less true because the conversation where they said it is archived. But facts from active conversations are more contextually relevant. The 0.6× multiplier dampens archive-sourced facts without silencing them. Edge cases:

- **User mentions their job in an old chat, asks about career advice in a new one:** The job fact still surfaces (0.6 × high similarity ≈ 0.36, plus importance and recency), just ranked below facts from the active conversation.
- **User corrects their job in an active chat:** New fact gets 1.0× weight, old contradicted fact gets 0.6× — contradiction detection + weight differential naturally suppresses the stale fact.

The 0.6 value is environment-configurable (`ARCHIVE_RETRIEVAL_WEIGHT`) for tuning.

### Why cross-conversation summaries instead of cross-conversation messages?

Loading messages from other conversations would be expensive (decrypt, token-budget, context window pressure) and noisy (most messages in other conversations aren't relevant to the current one). Summaries are:
- Already generated (every 10 messages, no new LLM calls)
- Compact (~500 tokens each, budget 1500 total for 3 conversations)
- Topic-focused (the summary prompt emphasizes "main topics, decisions, open questions")
- Sufficient for the LLM to say "you were also discussing X in another conversation" when relevant

### Why auto-archive instead of requiring the user to manage it?

Users don't archive conversations. They just stop using them. Auto-archival with a 7-day window means the sidebar stays clean without user effort, while pinning exempts important long-running conversations. The auto-promotion on open (touching `updated_at`) means there's zero friction to re-engage with an archived conversation.

---

## 12. Verification Checklist

### Phase 1

- [ ] Open a chat with 100+ messages → only 50 load initially
- [ ] Scroll to top → "Load earlier messages" trigger fires → older messages prepend
- [ ] Scroll position maintained after loading older messages
- [ ] Sidebar renders smoothly with 200+ chats (inspect DOM — should only have ~15-20 chat items rendered)
- [ ] Sidebar groups: "Recent" section expanded, "Archived" section collapsed with count
- [ ] Opening an archived chat from sidebar works normally

### Phase 2

- [ ] Create 10 conversations, leave 5 untouched for 7+ days → should auto-archive on next `list_chats()`
- [ ] Pinned conversations never auto-archive
- [ ] `_state_stores` dict never exceeds `MAX_STATE_STORES` entries (test with 150 mock principals)
- [ ] Evicted store can be re-created on next access without data loss
- [ ] Knowledge search: fact from active conversation ranks higher than identical-similarity fact from archived conversation
- [ ] `memory_facts` table has `source_chat_id` column (nullable, backward-compatible)
- [ ] Cross-conversation summaries appear in assembled prompt (inspect log output)
- [ ] Token budget for cross-conversation section stays within 1500 tokens
- [ ] Tests: `cd backend && python -m pytest tests/ -x -q` → all 1055+ pass

### Phase 3

- [ ] `startup.sh` syntax check: `bash -n startup.sh` passes
- [ ] After deploy: `/data/kv_cache/system_prefix.bin` file exists after first request
- [ ] Second request to cold server measurably faster (check Prometheus `llm_time_to_first_token`)
- [ ] Archived conversation uses 16K context budget (verify in logs)
- [ ] Sending a message in archived conversation promotes it to active (next request gets full 65K)

---

## Appendix: MicroGPT Alignment

This proposal follows the MicroGPT philosophy: **use the right-sized tool for each job**.

| Job | Tool | Why |
|-----|------|-----|
| Decide conversation tier | 7-day recency check + boolean flag | No AI needed — it's a timestamp comparison |
| Retrieve cross-conversation context | Existing rolling summaries (8B model) | Already generated, no new LLM calls |
| Weight retrieval by tier | Multiplier on existing score formula | One multiplication per scored item |
| Cache system prompt KV | llama-server `--prompt-cache` flag | Built-in feature, just needs wiring |
| Detect conversation relevance | Existing embedding similarity | Already computed during knowledge search |

No new models, no new training, no new inference calls. Just smarter use of what already exists.
