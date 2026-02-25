# Trinity Tiered Memory & Storage — Implementation Instructions

> **Status:** Active  
> **Source:** `plans/tiered-memory-storage-proposal.md`  
> **Date:** February 23, 2026  
> **Scope:** Phase 1 (Frontend), Phase 2 (Backend), Phase 3 (KV Cache)

---

## Overview

This document contains step-by-step implementation instructions for the Tiered Memory & Storage Architecture proposal. Each phase is self-contained and delivers standalone value. Changes are listed in dependency order within each phase.

**Pre-requisites:**
- Read the proposal: `plans/tiered-memory-storage-proposal.md`
- Read the codebase map: `docs/ai-context/CODEBASE-MAP.md`
- All backend tests pass before starting: `cd backend && python -m pytest tests/ -x -q`

---

## Phase 1 — Frontend Smart Loading

### Goal
Reduce client-side memory usage and improve perceived performance. No backend changes needed — the backend already supports cursor-based pagination.

### 1.1 — Store already has pagination state (VERIFIED — NO CHANGES NEEDED)

The Zustand store at `trinity-icp/src-react/store/index.ts` already has:
- `hasMoreMessages: boolean` — tracks whether more messages exist
- `oldestMessageId: number | null` — cursor for pagination
- `setHasMoreMessages()` / `setOldestMessageId()` — setters
- `prependMessages(messages)` — prepends older messages to `chatHistory`

The store types at `trinity-icp/src-react/store/types.ts` already declare these fields.

**Verification:** ✅ Already implemented.

### 1.2 — AppShell paginated loading (VERIFIED — NO CHANGES NEEDED)

`trinity-icp/src-react/components/layout/AppShell.tsx` already:
- Fetches with `?limit=50` in `handleLoadChat` (line ~358)
- Stores `pagination.has_more` and `oldestMessageId` from response
- Has `loadMoreMessages()` callback (line ~395) that fetches `?limit=50&before_message_id=...`
- Passes `hasMoreMessages` and `onLoadMore` to `<MessageList>`

**Verification:** ✅ Already implemented.

### 1.3 — MessageList scroll-to-load (VERIFIED — NO CHANGES NEEDED)

`trinity-icp/src-react/components/chat/MessageList.tsx` already:
- Has `IntersectionObserver` for the load-more sentinel at top (line ~137)
- Shows "Load earlier messages" button as fallback
- Maintains scroll position after prepending messages

**Verification:** ✅ Already implemented.

### 1.4 — Sidebar virtualization (VERIFIED — NO CHANGES NEEDED)

`trinity-icp/src-react/components/sidebar/Sidebar.tsx` already:
- Uses `@tanstack/react-virtual` (`useVirtualizer`)
- Has tier-grouped sidebar with Recent / Archived sections
- Collapsible "Archived (N)" header
- 56px per chat item, 32px for section header, overscan of 5

**Verification:** ✅ Already implemented.

### 1.5 — Sidebar tier grouping (VERIFIED — NO CHANGES NEEDED)

`trinity-icp/src-react/components/sidebar/Sidebar.tsx` already:
- Defines `SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000`
- Splits `sortedChats` into `recentChats` and `archivedChats` based on `lastUpdated` + `archived` + `pinned`
- Recent: pinned OR (not archived AND updated within 7 days)
- Archived: everything else
- Builds flat virtual list with `VirtualRow` union type

**Verification:** ✅ Already implemented.

### Phase 1 Summary

All Phase 1 frontend changes are already in the codebase. The pagination, virtualization, and tier-grouped sidebar were implemented previously. No frontend changes required.

---

## Phase 2 — Backend Tier-Aware Context & Eviction

### Goal
Make the backend tier-aware. Auto-manage conversation lifecycle. Evict stale state stores. Weight retrieval by tier. Inject cross-conversation summaries.

### 2.1 — Add new config constants

**File:** `backend/config.py`

Add after the existing `MAX_STATE_STORES` constant (around line 162):

```python
# ===== TIERED MEMORY CONFIGURATION =====
ARCHIVE_AFTER_DAYS = int(os.getenv("ARCHIVE_AFTER_DAYS", "7"))
ARCHIVE_RETRIEVAL_WEIGHT = float(os.getenv("ARCHIVE_RETRIEVAL_WEIGHT", "0.6"))
CROSS_CONVERSATION_SUMMARY_BUDGET = int(os.getenv("CROSS_CONVERSATION_SUMMARY_BUDGET", "1500"))
CROSS_CONVERSATION_MAX_CHATS = int(os.getenv("CROSS_CONVERSATION_MAX_CHATS", "3"))
ARCHIVED_CONTEXT_SIZE = int(os.getenv("ARCHIVED_CONTEXT_SIZE", "16384"))
```

**Why:** Centralizes all tier-related configuration. All values are env-overridable for tuning per deployment tier.

### 2.2 — Add `source_chat_id` column to `memory_facts` table

**File:** `backend/services/state_store.py`

In `_init_schema()`, add an ALTER TABLE migration after the CREATE TABLE block to add the nullable column:

```python
# After the CREATE TABLE ... executescript block, add:
try:
    self.conn.execute(
        "ALTER TABLE memory_facts ADD COLUMN source_chat_id TEXT DEFAULT NULL"
    )
    self.conn.commit()
except sqlite3.OperationalError:
    pass  # Column already exists
```

**Why:** Facts need to carry their source conversation ID so retrieval can weight them by tier. The ALTER TABLE is backward-compatible — existing facts get NULL (treated as active weight 1.0).

**Also update `list_facts()`** to include `source_chat_id` in its SELECT and return dict.

**Also update `create_fact()`** to accept and store `source_chat_id` parameter.

### 2.3 — Add auto-archival method to PrincipalStateStore

**File:** `backend/services/state_store.py`

Add a new method to the `PrincipalStateStore` class:

```python
def auto_archive_stale_chats(self, days: int = 7) -> int:
    """Archive chats untouched for `days` days. Pinned chats exempt. Returns count archived."""
    cutoff = int((time.time() - days * 86400) * 1000)  # epoch ms
    with self._lock:
        cursor = self.conn.execute(
            """UPDATE chats SET archived = 1
               WHERE principal_id = ? AND archived = 0 AND pinned = 0
               AND updated_at < ?""",
            (self.principal_id, cutoff)
        )
        self.conn.commit()
        return cursor.rowcount
```

Add a throttle instance variable in `__init__`:
```python
self._last_archive_check: float = 0.0
```

Add auto-archive call at the beginning of `list_chats()`:
```python
# At the start of list_chats(), before the SELECT:
now = time.time()
if now - self._last_archive_check > 3600:  # 1 hour throttle
    try:
        from config import ARCHIVE_AFTER_DAYS
        self.auto_archive_stale_chats(days=ARCHIVE_AFTER_DAYS)
    except Exception as e:
        logger.debug(f"Auto-archive check failed: {e}")
    self._last_archive_check = now
```

**Why:** Users don't archive conversations manually. This keeps the sidebar clean without user effort. Pinned chats are exempt. The throttle prevents running the UPDATE on every API call.

### 2.4 — Tier-aware retrieval scoring in KnowledgeStore

**File:** `backend/services/knowledge_store.py`

Modify `_score_item()` to accept and apply a `source_weight` multiplier:

```python
@staticmethod
def _score_item(
    item_id: int,
    text: str,
    category: str,
    importance: int,
    item_type: ItemType,
    similarity: float,
    created_at: int,
    now_ms: int,
    source_chat_id: Optional[str] = None,
    source_weight: float = 1.0,
) -> KnowledgeItem:
    # ... existing scoring ...
    combined = (
        WEIGHT_SIMILARITY * similarity
        + WEIGHT_IMPORTANCE * importance_norm
        + WEIGHT_RECENCY * recency
    )
    combined *= source_weight  # Apply tier weight
    # ...
```

Add a new method to look up whether a source chat is archived:

```python
def _get_source_weight(self, source_chat_id: Optional[str]) -> float:
    """Return retrieval weight multiplier based on source conversation tier."""
    if not source_chat_id:
        return 1.0  # Unknown source = treat as active
    try:
        from config import ARCHIVE_RETRIEVAL_WEIGHT
        chat_meta = self.store.get_chat(source_chat_id)
        if chat_meta and chat_meta.get("archived", False):
            return ARCHIVE_RETRIEVAL_WEIGHT
    except Exception:
        pass
    return 1.0
```

Wire `_get_source_weight()` into `_search_brute_force()` and `_hydrate_item()` so every scored item gets its tier weight applied.

**Why:** Facts from archived conversations are still valuable but less contextually relevant. The 0.6× multiplier dampens archive-sourced facts without silencing them.

### 2.5 — Cross-conversation summary injection

**File:** `backend/services/context_loader.py`

Add new fields to `RequestContext`:
```python
cross_conversation_summaries: List[Dict] = field(default_factory=list)
is_archived_chat: bool = False
ctx_budget: int = 65536  # Full context by default
```

In `load_context()`, after loading the conversation summary, add:

```python
# --- Check if current chat is archived ---
try:
    chat_meta = store.get_chat(chat_id)
    if chat_meta and chat_meta.get("archived", False):
        ctx.is_archived_chat = True
        from config import ARCHIVED_CONTEXT_SIZE
        ctx.ctx_budget = ARCHIVED_CONTEXT_SIZE
except Exception:
    pass

# --- Load cross-conversation summaries ---
try:
    from config import CROSS_CONVERSATION_MAX_CHATS
    all_summaries = store.list_conversation_summaries()
    active_chats = store.list_chats(include_archived=False, limit=10)
    active_chat_ids = {c["chatId"] for c in active_chats if c["chatId"] != chat_id}

    cross_summaries = []
    for c in active_chats:
        cid = c["chatId"]
        if cid == chat_id or cid not in active_chat_ids:
            continue
        if cid in all_summaries and all_summaries[cid].get("summary"):
            cross_summaries.append({
                "chat_id": cid,
                "title": c.get("title", ""),
                "summary": all_summaries[cid]["summary"],
                "updated_at": all_summaries[cid].get("updated_at", 0),
            })

    cross_summaries.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
    ctx.cross_conversation_summaries = cross_summaries[:CROSS_CONVERSATION_MAX_CHATS]
except Exception as e:
    logger.debug(f"Cross-conversation summary load failed: {e}")
```

**Why:** Loading summaries from other active conversations gives the LLM cross-conversation awareness — it can say "you were also discussing X in another conversation" when relevant.

### 2.6 — Wire cross-conversation summaries into prompt assembly

**File:** `backend/services/prompt_assembler.py`

In `PromptAssembler.assemble()`, add a new parameter `cross_conversation_summaries` and inject them after the conversation summary:

```python
def assemble(
    self,
    question: str,
    # ... existing params ...
    cross_conversation_summaries: Optional[List[Dict]] = None,
) -> List[Dict]:
```

After the conversation summary injection block, add:

```python
# --- Cross-conversation summaries ---
if cross_conversation_summaries:
    from config import CROSS_CONVERSATION_SUMMARY_BUDGET
    cross_parts = ["## Other Active Conversations (for cross-reference context)"]
    cross_tokens = _estimate_tokens(cross_parts[0])
    for cs in cross_conversation_summaries:
        title = cs.get("title", "Untitled")
        summary = cs.get("summary", "")
        line = f'- "{title}": {summary}'
        line_tokens = _estimate_tokens(line)
        if cross_tokens + line_tokens > CROSS_CONVERSATION_SUMMARY_BUDGET:
            break
        cross_parts.append(line)
        cross_tokens += line_tokens
    if len(cross_parts) > 1:
        cross_msg = "\n".join(cross_parts)
        messages.append({"role": "system", "content": cross_msg})
        remaining -= cross_tokens
```

### 2.7 — Wire context through generate route

**File:** `backend/routes/generate.py`

Pass cross-conversation summaries and ctx_budget through to the assembler:

```python
messages = assembler.assemble(
    question=user_prompt,
    context_messages=ctx.messages,
    knowledge_items=ctx.knowledge_items,
    conversation_summary=ctx.conversation_summary,
    search_context="",
    tools_active=has_tools,
    react_mode=has_tools,
    cross_conversation_summaries=ctx.cross_conversation_summaries,
)
```

### 2.8 — Tests to write

All changes must maintain the existing 1028+ test pass rate. Add new tests:

1. **`test_auto_archive`** — Create 10 chats, set 5 to have old `updated_at`. Call `list_chats()`. Verify 5 are archived.
2. **`test_pinned_exempt_from_archive`** — Pinned + old `updated_at` → NOT archived.
3. **`test_source_chat_id_column`** — Create a fact with `source_chat_id`, verify it persists.
4. **`test_tier_weighted_scoring`** — Two identical facts, one from archived chat → archived scores lower.
5. **`test_cross_conversation_summaries`** — Create 5 chats with summaries, load context → top 3 active summaries present.
6. **`test_archived_chat_ctx_budget`** — Load context for archived chat → `ctx_budget` is 16384.

---

## Phase 3 — KV Cache Optimization

### Goal
Reduce time-to-first-token via shared system prompt prefix caching.

### 3.1 — Wire `--prompt-cache` flag in startup.sh

**File:** `deploy/docker/startup.sh`

Add `--prompt-cache` to the chat server launch command (around line 270):

```bash
su -s /bin/bash trinity -c "LD_LIBRARY_PATH=/usr/local/lib llama-server \
    --host 0.0.0.0 \
    --port ${CHAT_PORT} \
    --model ${CHAT_MODEL_PATH} \
    --ctx-size ${CHAT_CTX} \
    --n-gpu-layers -1 \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --cont-batching \
    --prompt-cache ${CACHE_DIR}/system_prefix.bin \
    ${CHAT_EXTRA_FLAGS}" 2>&1 | sed 's/^/[chat-llama] /' &
```

**Why:** The system prompt (~2000 tokens) is identical for all users. Caching its KV state saves ~250ms prefill per request. The cache file is ~250 MB on ephemeral storage — rebuilt automatically on restart.

### 3.2 — Validate startup.sh syntax

After editing, verify:
```bash
bash -n deploy/docker/startup.sh
```

---

## Verification Checklist

### Phase 1 (Frontend — already done)
- [x] Chat loads with `?limit=50`
- [x] "Load earlier messages" trigger works
- [x] Scroll position maintained after prepending
- [x] Sidebar virtualized with `@tanstack/react-virtual`
- [x] Recent / Archived sections in sidebar

### Phase 2 (Backend)
- [ ] `config.py` has all new constants
- [ ] `memory_facts` table has `source_chat_id` column
- [ ] `auto_archive_stale_chats()` archives chats untouched 7+ days
- [ ] Pinned chats never auto-archived
- [ ] `_score_item()` applies `source_weight` multiplier
- [ ] `load_context()` loads cross-conversation summaries
- [ ] `load_context()` sets `ctx_budget` for archived chats
- [ ] `assemble()` injects cross-conversation summary section
- [ ] All 1028+ tests pass: `cd backend && python -m pytest tests/ -x -q`

### Phase 3 (KV Cache)
- [ ] `startup.sh` has `--prompt-cache` flag
- [ ] `bash -n startup.sh` passes

---

## Rollback Plan

All changes are additive. To rollback:
- **Phase 2:** Remove new config constants, revert `_score_item()` signature, remove cross-conversation loading from `load_context()`. No schema rollback needed — the `source_chat_id` column is nullable and ignored if unused.
- **Phase 3:** Remove the `--prompt-cache` flag from `startup.sh`.

No data migrations, no breaking API changes, no schema drops.
