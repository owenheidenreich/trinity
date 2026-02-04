# Trinity Storage Architecture
> Last Updated: January 20, 2026  
> Status: Individual Archive Production-Ready | Bulk Archive In Development

---

## Overview

Trinity uses a **two-tier storage strategy** combining Akash Network for active chat storage and Filecoin/IPFS for long-term archival. This architecture enables self-custodial, encrypted chat persistence without traditional cloud dependencies.

---

## Storage Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRINITY STORAGE LAYERS                             │
└─────────────────────────────────────────────────────────────────────────────┘

    Layer 1: ACTIVE STORAGE          Layer 2: ARCHIVE STORAGE
    (Akash Network)                  (Filecoin/IPFS)
    
    ┌─────────────────┐              ┌─────────────────┐
    │  Fast Access    │              │  Permanent      │
    │  Mutable        │              │  Immutable      │
    │  Low Cost       │              │  Ultra-Low Cost │
    │  Encrypted      │              │  Encrypted      │
    └─────────────────┘              └─────────────────┘
         │                                  │
         │ Autosave                         │ Archive
         │ (every message)                  │ (user-triggered)
         ▼                                  ▼
    chats/{principal}/              CID: QmXx...
    ├── chat-abc123.json            (IPFS Content ID)
    ├── chat-def456.json
    └── metadata.json
```

---

## Architecture Diagram: Akash + Filecoin Integration

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                     TRINITY STORAGE ARCHITECTURE                                 ║
║                  Akash Network ←→ Filecoin/IPFS Integration                      ║
╚══════════════════════════════════════════════════════════════════════════════════╝


    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                            👤 USER (Browser)                                 │
    │                         https://dubya.ai                                     │
    │                                                                              │
    │  ┌───────────────────────────────────────────────────────────────────────┐  │
    │  │                      FRONTEND (ICP Canister)                           │  │
    │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │  │
    │  │  │  Chat Interface │  │  Autosave       │  │  Archive Controls   │   │  │
    │  │  │  - Type message │  │  - Debounced    │  │  - Archive button   │   │  │
    │  │  │  - View history │  │  - Encrypted    │  │  - Recovery dialog  │   │  │
    │  │  └────────┬────────┘  └────────┬────────┘  └─────────┬───────────┘   │  │
    │  └───────────┼────────────────────┼──────────────────────┼───────────────┘  │
    └──────────────┼────────────────────┼──────────────────────┼──────────────────┘
                   │                    │                      │
                   │ AI Generation      │ Autosave             │ Archive/Recover
                   ▼                    ▼                      ▼
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │                                                                              │
    │  🖥️  AKASH NETWORK BACKEND (Python Flask + Ollama)                          │
    │      Provider: trinity-qwen72b (A100 GPU)                                   │
    │      URL: cls1e8des1db50r65f6dpc8c7g.ingress.a100.dsm.val.akash.pub         │
    │                                                                              │
    │  ┌────────────────────────────────────────────────────────────────────────┐ │
    │  │                        BACKEND COMPONENTS                              │ │
    │  │                                                                        │ │
    │  │  ┌───────────────────┐    ┌───────────────────┐    ┌──────────────┐  │ │
    │  │  │   LLM Engine      │    │   Auth Layer      │    │  Encryption  │  │ │
    │  │  │  Ollama/Qwen72B   │    │  Ed25519 Verify   │    │  AES-256-GCM │  │ │
    │  │  │  /generate        │    │  @require_auth    │    │  PBKDF2      │  │ │
    │  │  └───────────────────┘    └───────────────────┘    └──────────────┘  │ │
    │  │                                                                        │ │
    │  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
    │  │  │                    STORAGE MANAGER                               │ │ │
    │  │  │                                                                  │ │ │
    │  │  │  📁 Local Disk Storage (Active Chats)                           │ │ │
    │  │  │  Path: /var/lib/trinity/chats/{principal}/                      │ │ │
    │  │  │                                                                  │ │ │
    │  │  │  ┌─────────────────────────────────────────────────────────┐    │ │ │
    │  │  │  │  POST /chat/autosave                                    │    │ │ │
    │  │  │  │  ├─ Verify Ed25519 signature                            │    │ │ │
    │  │  │  │  ├─ Save encrypted JSON to disk                         │    │ │ │
    │  │  │  │  └─ Update metadata.json                                │    │ │ │
    │  │  │  └─────────────────────────────────────────────────────────┘    │ │ │
    │  │  │                              │                                   │ │ │
    │  │  │                              ▼                                   │ │ │
    │  │  │  ┌──────────────────────────────────────────────────────────┐   │ │ │
    │  │  │  │  chats/{principal}/                                      │   │ │ │
    │  │  │  │  ├── chat-abc123.json    (encrypted with principal ID)   │   │ │ │
    │  │  │  │  ├── chat-def456.json    {                               │   │ │ │
    │  │  │  │  ├── chat-ghi789.json      "encryptedData": "...",       │   │ │ │
    │  │  │  │  └── metadata.json         "salt": "...",                │   │ │ │
    │  │  │  │                            "iv": "..."                   │   │ │ │
    │  │  │  │                          }                               │   │ │ │
    │  │  │  └──────────────────────────────────────────────────────────┘   │ │ │
    │  │  └──────────────────────────────────────────────────────────────────┘ │ │
    │  │                                                                        │ │
    │  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
    │  │  │                    ARCHIVE MANAGER                               │ │ │
    │  │  │                                                                  │ │ │
    │  │  │  ┌────────────────────────────────────────────────────────────┐ │ │ │
    │  │  │  │  POST /chat/{chat_id}/archive  (CURRENT - Individual)     │ │ │ │
    │  │  │  │  ├─ Read single encrypted chat from disk                  │ │ │ │
    │  │  │  │  ├─ Upload to Pinata → Filecoin                           │ │ │ │
    │  │  │  │  └─ Return recovery ID: {principal}:{cid}:{timestamp}     │ │ │ │
    │  │  │  └────────────────────────────────────────────────────────────┘ │ │ │
    │  │  │                                                                  │ │ │
    │  │  │  ┌────────────────────────────────────────────────────────────┐ │ │ │
    │  │  │  │  POST /chat/archive-all  (PENDING - Bulk Archive)         │ │ │ │
    │  │  │  │  ├─ Read ALL chats from principal's directory             │ │ │ │
    │  │  │  │  ├─ Bundle into single JSON structure                     │ │ │ │
    │  │  │  │  ├─ Upload bundle to Pinata → Filecoin                    │ │ │ │
    │  │  │  │  └─ Return: {principal}:full-backup:{cid}:{timestamp}     │ │ │ │
    │  │  │  └────────────────────────────────────────────────────────────┘ │ │ │
    │  │  │                              │                                   │ │ │
    │  │  │                              ▼                                   │ │ │
    │  │  │                    Upload to Filecoin                            │ │ │
    │  │  └──────────────────────────┬───────────────────────────────────────┘ │ │
    │  └──────────────────────────────┼──────────────────────────────────────┘ │
    │                                 │                                         │
    └─────────────────────────────────┼─────────────────────────────────────────┘
                                      │
                                      │ HTTPS POST
                                      ▼
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │                                                                              │
    │  ☁️  PINATA (Filecoin Gateway Service)                                      │
    │      API: https://api.pinata.cloud/pinning/pinFileToIPFS                    │
    │      Auth: JWT Bearer Token (FILECOIN_API_KEY)                              │
    │                                                                              │
    │  ┌────────────────────────────────────────────────────────────────────────┐ │
    │  │  Process:                                                              │ │
    │  │  1. Receive multipart/form-data upload                                 │ │
    │  │  2. Generate IPFS CID (Content ID) hash                                │ │
    │  │  3. Pin to Filecoin network (replicas: FRA1, NYC1)                     │ │
    │  │  4. Return CID (e.g., QmZeYzPA3jTYKmjHDZzgDg4kEGTf6R1EUpaNsnKHKCLHoy)  │ │
    │  └────────────────────────────────────────────────────────────────────────┘ │
    │                                 │                                            │
    └─────────────────────────────────┼────────────────────────────────────────────┘
                                      │
                                      ▼
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │                                                                              │
    │  🗃️  FILECOIN NETWORK (Decentralized Storage)                               │
    │      Protocol: IPFS (InterPlanetary File System)                            │
    │      Content Addressing: CID = Hash(encrypted_chat_data)                    │
    │                                                                              │
    │  ┌────────────────────────────────────────────────────────────────────────┐ │
    │  │  Stored Content:                                                       │ │
    │  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
    │  │  │  CID: QmZeYzPA3jTYKmjHDZzgDg4kEGTf6R1EUpaNsnKHKCLHoy            │ │ │
    │  │  │  Size: ~10-50 KB per chat                                        │ │ │
    │  │  │  Replicas: 2 (FRA1, NYC1)                                        │ │ │
    │  │  │                                                                  │ │ │
    │  │  │  Content (encrypted):                                            │ │ │
    │  │  │  {                                                               │ │ │
    │  │  │    "encryptedData": "AES-256-GCM ciphertext...",                │ │ │
    │  │  │    "salt": "random 16 bytes",                                   │ │ │
    │  │  │    "iv": "random 12 bytes",                                     │ │ │
    │  │  │    "chatId": "abc123",                                          │ │ │
    │  │  │    "archivedAt": 1737331200000                                  │ │ │
    │  │  │  }                                                               │ │ │
    │  │  │                                                                  │ │ │
    │  │  │  ⚠️  Pinata/Filecoin CANNOT decrypt - no principal key          │ │ │
    │  │  └──────────────────────────────────────────────────────────────────┘ │ │
    │  └────────────────────────────────────────────────────────────────────────┘ │
    │                                 │                                            │
    │  Available via IPFS Gateways:   │                                            │
    │  ├─ https://ipfs.io/ipfs/{CID}  │                                            │
    │  ├─ https://cloudflare-ipfs.com/ipfs/{CID}                                  │
    │  ├─ https://w3s.link/ipfs/{CID}                                             │
    │  └─ https://{CID}.ipfs.w3s.link                                             │
    └──────────────────────────────────┼─────────────────────────────────────────┘
                                       │
                                       │ RECOVERY FLOW
                                       ▼
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │  User enters recovery ID: {principal}:{cid}:{timestamp}                      │
    │                                                                              │
    │  GET /chat/archive-recover/{filepointId}                                     │
    │  ├─ Parse recovery ID                                                        │
    │  ├─ Verify principal matches authenticated user                             │
    │  ├─ Download from IPFS gateways (multi-gateway fallback)                    │
    │  ├─ Decrypt with principal ID                                               │
    │  └─ Restore chat to browser                                                 │
    └──────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Autosave (Akash Storage)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AUTOSAVE FLOW (Every Message)                         │
└──────────────────────────────────────────────────────────────────────────────┘

    👤 User                    🎨 Frontend                  🖥️  Akash Backend
     │                          │                            │
     │  Type message            │                            │
     │─────────────────────────▶│                            │
     │                          │                            │
     │                          │  Send to LLM               │
     │                          │───────────────────────────▶│
     │                          │                            │
     │                          │                            │  /generate
     │                          │                            │  (Ollama/Qwen)
     │                          │◀───────────────────────────│
     │                          │  AI Response               │
     │                          │                            │
     │◀─────────────────────────│  Display                   │
     │  See AI response         │                            │
     │                          │                            │
     │                          │  [Debounce: 2 seconds]     │
     │                          │                            │
     │                          │  POST /chat/autosave       │
     │                          │  {                         │
     │                          │    chatId: "abc123",       │
     │                          │    encryptedData: "...",   │  Verify signature
     │                          │    salt: "...",            │  (Ed25519)
     │                          │    iv: "..."               │
     │                          │  }                         │
     │                          │───────────────────────────▶│
     │                          │  + X-Principal-ID          │  Derive key from
     │                          │  + X-Signature             │  principal ID
     │                          │  + X-Timestamp             │  (PBKDF2 100k iter)
     │                          │                            │
     │                          │                            │  Write to disk:
     │                          │                            │  /chats/{principal}/
     │                          │                            │    chat-abc123.json
     │                          │                            │
     │                          │◀───────────────────────────│
     │                          │  { success: true }         │
     │                          │                            │
     │                          │  ✅ Autosaved              │
     │  [Visual indicator]      │                            │
     │◀─────────────────────────│                            │
     │  Rainbow wave animation  │                            │


    STORAGE STRUCTURE:
    
    /var/lib/trinity/chats/
    └── {principal-id}/
        ├── chat-abc123.json      ← Encrypted with principal ID
        ├── chat-def456.json
        ├── chat-ghi789.json
        └── metadata.json         ← Chat list, titles, timestamps
            {
              "principalId": "abc...",
              "chats": [
                {
                  "chatId": "abc123",
                  "title": "Hello World Chat",
                  "createdAt": 1737331200000,
                  "lastUpdated": 1737331500000,
                  "messageCount": 12,
                  "isArchived": false
                }
              ]
            }
```

---

## Data Flow: Individual Archive (Current Implementation)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    INDIVIDUAL ARCHIVE FLOW (One Chat → One CID)               │
└──────────────────────────────────────────────────────────────────────────────┘

    👤 User                    🎨 Frontend                  🖥️  Akash              ☁️  Pinata/Filecoin
     │                          │                            │                     │
     │  Hover over chat         │                            │                     │
     │  Click 📦 Archive        │                            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │                            │                     │
     │                          │  Confirm:                  │                     │
     │◀─────────────────────────│  "Archive this chat?"      │                     │
     │  Click YES               │                            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │                            │                     │
     │                          │  POST /chat/abc123/archive │                     │
     │                          │───────────────────────────▶│                     │
     │                          │  + Auth headers            │                     │
     │                          │                            │                     │
     │                          │                            │  Read from disk:    │
     │                          │                            │  chat-abc123.json   │
     │                          │                            │  (already encrypted)│
     │                          │                            │                     │
     │                          │                            │  POST /pinning/     │
     │                          │                            │  pinFileToIPFS      │
     │                          │                            │────────────────────▶│
     │                          │                            │  Auth: JWT Bearer   │
     │                          │                            │  Content-Type:      │
     │                          │                            │  multipart/form-data│
     │                          │                            │                     │
     │                          │                            │                     │  Pin to Filecoin
     │                          │                            │                     │  (FRA1, NYC1)
     │                          │                            │                     │  Generate CID
     │                          │                            │                     │
     │                          │                            │◀────────────────────│
     │                          │                            │  { IpfsHash: "Qm..."}
     │                          │                            │                     │
     │                          │                            │  Create recovery ID: │
     │                          │                            │  {principal}:        │
     │                          │                            │   {cid}:             │
     │                          │                            │   {timestamp}        │
     │                          │                            │                     │
     │                          │                            │  Update metadata:    │
     │                          │                            │  isArchived = true   │
     │                          │                            │  archivedAt = ...    │
     │                          │                            │  filepointId = ...   │
     │                          │◀───────────────────────────│                     │
     │                          │  {                         │                     │
     │                          │    filepointId: "abc:Qm:ts"                      │
     │                          │    cid: "Qm...",           │                     │
     │                          │    success: true           │                     │
     │                          │  }                         │                     │
     │                          │                            │                     │
     │                          │  Show Recovery ID Dialog   │                     │
     │◀─────────────────────────│  ┌──────────────────────┐  │                     │
     │  See modal:              │  │ Archive Successful!  │  │                     │
     │  ┌──────────────────────┐│  │                      │  │                     │
     │  │ Recovery ID:         ││  │ Save this ID:        │  │                     │
     │  │ abc:Qm...:1737331200 ││  │ abc:Qm...:1737331200 │  │                     │
     │  │                      ││  │                      │  │                     │
     │  │ [Copy ID]  [Close]   ││  │ ⚠️  Keep it safe!     │  │                     │
     │  └──────────────────────┘│  └──────────────────────┘  │                     │
     │                          │                            │                     │
     │  Click [Copy ID]         │                            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │  navigator.clipboard       │                     │
     │                          │    .writeText(filepointId) │                     │
     │                          │                            │                     │
     │◀─────────────────────────│  "✅ Copied!"              │                     │
     │  Toast notification      │                            │                     │


    RESULT:
    
    Filecoin/IPFS:
    CID: QmZeYzPA3jTYKmjHDZzgDg4kEGTf6R1EUpaNsnKHKCLHoy
    Content: {encrypted chat data}
    Size: ~15 KB
    Accessible via: https://ipfs.io/ipfs/Qm...
    
    User has recovery ID: abc:Qm...:1737331200
    Chat removed from active list (moved to "Archived" section)
```

---

## Data Flow: Bulk Archive (Pending Implementation)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                  BULK ARCHIVE FLOW (All Chats → One CID)                     │
└──────────────────────────────────────────────────────────────────────────────┘

    👤 User                    🎨 Frontend                  🖥️  Akash              ☁️  Pinata/Filecoin
     │                          │                            │                     │
     │  Click button:           │                            │                     │
     │  "📦 Archive All Chats"  │                            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │                            │                     │
     │                          │  Confirm:                  │                     │
     │◀─────────────────────────│  "Archive all 15 chats     │                     │
     │  Click YES               │   to Filecoin?"            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │                            │                     │
     │                          │  POST /chat/archive-all    │                     │
     │                          │───────────────────────────▶│                     │
     │                          │  + Auth headers            │                     │
     │                          │                            │                     │
     │                          │                            │  Load metadata.json │
     │                          │                            │  Get all chat IDs   │
     │                          │                            │                     │
     │                          │                            │  Read ALL chats:    │
     │                          │                            │  ├─ chat-abc123.json│
     │                          │                            │  ├─ chat-def456.json│
     │                          │                            │  └─ chat-ghi789.json│
     │                          │                            │                     │
     │                          │                            │  Bundle into:       │
     │                          │                            │  {                  │
     │                          │                            │    version: "2.0",  │
     │                          │                            │    archiveType:     │
     │                          │                            │      "full-backup", │
     │                          │                            │    principal: "...", │
     │                          │                            │    chatCount: 15,   │
     │                          │                            │    chats: [...]     │
     │                          │                            │  }                  │
     │                          │                            │                     │
     │                          │                            │  POST /pinning/     │
     │                          │                            │  pinFileToIPFS      │
     │                          │                            │────────────────────▶│
     │                          │                            │  (Bundle ~200KB)    │
     │                          │                            │                     │
     │                          │                            │                     │  Pin to Filecoin
     │                          │                            │                     │  Generate CID
     │                          │                            │                     │
     │                          │                            │◀────────────────────│
     │                          │                            │  { IpfsHash: "bafy"}
     │                          │                            │                     │
     │                          │                            │  Create recovery ID: │
     │                          │                            │  {principal}:        │
     │                          │                            │   full-backup:       │
     │                          │                            │   {cid}:             │
     │                          │                            │   {timestamp}        │
     │                          │                            │                     │
     │                          │                            │  Mark ALL chats as  │
     │                          │                            │  archived in        │
     │                          │                            │  metadata.json      │
     │                          │◀───────────────────────────│                     │
     │                          │  {                         │                     │
     │                          │    filepointId:            │                     │
     │                          │      "abc:full-backup:     │                     │
     │                          │       bafy:ts",            │                     │
     │                          │    chatCount: 15,          │                     │
     │                          │    success: true           │                     │
     │                          │  }                         │                     │
     │                          │                            │                     │
     │                          │  Show Recovery ID Dialog   │                     │
     │◀─────────────────────────│  ┌───────────────────────┐ │                     │
     │  See modal:              │  │ Bulk Archive Success! │ │                     │
     │  ┌───────────────────────┐│  │                       │ │                     │
     │  │ ✅ 15 chats archived  ││  │ 15 chats → 1 CID     │ │                     │
     │  │                       ││  │                       │ │                     │
     │  │ Recovery ID:          ││  │ Recovery ID:          │ │                     │
     │  │ abc:full-backup:      ││  │ abc:full-backup:      │ │                     │
     │  │ bafy:1737331200       ││  │ bafy:1737331200       │ │                     │
     │  │                       ││  │                       │ │                     │
     │  │ [Copy ID]  [Close]    ││  │ ⚠️  Keep it safe!      │ │                     │
     │  └───────────────────────┘│  └───────────────────────┘ │                     │
     │                          │                            │                     │


    RESULT:
    
    Filecoin/IPFS:
    CID: bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi
    Content: {bundle with 15 encrypted chats}
    Size: ~200 KB (15 chats × ~13KB avg)
    Accessible via: https://ipfs.io/ipfs/bafy...
    
    User has ONE recovery ID for ALL chats:
    abc:full-backup:bafy...:1737331200
    
    All chats cleared from active storage (moved to "Archived")
```

---

## Data Flow: Recovery (Download from Filecoin)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          RECOVERY FLOW (IPFS → Akash)                         │
└──────────────────────────────────────────────────────────────────────────────┘

    👤 User                    🎨 Frontend                  🖥️  Akash              🗃️  IPFS Gateways
     │                          │                            │                     │
     │  Click "Recover Chat"    │                            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │                            │                     │
     │                          │  Show input dialog:        │                     │
     │◀─────────────────────────│  "Enter Recovery ID"       │                     │
     │                          │                            │                     │
     │  Paste ID:               │                            │                     │
     │  abc:Qm...:1737331200    │                            │                     │
     │─────────────────────────▶│                            │                     │
     │                          │                            │                     │
     │                          │  GET /chat/archive-recover/│                     │
     │                          │      abc:Qm...:1737331200  │                     │
     │                          │───────────────────────────▶│                     │
     │                          │  + Auth headers            │                     │
     │                          │                            │                     │
     │                          │                            │  Parse recovery ID: │
     │                          │                            │  parts = split(":")  │
     │                          │                            │                     │
     │                          │                            │  IF 4 parts &&      │
     │                          │                            │     parts[1] ==     │
     │                          │                            │     "full-backup":  │
     │                          │                            │    → Bulk restore   │
     │                          │                            │  ELSE:              │
     │                          │                            │    → Single restore │
     │                          │                            │                     │
     │                          │                            │  Verify principal   │
     │                          │                            │  matches auth user  │
     │                          │                            │                     │
     │                          │                            │  Extract CID: "Qm..." │
     │                          │                            │                     │
     │                          │                            │  Try Gateway 1:     │
     │                          │                            │  ipfs.io/ipfs/{CID} │
     │                          │                            │────────────────────▶│
     │                          │                            │                     │
     │                          │                            │◀────────────────────│
     │                          │                            │  (encrypted bytes)   │
     │                          │                            │                     │
     │                          │                            │  Decrypt with       │
     │                          │                            │  principal ID:      │
     │                          │                            │  - PBKDF2 derive key │
     │                          │                            │  - AES-256-GCM      │
     │                          │                            │                     │
     │                          │                            │  Decrypted:         │
     │                          │                            │  {                  │
     │                          │                            │    chatId: "...",   │
     │                          │                            │    messages: [...], │
     │                          │                            │    title: "..."     │
     │                          │                            │  }                  │
     │                          │◀───────────────────────────│                     │
     │                          │  {                         │                     │
     │                          │    chatId: "abc123",       │                     │
     │                          │    messages: [...],        │                     │
     │                          │    isArchived: true,       │                     │
     │                          │    recoveredAt: timestamp  │                     │
     │                          │  }                         │                     │
     │                          │                            │                     │
     │◀─────────────────────────│  Restore chat to UI        │                     │
     │  See chat messages       │                            │                     │
     │  ⚠️  Read-only view       │                            │                     │
     │                          │                            │                     │


    GATEWAY FALLBACK SEQUENCE:
    
    1. https://ipfs.io/ipfs/{CID}                (timeout: 30s)
       └─ FAIL → try next
    
    2. https://cloudflare-ipfs.com/ipfs/{CID}    (timeout: 30s)
       └─ FAIL → try next
    
    3. https://w3s.link/ipfs/{CID}                (timeout: 30s)
       └─ FAIL → try next
    
    4. https://{CID}.ipfs.w3s.link                (timeout: 30s)
       └─ FAIL → return error
    
    If all gateways fail: "Failed to download from Filecoin"
```

---

## Security Architecture

### Encryption Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TRINITY ENCRYPTION ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────────────┘

    🔐 Layer 1: AUTHENTICATION (Ed25519)
    ═══════════════════════════════════════
    Purpose: Verify user identity
    Algorithm: Ed25519 (256-bit elliptic curve)
    
    ┌─────────────────────────────────────┐
    │ Browser generates keypair:          │
    │ - Private Key (64 bytes)            │
    │ - Public Key (32 bytes)             │
    │                                     │
    │ Principal ID = base32(SHA-224(pk))  │
    └─────────────────────────────────────┘
                    │
                    ▼
    Every API request includes:
    - X-Principal-ID: {principal}
    - X-Timestamp: {unix_ms}
    - X-Signature: Ed25519.sign(timestamp, private_key)
    
    Backend verifies:
    ✓ Signature valid?
    ✓ Timestamp within 5 minutes?
    ✓ Principal matches signature?
    
    
    🔐 Layer 2: CONTENT ENCRYPTION (AES-256-GCM)
    ═══════════════════════════════════════════
    Purpose: Encrypt chat data at rest
    Algorithm: AES-256-GCM (authenticated encryption)
    
    ┌─────────────────────────────────────────────────────────┐
    │ Key Derivation (PBKDF2):                                │
    │                                                         │
    │ Input:                                                  │
    │ - Password: Principal ID (base32 string)                │
    │ - Salt: Random 16 bytes (per file)                      │
    │ - Iterations: 100,000                                   │
    │ - Hash: SHA-256                                         │
    │                                                         │
    │ Output:                                                 │
    │ - Encryption Key: 256 bits (32 bytes)                   │
    └─────────────────────────────────────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────────────────────────┐
    │ Encryption (AES-256-GCM):                               │
    │                                                         │
    │ Plaintext:                                              │
    │ {                                                       │
    │   "chatId": "abc123",                                   │
    │   "messages": [                                         │
    │     { "role": "user", "content": "Hello" },             │
    │     { "role": "assistant", "content": "Hi!" }           │
    │   ]                                                     │
    │ }                                                       │
    │                                                         │
    │ Encrypted:                                              │
    │ {                                                       │
    │   "encryptedData": "ZjIwMzRhNTY3ODk...",   (ciphertext) │
    │   "salt": "a1b2c3d4...",                  (16 bytes)    │
    │   "iv": "e5f6g7h8...",                    (12 bytes)    │
    │   "tag": "i9j0k1l2..."                    (16 bytes)    │
    │ }                                                       │
    └─────────────────────────────────────────────────────────┘
    
    
    🔐 Layer 3: ZERO-KNOWLEDGE STORAGE
    ═══════════════════════════════════
    
    ┌─────────────────────────────────────────────────────────┐
    │ Akash Backend Storage:                                  │
    │ - Stores encrypted JSON files                           │
    │ - CANNOT decrypt (no principal key stored)              │
    │ - Can only verify signatures                            │
    └─────────────────────────────────────────────────────────┘
    
    ┌─────────────────────────────────────────────────────────┐
    │ Pinata/Filecoin Storage:                                │
    │ - Stores encrypted files on IPFS                        │
    │ - CANNOT decrypt (no principal key)                     │
    │ - Content addressed by hash (CID)                       │
    │ - Publicly accessible but encrypted                     │
    └─────────────────────────────────────────────────────────┘
    
    
    🔐 Security Properties:
    ═══════════════════════
    
    ✅ Self-Custody: Only user has private key (browser localStorage)
    ✅ End-to-End: Data encrypted before leaving browser
    ✅ Zero-Knowledge: Servers cannot decrypt user data
    ✅ Authenticated: Ed25519 signatures prevent impersonation
    ✅ Replay Protection: Timestamp validation (5-minute window)
    ✅ Content Integrity: AES-GCM authentication tag
    ✅ Key Isolation: Separate keys per user (derived from principal)
```

---

## Storage Cost Analysis

### Pinata Free Tier
- **Storage**: 1 GB free
- **Bandwidth**: 100 GB/month free
- **API Requests**: Unlimited

### Estimated Chat Sizes
| Scenario | Messages per Chat | Size per Chat | 100 Chats | 1000 Chats |
|----------|-------------------|---------------|-----------|------------|
| Light usage | 10-20 messages | 5-15 KB | 0.5-1.5 MB | 5-15 MB |
| Medium usage | 50-100 messages | 20-50 KB | 2-5 MB | 20-50 MB |
| Heavy usage | 200+ messages | 80-150 KB | 8-15 MB | 80-150 MB |

### Individual Archive Strategy (Current)
- **Pro**: Granular control - archive specific chats
- **Pro**: Smaller uploads - faster for single chats
- **Con**: Many CIDs to manage - user tracks multiple recovery IDs
- **Con**: More API calls - each archive = 1 Pinata request

**Example:** 50 chats × 30 KB each = 1.5 MB total, but 50 separate CIDs

### Bulk Archive Strategy (Pending)
- **Pro**: Single recovery ID - one ID for entire history
- **Pro**: Fewer API calls - 1 request for all chats
- **Pro**: Better compression - bundle can be compressed
- **Con**: Larger uploads - may take longer for hundreds of chats
- **Con**: All-or-nothing - must restore entire bundle

**Example:** 50 chats bundled = 1.5 MB, 1 CID, 1 recovery ID

### Recommendation
- **Individual archive**: Good for selective archiving (specific important chats)
- **Bulk archive**: Best for "backup everything" use case
- **Hybrid approach**: Support both, let user choose per use case

---

## Implementation Status

### ✅ Phase 1: Akash Active Storage - COMPLETE
- Autosave every message (debounced 2 seconds)
- AES-256-GCM encryption with PBKDF2 key derivation
- Principal-based directory isolation
- Metadata management (chat list, titles, timestamps)
- Retry logic with exponential backoff

### 🟡 Phase 2: Filecoin Archive - PARTIAL
#### ✅ Complete:
- Individual chat archiving (`POST /chat/{chat_id}/archive`)
- Pinata API integration with JWT authentication
- Multi-gateway IPFS recovery (4 gateways with 30s timeout)
- Recovery endpoint with decryption (`GET /chat/archive-recover/{id}`)
- Principal verification for security
- Archive UI with hover-activated button (📦)

#### ⏳ Pending:
- Bulk archive endpoint (`POST /chat/archive-all`)
- 4-part recovery ID parsing (`principal:full-backup:cid:timestamp`)
- Copy ID button robustness (textarea + fallback)
- Bulk recovery flow (restore all chats from one CID)
- Archive strategy selection UI (individual vs bulk)

### 📋 Next Steps:
1. Implement `POST /chat/archive-all` in [inference_server.py](../deployment/scripts/inference_server.py)
2. Update recovery endpoint to detect 4-part IDs and handle bulk restore
3. Add "Archive All Chats" button to sidebar in [app.js](../trinity-icp/src/trinity_frontend/assets/app.js)
4. Improve copy button with textarea selection and `execCommand` fallback
5. Test end-to-end: bulk archive → recovery with 15+ chats

---

## Related Documentation

- **Network Architecture**: [trinity-network-architecture.md](trinity-network-architecture.md)
- **Implementation Status**: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- **Filecoin Setup Guide**: [../deployment/docs/FILECOIN_SETUP.md](../deployment/docs/FILECOIN_SETUP.md)
- **Backend Code**: [../deployment/scripts/inference_server.py](../deployment/scripts/inference_server.py)
- **Frontend Code**: [../trinity-icp/src/trinity_frontend/assets/app.js](../trinity-icp/src/trinity_frontend/assets/app.js)

---

**Last Updated:** January 20, 2026  
**Status:** Individual archive production-ready | Bulk archive in development  
**Tests:** 4/4 Filecoin integration tests passing
