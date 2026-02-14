# Trinity Backend API Reference

> **Last Updated:** February 13, 2026
> **Base URL:** `https://api.dubya.ai`

---

## Overview

Trinity exposes API endpoints organized into 8 blueprints. Auth uses Ed25519 signatures on all `/chat/*`, `/user/*`, and `/tools/*` routes.

**Auth headers:** `ICP-Principal`, `ICP-Timestamp`, `ICP-Signature`, `ICP-PublicKey`, `ICP-Nonce`
**Signed message:** `{timestamp}.{METHOD}.{path}.{sha256(body)}`
**Timestamp window:** 60 seconds

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

---

## Session & Funding

| Method | Path | Description |
|--------|------|-------------|
| GET | `/funding/status` | Akash funding (AKT balance, cost/day) |
| GET | `/session/status` | Session info |
| POST | `/session/request` | Request session |
| GET | `/session/check/<id>` | Check session |

---

## MCP (Model Context Protocol)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/mcp` | Server info & capabilities |
| POST | `/mcp` | JSON-RPC 2.0 (initialize, tools/list, tools/call) |

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
| `/tools/*` | 20 req/min per principal |
