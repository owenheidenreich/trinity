# Trinity — Memory System Architecture

> Last updated: February 19, 2026

## Overview

Trinity uses a **four-tier memory system** to give every chat context, personality, and persistent knowledge about you across sessions. All persistent state lives in a single per-principal encrypted SQLite database (`state.db`) managed by `services/state_store.py` — there is no separate vector DB file or flat JSON memory file in the runtime path.

The memory system was refactored in Feb 2026 to introduce three new modules:
- **`knowledge_store.py`** — unified retrieval layer (facts + messages + relationships via ANN/brute-force)
- **`ingestion_worker.py`** — background daemon replacing fire-and-forget threads
- **`context_loader.py`** — single function that loads all context (replaces 5 divergent paths)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      MEMORY SYSTEM — FOUR TIERS                            │
│                                                                            │
│  TIER 1 ── CONVERSATION CONTEXT                                            │
│            Last 25 messages from the current chat (server-side load)       │
│            Source: state_store.get_messages(chat_id, limit=25)             │
│                                                                            │
│  TIER 2 ── ROLLING CONVERSATION SUMMARY                                    │
│            LLM-compressed summary of older turns (injected as system msg)  │
│            Source: state_store.conversation_summaries table                │
│            Updater: ingestion_worker daemon (background, qwen3:8b)        │
│                                                                            │
│  TIER 3 ── SEMANTIC RETRIEVAL                                              │
│            Top 20 knowledge items across all chats, ranked by unified score│
│            Source: knowledge_store.search() → facts + messages + relations │
│            Scoring: similarity × 0.6 + importance × 0.25 + recency × 0.15│
│            Model: BAAI/bge-small-en-v1.5 (384-dim)                        │
│                                                                            │
│  TIER 4 ── LONG-TERM USER PROFILE                                          │
│            Persistent facts about the user, scored and budget-packed       │
│            Source: state_store.memory_facts + embeddings_facts tables      │
│            Manages: identity, work, interests, preferences, relationships  │
│                                                                            │
│  All tiers assembled by context_loader.load_context() +                   │
│  prompt_assembler.assemble() before each Ollama inference call.           │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Canonical State Store

Every principal gets their own `state.db` file at `$CHATS_DIR/<principal_id>/state.db`. All memory tiers, messages, embeddings, and ingestion jobs live here.

```
state.db schema
├── chats                  — chat metadata (title, pinned, archived, message_count)
├── messages               — all turns (role, content_enc, created_at, token_count)
├── memory_facts           — persistent user profile facts (text_enc, category, importance, ...)
├── conversation_summaries — rolling LLM-generated summaries per chat_id
├── graph_triples          — subject/predicate/object entity relationships
├── embeddings_messages    — 384-dim vectors for messages (for semantic retrieval)
├── embeddings_facts       — 384-dim vectors for facts (for dedup + recall)
├── ingestion_jobs         — durable async job queue (status: queued/processing/done/failed)
└── sync_checkpoints       — IPFS sync metadata
```

**Indexes on every hot query column** — `principal_id+updated_at DESC` on facts/chats, cascade deletes on messages→embeddings, WAL mode, `PRAGMA busy_timeout = 5000` to handle concurrent chat + ingestion writes.

**Encryption:** all `*_enc` columns are AES-256-GCM encrypted with the user's session passphrase before being written. The database file itself is unencrypted (SQLite); individual fields are encrypted.

---

## Tier 1 — Conversation Context

**Source:** `state_store.get_messages(chat_id, limit=25)`  
**Loaded by:** `generate_agent()` route, server-side only — the frontend does **not** send conversation history in the request body.

```
POST /generate/agent { prompt, chat_id }
│
└── store.get_messages(chat_id=chat_id, limit=25)
    SELECT message_id, role, content_enc, created_at, token_count
    FROM messages
    WHERE principal_id = ? AND chat_id = ?
    ORDER BY message_id ASC
    LIMIT 25
```

**Fast-path bypass:** For trivial greetings (`is_trivial_smalltalk()`) and short non-memory prompts (`_is_lightweight_non_memory_prompt()`), context loading and memory retrieval are skipped entirely to minimize first-token latency.

---

## Tier 2 — Rolling Conversation Summary

**Problem:** A 200-message chat would overflow the LLM context window if sent raw.  
**Solution:** Older turns are incrementally compressed into a summary stored in `state.db`. Only the unsummarized tail is sent as structured messages.

### Summary Generation

Run by the background ingestion worker (`memory_ingestion.py`) after each batch of user/assistant turns:

```
_maybe_update_conversation_summary(principal_id, chat_id)
│
├── Load current summary from state_store.conversation_summaries
├── Check: new messages since last_message_id > SUMMARY_TRIGGER_MESSAGES (10)?
│   └── If not → skip
│
├── Build incremental summary prompt:
│   "Previous summary: <summary>
│    New messages: <rendered turns>
│    Return: concise summary of topics, decisions, open questions"
│
├── POST to OLLAMA_INGEST_HOST/api/chat
│   model=qwen3:8b, think=False, temperature=0.1
│
└── store.upsert_conversation_summary(chat_id, new_summary, latest_message_id)
```

### Summary Injection at Prompt-Build Time

```
build_chat_messages() — context assembly
│
├── If summary exists for chat_id:
│   ├── Append second system message:
│   │   "Conversation summary (older messages): <summary>"
│   └── Include only messages with message_id > last_summarized_id (max 15)
│
└── If no summary:
    └── Include last 20 messages (legacy behavior)
```

This keeps every request under ~15 turns of raw history regardless of total conversation length.

---

## Tier 3 — Semantic Memory Retrieval (via KnowledgeStore)

**Source:** `services/knowledge_store.py` — unified retrieval across facts, messages, and relationships.
**Retrieval:** `context_loader.load_context()` calls `knowledge_store.search()` with the query embedding.

### Indexing (post-generation, async)

Handled by the **ingestion worker** (`services/ingestion_worker.py`), a background daemon thread:

```
Message persisted to state.db → enqueue_ingestion(source, message_id)
│
└── ingestion_worker daemon (event-driven wakeup)
    └── _index_message()
        ├── embed_text(content) → 384-dim BAAI/bge-small-en-v1.5 vector
        └── knowledge_store.index_message(chat_id, message_id, role, content)
```

Both user and assistant messages are indexed via `enqueue_ingestion()`.

### Retrieval (per-request)

```
User prompt → context_loader.load_context()
│
├── embed_text(query) → query_embedding (computed once, reused everywhere)
│
├── knowledge_store.search(query_embedding, top_k=20, item_types=[FACT, MESSAGE, RELATIONSHIP])
│   ├── ANN search via sqlite-vec (if available) or brute-force fallback
│   └── Unified scoring for each result:
│       combined_score = similarity × 0.6 + importance × 0.25 + recency × 0.15
│
└── Results returned as KnowledgeItem[] in RequestContext
    → passed to prompt_assembler.assemble() for token-budgeted injection
```

**Unified Scoring:**
| Signal | Weight | Decay |
|--------|--------|-------|
| Cosine similarity | 60% | — |
| Importance (1-5) | 25% | — |
| Recency | 15% | Linear, 30-day window |

---

## Tier 4 — Long-Term User Profile

**Source:** `state_store.memory_facts` + `state_store.embeddings_facts`  
**Loaded by:** `_load_prompt_memory_from_store(store)` in the generate route.

### Fact Structure

Each row in `memory_facts`:

```
fact_id         INTEGER PRIMARY KEY
principal_id    TEXT
text_enc        TEXT        ← AES-256-GCM encrypted fact text
category        TEXT        ← identity | work | interests | preferences | relationships | general
importance      INTEGER     ← 1–5
created_at      INTEGER     ← millisecond timestamp
updated_at      INTEGER
deleted_at      INTEGER     ← NULL = active; set = soft-deleted
valid_at        INTEGER     ← when fact became true
invalid_at      INTEGER     ← when fact stopped being true (superseded)
source_message_id INTEGER   ← message that triggered extraction
```

Embeddings live in a separate `embeddings_facts` table joined by `fact_id`.

### Auto-Extraction Pipeline

Facts are extracted automatically in the background after every non-trivial message by the **ingestion worker** (`services/ingestion_worker.py`):

```
User message persisted → enqueue_ingestion(principal, source="user", message_id=N)
                                            (also for "assistant" if AUTO_EXTRACT_ASSISTANT_MEMORY)
│
Ingestion worker daemon (event-driven wakeup, ThreadPoolExecutor with 2 workers)
│
├── store.claim_job(job_id)       ← atomic UPDATE status=processing
├── store.get_message_by_id(N)    ← decrypt content from state.db
│
├── _index_message()              ← embed + knowledge_store.index_message()
│
├── _extract_and_save() via profile_extractor
│   └── POST OLLAMA_INGEST_HOST/api/chat   ← qwen3:8b (isolated from chat path)
│       model=OLLAMA_INGEST_MODEL, think=False, format=json, temperature=0.1
│       → Returns { facts:[{fact, category, importance}], triples:[{subject, predicate, object}] }
│
├── For each fact: knowledge_store.save_fact(text, category, importance)
│   → dedup via KNN (O(log n)) + merge logic (see below)
│
├── For each triple: knowledge_store.save_relationship(subject, predicate, object)
│
├── _maybe_update_summary(principal_id, chat_id)
│   └── (see Tier 2)
│
└── store.complete_job(job_id)
    (on failure: retry up to 5 attempts with exponential backoff)
```

**Model isolation:** `OLLAMA_INGEST_HOST`/`OLLAMA_INGEST_MODEL` (production: `qwen3:8b`) is strictly separate from `OLLAMA_CHAT_HOST`/`OLLAMA_CHAT_MODEL` (`qwen3:32b`). Background extraction never steals GPU capacity from user-facing inference.

### Deduplication & Merge Semantics

When a new fact arrives via `tool_save_memory()`:

```
New candidate fact: "User is a Python developer"
│
├── embed_text(fact)
├── Compare cosine similarity with all active fact embeddings:
│
├── similarity ≥ DEDUP_SKIP_THRESHOLD (0.95):
│   └── SKIP — identical, return "Already knew that"
│
├── similarity ≥ DEDUP_MERGE_THRESHOLD (0.85):
│   └── MERGE — update existing fact text + re-embed
│       (keeps newer, more specific version)
│
└── Otherwise:
    └── INSERT new fact into memory_facts + embeddings_facts
```

### Token-Budget Profile Injection

`prompt_assembler.assemble()` in `services/prompt_assembler.py` selects and formats facts before each inference call (replaces the former `_format_user_memory()` in `agent.py`):

```
All active facts (deleted_at IS NULL AND invalid_at IS NULL)
│
├── Score each fact:
│   relevance  = cosine_sim(query_embedding, fact_embedding)  [0–1]
│   importance = fact.importance / 5.0                        [0–1]
│   recency    = max(0, 1 - age_days / 30)                   [0–1]
│   base_score = relevance × 0.5 + importance × 0.3 + recency × 0.2
│
│   + category_boost (query-adaptive, via embedding sim vs category exemplars):
│     Personal query  → identity +0.22, relationships +0.22, work +0.08
│     General query   → work +0.18, interests +0.18, preferences +0.14
│
├── Special rules:
│   - preferences category: only injected on style/profile-recall queries
│   - non-personal query + score < PROFILE_RELEVANCE_FLOOR (0.52): skip
│
├── Sort descending by score
│
├── Pack into token budget (PROFILE_TOKEN_BUDGET, PROFILE_MAX_FACTS):
│   Default config: 3500 tokens, 25 facts
│   Production Akash: 2500 tokens, 15 facts
│
└── Format with category headers:
    ## What you know about this user
    ### Identity
    - <fact>
    ### Work
    - <fact>
    ...
    *(This is everything you know. If it's not listed here, say so.)*
```

---

## Full Request Lifecycle

```
Browser                      Flask route                    state.db          Ollama
  │                              │                              │                 │
  │  POST /generate/agent        │                              │                 │
  │  { prompt, chat_id }  ──────►│                              │                 │
  │                              │                              │                 │
  │                     context_loader.load_context()           │                 │
  │                       ├─ classify_context_level()           │                 │
  │                       ├─ get_messages(chat_id, 25) ────────►│                 │
  │                       ├─ list_conversation_summaries() ────►│                 │
  │                       ├─ embed_text(query) (computed once)  │                 │
  │                       ├─ knowledge_store.search(emb, 20) ──►│                 │
  │                       └─ detect_tools_needed(prompt)        │                 │
  │                              │◄─ RequestContext ────────────│                 │
  │                              │                              │                 │
  │                     prompt_assembler.assemble()             │                 │
  │                       ├─ [system: identity + knowledge items]│                 │
  │                       ├─ [system: conversation summary]     │                 │
  │                       ├─ [user/assistant: unsummarized tail]│                 │
  │                       └─ [user: current prompt]             │                 │
  │                              │                              │                 │
  │                              │  append_message(user turn) ─►│                 │
  │                              │  enqueue_ingestion(msg_id) ──►│                 │
  │                              │                              │                 │
  │◄─ SSE {type:session} ────────│                              │                 │
  │                              │                              │                 │
  │                     StreamingPipeline.process_streaming()   │                 │
  │                              │  POST /api/chat ────────────────────────────► │
  │◄─ SSE {token:...} ──────────┤  stream tokens ◄─────────────────────────────  │
  │◄─ SSE {token:...} ───────── │  (think_filter strips <think> blocks)          │
  │                              │                              │                 │
  │                              │  append_message(assistant) ─►│                 │
  │                              │  enqueue_ingestion() ────────►│                 │
  │◄─ SSE {done:true} ──────────│                              │                 │

Background (ingestion_worker daemon thread, ThreadPoolExecutor × 2):
  state.db ingestion_jobs                      OLLAMA_INGEST_HOST (qwen3:8b)
  ├── claim_job(job_id)                              │
  ├── get_message_by_id(N) → decrypt               │
  ├── _index_message() → knowledge_store.index_message()
  ├── extract_memory_candidates(text) ────────────► │
  │   ← { facts, triples } ───────────────────────  │
  ├── knowledge_store.save_fact()   → dedup via KNN + insert/merge
  ├── knowledge_store.save_relationship() → graph triples as facts
  └── _maybe_update_summary() → conversation_summaries
```

---

## Tool Interface

The model can also call memory tools explicitly during a ReAct loop turn:

| Tool | Trigger | Behavior |
|------|---------|----------|
| `save_memory` | AI detects something worth remembering | Embeds + dedup/merge into memory_facts |
| `recall_memory` | AI needs user context before answering | Semantic search over active facts |
| `search_memory` | AI needs specific past context | exact / semantic / hybrid search |
| `update_memory` | User's situation has changed | Find best-match fact by similarity, update text + re-embed |
| `forget_memory` | User asks to forget something | Soft-delete: sets `deleted_at`, preserved for audit |

All five tools are implemented in `services/memory_tools.py` and operate directly on `state_store`.

---

## Graph Memory

Parallel to the fact store, the system maintains a knowledge graph of entity relationships.

**Storage:** `state_store.graph_triples`  
**Structure:** `(subject TEXT, predicate TEXT, object TEXT, source_message_id INTEGER)`  
**Extraction:** `profile_extractor.extract_memory_candidates()` returns `triples` alongside `facts`  
**Retrieval:** `state_store.search_graph_triples(query, limit=GRAPH_MEMORY_TOP_K)` — full-text match on subject/predicate/object  
**Injection:** `_format_graph_context()` in `agent.py` formats top-6 triples as `- <subject> <predicate> <object>` bullet lines

---

## Embeddings Engine

All embedding computation uses **FastEmbed** with `BAAI/bge-small-en-v1.5`.

| Property | Value |
|----------|-------|
| Model | BAAI/bge-small-en-v1.5 |
| Dimension | 384 |
| Library | fastembed |
| Cache | LRU, SHA-256 key, 1000 entries, 1-hour TTL, thread-safe RLock |

**Key functions** (`services/embeddings.py`):

| Function | Purpose |
|----------|---------|
| `embed_text(text)` | Single text → 384-dim vector (cache-first) |
| `embed_batch(texts)` | Batch with cache-aware optimization |
| `cosine_similarity(a, b)` | Similarity between two `np.ndarray` vectors |

**SQLite storage:** vectors stored as raw `float32` bytes via `numpy.tobytes()` / `numpy.frombuffer()` for compact, fast retrieval without JSON overhead.

---

## Semantic Response Cache

`services/caching.py` also wraps a semantic caching layer on top of Ollama responses:

| Property | Value |
|----------|-------|
| Max size | 500 entries |
| TTL | 1 hour |
| Hit threshold | cosine_similarity ≥ 0.95 |

If a new query embedding is ≥ 95% similar to a cached query, the cached response is returned immediately — no Ollama call needed.

---

## Frontend Context Window

The Zustand store maintains `contextMemory` (up to `CONTEXT_WINDOW_SIZE=50` messages) for client-side state only. This is **not** sent to the backend — the backend loads canonical context from `state.db`. The frontend window is used for live streaming display and local message ordering only.

---

## API Endpoints (Memory)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/user/memory` | GET | Return all facts + ingestion job status |
| `/user/memory` | POST | Replace entire memory payload (migrate-safe) |
| `/user/memory/fact` | POST | Add single fact (dedup/merge logic applied) |
| `/user/memory/fact/<id>` | PATCH | Edit a specific fact |
| `/user/memory/fact/<id>` | DELETE | Soft-delete a fact |
| `/user/export` | GET | ZIP: profile.json + chat markdowns |

---

## Configuration Reference

| Key | Default | Production Akash | Description |
|-----|---------|-----------------|-------------|
| `WORKING_MEMORY_SIZE` | 5 | — | Legacy; context is now 25 messages server-side |
| `SEMANTIC_MEMORY_SIZE` | 8 | — | Semantic retrieval top-k |
| `RECENCY_WEIGHT` | 0.3 | 0.3 | Recency vs similarity balance |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | — | Embedding model |
| `PROFILE_TOKEN_BUDGET` | 3500 | 2500 | Max tokens for profile in system prompt |
| `PROFILE_MAX_FACTS` | 25 | 15 | Max facts packed into profile section |
| `PROFILE_RELEVANCE_FLOOR` | 0.52 | — | Min score for non-preference facts on non-personal queries |
| `DEDUP_MERGE_THRESHOLD` | 0.85 | — | Cosine sim to merge (update) existing fact |
| `DEDUP_SKIP_THRESHOLD` | 0.95 | — | Cosine sim to skip (identical) |
| `GRAPH_MEMORY_ENABLED` | true | — | Enable graph triple extraction + retrieval |
| `GRAPH_MEMORY_TOP_K` | 6 | — | Graph triples retrieved per request |
| `MEMORY_INGESTION_ENABLED` | true | — | Enable async ingestion worker |
| `SUMMARY_TRIGGER_MESSAGES` | 10 | — | New messages before summary update |
| `OLLAMA_CHAT_HOST` | `OLLAMA_HOST` | `localhost:11434` | Host for user-facing inference |
| `OLLAMA_CHAT_MODEL` | `MODEL_NAME` | `qwen3:32b` | Model for chat responses |
| `OLLAMA_INGEST_HOST` | `OLLAMA_HOST` | `localhost:11434` | Host for background extraction |
| `OLLAMA_INGEST_MODEL` | `OLLAMA_CHAT_MODEL` | `qwen3:8b` | Model for extraction/summarization |
| `MEMORY_INGEST_STRICT_ISOLATION` | true | — | Prevent ingest from using chat host |
| `CONTEXT_WINDOW_SIZE` | 50 | — | Frontend Zustand window (display only) |

---

## Key Files

| File | Role |
|------|------|
| `services/knowledge_store.py` | **NEW** — Unified retrieval: facts + messages + relationships (ANN/brute-force) |
| `services/ingestion_worker.py` | **NEW** — Background daemon: index messages, extract facts, update summaries |
| `services/context_loader.py` | **NEW** — Single `load_context()` → `RequestContext` (replaces 5 paths) |
| `services/prompt_assembler.py` | **NEW** — Token-budgeted prompt builder with auto-generated tool sections |
| `services/db.py` | **NEW** — Database connection factory (sqlcipher + sqlite-vec) |
| `services/state_store.py` | Canonical per-principal encrypted SQLite store — all memory tiers |
| `services/memory_tools.py` | Tool handlers: `save_memory`, `recall_memory`, `search_memory`, `update_memory`, `forget_memory` (now uses KnowledgeStore) |
| `services/profile_extractor.py` | LLM extraction call (qwen3:8b) → `{ facts, triples }` |
| `services/embeddings.py` | `embed_text()`, `cosine_similarity()`, LRU cache |
| `services/caching.py` | `EmbeddingCache`, `SemanticResponseCache`, `TokenTracker` |
| `services/memory.py` | Legacy shim — `build_enhanced_context()` (being superseded by KnowledgeStore) |
| `services/memory_ingestion.py` | Shim re-exports from `ingestion_worker.py` |
| `storage.py` | Compatibility facade — memory payload helpers |
| `routes/generate.py` | `generate_agent()` — context load, persist, enqueue, SSE stream |
| `store/index.ts` | Frontend Zustand store — `contextMemory`, `CONTEXT_WINDOW_SIZE` (display only) |

