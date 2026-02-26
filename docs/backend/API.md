# Trinity Backend API Reference

> **Last Updated:** February 25, 2026
> **Base URL:** `https://api.dubya.ai`

---

## Overview

Trinity exposes 31 API endpoints organized into 7 blueprints. Auth uses Ed25519 signatures on protected routes (`/chat/*`, `/user/*`, `/tools/*`, `/api/passphrase/*`).

**Auth headers:** `ICP-Principal`, `ICP-Timestamp`, `ICP-Signature`, `ICP-PublicKey`, `ICP-Nonce`
**Signed message:** `{principal}:{timestamp}:{endpoint}:{nonce}`
**Timestamp window:** Config-driven via `AUTH_TIMESTAMP_WINDOW_MS` (default `60000`, i.e. 60 seconds)
**Binding rule:** `ICP-Principal` must match the principal derived from `ICP-PublicKey` (Ed25519 principal derivation)

---

## Health & Monitoring

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Server + llama-server status, model info, tier |
| GET | `/health/icp` | No | ICP-specific health check |
| GET | `/metrics` | No | Prometheus metrics (text/plain) |
| GET | `/stats` | No | Server statistics (JSON) |

---

## Generate

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/generate` | No | Standard inference |
| POST | `/generate/agent` | Yes | Agent inference with canonical server-side persistence (primary endpoint) |

### POST /generate/agent

**Request:**
```json
{
  "prompt": "What is the current price of Bitcoin?",
  "chat_id": "optional-chat-id"
}
```

**Response:** Server-Sent Events:
```
data: {"type": "session", "chat_id": "chat-abc123", "user_message_id": 123}
data: {"phase": "understanding", "message": "Analyzing..."}
data: {"token": "The "}
data: {"token": "current "}
data: {"done": true, "assistant_message_id": 124, "done_reason": "stop"}
```

---

## Chat Storage (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat/start` | Create chat, return canonical `chat_id` |
| GET | `/chat/list` | List user's chats |
| GET | `/chat/<chat_id>?before_message_id=&limit=` | Load specific chat (paginated) |
| PATCH | `/chat/<chat_id>` | Update chat title/pin/archive |
| DELETE | `/chat/<chat_id>` | Delete chat |
| POST | `/chat/<chat_id>/pin` | Pin/unpin chat |
| POST | `/chat/<chat_id>/archive` | Archive to IPFS |
| GET | `/chat/recover-archives` | List IPFS archives |
| GET | `/chat/archive/status/<cid>` | Check archive status |

---

## User Memory (Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/user/status` | User account status |
| GET | `/user/memory` | Get stored facts |
| POST | `/user/memory/fact` | Add single fact |
| PATCH | `/user/memory/fact/<fact_id>` | Edit fact (text, category, importance) |
| DELETE | `/user/memory/fact/<fact_id>` | Soft-delete fact |
| GET | `/user/export` | Download all user data as ZIP |
| GET | `/user/stats` | User profile/chat/storage statistics |

---

## Tools (Rate-Limited)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tools/search` | Rate-limited | Web search (Brave API) |
| POST | `/tools/browse` | Rate-limited | Fetch & summarize webpage |
| POST | `/tools/search-and-summarize` | Rate-limited | Search + summarize |
| POST | `/tools/documents/upload` | Rate-limited | Upload document for RAG |
| POST | `/tools/documents/query` | Auth + rate-limited | Query documents |

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
| `/chat/*` | 30 req/min per principal |
| `/tools/*` | 30 req/min per principal |
| `/api/passphrase/unlock` | Rate-limited |

---

## Deleted Endpoints (Feb 25, 2026 Cleanup)

The following endpoint groups were removed — no frontend UI existed for them:

- **Admin** (`/admin/*`) — cache stats, token usage, quota, storage, SLO metrics (7 endpoints)
- **Session & Funding** (`/session/*`, `/funding/*`) — funding status, session requests (4 endpoints)
- **MCP** (`/mcp`) — Model Context Protocol JSON-RPC (2 endpoints)
- **Diagnostic** — diagnostic endpoints (2 endpoints)
- **Tools** — `/tools/transcript/clean`, `/tools/status` (2 endpoints)
- **Chat** — `/chat/archive/<cid>` (410 stub), `POST /user/memory` (410 stub)
- **V4 Vector** (`/v4/*`) — vector indexing, document embedding, semantic search (6 endpoints)
