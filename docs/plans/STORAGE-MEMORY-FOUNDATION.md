# Storage & Memory Foundation — Milestone 1

> **Created:** February 15, 2026
> **Status:** ✅ Implementation Complete — Ready for Verification
> **Goal:** Make login → restore → chat → extract → persist → redeploy → restore bulletproof

---

## Thesis

IPFS is the **source of truth** for user identity — not a backup. Local disk is cache. When a user logs in, their full memory restores from IPFS. When they chat, facts are extracted and persisted. When the Akash container recycles, nothing is lost. This foundation enables the eventual vision: a portable, encrypted AI identity layer that works across any provider.

This milestone focuses on what we have today — single Ollama provider on Akash — and makes the storage/memory loop unbreakable.

---

## Steps

### Phase A: IPFS Reliability (Steps 1–3)

**1. Add retry logic to IPFS sync**
- File: `backend/services/user_data_store.py`
- Wrap all `upload_to_ipfs()` calls with exponential-backoff retry (3 attempts: 1s, 4s, 16s)
- Add `_pending_syncs` dict for at-least-once delivery — failed uploads retry on next user request
- This is the single most important reliability fix

**2. Add storage monitoring endpoint**
- New: `GET /admin/storage/status`
- Returns per-user sync state: last sync times, pending uploads, total IPFS bytes, manifest CID
- Protected with `@require_auth` + admin check

**3. Wire auto-extraction into all generate paths**
- Currently `auto_extract_and_save()` only runs on `/generate/agent`
- Wire into non-streaming `/generate` endpoint too
- Both paths get the same post-response pipeline: index in vector store + extract facts

### Phase B: Better Facts (Steps 4–7)

**4. Extract from both user AND assistant messages**
- Currently `auto_extract_and_save()` only processes user messages
- Extend to also extract from assistant responses (the AI's summaries are valuable context)
- Existing dedup logic prevents redundant saves

**5. Add temporal metadata to facts**
- Extend fact schema: add `valid_at` (when fact became true) and `invalid_at` (when superseded)
- Update `tool_save_memory()` and `tool_update_memory()` to set these fields
- Migrate existing facts: `valid_at = created_at`, `invalid_at = null`

**6. Improve contradiction handling**
- When dedup detects 0.85–0.95 cosine match, check for contradiction (same category, contradictory content)
- Use heuristic detection: negation words, different values for same attribute
- Contradicted facts: set `invalid_at = now`, save new fact with `valid_at = now`
- No LLM call needed — simple keyword/pattern matching

**7. Use temporal metadata in retrieval scoring**
- Exclude facts with `invalid_at` set (they're superseded)
- Use `valid_at` instead of `created_at` for recency signal in scoring
- Existing formula: relevance × 0.5 + importance × 0.3 + recency × 0.2

### Phase C: Persistence & Reliability (Steps 8–10)

**8. Sync after every agent response**
- Ensure profile sync fires after fact extraction in BOTH generate paths
- Verify vector DB debounced sync is wired into both paths (not just `/generate/agent`)
- Sync manifest after profile or vector DB changes

**9. Improve restore-on-login reliability**
- Add verification after restore: re-read files, confirm decryption succeeds
- Log restore timing (IPFS download + decrypt duration)
- Handle race condition: two simultaneous requests for a new user

**10. Raise memory budgets**
- `WORKING_MEMORY_SIZE`: 3 → 5
- `SEMANTIC_MEMORY_SIZE`: 5 → 8
- `PROFILE_TOKEN_BUDGET`: 1500 → 2500
- All env-configurable, well within Qwen 32K context

### Phase D: Docs & Verification (Steps 11–12)

**11. Update Dockerfile / test deployment**
- No new dependencies this milestone
- Docker build `--platform linux/amd64`, deploy to Akash
- Full loop test: deploy → login → chat → kill → redeploy → login → verify memory

**12. Update docs and close handoff items**
- Update `MEMORY-SYSTEM.md` with temporal fact model
- Update `CODEBASE-MAP.md` and `FEATURE-CATALOG.md`
- Close stale items in `2026-02-14-storage-durability.md`
- Write handoff document

---

## Verification

- `cd backend && python -m pytest tests/ -x -q` — all existing tests pass
- New tests: `test_sync_retry.py`, `test_temporal_facts.py`, `test_extraction_paths.py`
- Manual: deploy → login → facts → kill → redeploy → login → verify restored
- `GET /admin/storage/status` returns correct sync state
- `GET /user/memory` shows `valid_at`/`invalid_at` fields

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| No graph DB this milestone | Get flat facts + IPFS bulletproof first |
| No LLM extraction this milestone | Improve regex, wire all paths. LLM extraction = milestone 2 |
| IPFS = source of truth | Local disk is cache. Manifest on IPFS is authoritative |
| Heuristic contradiction handling | Regex/keyword negation detection covers common cases |
| Conservative budget increases | 5/8/2500 stays well within 32K context |

---

## Future Milestones (Separate)

### Milestone 2: Knowledge Graph + LLM Extraction
- Add Kuzu embedded graph DB (per-user `identity.kuzu`)
- Build LLM-powered entity/relationship extraction (Ollama background thread)
- Graph-augmented retrieval: entity → edge → entity triples in system prompt
- Graph memory tools: `graph_query`, `graph_explore`
- IPFS sync for Kuzu DB as portable identity

### Milestone 3: Multi-Provider Support
- Provider-agnostic conversation routing (OpenAI, Grok, Claude APIs alongside Ollama)
- Common post-response pipeline: any provider → extract → persist → IPFS
- Provider-specific API key management (user brings their own keys)
- Conversation history unified across providers

### Milestone 4: SSL / Networking Simplification
- Evaluate Cloudflare Worker alternatives (DNS proxy, in-container Caddy)
- Custom domain with stable SSL on Akash
- Reduce centralized chokepoints
