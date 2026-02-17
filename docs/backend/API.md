# Trinity Backend API Reference

> **Last Updated:** February 16, 2026
> **Base URL:** `https://api.dubya.ai`

---

## Overview

Trinity exposes API endpoints organized into 9 blueprints. Auth uses Ed25519 signatures on protected routes (`/chat/*`, `/user/*`, `/tools/*`, `/mcp` POST, `/api/passphrase/*`, and `/v4/*`).

**Auth headers:** `ICP-Principal`, `ICP-Timestamp`, `ICP-Signature`, `ICP-PublicKey`, `ICP-Nonce`
**Signed message:** `{principal}:{timestamp}:{endpoint}:{nonce}`
**Timestamp window:** Config-driven via `AUTH_TIMESTAMP_WINDOW_MS` (default `60000`, i.e. 60 seconds)
**Binding rule:** `ICP-Principal` must match the principal derived from `ICP-PublicKey` (Ed25519 principal derivation)

---

## Health & Monitoring

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Server + Ollama status, model info, tier |
| GET | `/health/icp` | No | ICP-specific health check |
| GET | `/metrics` | No | Prometheus metrics (text/plain) |
| GET | `/stats` | No | Server statistics (JSON) |

---

## Generate

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/generate` | No | Standard inference |
| POST | `/generate/agent` | No | Agent inference with ReAct + tool calling (primary endpoint) |

### POST /generate/agent

**Request:**
```json
{
  "prompt": "What is the current price of Bitcoin?",
  "principal": "icp-principal-string",
  "context_messages": [{"role": "user", "content": "..."}],
  "user_memory": {"facts": [...]},
  "chat_id": "chat-abc123",
  "message_index": 10
}
```

**Response:** Server-Sent Events:
```
data: {"phase": "understanding", "message": "Analyzing..."}
data: {"token": "The "}
data: {"token": "current "}
data: {"done": true, "response": {"complexity": "medium"}}
```

---

## Chat Storage (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat/autosave` | Save encrypted chat (`chatId` field, camelCase) |
| GET | `/chat/list` | List user's chats |
| GET | `/chat/<chat_id>` | Load specific chat |
| DELETE | `/chat/<chat_id>` | Delete chat |
| POST | `/chat/<chat_id>/pin` | Pin/unpin chat |
| POST | `/chat/<chat_id>/archive` | Archive to IPFS |
| GET | `/chat/recover-archives` | List IPFS archives |
| GET | `/chat/archive/<cid>` | Load archived chat |
| GET | `/chat/archive/status/<cid>` | Check archive status |

---

## User Memory (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/user/status` | User account status |
| GET | `/user/memory` | Get stored facts |
| POST | `/user/memory` | Replace all facts |
| POST | `/user/memory/fact` | Add single fact |
| DELETE | `/user/memory/fact/<index>` | Delete fact |

---

## Tools (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tools/search` | Web search (Brave API) |
| POST | `/tools/browse` | Fetch & summarize webpage |
| POST | `/tools/search-and-summarize` | Search + summarize |
| POST | `/tools/documents/upload` | Upload document for RAG |
| POST | `/tools/documents/query` | Query documents |
| POST | `/tools/transcript/clean` | Clean transcript |
| GET | `/tools/status` | Tool availability |

---

## Admin (ADMIN_PRINCIPALS only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/cache/stats` | Cache statistics |
| POST | `/admin/cache/clear` | Clear all caches |
| GET | `/admin/tokens/usage` | Token usage |
| GET | `/admin/quota/usage` | Quota status |
| GET | `/admin/storage/status` | Storage status |
| POST | `/admin/storage/rollback/<principal_id>` | Rollback user storage |
| GET | `/admin/slo/status` | SLO metrics status |

---

## Session & Funding

| Method | Path | Description |
|--------|------|-------------|
| GET | `/funding/status` | Akash funding (AKT balance, cost/day) |
| GET | `/session/status` | Session info |
| POST | `/session/request` | Request session |
| GET | `/session/check/<id>` | Check session |

---

## Passphrase (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/passphrase/setup` | Set up passphrase for user |
| POST | `/api/passphrase/unlock` | Unlock with passphrase (rate-limited) |
| POST | `/api/passphrase/change` | Change passphrase |
| POST | `/api/passphrase/lock` | Lock session |
| GET | `/api/passphrase/status` | Get passphrase status |

---

## MCP (Model Context Protocol)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/mcp` | Server info & capabilities |
| POST | `/mcp` | **Auth required + rate-limited** JSON-RPC 2.0 (initialize, tools/list, tools/call) |

---

## V4 Vector (Experimental)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v4/status` | Feature status |
| POST | `/v4/vector/index` | Bulk index messages |
| POST | `/v4/vector/document` | Add document |
| POST | `/v4/vector/search` | Semantic search |
| POST | `/v4/vector/sync` | Sync to disk |
| POST | `/v4/tools/execute` | Execute tool |

---

## Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `AUTH_REQUIRED` | 401 | Missing auth headers |
| `AUTH_INVALID` | 401 | Invalid signature/expired |
| `RATE_LIMITED` | 429 | Too many requests |
| `VALIDATION_ERROR` | 400 | Invalid request |
| `NOT_FOUND` | 404 | Resource not found |
| `INTERNAL_ERROR` | 500 | Server error |

## Rate Limits

| Category | Limit |
|----------|-------|
| `/generate/*` | 30 req/min per principal |
| `/chat/*` | 10 req/min per principal |
| `/tools/*` | 30 req/min per principal |
| `/mcp` (POST) | 30 req/min per principal |
| `/api/passphrase/unlock` | Rate-limited |

---

## Feb 16, 2026 Corrections

- Enforced nonce-required auth and principal/public-key cryptographic binding.
- Removed legacy nonce-optional verification path.
- Locked down `/mcp` POST with `@require_auth` and rate limiting.
- Added auth + rate limiting protections for `/tools/documents/query` and `/tools/transcript/clean`.
- Hardened `run_command` execution path (`shell=False` + argument parsing), removing `shell=True` injection surface.
- Standardized quota identity resolution to authenticated principal.
- Applied token quota accounting/enforcement across generation paths.
- Added passphrase unlock throttling.
- Fixed cleanup metadata handling to decrypt/re-save through encrypted storage flow.

Minor interface fixes documented in code and tests:
- New accounts no longer show false "Recovered Chat" entries from non-chat artifacts.
- New chat creation no longer overwrites a single sidebar chat.
- Autosave now uses latest chat state so full conversation history is persisted per chat.

Validation snapshots:
- Security patch set: `976 passed, 9 skipped` (`backend/tests/`, no coverage gate).
- UI/chat fixes: backend lifecycle tests + frontend `useChat` tests + TypeScript check pass.
