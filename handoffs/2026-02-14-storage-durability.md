# Handoff: Storage Durability & IPFS Persistence

**Date:** February 14, 2026  
**Status:** Implemented, all 721 tests passing

---

## What Was Done

Trinity had a critical gap: user memory (facts, preferences — everything that makes the AI "know" a user) was stored locally on the container and **never synced to IPFS**. Every Akash redeploy wiped it. The vector database (semantic memory for cross-conversation recall) had the same problem — manual sync only, and uploaded unencrypted.

### New: `backend/services/user_data_store.py`

Single unified IPFS persistence pipeline. Replaces scattered, inconsistent sync logic across `chat.py`, `lighthouse.py`, and `storage.py`.

- **Profile sync** — `save_user_memory()` now triggers encrypted IPFS upload in a background thread on every save
- **Vector DB sync** — auto-triggered (debounced: every 10 indexed messages or 60s), encrypted before upload
- **Manifest** — encrypted root document on IPFS tracking CIDs for profile, vector DB, and all chats
- **Restore-on-login** — `ensure_user_data_restored()` runs on first authenticated request per session; downloads and decrypts all artifacts from IPFS if local cache is missing
- **CID cleanup** — unpins superseded CIDs from Lighthouse to manage storage quota

### Modified Files

| File | Change |
|------|--------|
| `backend/storage.py` | `save_user_memory()` triggers IPFS sync. `save_metadata()` now encrypts on disk. `load_metadata()` handles encrypted + legacy plaintext. |
| `backend/services/memory.py` | `index_message()` calls `notify_message_indexed()` for debounced vector DB auto-sync |
| `backend/routes/chat.py` | `GET /user/memory` triggers `ensure_user_data_restored()`. Autosave updates unified manifest. |
| `backend/routes/generate.py` | Both `/generate` and `/generate/agent` call `ensure_user_data_restored()` before `load_user_memory()` — fixes race condition where user sends message before IPFS restore completes |
| `backend/services/__init__.py` | Exports new `user_data_store` functions |

### Security Fixes Included

- Vector DB on IPFS: was **unencrypted raw SQLite** (message text readable) → now AES-256-GCM encrypted
- Metadata on disk: was **plaintext JSON** (chat titles visible) → now encrypted

---

## What's NOT Done Yet (Phase 2 — future work)

- ~~**Smart fact ranking** — still `facts[:10]` array slice, not relevance-ranked~~ ✅ Done (Feb 15 — `_format_user_memory` scores by relevance × 0.5 + importance × 0.3 + recency × 0.2 with token-budget packing)
- ~~**Auto fact extraction** — still depends on LLM voluntarily calling `save_memory`~~ ✅ Done (Feb 15 — `auto_extract_and_save` runs on both user and assistant messages in `/generate` and `/generate/agent`)
- ~~**Raised memory budgets** — still 3 working / 5 semantic / 10 facts (Qwen 32K constraints)~~ ✅ Done (Feb 15 — 5 working / 8 semantic / 2500 token budget, env-configurable)
- ~~**Lighthouse storage monitoring** — no per-user budget tracking endpoint yet~~ ✅ Done (Feb 15 — `GET /admin/storage/status` returns sync status, pending uploads)

### Additional improvements (Feb 15 — Storage & Memory Foundation milestone):
- **IPFS retry logic** — 3-attempt exponential backoff (1s/4s/16s), pending sync queue for at-least-once delivery
- **Temporal fact metadata** — `valid_at`/`invalid_at` fields on facts for temporal reasoning
- **Contradiction handling** — heuristic detection invalidates old facts when new ones contradict (e.g., "lives in NYC" → "lives in LA")
- **Assistant message extraction** — profile facts extracted from assistant responses ("Since you work at Google...")
- **Restore reliability** — failed restores no longer block retries; restore-on-login retries until profile succeeds
- **32 new tests** in `test_memory_foundation.py`, all 808 total tests passing

---

## How to Verify

1. Create user, save facts, send messages
2. Delete local data: `rm -rf /var/lib/trinity/chats/{principal}/`
3. Hit `GET /user/memory` → should restore from IPFS
4. Send a message → AI should reference restored facts in its response
