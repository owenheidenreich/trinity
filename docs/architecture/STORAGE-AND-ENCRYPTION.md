# Trinity — Storage & Encryption Architecture

> Last updated: February 2026

## Overview

Trinity's storage system is designed around a core principle: **the user owns their data**. No one — not even the server operator — can read a user's chat history or personal memories. All data is encrypted with keys derived from the user's identity before it ever leaves the backend.

Storage operates on a **local-first, cloud-synced** model:

1. **Frontend:** Saves to IndexedDB instantly (local-first)
2. **Backend:** Encrypts and uploads to IPFS (durable cloud backup)
3. **IPFS:** Content-addressed, immutable, retrievable from multiple gateways

```
┌─────────────────────────────────────────────────────────────────────┐
│                       STORAGE ARCHITECTURE                           │
│                                                                      │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │  IndexedDB   │    │  Akash Backend   │    │      IPFS         │  │
│  │  (Browser)   │    │  (Encryption)    │    │  (Lighthouse)     │  │
│  │              │    │                  │    │                   │  │
│  │  Immediate   │───>│  AES-256-GCM     │───>│  Content-addressed│  │
│  │  local save  │    │  Argon2id KDF    │    │  Immutable        │  │
│  │              │    │  Per-user keys   │    │  Multi-gateway    │  │
│  │  Unencrypted │    │                  │    │  Encrypted blobs  │  │
│  │  (local only)│    │  Ephemeral       │    │  Permanent        │  │
│  └──────────────┘    └──────────────────┘    └───────────────────┘  │
│                                                                      │
│  Also stored on Akash (ephemeral, rebuilt from IPFS):                │
│  ├── SQLite: sessions, rate limits, usage stats, chat metadata       │
│  └── Per-user vector databases (SQLite)                              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Encryption

### Algorithm

| Property | Value |
|----------|-------|
| Cipher | AES-256-GCM (authenticated encryption) |
| Primary KDF | Argon2id (64 MB memory, 4 threads, 3 iterations) |
| Fallback KDF | PBKDF2-HMAC-SHA256 (100,000 iterations) |
| Key derivation password | User's ICP principal ID |
| Salt | Random 16 bytes per encryption |
| Nonce | Random 12 bytes per encryption |

### Why Argon2id?

Argon2id is a memory-hard key derivation function. Unlike PBKDF2 (which only requires CPU), Argon2id requires 64 MB of RAM per derivation attempt. This makes brute-force attacks with GPUs or ASICs dramatically more expensive.

The system auto-selects Argon2id when available, falling back to PBKDF2 for environments where `argon2-cffi` is not installed.

### Encrypted Envelope Format

When a chat is encrypted, the result is a JSON envelope:

```json
{
  "version": "1.1",
  "kdf": "argon2id",
  "salt": "<base64-encoded 16-byte salt>",
  "nonce": "<base64-encoded 12-byte nonce>",
  "ciphertext": "<base64-encoded AES-256-GCM encrypted data>"
}
```

The `kdf` field enables backward compatibility — older data encrypted with PBKDF2 (`kdf: "pbkdf2"`) can still be decrypted since the system checks this field and selects the appropriate key derivation.

### Encryption Flow

```
plaintext chat data (dict)
│
├── Serialize to JSON bytes
│
├── Generate random 16-byte salt
├── Generate random 12-byte nonce
│
├── Derive key:
│   Argon2id(password=principal_id, salt=salt)
│   → 32-byte AES key
│
├── AES-256-GCM encrypt:
│   encrypt(key, nonce, plaintext_bytes)
│   → ciphertext + 16-byte authentication tag
│
└── Return envelope:
    {version, kdf, salt, nonce, ciphertext}
    (all binary fields base64-encoded)
```

### Decryption Flow

```
encrypted envelope
│
├── Decode base64 fields (salt, nonce, ciphertext)
│
├── Read kdf field:
│   ├── "argon2id" → Argon2id(principal, salt) → key
│   └── "pbkdf2"   → PBKDF2(principal, salt)   → key
│
├── AES-256-GCM decrypt:
│   decrypt(key, nonce, ciphertext)
│   → plaintext bytes (or authentication failure)
│
└── Deserialize JSON → dict
```

### Key Point

The encryption password is the user's **ICP principal ID**. This means:
- Only the user who owns the principal can decrypt their data
- The server operator cannot read stored data (they don't know the principal-to-key mapping)
- If a user loses their private key, their encrypted data is permanently inaccessible

---

## Autosave Pipeline

### Frontend Side

```
User sends message                   Debounce timer: 2 seconds
│                                    │
├── addMessage() to store            │
├── AI generates response            │
├── addMessage() to store            │
├── scheduleAutosave() ─────────────>│ start/reset timer
│                                    │
│                              (2 seconds pass)
│                                    │
│                              executeSave()
│                              │
│                              ├── 1. Save to IndexedDB immediately
│                              │      IndexedDBStorage.saveChat({
│                              │        chatId, principal, title,
│                              │        messages, metadata, lastUpdated
│                              │      })
│                              │
│                              ├── 2. POST /chat/autosave
│                              │      with auth headers + encrypted body
│                              │
│                              ├── On success:
│                              │   ├── Mark synced in IndexedDB
│                              │   ├── Set status: 'saved'
│                              │   └── Reset to 'idle' after 2s
│                              │
│                              └── On failure:
│                                  ├── Queue in IndexedDB pendingSync
│                                  └── Retry up to 5x with backoff
│                                      (1s × 2^attempt)
```

### Backend Side (`POST /chat/autosave`)

```
Incoming request (authenticated)
│
├── Validate request body: chatId, title, messages, metadata
│
├── EncryptionUtils.encrypt_chat(chat_data, principal)
│   → AES-256-GCM encrypted envelope
│
├── upload_to_ipfs(encrypted_data, filename="{chatId}.json")
│   → Returns CID (content identifier)
│
├── TrinityDB.upsert_chat_metadata(
│     chat_id, principal, title, cid, message_count, ...
│   )
│
├── save_metadata(principal, updated_index)
│   → Save metadata.json to disk
│
├── upload_to_ipfs(metadata)
│   → Upload metadata to IPFS for recovery
│
└── Return: { status: "saved", cid: "bafy..." }
```

---

## Chat Loading

### Loading a Chat (`GET /chat/<chat_id>`)

```
Request for chat_id
│
├── TrinityDB.get_chat_metadata(chat_id, principal)
│   → { cid, title, ... }
│
├── download_from_ipfs(cid)
│   │
│   ├── Try Lighthouse gateway
│   ├── Try ipfs.io gateway (fallback)
│   ├── Try dweb.link gateway (fallback)
│   └── Try cloudflare-ipfs.com (fallback)
│
├── EncryptionUtils.decrypt_chat(encrypted_data, principal)
│   → Plaintext chat data
│
└── Return: { chatId, title, messages, metadata }
```

### Loading the Chat List (`GET /chat/list`)

```
Request for user's chats
│
├── Load metadata from IPFS (latest metadata CID for principal)
│
├── Return list of: {
│     chatId, title, messageCount,
│     createdAt, lastUpdated,
│     pinned, isArchived, cid
│   }
│
└── Frontend sorts: pinned first, then by lastUpdated desc
```

---

## IPFS Integration

### What Gets Stored on IPFS

| Data | When | How |
|------|------|-----|
| Individual chat archives | On autosave | Encrypted JSON → upload → CID |
| User metadata index | After each save | JSON manifest of all chats → upload → CID |
| Master recovery bundle | On archive | Encrypted manifest of all archived chats |
| Vector database snapshots | On manual sync | Full DB dump as JSON |

### Multi-Gateway Retrieval

When downloading from IPFS, the system tries four gateways in order:

1. `https://gateway.lighthouse.storage/ipfs/{cid}` (Lighthouse's own gateway)
2. `https://ipfs.io/ipfs/{cid}` (Protocol Labs' public gateway)
3. `https://dweb.link/ipfs/{cid}` (DWeb gateway)
4. `https://cloudflare-ipfs.com/ipfs/{cid}` (Cloudflare's gateway)

If all four fail, the operation returns an error. This redundancy ensures data availability even if one gateway is down.

### IPFS Immutability

IPFS data is **immutable** — once uploaded, a CID always points to the same content. This means:
- "Deleting" a chat only removes it from the metadata index; the encrypted blob still exists on IPFS
- This is acceptable because the encrypted blob is useless without the user's principal
- Recovery is always possible if you have the CID and the principal

---

## IndexedDB (Frontend Local Storage)

The browser maintains a local cache of all chats for offline access and instant loading.

### Database Structure

```
Database: TrinityChats (v1)
│
├── Object Store: "chats"
│   ├── keyPath: chatId
│   ├── Indexes:
│   │   ├── principal  (for filtering by user)
│   │   └── lastUpdated (for sorting)
│   └── Record shape:
│       {
│         chatId: string,
│         principal: string,
│         title: string,
│         messages: ChatMessage[],
│         metadata: { createdAt, updatedAt, messageCount, appVersion },
│         lastUpdated: number
│       }
│
└── Object Store: "pendingSync"
    ├── keyPath: chatId
    ├── Index: timestamp
    └── Record shape:
        {
          chatId: string,
          chatData: { title, messages, metadata },
          timestamp: number,
          retryCount: number
        }
```

### Sync Strategy

```
┌──────────────────────────────────────────────────────────────────┐
│                    LOCAL-FIRST SYNC MODEL                         │
│                                                                   │
│  Save:                                                            │
│  1. Write to IndexedDB immediately (instant, offline-capable)     │
│  2. Attempt cloud sync to /chat/autosave                          │
│     ├── Success → markSynced(chatId) in IndexedDB                 │
│     └── Failure → queueForSync(chatId, chatData) in pendingSync   │
│                                                                   │
│  Retry:                                                           │
│  ├── On next successful save: retryPendingSync()                  │
│  └── On app reload: retryPendingSync()                            │
│      └── For each pending item: retry up to 10 attempts           │
│                                                                   │
│  Load:                                                            │
│  ├── Primary: load from cloud (IPFS via backend)                  │
│  └── Fallback: load from IndexedDB (if offline)                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## User Memory Storage

User memory (persistent facts across all chats) is stored as encrypted JSON:

### Storage Path

```
On Akash disk:
  /data/chats/<principal>/user_memory.json  (encrypted)
  /data/chats/<principal>/metadata.json     (plaintext index)

On IPFS:
  Encrypted user_memory.json → CID
  (backed up alongside chat archives)
```

### Operations

| Function | Location | Purpose |
|----------|----------|---------|
| `load_user_memory(principal)` | `storage.py` | Load + decrypt from disk. Returns `{facts: [], preferences: {}}` if not found |
| `save_user_memory(principal, memory)` | `storage.py` | Encrypt + write to disk |
| `_normalize_facts(facts)` | `storage.py` | Migrate legacy fact formats to current schema |
| `load_metadata(principal)` | `storage.py` | Load plaintext metadata (chat index, CIDs, sync state) |
| `save_metadata(principal, metadata)` | `storage.py` | Save metadata JSON |
| `get_user_dir(principal)` | `storage.py` | Returns safe path with path-traversal protection |

---

## Chat Archives & Recovery

### Archiving

When a chat is archived (`POST /chat/<id>/archive`):

1. Chat metadata is updated with `is_archived: true`
2. A master recovery bundle is created:
   - Collects all archived chat CIDs
   - Encrypts the manifest
   - Uploads to IPFS as a single recovery CID
3. Hard limit: 20 archived chats per user

### Recovery

If the user loses local data, they can recover from IPFS:

```
GET /chat/recover-archives
│
├── Load master bundle CID from metadata
├── Download from IPFS
├── Decrypt with principal
├── Iterate archived chat CIDs
│   ├── Download each chat from IPFS
│   ├── Decrypt with principal
│   └── Restore to metadata index
│
└── Return recovered chat list
```

---

## Browser-Side Encryption

The frontend also uses encryption — but for a different purpose. The user's Ed25519 private key is encrypted before being stored in localStorage:

```
Private key hex string
│
├── Derive AES key from browser fingerprint:
│   fingerprint = origin + userAgent + platform + screenWidth + screenHeight
│   key = PBKDF2(fingerprint, salt="trinity-key-storage", iterations=50000)
│   → 256-bit AES key
│
├── Generate random 12-byte IV
│
├── AES-256-GCM encrypt(key, iv, private_key_hex)
│
└── Store as base64 in localStorage:
    trinity_identity_key = base64(iv + ciphertext)
```

This means the encrypted private key in localStorage is:
- Useless on a different browser/device (different fingerprint)
- Useless if you copy the localStorage value (can't derive the key)
- Only decryptable on the same browser + same device

### Validation (`isEncrypted()`)

A heuristic function detects whether a stored value is encrypted or plaintext:
- Valid base64? Not raw hex? Minimum length? → Encrypted
- Otherwise → Legacy plaintext (auto-migrated on load)

---

## Data Lifecycle

```
┌─ Message Created ────────────────────────────────────────────────┐
│                                                                   │
│  1. User sends message → addMessage('user', content)              │
│  2. AI responds → addMessage('assistant', content)                │
│  3. Both added to chatHistory (permanent) + contextMemory (window)│
│                                                                   │
├─ Autosave (2s debounce) ─────────────────────────────────────────┤
│                                                                   │
│  4. Save to IndexedDB (instant, local)                            │
│  5. POST to /chat/autosave:                                       │
│     a. Encrypt with AES-256-GCM (Argon2id KDF, principal as key)  │
│     b. Upload to IPFS → get CID                                   │
│     c. Update metadata index                                      │
│     d. Upload metadata to IPFS                                    │
│                                                                   │
├─ Semantic Indexing ──────────────────────────────────────────────┤
│                                                                   │
│  6. Embed message content → 384-dim vector                        │
│  7. Store in per-user SQLite vector database                      │
│  8. Available for semantic memory retrieval in future queries      │
│                                                                   │
├─ Cleanup (daily at 2 AM) ───────────────────────────────────────┤
│                                                                   │
│  9. Chats inactive > 7 days: metadata deleted (IPFS data remains) │
│  10. Pinned and archived chats: exempt from cleanup               │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Server operator reads user data | All data encrypted with user's principal before storage |
| IPFS data is public | Encrypted blobs — content is gibberish without the principal |
| Path traversal in storage operations | `get_user_dir()` validates and resolves paths, blocks `..` |
| Replay attacks on autosave | Ed25519 signed requests with nonce + timestamp validation |
| Data loss (Akash restart) | Primary data on IPFS (immutable); Akash disk is cache only |
| Browser local data stolen | Private key encrypted with browser fingerprint (device-specific) |
| Brute-force key derivation | Argon2id requires 64MB RAM per attempt |

---

## Key Files

| File | Role |
|------|------|
| `backend/encryption.py` | `EncryptionUtils`: encrypt/decrypt with AES-256-GCM |
| `backend/storage.py` | User memory + metadata file I/O |
| `backend/lighthouse.py` | IPFS upload/download with multi-gateway fallback |
| `backend/routes/chat.py` | Chat CRUD + autosave + archive endpoints |
| `src-react/utils/indexedDB.ts` | Frontend IndexedDB operations |
| `src-react/utils/crypto.ts` | Browser-side AES-GCM for localStorage |
| `src-react/hooks/useAutosave.ts` | Debounced save with retry logic |
