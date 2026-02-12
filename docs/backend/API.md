# Trinity Backend API Reference

> **Last Updated:** February 10, 2026  
> **Base URL:** `https://api.dubya.ai`  
> **Source:** [backend/inference_server.py](../../backend/inference_server.py)

---

## Overview

Trinity exposes **47 API endpoints** organized into these categories:

| Category | Endpoints | Auth Required | Description |
|----------|-----------|---------------|-------------|
| [Health](#health) | 2 | No | System status |
| [Metrics](#metrics) | 1 | No | Prometheus metrics |
| [Generate](#generate) | 6 | No | AI inference |
| [Chat Storage](#chat-storage) | 7 | Yes (Ed25519) | Encrypted chat persistence |
| [User Memory](#user-memory) | 4 | Yes (Ed25519) | Persistent user facts |
| [Tools](#tools) | 6 | No | Web search, document upload |
| [Admin](#admin) | 5 | No | Cache, experiments, quotas |
| [Session](#session) | 3 | No | Funding/session management |
| [V4 Vector](#v4-vector) | 5 | No | Semantic search (experimental) |

---

## Authentication

### Ed25519 Signature Auth

Required for all `/chat/*` and `/user/*` endpoints.

**Headers:**
```
X-ICP-Principal: <principal-id>
X-ICP-Timestamp: <unix-timestamp-ms>
X-ICP-Signature: <base64-signature>
X-ICP-Public-Key: <hex-public-key>
```

**Signature creation:**
```javascript
const message = JSON.stringify({
    timestamp: Date.now(),
    method: 'POST',
    path: '/chat/autosave',
    body: requestBody
});
const signature = ed25519.sign(message, privateKey);
```

**Timestamp window:** 60 seconds (configurable via `AUTH_TIMESTAMP_WINDOW`)

---

## Health

### GET /health

System health check with comprehensive status.

**Response:**
```json
{
  "status": "healthy",
  "version": "4.0.2",
  "build": "20260210-143052",
  "model": "qwen2.5:14b",
  "backend": "ollama",
  "tier": 2,
  "tier_name": "tier2-balanced",
  "gpu": "P40",
  "provider": "akash1xyz...",
  "features": {
    "v4_intelligence": true,
    "code_execution": false,
    "multi_model": true
  },
  "metrics": {
    "requests_total": 1523,
    "errors_total": 12,
    "uptime_seconds": 86400
  }
}
```

### GET /health/icp

ICP-specific health check for canister polling.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": 1707580800000,
  "icp_compatible": true
}
```

---

## Metrics

### GET /metrics

Prometheus-format metrics for monitoring.

**Response:** (text/plain)
```
# HELP trinity_http_requests_total Total HTTP requests
# TYPE trinity_http_requests_total counter
trinity_http_requests_total{endpoint="/generate",method="POST",status="200"} 1523

# HELP trinity_inference_duration_seconds LLM inference time
# TYPE trinity_inference_duration_seconds histogram
trinity_inference_duration_seconds_bucket{le="1.0"} 50
trinity_inference_duration_seconds_bucket{le="5.0"} 450
trinity_inference_duration_seconds_bucket{le="30.0"} 1500

# HELP trinity_tokens_generated_total Total tokens generated
# TYPE trinity_tokens_generated_total counter
trinity_tokens_generated_total 2500000
```

---

## Generate

### POST /generate

Main inference endpoint with complexity-based routing.

**Request:**
```json
{
  "prompt": "Explain quantum computing",
  "context": [
    {"role": "user", "content": "Previous message"},
    {"role": "assistant", "content": "Previous response"}
  ],
  "max_tokens": 500,
  "temperature": 0.7,
  "system_prompt": "You are a helpful assistant"
}
```

**Response:**
```json
{
  "response": "Quantum computing is...",
  "model": "qwen2.5:14b",
  "tokens_used": 450,
  "complexity": "medium",
  "pipeline": "legacy",
  "latency_ms": 5230
}
```

### POST /generate/simple

Direct Ollama call without agent pipeline.

**Request:**
```json
{
  "prompt": "What is 2+2?",
  "max_tokens": 100
}
```

### POST /generate/stream

Streaming inference with Server-Sent Events.

**Request:** Same as `/generate`

**Response:** (text/event-stream)
```
data: {"token": "Quantum"}
data: {"token": " computing"}
data: {"token": " is"}
data: {"done": true, "tokens_used": 450}
```

### POST /generate/simple/stream

Streaming without agent pipeline.

### POST /generate/agent

Legacy multi-pass agentic pipeline.

**Passes:** Understand → Plan → Execute → Critique → Refine

**Request:**
```json
{
  "prompt": "Write a Python function to sort a list",
  "context": [],
  "passes": 3
}
```

**Response:**
```json
{
  "response": "def sort_list(items):\n    return sorted(items)",
  "pipeline": "legacy_agent",
  "passes_used": 3,
  "complexity_score": 5
}
```

### POST /generate/langgraph

LangGraph multi-agent pipeline (for complex queries).

**Agents:** Supervisor → Research/Code/Synthesis → Final

**Request:**
```json
{
  "prompt": "Research the latest advances in fusion energy",
  "use_tools": true
}
```

---

## Chat Storage

All endpoints require Ed25519 authentication.

### POST /chat/autosave

Save encrypted chat to server storage.

**Request:**
```json
{
  "chat_id": "chat_abc123",
  "title": "Quantum Computing Discussion",
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ],
  "encrypted_content": "<base64-encrypted-data>",
  "metadata": {
    "created_at": 1707580800000,
    "updated_at": 1707580900000
  }
}
```

**Response:**
```json
{
  "success": true,
  "chat_id": "chat_abc123",
  "saved_at": 1707580900000
}
```

### GET /chat/list

List all chats for authenticated user.

**Response:**
```json
{
  "chats": [
    {
      "chat_id": "chat_abc123",
      "title": "Quantum Computing Discussion",
      "created_at": 1707580800000,
      "updated_at": 1707580900000,
      "message_count": 10
    }
  ],
  "total": 1
}
```

### GET /chat/:chat_id

Load specific chat.

**Response:**
```json
{
  "chat_id": "chat_abc123",
  "encrypted_content": "<base64-encrypted-data>",
  "metadata": {...}
}
```

### DELETE /chat/:chat_id

Delete specific chat.

**Response:**
```json
{
  "success": true,
  "deleted": "chat_abc123"
}
```

### POST /chat/:chat_id/archive

Archive chat to IPFS via Lighthouse.

**Response:**
```json
{
  "success": true,
  "cid": "bafybeib...",
  "archived_at": 1707580900000
}
```

### GET /chat/recover-archives

List IPFS archives for recovery.

**Response:**
```json
{
  "archives": [
    {
      "cid": "bafybeib...",
      "uploaded_at": 1707580800000,
      "size_bytes": 1024
    }
  ]
}
```

### GET /chat/archive/:cid

Download archived chat from IPFS.

---

## User Memory

Persistent facts across all conversations.

### GET /user/memory

Get all stored facts.

**Response:**
```json
{
  "facts": [
    "User prefers Python over JavaScript",
    "User works in healthcare AI"
  ],
  "updated_at": 1707580800000
}
```

### POST /user/memory

Replace all facts.

**Request:**
```json
{
  "facts": ["Fact 1", "Fact 2"]
}
```

### POST /user/memory/fact

Add single fact.

**Request:**
```json
{
  "fact": "User prefers dark mode"
}
```

### DELETE /user/memory/fact/:index

Delete fact by index.

---

## Tools

### POST /tools/search

Web search via Brave API.

**Request:**
```json
{
  "query": "latest AI news 2026",
  "count": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "title": "AI Breakthrough...",
      "url": "https://example.com/article",
      "snippet": "Researchers announced..."
    }
  ]
}
```

### POST /tools/browse

Fetch and summarize webpage.

**Request:**
```json
{
  "url": "https://example.com/article"
}
```

### POST /tools/search-and-summarize

Combined search + summarization.

### POST /tools/documents/upload

Upload document for RAG.

**Request:** multipart/form-data with file

### POST /tools/documents/query

Query uploaded documents.

### POST /tools/transcript/clean

Clean up meeting transcripts.

### GET /tools/status

Tool availability status.

---

## Admin

### GET /admin/experiments

List A/B experiments and assignments.

### POST /admin/experiments/:name/enable

Enable experiment.

### POST /admin/experiments/:name/disable

Disable experiment.

### GET /admin/experiments/assignment/:session_id

Check experiment assignment for session.

### GET /admin/cache/stats

Embedding and semantic cache statistics.

### POST /admin/cache/clear

Clear caches.

### GET /admin/tokens/usage

Token usage statistics.

### GET /admin/quota/usage

Rate limit quota status.

---

## Session

### GET /funding/status

Akash deployment funding status.

**Response:**
```json
{
  "session_id": "sess_xyz",
  "funded_akt": 100.5,
  "daily_cost_akt": 2.1,
  "days_remaining": 47.8,
  "wallet": "akash1xyz..."
}
```

### GET /session/status

Current session information.

### POST /session/request

Request new session (ICP integration).

### GET /session/check/:session_id

Check session status.

---

## V4 Vector (Experimental)

Semantic search and RAG capabilities.

### POST /v4/vector/index

Create vector index.

### POST /v4/vector/document

Add document to index.

### POST /v4/vector/search

Semantic search.

**Request:**
```json
{
  "query": "machine learning optimization",
  "top_k": 5
}
```

### POST /v4/vector/sync

Sync vector store to disk.

### POST /v4/tools/execute

Execute tool by name.

### GET /v4/status

V4 feature status.

---

## GET /stats

Legacy statistics endpoint.

**Response:**
```json
{
  "requests_total": 1523,
  "tokens_generated": 2500000,
  "uptime_seconds": 86400,
  "model": "qwen2.5:14b"
}
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {...}
}
```

**Common Error Codes:**

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_REQUIRED` | 401 | Missing authentication headers |
| `AUTH_INVALID` | 401 | Invalid signature or expired timestamp |
| `RATE_LIMITED` | 429 | Too many requests |
| `VALIDATION_ERROR` | 400 | Invalid request body |
| `NOT_FOUND` | 404 | Resource not found |
| `INTERNAL_ERROR` | 500 | Server error |

---

## Rate Limits

| Endpoint Category | Limit |
|-------------------|-------|
| `/generate/*` | 30 req/min per IP |
| `/chat/*` | 10 req/min per IP |
| `/tools/*` | 20 req/min per IP |
| `/admin/*` | No limit |

---

## CORS

Allowed origins:
- `https://dubya.ai`
- `https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io`
- `http://localhost:*` (development)
