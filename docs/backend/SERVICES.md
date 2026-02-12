# Trinity Backend Services

> **Last Updated:** February 10, 2026  
> **Location:** [backend/services/](../../backend/services/)

---

## Overview

The backend is organized into modular services:

```
backend/
├── inference_server.py      # App factory (349 lines) — blueprint registration, startup
├── config.py                # Environment variables and constants
├── encryption.py            # AES-256-GCM encryption
├── storage.py               # User directory management
├── validation.py            # Input validation, SSRF protection
├── icp_auth.py              # Ed25519 authentication
├── lighthouse.py            # IPFS/Filecoin storage
├── middleware/              # Request middleware
│   ├── rate_limit.py        # Per-IP rate limiting
│   ├── icp_cache.py         # Idempotency cache
│   └── observability.py     # Prometheus metrics
└── services/                # Business logic
    ├── agent.py             # Legacy multi-pass pipeline
    ├── agent_prompts.py     # Agent system prompts
    ├── akash.py             # Akash deployment info
    ├── caching.py           # Embedding cache
    ├── code_executor.py     # Sandboxed code execution
    ├── complexity.py        # Query complexity scoring
    ├── embeddings.py        # Text embeddings
    ├── experiments.py       # A/B testing
    ├── graph/               # LangGraph multi-agent
    ├── memory.py            # Conversation memory
    ├── ollama.py            # Ollama client
    ├── parallel.py          # Parallel inference
    ├── prompts.py           # System prompts
    ├── search.py            # Web search
    ├── structured.py        # Structured output
    ├── tools.py             # Tool definitions
    ├── tracing.py           # Request tracing
    ├── vector_store.py      # Vector database
    └── voting.py            # Response voting
```

---

## Core Modules

### config.py

Environment configuration and constants.

**Key Variables:**
```python
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5:14b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEPLOYMENT_TIER = int(os.getenv("DEPLOYMENT_TIER", "2"))
MAX_PROMPT_LENGTH = 32000
AUTH_TIMESTAMP_WINDOW = 60  # seconds
```

**Tier Detection:**
```python
DEPLOYMENT_TIER = {
    "tinyllama:1.1b": 1,
    "qwen2.5:14b": 2,
    "qwen2.5:72b": 3,
}.get(MODEL_NAME, 2)
```

---

### encryption.py

AES-256-GCM encryption with PBKDF2 key derivation.

**Class:** `EncryptionUtils`

**Methods:**
```python
@staticmethod
def encrypt(plaintext: str, password: str) -> str:
    """Encrypt with random salt + nonce, return base64."""
    
@staticmethod
def decrypt(ciphertext: str, password: str) -> str:
    """Decrypt base64 ciphertext."""
```

**Parameters:**
- Key derivation: PBKDF2 with 100,000 iterations
- Salt: 16 bytes random
- Nonce: 12 bytes random
- Password: Principal ID (user's identity)

---

### icp_auth.py

Ed25519 signature verification.

**Decorator:** `@require_auth`

**Usage:**
```python
@app.route("/chat/autosave", methods=["POST"])
@require_auth
def autosave():
    principal = g.principal  # Verified principal ID
    ...
```

**Verification Flow:**
1. Extract headers: `X-ICP-Principal`, `X-ICP-Timestamp`, `X-ICP-Signature`, `X-ICP-Public-Key`
2. Check timestamp within 60-second window
3. Reconstruct signed message
4. Verify Ed25519 signature
5. Derive principal from public key, compare

---

### validation.py

Input validation and security.

**Functions:**
```python
def validate_chat_id(chat_id: str) -> bool:
    """Alphanumeric + underscore, 1-64 chars."""

def validate_principal(principal: str) -> bool:
    """Valid ICP principal format."""

def validate_prompt(prompt: str) -> tuple[bool, str]:
    """Length check, encoding validation."""

def validate_url(url: str) -> tuple[bool, str]:
    """SSRF protection - blocks private IPs, file://, etc."""
```

**SSRF Protection:**
- Blocks: `10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`, `127.x.x.x`
- Blocks: `file://`, `ftp://`, `data:` schemes
- Follows redirects (max 5) and validates each hop

---

### storage.py

User directory and metadata management.

**Functions:**
```python
def get_user_dir(principal: str) -> Path:
    """Get/create user directory: data/users/{principal}/"""

def load_metadata(principal: str) -> dict:
    """Load user's metadata.json"""

def save_metadata(principal: str, metadata: dict) -> None:
    """Save user's metadata.json"""

def load_user_memory(principal: str) -> list[str]:
    """Load persistent facts from user_memory.json"""

def save_user_memory(principal: str, facts: list[str]) -> None:
    """Save persistent facts"""
```

**Directory Structure:**
```
data/users/{principal}/
├── metadata.json        # User metadata
├── user_memory.json     # Persistent facts
└── chats/
    ├── chat_abc.json    # Encrypted chat
    └── chat_xyz.json
```

---

### lighthouse.py

IPFS/Filecoin storage via Lighthouse SDK.

**Functions:**
```python
async def upload_to_ipfs(content: bytes, filename: str) -> str:
    """Upload to Lighthouse, return CID."""

async def download_from_ipfs(cid: str) -> bytes:
    """Download from IPFS gateway."""

async def get_lighthouse_uploads(api_key: str) -> list[dict]:
    """List user's uploads."""
```

**Gateway:** `https://gateway.lighthouse.storage/ipfs/{cid}`

---

## Middleware

### middleware/rate_limit.py

Per-IP request throttling.

**Decorators:**
```python
@rate_limit  # 30 req/min for generate endpoints
def generate():
    ...

@storage_rate_limit  # 10 req/min for storage endpoints
def autosave():
    ...
```

**Storage:** In-memory `defaultdict(list)` with timestamps

**⚠️ Known Issue:** Resets on container restart. Consider Redis for persistence.

---

### middleware/icp_cache.py

Idempotency cache for ICP consensus replay.

**Decorator:** `@icp_idempotent`

**How it works:**
1. Hash request (method + path + body)
2. Check if hash seen in last 5 minutes
3. If seen, return cached response
4. If new, process and cache result

---

### middleware/observability.py

Prometheus metrics collection.

**Metrics:**
```python
trinity_http_requests_total      # Counter by endpoint/method/status
trinity_http_request_duration    # Histogram
trinity_active_requests          # Gauge
trinity_inference_duration       # Histogram
trinity_tokens_generated_total   # Counter
trinity_errors_total             # Counter by type
trinity_auth_attempts_total      # Counter by success/failure
```

**Functions:**
```python
def start_request() -> float:
    """Start timing, increment active requests."""

def end_request(start_time: float, endpoint: str, status: int):
    """Record duration, decrement active."""

def track_inference(duration: float, tokens: int, model: str):
    """Record inference metrics."""

def track_error(error_type: str):
    """Increment error counter."""
```

---

## Services

### services/complexity.py

Query complexity scoring for routing.

**Function:**
```python
def classify_complexity(prompt: str) -> tuple[str, int]:
    """
    Returns: ('simple'|'medium'|'complex', score 0-10)
    
    Scoring factors:
    - Word count (longer = more complex)
    - Question marks (multiple questions)
    - Technical terms (code, math, science)
    - Multi-part indicators ("and", "also", numbered lists)
    """
```

**Routing:**
| Score | Classification | Pipeline |
|-------|----------------|----------|
| 0-3 | Simple | 1-pass direct |
| 4-6 | Medium | 3-pass legacy agent |
| 7-10 | Complex | LangGraph multi-agent |

---

### services/agent.py

Legacy multi-pass agentic pipeline (handles 80% of traffic).

**Passes:**
1. **Understand** — Parse user intent
2. **Plan** — Create response strategy
3. **Execute** — Generate response
4. **Critique** — Self-evaluate
5. **Refine** — Improve based on critique

**Function:**
```python
async def run_agent_pipeline(
    prompt: str,
    context: list[dict],
    passes: int = 3
) -> dict:
    """Run multi-pass reasoning."""
```

---

### services/graph/

LangGraph multi-agent system (handles 20% of complex queries).

**Files:**
- `state.py` — `AgentState` TypedDict
- `llm.py` — LangChain Ollama wrapper
- `agents.py` — Specialized agents
- `nodes.py` — Graph nodes
- `edges.py` — Conditional routing
- `builder.py` — Graph construction

**Agents:**
| Agent | Role |
|-------|------|
| Supervisor | Routes to specialists |
| Research | Web search, fact-gathering |
| Code | Code generation/analysis |
| Synthesis | Combines results |

---

### services/caching.py

Embedding and semantic caching.

**Caches:**
```python
embedding_cache = LRUCache(maxsize=1000)
semantic_cache = LRUCache(maxsize=500)
```

**Functions:**
```python
def get_cached_embedding(text: str) -> Optional[list[float]]:
    """Check embedding cache."""

def cache_embedding(text: str, embedding: list[float]):
    """Store embedding."""

def get_semantic_match(query: str, threshold: float = 0.95) -> Optional[str]:
    """Find semantically similar cached response."""
```

---

### services/code_executor.py

Sandboxed Python code execution.

**⚠️ Security Warning:** Uses RestrictedPython which has known escape vectors.

**Function:**
```python
def execute_code(code: str, timeout: int = 5) -> dict:
    """
    Execute Python in restricted environment.
    
    Blocked:
    - import (except math, json, re)
    - open, exec, eval, compile
    - __builtins__ access
    """
```

**Recommendation:** Disable in production (`CODE_EXECUTION_ENABLED=false`) or migrate to Pyodide (WASM sandbox).

---

### services/experiments.py

Hash-based A/B testing.

**Function:**
```python
def get_experiment_assignment(
    session_id: str,
    experiment_name: str,
    variants: list[str]
) -> str:
    """
    Deterministic assignment via SHA256(session_id + experiment_name).
    No database needed — same input always returns same variant.
    """
```

**Active Experiments:**
- `pipeline_routing` — Legacy vs LangGraph (80/20 split)

---

### services/voting.py

Response quality voting.

**Function:**
```python
async def vote_responses(
    candidates: list[str],
    prompt: str,
    num_candidates: int = 3
) -> dict:
    """
    Generate multiple candidates, have LLM vote on best.
    Returns winning response with confidence score.
    """
```

---

### services/embeddings.py

Text embedding generation.

**Function:**
```python
def get_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Generate embedding via Ollama."""
```

---

### services/vector_store.py

In-memory vector database.

**Class:** `VectorStore`

**Methods:**
```python
def add_document(doc_id: str, text: str, metadata: dict):
    """Add document with embedding."""

def search(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search by cosine similarity."""

def sync_to_disk(path: str):
    """Persist to JSON file."""
```

**⚠️ Limitation:** In-memory only, max 100 documents, lost on restart.

---

### services/search.py

Web search via Brave API.

**Function:**
```python
async def brave_search(query: str, count: int = 5) -> list[dict]:
    """
    Search web via Brave Search API.
    Returns: [{title, url, snippet}, ...]
    """
```

**Requires:** `BRAVE_SEARCH_API_KEY` environment variable

---

### services/ollama.py

Ollama client wrapper.

**Functions:**
```python
def check_ollama_connection() -> bool:
    """Verify Ollama is running."""

def warmup_model(model: str):
    """Load model into memory."""

async def generate(
    prompt: str,
    model: str = None,
    max_tokens: int = 500,
    temperature: float = 0.7,
    stream: bool = False
) -> Union[str, AsyncGenerator]:
    """Generate completion."""
```

---

### services/akash.py

Akash deployment information.

**Functions:**
```python
def get_akash_deployment_info() -> dict:
    """Current deployment status."""

def get_escrow_balance() -> float:
    """Remaining AKT in escrow."""

def get_actual_lease_price() -> float:
    """Current hourly cost in AKT."""

def get_akt_price_usd() -> float:
    """Current AKT/USD price."""
```

---

## Testing

**Location:** [backend/tests/](../../backend/tests/)

**Coverage:** 91.30% (607+ tests across 14 unit test files + integration + e2e)

**Run tests:**
```bash
cd backend
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html
```

**Test structure:**
```
tests/
├── unit/                    # Unit tests
│   ├── test_encryption.py   # 15 tests
│   ├── test_icp_auth.py     # 20 tests
│   ├── test_validation.py   # 70 tests
│   ├── test_complexity.py   # 25 tests
│   └── ...
├── integration/             # (Empty - needs work)
├── e2e/                     # End-to-end tests
└── fixtures/                # Test data
```
