# Trinity — Memory System Architecture

> Last updated: February 2026

## Overview

Trinity uses a **three-tier memory system** that gives the AI context, personality, and the ability to remember things about you across conversations. Each tier serves a different purpose and operates at a different timescale.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        MEMORY ARCHITECTURE                           │
│                                                                      │
│  ┌────────────────────┐                                              │
│  │   WORKING MEMORY   │  Last 3 messages from current chat           │
│  │   (Short-term)     │  Always available, zero retrieval cost       │
│  │                    │  Source: vector_store.get_recent_messages()   │
│  └────────┬───────────┘                                              │
│           │                                                          │
│  ┌────────┴───────────┐                                              │
│  │  SEMANTIC MEMORY   │  Top 5 most relevant past messages           │
│  │  (Medium-term)     │  Retrieved by embedding similarity           │
│  │                    │  Weighted by recency (30% recency, 70% sim)  │
│  │                    │  Source: vector_store.search_messages()       │
│  └────────┬───────────┘                                              │
│           │                                                          │
│  ┌────────┴───────────┐                                              │
│  │    USER MEMORY     │  Persistent facts across all chats           │
│  │  (Long-term)       │  Stored encrypted on IPFS                    │
│  │                    │  Managed via tools or API                     │
│  │                    │  Source: storage.load_user_memory()           │
│  └────────────────────┘                                              │
│                                                                      │
│  All three tiers are assembled into the system prompt before         │
│  each LLM call by build_system_prompt() in agent_prompts.py         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Tier 1: Working Memory

**What:** The last few messages from the current conversation.  
**Purpose:** Ensures the AI has immediate context about what was just said.  
**Size:** 3 messages (configurable via `WORKING_MEMORY_SIZE`).  
**Source:** `vector_store.get_recent_messages(chat_id, limit=3)`

This is the cheapest tier — no embedding search needed, just a simple database query sorted by timestamp. These messages are always included in the LLM context regardless of relevance.

### How It Works

```
User sends message #10 in a conversation
│
├── Messages #8, #9, #10 are automatically included
│   as working memory (last 3)
│
└── No embedding computation needed
    Just: SELECT * FROM message_embeddings
          WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 3
```

---

## Tier 2: Semantic Memory

**What:** Past messages from any conversation that are semantically relevant to the current query.  
**Purpose:** Surfaces context from earlier in a conversation (or other conversations) that helps answer the current question.  
**Size:** 5 results (configurable via `SEMANTIC_MEMORY_SIZE`).  
**Source:** `vector_store.search_messages(query_embedding, top_k=5, chat_id)`

### How Retrieval Works

```
User asks: "What was that Python sorting trick you showed me?"
│
├── embed_text("What was that Python sorting trick you showed me?")
│   → 384-dimensional vector via BAAI/bge-small-en-v1.5
│
├── Search all stored message embeddings:
│   └── For each stored message:
│       ├── similarity = cosine_similarity(query_embedding, stored_embedding)
│       ├── age_hours = (now - message_timestamp) / 3600
│       ├── recency_bonus = max(0, 1 - (age_hours / 168))  ← 7-day decay
│       └── final_score = (1 - RECENCY_WEIGHT) × similarity
│                       + RECENCY_WEIGHT × recency_bonus
│                       = 0.7 × similarity + 0.3 × recency_bonus
│
├── Return top 5 by final_score
│
└── Format for prompt injection:
    "[From earlier conversation] <role>: <content>"
```

### Recency Weighting

The scoring formula balances two signals:

| Signal | Weight | Description |
|--------|--------|-------------|
| Semantic similarity | 70% | How relevant the content is to the current query |
| Recency | 30% | How recently the message was sent (linear decay over 7 days) |

This means a slightly less similar message from 1 hour ago will score higher than a slightly more similar message from 5 days ago — reflecting how humans use context.

### Message Indexing

Messages are indexed into the vector store after each successful generation:

```
Agent completes response
│
├── SemanticMemory.index_message(
│     role="assistant",
│     content="Here's how to sort...",
│     chat_id="chat-1234",
│     msg_index=10
│   )
│
├── embed_text(content) → 384-dim vector
│
└── vector_store.add_message_embedding(
      chat_id, msg_index, role, content, embedding
    )
    → Stored in per-user SQLite database
```

---

## Tier 3: User Memory

**What:** Persistent facts about the user that survive across all conversations.  
**Purpose:** Makes the AI feel like it "knows" you — your preferences, background, ongoing projects, etc.  
**Size:** Unlimited facts, stored as an encrypted JSON file on IPFS.

### Data Structure

```json
{
  "facts": [
    {
      "text": "User is building a decentralized AI platform called Trinity",
      "category": "project",
      "importance": 4,
      "embedding": [0.023, -0.114, ...],    // 384-dim vector
      "created_at": 1707840000
    },
    {
      "text": "User prefers dark mode and minimal UI",
      "category": "preference",
      "importance": 3,
      "embedding": [0.045, 0.089, ...],
      "created_at": 1707841000
    }
  ],
  "preferences": {}
}
```

### How Facts Are Managed

There are three ways to manage user memory:

#### 1. Agent Tool Calls (Automatic)

During a conversation, the AI can decide to save or recall memories using built-in tools:

```
User: "I'm a Python developer who focuses on security"

AI internally triggers:
  <tool_call name="save_memory">
    {"fact": "User is a Python developer focused on security",
     "category": "background",
     "importance": 4}
  </tool_call>

→ tool_save_memory(principal, fact_text, category, importance)
  ├── embed_text(fact_text) → embedding vector
  ├── Check existing facts for duplicates (>0.95 cosine similarity)
  │   └── If duplicate found → skip (return "already known")
  └── Append to user_memory.json (encrypted on disk)
```

#### 2. API Endpoints (Manual)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/user/memory` | GET | Retrieve all facts + preferences |
| `/user/memory` | POST | Replace entire memory |
| `/user/memory/fact` | POST | Add single fact (with auto-dedup) |
| `/user/memory/fact/<index>` | DELETE | Remove a specific fact |

#### 3. Memory Tool Handlers

Three tool functions in `services/memory_tools.py`:

| Tool | Trigger | Behavior |
|------|---------|----------|
| `save_memory` | AI detects something worth remembering | Embeds fact, deduplicates, saves |
| `recall_memory` | AI needs user context for a response | Retrieves by semantic similarity. Score = `0.7 × similarity + 0.3 × (importance / 5)` |
| `search_memory` | AI needs specific past context | Three modes: `exact` (substring), `semantic` (embeddings), `hybrid` (both) |

### Deduplication

When saving a new fact, the system checks all existing facts for semantic similarity:

```
New fact: "User is a Python dev"
│
├── Compute embedding for new fact
├── Compare with all existing fact embeddings
├── If any existing fact has cosine_similarity > 0.95:
│   └── SKIP — considered a duplicate
│       Return: "I already know that about you"
└── Otherwise: save new fact
```

This prevents the memory from filling up with slight rephrasings of the same information.

---

## How Memory Is Assembled for Each Request

When the agent processes a message, all three tiers are assembled into the system prompt:

```
User sends prompt
│
▼
AgentPipeline.process_streaming(prompt, context_messages, ...)
│
├── Load user memory (Tier 3):
│   memory_data = storage.load_user_memory(principal)
│   → Decrypt user_memory.json from disk
│   → Format facts for prompt injection
│
├── Build semantic context (Tiers 1 + 2):
│   semantic_memory = SemanticMemory(principal, vector_store)
│   context = semantic_memory.build_enhanced_context(
│     query=prompt,
│     context_messages=last_N_messages,
│     chat_id=current_chat_id
│   )
│   ├── Working memory: last 3 messages
│   └── Semantic memory: top 5 relevant past messages
│
├── Build system prompt:
│   build_system_prompt(
│     context=semantic_context,
│     memory=user_memory,
│     search_results=None,
│     tools=available_tools
│   )
│
│   Resulting prompt structure:
│   ┌──────────────────────────────────────────────┐
│   │ SYSTEM PROMPT                                 │
│   │                                               │
│   │ [Trinity identity + formatting guidelines]    │
│   │                                               │
│   │ ## What You Know About This User              │
│   │ - User is a Python developer...              │
│   │ - User prefers dark mode...                  │
│   │                                               │
│   │ ## Relevant Context From Previous Messages    │
│   │ [assistant]: Here's how to sort a list...    │
│   │ [user]: Can you also show filtering?         │
│   │                                               │
│   │ ## Available Tools                            │
│   │ [tool documentation if tools detected]       │
│   └──────────────────────────────────────────────┘
│
└── Send to Ollama for inference
```

---

## Embeddings Engine

All embedding operations use FastEmbed with the `BAAI/bge-small-en-v1.5` model:

| Property | Value |
|----------|-------|
| Model | BAAI/bge-small-en-v1.5 |
| Dimension | 384 |
| Library | FastEmbed 0.7.4 |
| Cache | LRU with SHA-256 key, 1000 entries, 1-hour TTL |

### Embedding Cache

An `EmbeddingCache` (in `services/caching.py`) avoids re-computing embeddings for the same text:

- **Max size:** 1000 entries
- **TTL:** 1 hour
- **Thread-safe:** Yes (RLock)
- **Key strategy:** SHA-256 hash of the input text
- **Prometheus metrics:** `EMBEDDING_CACHE_HITS`, `EMBEDDING_CACHE_MISSES`, `EMBEDDING_CACHE_SIZE`

### Key Functions (`services/embeddings.py`)

| Function | Purpose |
|----------|---------|
| `embed_text(text)` | Single text → 384-dim vector (checks cache first) |
| `embed_batch(texts)` | Batch embedding with cache-aware optimization |
| `cosine_similarity(a, b)` | Similarity score between two vectors |
| `chunk_text(text, size, overlap)` | Split text into overlapping chunks for RAG |
| `compute_text_hash(text)` | SHA-256 hash for cache keys |

---

## Vector Store

Each user gets their own SQLite database for vector storage (`services/vector_store.py`).

### Database Schema

```sql
-- Embedded document chunks (for RAG over uploaded documents)
CREATE TABLE document_chunks (
    doc_id TEXT,
    filename TEXT,
    chunk_index INTEGER,
    content TEXT,
    embedding TEXT,        -- JSON array of floats
    created_at TIMESTAMP
);

-- Embedded chat messages (for semantic memory retrieval)
CREATE TABLE message_embeddings (
    chat_id TEXT,
    message_index INTEGER,
    role TEXT,
    content TEXT,
    embedding TEXT,        -- JSON array of floats
    timestamp TIMESTAMP
);

-- Sync metadata (for IPFS backup tracking)
CREATE TABLE sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### Vector Search Implementation

The vector store attempts to load the `sqlite_vss` extension for native vector similarity search. If unavailable (which is common), it falls back to brute-force Python cosine similarity:

```
Search query arrives
│
├── If sqlite_vss loaded:
│   └── Use native SQLite vector indexing (fast)
│
└── If not available (fallback):
    ├── Load all embeddings from the table
    ├── Compute cosine_similarity for each one in Python
    ├── Sort by score descending
    └── Return top K results
```

### IPFS Sync

The vector database can be backed up to and restored from IPFS:

| Operation | What Happens |
|-----------|-------------|
| Export (`export_for_ipfs()`) | Dumps all tables to JSON |
| Import (`import_from_ipfs(data)`) | Restores tables from JSON dump |
| Sync on login (`sync_vector_db_on_login()`) | Downloads latest snapshot if CID exists in user metadata |

---

## Semantic Response Cache

Beyond embedding caching, there is also a semantic response cache (`services/caching.py`) that caches LLM responses for near-identical queries:

| Property | Value |
|----------|-------|
| Max size | 500 entries |
| TTL | 1 hour |
| Similarity threshold | ≥ 0.95 cosine similarity |

If a new query's embedding is ≥ 95% similar to a cached query, the cached response is returned instantly without calling Ollama. This dramatically reduces costs for repeated or near-repeated questions.

---

## Token Tracking

The `TokenTracker` class (`services/caching.py`) records all token consumption for cost estimation:

| Method | Purpose |
|--------|---------|
| `record(prompt_tokens, completion_tokens, model, user_id)` | Log usage with per-model cost rates |
| `get_totals()` | Aggregate: total tokens, requests, estimated cost, tokens/hour |
| `get_user_usage(user_id)` | Per-user stats |
| `get_top_users(limit)` | Usage leaderboard |

Cost estimation uses model-specific rates (since all inference is self-hosted, this tracks opportunity cost rather than actual billing).

---

## Frontend Context Window

On the frontend side, a simpler context window manages what gets sent to the API:

```
Zustand Store:
  contextMemory: ChatMessage[]    (sliding window)
  CONTEXT_WINDOW_SIZE: 20         (max messages)

When addMessage() is called:
  1. Append to chatHistory (permanent)
  2. Append to contextMemory
  3. If contextMemory.length > 20:
     Remove oldest messages from front

getContextForLLM() returns:
  {
    recentMessages: contextMemory,    // last 20 messages
    totalConversationLength: chatHistory.length,
    totalTokens: estimated_count
  }
```

This ensures the API request body doesn't grow unbounded while keeping enough recent context for coherent conversation.

---

## Configuration Reference

| Config Key | Default | Location | Description |
|-----------|---------|----------|-------------|
| `WORKING_MEMORY_SIZE` | 3 | `config.py` | Messages in working memory |
| `SEMANTIC_MEMORY_SIZE` | 5 | `config.py` | Semantic search results |
| `RECENCY_WEIGHT` | 0.3 | `config.py` | Recency vs similarity balance |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | `config.py` | Embedding model |
| `EMBEDDING_DIM` | 384 | `config.py` | Vector dimensions |
| `CHUNK_SIZE` | 500 | `config.py` | Document chunk size (chars) |
| `RAG_TOP_K` | 5 | `config.py` | Top RAG results |
| `CONTEXT_WINDOW_SIZE` | 20 | `store/types.ts` | Frontend context window |

---

## Key Files

| File | Role |
|------|------|
| `services/memory.py` | `SemanticMemory` class — orchestrates working + semantic retrieval |
| `services/memory_tools.py` | Tool handlers: `save_memory`, `recall_memory`, `search_memory` |
| `services/embeddings.py` | Embedding computation + caching |
| `services/vector_store.py` | Per-user SQLite vector database |
| `services/caching.py` | `EmbeddingCache`, `SemanticResponseCache`, `TokenTracker` |
| `storage.py` | `load_user_memory()`, `save_user_memory()` — encrypted file I/O |
| `store/index.ts` | Frontend Zustand store — `contextMemory`, `CONTEXT_WINDOW_SIZE` |
