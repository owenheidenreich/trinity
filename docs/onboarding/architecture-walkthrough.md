# Trinity Architecture Walkthrough

This document provides a comprehensive overview of Trinity's architecture for new developers.

## System Overview

Trinity is a **decentralized AI chat application** with:
- **Self-custody authentication** (Ed25519 keypairs, no passwords)
- **Encrypted storage** (AES-256-GCM)
- **Multi-model routing** (complexity-based LLM selection)
- **Fully decentralized deployment** (ICP + Akash + IPFS)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER'S BROWSER                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Trinity Frontend (ICP Canister)                             │    │
│  │  - Vanilla JS + Zustand state                                │    │
│  │  - Ed25519 key generation                                    │    │
│  │  - KaTeX math rendering                                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS (signed requests)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Cloudflare Worker (SSL Termination + Proxy)                         │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTP (internal)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     AKASH DEPLOYMENT                                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Trinity Backend (Flask + Ollama)                              │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐ │  │
│  │  │ Auth Layer  │  │ Agent Layer  │  │ Storage Layer         │ │  │
│  │  │ - Ed25519   │  │ - Complexity │  │ - Encrypted JSON      │ │  │
│  │  │ - Principal │  │ - LangGraph  │  │ - IPFS backup         │ │  │
│  │  │ - Rate Lim  │  │ - Voting     │  │ - User memory         │ │  │
│  │  └─────────────┘  └──────────────┘  └───────────────────────┘ │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  Ollama (Local LLM Inference)                           │  │  │
│  │  │  - Tier 2: Llama 3.1 8B (~$50/mo)                       │  │  │
│  │  │  - Tier 3: Qwen 72B (~$200/mo)                          │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow

### 1. User Sends Message

```
User types "What is quantum computing?" → Frontend
```

### 2. Frontend Signs Request

```javascript
// Frontend creates Ed25519 signature
const signature = await signMessage(privateKey, {
    principal: derivePrincipal(publicKey),
    timestamp: Date.now(),
    body: { prompt: "What is quantum computing?" }
});
```

### 3. Backend Authenticates

```python
# middleware/icp_auth.py
@require_auth
def generate_endpoint():
    # Signature verified, principal extracted
    principal = g.principal  # e.g., "rrkah-fqaaa-aaaaa-aaaaq-cai"
```

### 4. Complexity Classification

```python
# services/complexity.py
complexity = classify_complexity("What is quantum computing?")
# Returns: 'simple' | 'medium' | 'complex'

if complexity == 'complex':
    route_to_langgraph()
else:
    route_to_legacy()
```

### 5. Agent Processing

#### Legacy Pipeline (Simple/Medium queries)
```python
# Single-pass generation
response = call_ollama(prompt, max_tokens=500)
```

#### LangGraph Pipeline (Complex queries)
```python
# Multi-agent orchestration
graph = StateGraph(AgentState)
graph.add_node("planner", planner_node)
graph.add_node("executor", executor_node)
graph.add_node("critic", critic_node)
graph.add_edge("planner", "executor")
graph.add_edge("executor", "critic")
# ... cycles until quality threshold met
```

### 6. Response Returned

```python
return jsonify({
    "response": "Quantum computing is...",
    "complexity": "medium",
    "model": "llama3.1:8b",
    "passes": 1,
    "token_usage": {"prompt": 150, "completion": 200}
})
```

## Component Deep Dives

### Authentication (`icp_auth.py`)

Trinity uses **ICP-style authentication** with Ed25519 signatures:

```python
# Principal derivation (like ICP)
def derive_principal(public_key: bytes) -> str:
    """
    SHA224(public_key) + CRC32 checksum → base32 encoding
    Result: "rrkah-fqaaa-aaaaa-aaaaq-cai"
    """

# Request verification
def verify_signature(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Ed25519 signature verification (5-minute timestamp window)"""
```

### Complexity Classifier (`complexity.py`)

Determines query complexity for routing:

```python
def classify_complexity(query: str) -> str:
    """
    Analyzes:
    - Query length and structure
    - Keywords (simple: "what is", complex: "compare", "analyze")
    - Domain indicators (code, math, research)
    - Multi-step reasoning requirements
    
    Returns: 'simple' | 'medium' | 'complex'
    """
```

| Complexity | Examples | Pipeline |
|------------|----------|----------|
| Simple | "Hello", "What time is it?" | Legacy (1 pass) |
| Medium | "Explain REST APIs" | Legacy (1-2 passes) |
| Complex | "Compare React vs Vue for a large SPA" | LangGraph (3+ passes) |

### LangGraph Agent (`services/agent.py`)

Multi-agent orchestration for complex queries:

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Pipeline                    │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ Planner  │───▶│ Executor │───▶│  Critic  │          │
│  │          │    │          │    │          │          │
│  │ Break    │    │ Execute  │    │ Evaluate │          │
│  │ down     │    │ steps    │    │ quality  │          │
│  │ task     │    │          │    │          │          │
│  └──────────┘    └──────────┘    └────┬─────┘          │
│                                       │                 │
│                       ┌───────────────┴──────────────┐  │
│                       │                              │  │
│                       ▼                              ▼  │
│               Quality OK?                    Need more? │
│                   │                              │      │
│                   ▼                              ▼      │
│              Return response            Loop back to   │
│                                         Planner        │
└─────────────────────────────────────────────────────────┘
```

### Caching Layer (`services/caching.py`)

Two-tier caching for cost optimization:

```
┌─────────────────────────────────────────────────────────┐
│                    Caching Layer                         │
│                                                          │
│  Request: "What is machine learning?"                    │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────────┐│
│  │           SemanticResponseCache                      ││
│  │  Is there a >95% similar cached query?               ││
│  │  ✓ Yes → Return cached response                      ││
│  │  ✗ No  → Continue to embedding                       ││
│  └─────────────────────────────────────────────────────┘│
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────────┐│
│  │             EmbeddingCache                           ││
│  │  Is this exact text cached?                          ││
│  │  ✓ Yes → Return cached embedding                     ││
│  │  ✗ No  → Compute embedding, cache it                 ││
│  └─────────────────────────────────────────────────────┘│
│                     │                                    │
│                     ▼                                    │
│              Continue to LLM...                          │
└─────────────────────────────────────────────────────────┘
```

### A/B Testing (`services/experiments.py`)

Hash-based deterministic experiment assignment:

```python
# Same user always gets same variant
def assign_variant(experiment: str, session_id: str) -> Variant:
    hash_value = sha256(f"{experiment}:{session_id}")
    # 50/50 split example:
    # hash < 0.5 → control
    # hash >= 0.5 → treatment
```

Current experiments:
- `agent_mode`: Legacy vs LangGraph routing
- `complexity_threshold`: Tuning complexity classifier
- `parallel_execution`: Run both pipelines, compare results

### Observability (`middleware/observability.py`)

Prometheus metrics for monitoring:

```python
# Key metrics
REQUEST_LATENCY = Histogram('trinity_http_request_duration_seconds', ...)
INFERENCE_DURATION = Histogram('trinity_inference_duration_seconds', ...)
EMBEDDING_CACHE_HITS = Counter('trinity_embedding_cache_hits_total', ...)
TOKENS_GENERATED = Counter('trinity_tokens_generated_total', ...)
```

Dashboard URLs (when deployed):
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Raw metrics: `http://localhost:5000/metrics`

## Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              REQUEST LIFECYCLE                              │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. INGRESS                                                                 │
│  ──────────                                                                 │
│  Browser → Cloudflare → Akash → Flask                                       │
│                                                                             │
│  2. MIDDLEWARE CHAIN                                                        │
│  ─────────────────────                                                      │
│  Request → Rate Limit → Auth Check → Experiment Assignment → Cache Check    │
│                                                                             │
│  3. PROCESSING                                                              │
│  ─────────────                                                              │
│  Query → Complexity → Route → [Legacy|LangGraph] → LLM → Response          │
│                                                                             │
│  4. EGRESS                                                                  │
│  ────────                                                                   │
│  Response → Metrics → Autosave → Return to Client                          │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

## Key Files Reference

| File | Purpose |
|------|---------|
| `inference_server.py` | Main Flask app, all endpoints |
| `icp_auth.py` | Ed25519 authentication |
| `encryption.py` | AES-256-GCM encryption |
| `services/agent.py` | LangGraph pipeline |
| `services/complexity.py` | Query complexity classifier |
| `services/caching.py` | Embedding + response caches |
| `services/experiments.py` | A/B testing framework |
| `middleware/observability.py` | Prometheus metrics |
| `middleware/rate_limit.py` | Rate limiting + quotas |

## Next Steps

- Read [Developer Setup](developer-setup.md) to configure your environment
- Check [Common Tasks](common-tasks.md) for development workflows
- Review [ADRs](../decisions/) for architectural decisions
