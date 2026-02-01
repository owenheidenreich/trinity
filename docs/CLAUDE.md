# Trinity Codebase Reference

> **Purpose:** Comprehensive documentation for AI assistants to quickly understand the Trinity project
> **Last Updated:** January 31, 2026
> **Last Verified:** January 31, 2026
> **Status:** Production - V4.0 Intelligence Upgrade
> **Version:** v4.0.0 (Semantic Memory, Multi-Model, Tools, Voting)

---

## ⚡ Quick Reference

| Component | Value |
|-----------|-------|
| **ICP Frontend Canister** | `zc67k-kiaaa-aaaal-qtmiq-cai` |
| **ICP Backend Canister** | `au5zq-2qaaa-aaaal-qtowa-cai` |
| **Primary URL** | https://trinityai.cc |
| **Canister URL** | https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io |
| **Vercel Proxy** | https://vercel-proxy-swart-nine.vercel.app |
| **Docker Image** | `gdubx/trinity-inference:v4-unlimited` |
| **Akash Wallet** | `akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp` |

---

## 🚀 Deployment (Single Command)

```bash
./scripts/trinity-deploy-production.sh [tier]

# Examples:
./scripts/trinity-deploy-production.sh      # Interactive tier selection
./scripts/trinity-deploy-production.sh 1    # TinyLlama 1.1B (~$25/mo)
./scripts/trinity-deploy-production.sh 2    # Llama 3.1 8B (~$50/mo)
./scripts/trinity-deploy-production.sh 3    # Qwen 2.5 72B (~$200/mo)
```

**⚠️ IMPORTANT FOR AI ASSISTANTS:**
- **DO NOT run the deployment script and then run other commands** - this will interrupt/cancel the deployment
- If the user says they are running the deployment, **wait for them to report the result**
- The deployment script takes 5-10 minutes to complete - do not run `sleep` or other commands that would interrupt it
- Only check terminal output if the user asks or reports an issue

**The script handles EVERYTHING:**
1. Prerequisites check (Docker, provider-services CLI, wallet)
2. Local validation (Python syntax, Docker build)
3. Docker push to Docker Hub
4. Akash deployment via CLI (closes old deployments, creates new)
5. Vercel proxy URL update
6. ICP frontend canister deployment
7. Production verification (/health, /generate tests)

---

## 📁 Project Structure

```
Trinity/
├── dev                          # → scripts/dev.sh (local development)
├── test-prod                    # → scripts/test-prod.sh (production testing)
├── icp-deploy                   # → ICP canister deployment
├── README.md                    # Project overview
│
├── backend/                     # 🖥️ FLASK BACKEND
│   ├── inference_server.py      # Main server (endpoints, Flask app)
│   ├── icp_auth.py              # Ed25519 signature verification
│   ├── config.py                # Environment configuration
│   ├── encryption.py            # AES-256-GCM encryption
│   ├── storage.py               # File storage operations
│   ├── lighthouse.py            # IPFS/Filecoin uploads
│   ├── validation.py            # Input validation
│   ├── requirements.txt         # Python dependencies
│   ├── middleware/              # Request middleware
│   │   ├── __init__.py
│   │   ├── rate_limit.py        # Rate limiting
│   │   └── icp_cache.py         # ICP caching
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── prompts.py           # System prompts
│   │   ├── metrics.py           # Stats collection
│   │   ├── akash.py             # Akash blockchain API
│   │   ├── ollama.py            # Ollama API client
│   │   ├── agent.py             # Agentic pipeline orchestrator
│   │   ├── agent_prompts.py     # Multi-pass prompts + XML parsing
│   │   ├── complexity.py        # Question complexity classifier
│   │   ├── search.py            # Brave web search integration
│   │   ├── loading_messages.py  # Whimsical loading phrases
│   │   ├── embeddings.py        # 🆕 V4: FastEmbed text embeddings
│   │   ├── vector_store.py      # 🆕 V4: Per-user SQLite vector DB
│   │   ├── memory.py            # 🆕 V4: Semantic memory retrieval
│   │   ├── tools.py             # 🆕 V4: Tool registry and parser
│   │   ├── code_executor.py     # 🆕 V4: RestrictedPython sandbox
│   │   ├── voting.py            # 🆕 V4: Self-consistency voting
│   │   └── structured.py        # 🆕 V4: JSON schema enforcement
│   └── routes/                  # (Reserved for future)
│       └── __init__.py
│
├── deploy/                      # 🚀 DEPLOYMENT CONFIGS
│   ├── akash/                   # Akash SDL manifests
│   │   ├── deploy-tier1-basic.yaml      # TinyLlama 1.1B
│   │   ├── deploy-tier2-balanced.yaml   # Llama 3.1 8B
│   │   └── deploy-tier3-complex.yaml    # Qwen 2.5 72B
│   ├── docker/                  # Docker build files
│   │   ├── Dockerfile           # Container definition
│   │   ├── build.sh             # Build script
│   │   └── startup.sh           # Container entrypoint
│   ├── local/                   # Local development
│   │   ├── start.sh             # Start TinyLlama locally
│   │   ├── stop.sh              # Stop local backend
│   │   └── status.sh            # Check local status
│   └── vercel-proxy/            # SSL termination proxy
│       ├── api/proxy.js         # Node.js proxy (http/https support)
│       ├── vercel.json          # Routing config
│       └── package.json         # Dependencies
│
├── scripts/                     # 📜 AUTOMATION SCRIPTS
│   ├── trinity-deploy-production.sh  # ⭐ MAIN DEPLOYMENT SCRIPT
│   ├── akash_deploy.py          # Akash CLI helper (Python)
│   ├── dev.sh                   # Start local development
│   ├── test-prod.sh             # Test production backend
│   ├── switch-provider.sh       # Update Vercel proxy URL
│   ├── trinity-test-local.sh    # Local testing script
│   └── docker-cleanup.sh        # Clean Docker cache
│
├── trinity-icp/                 # 🎨 FRONTEND (ICP)
│   ├── dfx.json                 # ICP canister config
│   ├── canister_ids.json        # Production canister IDs
│   ├── package.json             # npm dependencies
│   ├── vite.config.js           # Vite bundler config
│   └── src/                     # Source code
│       ├── app.js               # Main application
│       ├── config.js            # Environment config
│       ├── index.html           # HTML template
│       ├── styles.css           # CSS styling
│       ├── tools.js             # Tools dropdown
│       ├── api/
│       │   └── canister-client.js  # ICP backend client
│       ├── auth/
│       │   ├── authManager.js   # Ed25519 keypair management
│       │   ├── keyExportModal.js # Key display modal
│       │   ├── auth-client.js   # Auth utilities
│       │   ├── auth-entry.js    # Auth entry point
│       │   └── icp-auth.js      # ICP auth library
│       ├── state/
│       │   ├── store.js         # Zustand state management
│       │   └── contextMemory.js # Conversation compression
│       ├── storage/
│       │   ├── autosave.js      # Debounced persistence
│       │   ├── lighthouse.js    # Filecoin/IPFS uploads
│       │   └── mock.js          # Test mode storage
│       ├── ui/
│       │   ├── index.js         # UI module aggregator
│       │   ├── domCache.js      # DOM element caching
│       │   ├── messages.js      # Message rendering
│       │   ├── sidebar.js       # Chat list
│       │   ├── modals.js        # Dialog boxes
│       │   ├── notifications.js # Toast notifications
│       │   ├── rainbowBorder.js # Rainbow effects
│       │   └── loadingMessages.js # 🆕 Whimsical loading phrases
│       ├── modules/             # Feature modules (empty - archive/funding removed in v3.7)
│       ├── utils/
│       │   └── validation.js    # Input validation
│       └── backend_canister/    # ICP Backend (Rust)
│           ├── src/lib.rs       # HTTPS Outcalls canister
│           ├── Cargo.toml       # Rust dependencies
│           └── trinity_backend.did  # Candid interface
│
└── docs/                        # 📚 DOCUMENTATION
    ├── CLAUDE.md                # This file
    ├── diagrams/
    │   └── trinity-storage-architecture.md
    └── user/
        └── quickstart.md
```

---

## 🧠 Agentic Pipeline (v3.6.0)

Trinity uses a multi-pass reasoning pipeline that routes questions by complexity:

### Complexity Routing
| Complexity | Passes | Pipeline |
|------------|--------|----------|
| **Simple** | 1 | Direct answer |
| **Medium** | 3 | Understand → Execute → Critique |
| **Complex** | 5 | Understand → Plan → Execute → Critique → Refine |

### Automatic Detection
- **Complexity**: Word count, question marks, technical terms
- **Web Search**: Keywords like "current", "today", "price", "bitcoin", "latest"

### Pass Timeouts
| Pass | Timeout | Token Limit |
|------|---------|-------------|
| Understand | 120s | 1000 |
| Plan | 120s | 1000 |
| Execute | 300s (5 min) | 4000 |
| Critique | 120s | 1000 |
| Refine | 300s (5 min) | 4000 |
| Search | 30s | N/A |

### Data Persistence
| Data | Saved | Where |
|------|-------|-------|
| User messages | ✅ | Encrypted autosave |
| Final AI answer | ✅ | Encrypted autosave |
| Understanding | ❌ | Ephemeral (internal) |
| Planning | ❌ | Ephemeral (internal) |
| Critique | ❌ | Ephemeral (internal) |
| Search results | ❌ | Ephemeral (in prompt) |
| Phase messages | ❌ | UI only |

### Key Files
- `backend/services/agent.py` - Pipeline orchestrator
- `backend/services/agent_prompts.py` - Pass prompts + XML parsing
- `backend/services/complexity.py` - Question classifier
- `backend/services/search.py` - Brave web search
- `backend/services/loading_messages.py` - Whimsical phrases
- `trinity-icp/src/app.js` - `generateAgent()` function

### Tier Requirements
| Tier | Model | Agentic Support |
|------|-------|-----------------|
| 1 | TinyLlama 1.1B | ❌ Too small for XML parsing |
| 2 | Llama 8B | ✅ Works well |
| 3 | Qwen 32B | ✅ Best results |

---

## 🧠 V4.0 Intelligence Upgrade (January 2026)

A comprehensive intelligence enhancement adding semantic memory, tool use, multi-model routing, self-consistency voting, and structured outputs.

### Overview

V4.0 transforms Trinity from a simple prompt-response system into an intelligent agent with:
1. **Semantic Memory**: Retrieves relevant past conversations using embeddings
2. **Multi-Model Routing**: Uses different models for different task complexities
3. **Tool Use**: Calculator, code execution, web search with structured calls
4. **Self-Consistency Voting**: Multiple samples + majority vote for complex queries
5. **Structured Output**: JSON schema enforcement for reliable parsing

### Architecture Diagram

```
User Query
    ↓
┌─────────────────────────────────────────────────────────────┐
│                    INFERENCE SERVER                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │  Complexity  │───→│ Multi-Model  │───→│   Response   │   │
│  │  Classifier  │    │   Router     │    │   Pipeline   │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│         │                   │                    │           │
│         ↓                   ↓                    ↓           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Semantic   │    │    Tools     │    │   Voting     │   │
│  │   Memory     │    │  Executor    │    │   Engine     │   │
│  │  (FastEmbed) │    │ (Restricted) │    │ (3 samples)  │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│         │                   │                    │           │
│         ↓                   ↓                    ↓           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Vector Store │    │  Structured  │    │   Output     │   │
│  │  (per-user)  │    │   Output     │    │  Formatter   │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### New Files Created (v4.0)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `backend/services/embeddings.py` | FastEmbed wrapper for text embeddings | `embed_text()`, `embed_batch()`, `cosine_similarity()`, `V4_EMBEDDINGS_AVAILABLE` |
| `backend/services/vector_store.py` | SQLite-based per-user vector database | `VectorStore`, `get_user_vector_store()`, `V4_VECTOR_STORE_AVAILABLE` |
| `backend/services/memory.py` | Semantic memory retrieval system | `SemanticMemory`, `build_enhanced_context()`, `V4_MEMORY_AVAILABLE` |
| `backend/services/tools.py` | Tool registry and parser | `parse_tool_calls()`, `detect_tools_needed()`, `get_tool_definitions_for_prompt()`, `V4_TOOLS_AVAILABLE` |
| `backend/services/code_executor.py` | RestrictedPython sandbox | `execute_tool()`, `evaluate_math_expression()`, `execute_python_code()`, `V4_CODE_EXECUTOR_AVAILABLE` |
| `backend/services/voting.py` | Self-consistency voting pipeline | `run_voting_pipeline()`, `should_use_voting()`, `V4_VOTING_AVAILABLE` |
| `backend/services/structured.py` | JSON schema enforcement | `generate_structured()`, `SCHEMAS`, `V4_STRUCTURED_AVAILABLE` |

### Configuration (config.py)

```python
# Multi-Model Architecture
MULTI_MODEL_ENABLED = os.getenv('MULTI_MODEL_ENABLED', 'false').lower() == 'true'
FAST_MODEL = os.getenv('FAST_MODEL', 'phi3:mini')           # Classification/routing
SMART_MODEL = os.getenv('SMART_MODEL', 'llama3.1:8b')       # General tasks
REASONING_MODEL = os.getenv('REASONING_MODEL', 'qwen2.5:32b')  # Complex reasoning

# Embeddings (FastEmbed)
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-small-en-v1.5')
EMBEDDING_DIM = 384  # Output dimension for bge-small

# RAG Configuration
RAG_TOP_K = int(os.getenv('RAG_TOP_K', '5'))           # Retrieved documents
RAG_CHUNK_SIZE = int(os.getenv('RAG_CHUNK_SIZE', '512'))
RAG_CHUNK_OVERLAP = int(os.getenv('RAG_CHUNK_OVERLAP', '50'))

# Memory System
WORKING_MEMORY_SIZE = int(os.getenv('WORKING_MEMORY_SIZE', '3'))   # Recent messages
SEMANTIC_MEMORY_SIZE = int(os.getenv('SEMANTIC_MEMORY_SIZE', '5')) # Retrieved memories
RECENCY_WEIGHT = float(os.getenv('RECENCY_WEIGHT', '0.3'))         # Balance recency vs relevance

# Tool Use
CODE_EXECUTION_ENABLED = os.getenv('CODE_EXECUTION_ENABLED', 'true').lower() == 'true'
CODE_EXECUTION_TIMEOUT = int(os.getenv('CODE_EXECUTION_TIMEOUT', '5'))  # Seconds

# Voting
VOTING_ENABLED = os.getenv('VOTING_ENABLED', 'true').lower() == 'true'
VOTING_CANDIDATES = int(os.getenv('VOTING_CANDIDATES', '3'))
VOTING_COMPLEXITY_THRESHOLD = int(os.getenv('VOTING_COMPLEXITY_THRESHOLD', '7'))
```

### Module Deep Dive

#### 1. Embeddings (`embeddings.py`)

Uses FastEmbed with BAAI/bge-small-en-v1.5 model (384 dimensions, ONNX-based, CPU-friendly).

```python
# Key functions
embed_text(text: str) -> np.ndarray          # Single text → 384-dim vector
embed_batch(texts: List[str]) -> List[np.ndarray]  # Batch embedding
cosine_similarity(a: np.ndarray, b: np.ndarray) -> float
chunk_text(text: str, chunk_size=512, overlap=50) -> List[str]

# Availability check
V4_EMBEDDINGS_AVAILABLE = True  # Set at module load
```

**Lazy Loading**: Model is loaded on first use to avoid slow startup.

#### 2. Vector Store (`vector_store.py`)

Per-user SQLite database storing embeddings with metadata.

```python
class VectorStore:
    def __init__(self, principal_id: str)
    def add_message_embedding(content, role, timestamp, chat_id, metadata)
    def search_similar(query_text, top_k=5) -> List[Dict]
    def export_for_ipfs() -> bytes  # For IPFS backup
    def import_from_ipfs(data: bytes)  # Restore from backup

# Factory function
get_user_vector_store(principal_id: str) -> VectorStore
```

**Storage Location**: `/data/vectors/{principal_id}/vector.db`

**Schema**:
```sql
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    content TEXT,
    embedding BLOB,  -- numpy array as bytes
    role TEXT,       -- 'user' or 'assistant'
    timestamp REAL,
    chat_id TEXT,
    metadata TEXT    -- JSON
);
```

**Fallback Mode**: If sqlite-vss is not available, uses Python-based cosine similarity search (slower but functional).

#### 3. Semantic Memory (`memory.py`)

Combines working memory (recent) + semantic memory (relevant).

```python
class SemanticMemory:
    def __init__(self, principal_id: str)
    def add_interaction(user_msg, assistant_msg, chat_id)
    def get_relevant_context(query: str) -> List[Dict]
    
def build_enhanced_context(
    principal_id: str,
    current_query: str,
    chat_history: List[Dict]
) -> str  # Returns formatted context for LLM prompt
```

**Context Building Algorithm**:
1. Take last N messages (WORKING_MEMORY_SIZE=3) as "working memory"
2. Embed current query
3. Search vector store for semantically similar past messages
4. Score by: `relevance * (1 - RECENCY_WEIGHT) + recency * RECENCY_WEIGHT`
5. Return top SEMANTIC_MEMORY_SIZE results
6. Format as: `[Working Memory] + [Semantic Memory] + [Current Query]`

#### 4. Tools (`tools.py`)

Registry of available tools with structured calling.

```python
TOOL_REGISTRY = {
    'calculator': {
        'description': 'Evaluate mathematical expressions',
        'parameters': {'expression': 'string'},
        'handler': 'code_executor.evaluate_math_expression'
    },
    'code_execute': {
        'description': 'Execute Python code in sandbox',
        'parameters': {'code': 'string'},
        'handler': 'code_executor.execute_python_code'
    },
    'web_search': {
        'description': 'Search the web for current information',
        'parameters': {'query': 'string'},
        'handler': 'search.brave_search'
    },
    'document_search': {
        'description': 'Search user conversation history',
        'parameters': {'query': 'string'},
        'handler': 'memory.search_user_history'
    },
    'fact_check': {
        'description': 'Verify a factual claim',
        'parameters': {'claim': 'string'},
        'handler': 'tools.fact_check_claim'
    }
}

def detect_tools_needed(prompt: str) -> List[str]  # Heuristic detection
def parse_tool_calls(response: str) -> List[Dict]  # Parse <tool>...</tool> XML
def get_tool_definitions_for_prompt() -> str       # Format for system prompt
```

**Tool Call Format** (in LLM response):
```xml
<tool name="calculator">
  <param name="expression">sqrt(144) * 7</param>
</tool>
```

#### 5. Code Executor (`code_executor.py`)

Safe Python execution using RestrictedPython.

```python
def evaluate_math_expression(expr: str) -> Dict:
    """
    Safe math evaluation using AST parsing.
    Allowed: +, -, *, /, **, sqrt, sin, cos, tan, log, exp, abs, round
    """

def execute_python_code(code: str, timeout: int = 5) -> Dict:
    """
    Execute Python in RestrictedPython sandbox.
    - No file I/O
    - No network access
    - No imports (except math, random)
    - 5 second timeout
    - Limited builtins
    """

def execute_tool(tool_name: str, args: Dict, principal_id: str = None) -> Dict:
    """
    Main entry point - routes to appropriate handler.
    """
```

**Security Features**:
- RestrictedPython compiles code with restricted builtins
- Timeout via threading
- No access to `__import__`, `open`, `eval`, `exec`
- Whitelisted functions only

#### 6. Voting (`voting.py`)

Self-consistency voting for complex queries.

```python
def should_use_voting(query: str, complexity: int) -> bool:
    """Returns True if query complexity >= VOTING_COMPLEXITY_THRESHOLD (7)"""

def run_voting_pipeline(
    prompt: str,
    model: str,
    num_candidates: int = 3,
    temperatures: List[float] = [0.3, 0.7, 1.0]
) -> Dict:
    """
    1. Generate N responses at different temperatures
    2. Extract key claims/answers from each
    3. Find consensus (majority vote)
    4. Return best response + confidence score
    """
```

**Algorithm**:
1. Generate 3 responses at temperatures [0.3, 0.7, 1.0]
2. For each response, extract "answer fingerprint" (key facts/numbers)
3. Group similar fingerprints
4. Return response from largest group
5. Confidence = group_size / total_candidates

#### 7. Structured Output (`structured.py`)

JSON schema enforcement for reliable parsing.

```python
SCHEMAS = {
    'understanding': {
        'type': 'object',
        'properties': {
            'main_question': {'type': 'string'},
            'sub_questions': {'type': 'array'},
            'required_knowledge': {'type': 'array'},
            'complexity': {'type': 'integer'}
        }
    },
    'plan': {...},
    'critique': {...},
    'tool_call': {...}
}

def generate_structured(
    prompt: str,
    schema_name: str,
    model: str = None
) -> Dict:
    """
    Generate response conforming to JSON schema.
    Uses prompt engineering + post-processing.
    Fallback: Regex extraction if JSON parsing fails.
    """
```

**Note**: `outlines` library was removed due to Rust compiler requirement. Uses fallback JSON extraction.

### Multi-Model Routing

The agent pipeline routes queries based on complexity:

```python
def select_model_for_task(complexity: int, task_type: str) -> str:
    if not MULTI_MODEL_ENABLED:
        return MODEL_NAME  # Use default model
    
    if task_type == 'classification':
        return FAST_MODEL      # phi3:mini
    elif complexity <= 4:
        return SMART_MODEL     # llama3.1:8b
    else:
        return REASONING_MODEL # qwen2.5:32b
```

**Tier Configuration**:

| Tier | FAST_MODEL | SMART_MODEL | REASONING_MODEL | MULTI_MODEL_ENABLED |
|------|------------|-------------|-----------------|---------------------|
| 1 | - | - | - | false |
| 2 | phi3:mini | llama3.1:8b | qwen2.5:14b | true |
| 3 | phi3:mini | llama3.1:8b | qwen2.5:32b | true |

### API Endpoints (v4)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v4/status` | GET | No | Feature availability status |
| `/v4/vector/index` | POST | Yes | Bulk index chat history |
| `/v4/vector/document` | POST | Yes | Index a document |
| `/v4/vector/search` | POST | Yes | Semantic search |
| `/v4/vector/sync` | POST | Yes | Sync vector DB to/from IPFS |
| `/v4/tools/execute` | POST | Yes | Execute a tool |

### Startup Import Sequence

In `inference_server.py`, v4 modules are imported individually with error handling:

```python
V4_IMPORT_ERROR = None
V4_EMBEDDINGS_AVAILABLE = False
V4_VECTOR_STORE_AVAILABLE = False
# ... etc

try:
    from services.embeddings import ..., V4_EMBEDDINGS_AVAILABLE
    logger.info(f"✅ embeddings: V4_EMBEDDINGS_AVAILABLE={V4_EMBEDDINGS_AVAILABLE}")
except Exception as e:
    V4_IMPORT_ERROR = f"embeddings: {e}"
    logger.error(f"❌ embeddings import failed: {e}")

# ... repeat for each module

V4_FEATURES_AVAILABLE = all([
    V4_EMBEDDINGS_AVAILABLE,
    V4_VECTOR_STORE_AVAILABLE,
    V4_MEMORY_AVAILABLE,
    V4_TOOLS_AVAILABLE,
    V4_CODE_EXECUTOR_AVAILABLE
])
```

### Troubleshooting V4

**Check v4 status**:
```bash
curl -s https://vercel-proxy-swart-nine.vercel.app/v4/status | jq .
```

**Expected response (all working)**:
```json
{
  "available": true,
  "features": {
    "code_executor": true,
    "embeddings": true,
    "semantic_memory": true,
    "structured": true,
    "tools": true,
    "vector_store": true,
    "voting": true
  },
  "version": "4.0.0"
}
```

**If features show false**:
- Check for `import_error` field in response
- Common issues:
  - `fastembed` not installed → check requirements.txt
  - `RestrictedPython` not installed → check requirements.txt
  - numpy version mismatch → needs numpy 1.26.4

**Verify build timestamp**:
```bash
curl -s https://vercel-proxy-swart-nine.vercel.app/health | jq '.build_timestamp'
```

### Dependencies Added (requirements.txt)

```
# V4.0 Intelligence Upgrade
fastembed>=0.3.0          # Text embeddings (uses ONNX, no GPU required)
RestrictedPython>=7.0     # Safe code execution sandbox
numpy>=1.26.0             # Vector operations

# REMOVED (compatibility issues):
# sqlite-vss              # Needs special build - using Python fallback
# outlines                # Needs Rust compiler - using regex fallback
```

### Output Limits (v4-unlimited)

Token and timeout limits were significantly increased to allow long-form generation:

| Setting | Old Value | New Value | Location |
|---------|-----------|-----------|----------|
| Default tokens | 800 | 4,000 | `inference_server.py` |
| Reasoning tokens | 4,000 | 8,000 | `inference_server.py` |
| Execute pass tokens | 4,000 | 8,000 | `agent.py` |
| Refine pass tokens | 4,000 | 8,000 | `agent.py` |
| Ollama timeout | 300s | 600s | `inference_server.py` |
| Akash HTTP timeout | 60s | 600s | `deploy-tier3-complex.yaml` |
| Vercel function timeout | 300s | 300s (max) | `vercel.json` |

### Testing V4 Features

**Benchmark Tests** (run after deployment):

```bash
# 1. Math reasoning
curl -s -X POST https://vercel-proxy-swart-nine.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A store sells apples for $0.75 each. Buy 12+, get 15% off. How much for 15 apples?", "max_length": 400}' | jq -r '.response'

# 2. Logic puzzle
curl -s -X POST https://vercel-proxy-swart-nine.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Alice, Bob, Carol have cat, dog, fish. Alice has no dog. Cat owner is not Carol. Bob has fish. Who has what?", "max_length": 400}' | jq -r '.response'

# 3. Code generation
curl -s -X POST https://vercel-proxy-swart-nine.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write Python to find longest palindromic substring. Handle edge cases.", "max_length": 800}' | jq -r '.response'

# 4. Trick question
curl -s -X POST https://vercel-proxy-swart-nine.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A farmer has 17 sheep. All but 9 run away. How many left?", "max_length": 200}' | jq -r '.response'
```

### Future Enhancements (Not Yet Implemented)

1. **Chain-of-Thought Prompting**: Explicit reasoning steps
2. **Retrieval-Augmented Generation (RAG)**: Document ingestion pipeline
3. **Fine-tuning Integration**: LoRA adapters for domain specialization
4. **Agent Loops**: Multi-turn tool use with reflection
5. **Streaming Tool Calls**: Show tool execution in real-time

---

## 📊 V4.0 Intelligence Assessment (January 31, 2026)

### Benchmark Results: 17/20 (85%) - Excellent

Trinity v4.0 running on **Tier 3 (Qwen 2.5 32B)** was evaluated against a standardized 7-test intelligence benchmark covering math reasoning, logic, code generation, factual accuracy, multi-hop reasoning, constraint following, and trick questions.

| Test | Category | Score | Max | Result |
|------|----------|-------|-----|--------|
| 1 | Multi-Step Math | 3 | 3 | ✅ Perfect |
| 2 | Logic Puzzle | 3 | 3 | ✅ Perfect |
| 3 | Code Generation | 4 | 4 | ✅ Perfect |
| 4 | Factual + Calculation | 3 | 3 | ✅ Perfect |
| 5 | Multi-Hop Reasoning | 2 | 2 | ✅ Perfect |
| 6 | Constraint Following | 0 | 3 | ❌ Failed |
| 7 | Trick Question | 2 | 2 | ✅ Perfect |
| **Total** | | **17** | **20** | **85%** |

### Demonstrated Strengths

#### 1. Mathematical Reasoning
Trinity now exhibits structured, step-by-step mathematical problem-solving. When asked to calculate a discounted price, it:
- Identified the base calculation (15 × $0.75 = $11.25)
- Applied the discount correctly (15% off = $11.25 × 0.85)
- Arrived at the precise answer ($9.5625 → $9.56)
- Showed all work with clear mathematical notation

This represents a significant improvement from baseline LLM behavior, likely enhanced by the **tool use framework** that allows the model to reason about calculations methodically.

#### 2. Logical Deduction
The logic puzzle test (Alice/Bob/Carol with cat/dog/fish) was solved flawlessly:
- Constraint parsing: Correctly identified all 3 constraints
- Elimination reasoning: Applied constraints in optimal order
- Verification: Confirmed solution satisfies all constraints

The **multi-pass agentic pipeline** (Understand → Plan → Execute) appears to help the model break down constraint satisfaction problems into manageable steps.

#### 3. Code Generation Quality
The longest palindromic substring problem showcased:
- **Algorithm selection**: Chose expand-around-center (O(n²)) - optimal for this problem
- **Edge case handling**: Empty string, single character
- **Code structure**: Clean Python with proper typing hints
- **Testing**: Included 4 test cases covering different scenarios

This quality suggests the **structured output** capabilities help organize code generation into logical components.

#### 4. Factual Accuracy with Calculation
The sunlight travel time question required both:
- Factual recall (speed of light ≈ 300,000 km/s, Sun distance ≈ 150M km)
- Mathematical computation (150,000,000 ÷ 300,000 = 500s = 8.33 min)

Trinity correctly integrated both knowledge retrieval and calculation, demonstrating the **semantic memory** system's ability to surface relevant facts.

#### 5. Multi-Hop Reasoning Chains
The height ordering problem (John > Mary > Susan > Tom > Lisa) required chaining 4 comparative statements. Trinity:
- Built the transitive relationship correctly
- Inverted the chain for "shortest to tallest" ordering
- Produced the exact correct answer: Lisa, Tom, Susan, Mary, John

The **complexity classifier** likely identified this as a medium-complexity query, engaging the appropriate reasoning model.

#### 6. Trap Question Resistance
The classic "17 sheep, all but 9 run away" trick question tests whether models:
- Parse language precisely ("all but 9" = 9 remain, not 17-9=8)
- Avoid pattern-matching to subtraction

Trinity answered correctly: **9 sheep**. This suggests the **self-consistency voting** mechanism may help by generating multiple interpretations and selecting the majority consensus.

### Known Limitation: Negative Character Constraints

The only failed test asked Trinity to write about climate change without using the letter "E". Both attempts contained numerous E's:
- "temperatures", "ice", "levels", "unprecedented", "escalates", "ecosystems"

This is a **fundamental LLM limitation**, not specific to Trinity:
- Tokenization operates on subwords, not characters
- Models lack character-level awareness during generation
- Negative constraints ("don't do X") are harder than positive ("do Y")

**Mitigation strategies** (not yet implemented):
- Post-generation filtering with retry
- Character-aware decoding constraints
- Fine-tuning on constraint-following datasets

### Impact of V4.0 Upgrades

| V4 Feature | Observed Benefit |
|------------|-----------------|
| **Semantic Memory** | Factual recall appears stronger; relevant knowledge surfaces naturally |
| **Multi-Model Routing** | Complex queries use larger model; simple queries stay fast |
| **Tool Use Framework** | Math problems show structured calculation attempts |
| **Self-Consistency Voting** | Trap question avoided; ambiguous queries resolved correctly |
| **Structured Output** | Code generation is well-organized with proper sections |
| **Complexity Classification** | Queries routed to appropriate reasoning depth |

### Performance by Tier

| Tier | Model | Expected Score | Use Case |
|------|-------|----------------|----------|
| 1 | TinyLlama 1.1B | 40-50% | Basic Q&A only |
| 2 | Llama 3.1 8B | 65-75% | General reasoning |
| 3 | Qwen 2.5 32B | **85%** (tested) | Complex analysis |

### Conclusion

Trinity v4.0 represents a **substantial intelligence upgrade** from baseline LLM inference:

1. **Reasoning Quality**: 6 of 7 tests passed with perfect scores
2. **Step-by-Step Thinking**: Math and logic problems show clear work
3. **Code Competence**: Production-quality Python with edge cases
4. **Trap Resistance**: Avoided classic "all but N" linguistic trap
5. **Knowledge Integration**: Combined recall with calculation seamlessly

The 85% score places Trinity in the **"Excellent"** category for a self-hosted, decentralized AI system. The only weakness (character-level constraints) is a known limitation of transformer architectures, not a Trinity-specific issue.

**Recommendation**: For production use, Tier 3 (Qwen 32B) provides the best intelligence. Tier 2 (Llama 8B) offers good performance at lower cost for general-purpose queries.

---

## 🏗️ Architecture

```
User Browser
    ↓ HTTPS
ICP Frontend Canister (zc67k-kiaaa-aaaal-qtmiq-cai)
    │
    ├─→ Direct API calls (most endpoints)
    │       ↓
    │   Vercel Proxy (SSL termination)
    │       ↓
    │   Akash Backend (Flask + Ollama)
    │
    └─→ ICP Backend Canister (au5zq-2qaaa-aaaal-qtowa-cai)
            ↓ HTTPS Outcalls (for ICP consensus)
        Vercel Proxy → Akash Backend
```

### Why Vercel Proxy?
- Akash providers have invalid/self-signed SSL certificates
- ICP HTTPS Outcalls require valid SSL
- Vercel provides valid SSL and forwards requests with certificate bypass

---

## 🔧 Akash CLI Reference

### Prerequisites
```bash
# Install provider-services CLI
curl -sfL https://raw.githubusercontent.com/akash-network/provider/main/install.sh | bash

# Import wallet
provider-services keys add trinity-wallet --recover --keyring-backend os

# Verify wallet
provider-services keys show trinity-wallet --keyring-backend os -a
```

### Key Commands
```bash
# Check balance
provider-services query bank balances akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --node https://rpc.akashnet.net:443 -o json

# List active deployments
provider-services query deployment list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --state active --node https://rpc.akashnet.net:443 -o json

# Close deployment
provider-services tx deployment close --dseq <DSEQ> \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Create deployment
provider-services tx deployment create deploy.yaml \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Get bids
provider-services query market bid list \
  --owner akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp \
  --dseq <DSEQ> --node https://rpc.akashnet.net:443 -o json

# Create lease
provider-services tx market lease create \
  --dseq <DSEQ> --gseq 1 --oseq 1 --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --chain-id akashnet-2 --node https://rpc.akashnet.net:443 \
  --gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y

# Send manifest
provider-services send-manifest deploy.yaml \
  --dseq <DSEQ> --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# Get lease status (includes URI)
provider-services query provider lease-status \
  --dseq <DSEQ> --gseq 1 --oseq 1 --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443

# View logs
provider-services lease-logs \
  --dseq <DSEQ> --provider <PROVIDER> \
  --from trinity-wallet --keyring-backend os \
  --node https://rpc.akashnet.net:443 --follow
```

### Provider Selection
**GOOD (Reliable):**
- `*.pcgameservers.com` - Fast image caching, reliable ingress
- `*.akash.pub` domains (e.g., `hurricane.akash.pub`, `europlots.akash.pub`)

**AVOID (Unreliable):**
- `*.leet.haus` domains - ingress networking often broken
- `quanglong.org` - Very slow image pulls (26+ minutes)
- `digitalfrontier` providers - Intermittent 502 errors

---

## 📊 Model Tiers

| Tier | Model | GPU | Memory | Cost | Use Case |
|------|-------|-----|--------|------|----------|
| 1 | TinyLlama 1.1B | T4/RTX3090/4090 | 16GB | ~$25/mo | Testing |
| 2 | Llama 3.1 8B | RTX4090/A10 | 32GB | ~$50/mo | Balanced |
| 3 | Qwen 2.5 72B | A100 80GB | 180GB | ~$200/mo | Complex |

---

## 🔐 Authentication

### Ed25519 Self-Custody
- Keypairs generated in browser
- Principal ID derived from public key
- Private key stored in localStorage (user's responsibility)
- All `/chat/*` endpoints require signature

### Signature Verification
```python
# Backend decorator
@require_auth
def protected_endpoint():
    principal = request.principal  # Set by decorator
    # Access user-specific data
```

### Headers Required
```
ICP-Principal: <principal-id>
ICP-Timestamp: <unix-timestamp>
ICP-Signature: <base64-signature>
ICP-PublicKey: <hex-public-key>
```

---

## 💾 Storage Architecture

### Persistent Cloud Storage (v3.4.0+)
**CRITICAL FIX:** All autosaves now sync to Lighthouse (IPFS + Filecoin) in addition to local disk.
This ensures user data survives Akash redeployments.

**Data Flow:**
```
User Message → Autosave (2s debounce)
    ├─→ Local Disk (fast, ephemeral on Akash)
    └─→ Lighthouse Upload (IPFS + Filecoin, permanent)

User Login (after redeploy):
    1. Check local disk (fast)
    2. If empty → Recover from Lighthouse (IPFS gateway)
    3. Cache recovered data locally
```

### Storage Layers
| Layer | Speed | Persistence | Purpose |
|-------|-------|-------------|---------|
| IPFS (Lighthouse) | Medium | Permanent | **Source of truth** - all chat data |
| Akash Disk | Fast | Lost on redeploy | Metadata cache only |
| Browser (IndexedDB) | Instant | Session only | UI responsiveness |

**Note:** Filecoin archive feature was removed in v3.7.0. IPFS is now the primary permanent storage.

### Encryption
- AES-256-GCM with PBKDF2 key derivation
- Principal ID used as encryption password
- 100k PBKDF2 iterations, random salt + nonce
- All data encrypted before upload to IPFS

### Autosave (v3.7.0)
- 2-second debounce after each message
- Direct upload to IPFS (Lighthouse)
- CID stored in metadata for recovery
- Exponential backoff retry (5 attempts max)
- Rainbow wave animation during save

---

## ⚠️ Critical Conventions

### Zustand State Management
**CRITICAL:** Direct assignments fail silently!

```javascript
// ❌ WRONG - Fails silently
State.isAuthenticated = true;
State.chatHistory = [...messages];

// ✅ CORRECT - Use setter methods
State.setAuthenticated(principal, timestamp);
State.setChatHistory(messages);
State.addMessage('user', content);
```

### Docker Build (Apple Silicon)
```bash
# ✅ CORRECT - AMD64 for Akash
docker build --platform linux/amd64 -t image:tag .

# ❌ WRONG - ARM64 won't work on Akash
docker build -t image:tag .
```

### Environment Differences
| Feature | Local (TinyLlama) | Production (Akash) |
|---------|-------------------|-------------------|
| AI Inference | ✅ | ✅ |
| Autosave | ❌ No storage | ✅ Encrypted disk |
| Filecoin Archive | ❌ No Lighthouse | ✅ Full archival |
| Context Memory | ⚠️ Not persisted | ✅ Persisted |

---

## 🛠️ Common Tasks

### Deploy Everything
```bash
./scripts/trinity-deploy-production.sh 1  # Tier 1
./scripts/trinity-deploy-production.sh 2  # Tier 2
./scripts/trinity-deploy-production.sh 3  # Tier 3
```

### Frontend Only
```bash
cd trinity-icp && npm run build && dfx deploy --ic trinity_frontend
```

### Switch Akash Provider
```bash
./scripts/switch-provider.sh https://new-url.ingress.akash.pub
```

### Clean Docker
```bash
./scripts/docker-cleanup.sh
```

### Local Development
```bash
./dev  # or ./scripts/dev.sh
```

### Test Production
```bash
./test-prod  # or ./scripts/test-prod.sh
```

---

## 🧪 Testing

```bash
# Health check
curl https://vercel-proxy-swart-nine.vercel.app/health

# Test LLM response
curl -X POST https://vercel-proxy-swart-nine.vercel.app/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?", "max_length": 50}'

# ICP canister health
dfx canister --network ic call au5zq-2qaaa-aaaal-qtowa-cai health

# Local development
./dev

# Test against production (stops local backend first)
./test-prod
```

---

## 📋 API Endpoints

**Security Features:**
- All `/chat/*` endpoints validate input parameters (chat_id, principal_id, CID format)
- All `/generate*` endpoints are rate-limited (30 requests/60 seconds per IP)
- All `/chat/*` endpoints are rate-limited (10 requests/minute per IP)
- Prompt length limited to 50KB max to prevent DoS
- CORS restricted to known origins only

| Endpoint | Method | Auth | Rate Limit | Purpose |
|----------|--------|------|------------|---------|
| `/health` | GET | No | None | Health check |
| `/health/icp` | GET | No | None | ICP consensus health |
| `/generate` | POST | No | 30/min | LLM generation |
| `/generate/agent` | POST | No | 30/min | Agentic pipeline |
| `/stats` | GET | No | None | Performance stats |
| `/chat/autosave` | POST | ✅ | 10/min | Save encrypted chat |
| `/chat/list` | GET | ✅ | 10/min | List user's chats |
| `/chat/<id>` | GET | ✅ | 10/min | Load specific chat |
| `/chat/<id>` | DELETE | ✅ | 10/min | Delete chat |
| `/user/memory` | GET/POST | ✅ | 10/min | User memory CRUD |
| `/tools/browse` | POST | No | 30/min | Web browsing (SSRF protected) |

---

## 🔒 Security Hardening (v3.8.0)

### v3.8.0 Security Audit Fixes (January 2026)
Major security audit identified 67 issues across the codebase. Key fixes implemented:

| Category | Fix | File |
|----------|-----|------|
| **API Key Exposure** | Removed hardcoded keys, now injected from `.env` at deploy time | `deploy/akash/deploy-tier*.yaml` |
| **XSS Prevention** | All innerHTML wrapped with DOMPurify sanitization | `trinity-icp/src/app.js` |
| **CORS Hardening** | Removed wildcard, restricted to known origins | `deploy/vercel-proxy/api/proxy.js` |
| **CSP Hardening** | Removed dangerous wildcard from connect-src | `trinity-icp/.ic-assets.json5` |
| **Docker Security** | Added non-root user (trinity) to prevent container escape | `deploy/docker/Dockerfile` |
| **Thread Safety** | Added locks to global state (document_store, funding_cache) | `backend/inference_server.py` |
| **Replay Attack** | Reduced auth timestamp window from 5min to 30s | `backend/icp_auth.py` |
| **DoS Prevention** | Added 5MB limit on document uploads | `backend/inference_server.py` |
| **Exception Handling** | Replaced bare `except:` with specific exception types | `backend/inference_server.py` |
| **Dependency Pinning** | Pinned exact versions (== instead of >=) | `backend/requirements.txt` |

### Backend Security
| Feature | Implementation | File |
|---------|----------------|------|
| Storage rate limiting | `@storage_rate_limit` decorator (10 req/min) | `middleware/rate_limit.py` |
| Prompt length validation | 50KB max, returns 400 if exceeded | `config.py`, `inference_server.py` |
| SSRF protection | `is_safe_url()` blocks private IPs, metadata endpoints | `validation.py` |
| CORS restriction | Whitelist of allowed origins | `inference_server.py` |
| Connection pooling | `requests.Session` with HTTPAdapter | `config.py` |
| Memory leak prevention | Auto-cleanup of stale rate limit IPs, document store TTL | `middleware/rate_limit.py` |
| Thread-safe globals | `threading.Lock()` on document_store and funding_cache | `inference_server.py` |
| Document size limit | 5MB max per upload, returns 413 if exceeded | `inference_server.py` |
| Auth timestamp validation | 30-second window prevents replay attacks | `icp_auth.py` |

### Frontend Security
| Feature | Implementation | File |
|---------|----------------|------|
| XSS prevention | DOMPurify sanitization on all dynamic HTML | `app.js` |
| Private key encryption | AES-GCM encryption in localStorage | `utils/crypto.js` |
| Content Security Policy | Hardened CSP without wildcards | `index.html`, `.ic-assets.json5` |
| Ed25519 signatures | Constant-time verification (cryptography lib) | `icp_auth.py` |
| Request cancellation | AbortController on all fetch calls | `app.js` |

### Proxy Security Headers
The Vercel proxy now includes:
```javascript
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### Dependencies (Pinned Versions)
```
flask==3.0.3
flask-cors==4.0.0
flask-compress==1.15
requests==2.31.0
urllib3==2.2.1
psutil==5.9.8
APScheduler==3.10.4
pycryptodome==3.20.0
python-dotenv==1.0.1
cryptography==42.0.5
yfinance==0.2.37
feedparser==6.0.11
beautifulsoup4==4.12.3
argon2-cffi==23.1.0
```

### API Key Management
**CRITICAL:** API keys are now managed via `.env` file and injected at deploy time:
```bash
# .env file (never commit to git!)
LIGHTHOUSE_API_KEY=your-key-here
BRAVE_SEARCH_API_KEY=your-key-here
```
The `scripts/akash_deploy.py` script reads `.env` and injects values into YAML before deployment.

### SSRF Protection
The `/tools/browse` endpoint blocks:
- Private IP ranges (10.x, 172.16-31.x, 192.168.x)
- Localhost (127.x, ::1)
- Link-local addresses (169.254.x)
- Cloud metadata endpoints (169.254.169.254)

---

## 🐛 Troubleshooting

### Cold Start (20-30s first request)
**Expected behavior.** LLM loads into GPU memory on first request.

### No Consensus Error (ICP)
```
❌ No consensus could be reached. Replicas had different responses.
```
**Solution:** Use `/health/icp` endpoint. Backend strips non-deterministic fields for ICP requests with `X-Request-ID` header.

### Docker Disk Full
```bash
docker system prune -a --volumes -f
docker builder prune -a -f
```

### Git Slow
Delete build artifacts:
```bash
rm -rf trinity-icp/target trinity-icp/node_modules
```

### Browser Cache
Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows/Linux)

---

## 📚 Key Files Reference

| Need to... | Edit this file |
|------------|----------------|
| Change backend logic | `backend/inference_server.py` |
| Change auth verification | `backend/icp_auth.py` |
| Change frontend UI | `trinity-icp/src/ui/*.js` |
| Change state management | `trinity-icp/src/state/store.js` |
| Change context memory | `trinity-icp/src/state/contextMemory.js` |
| Change auth flow | `trinity-icp/src/auth/authManager.js` |
| Change autosave | `trinity-icp/src/storage/autosave.js` |
| Change environment config | `trinity-icp/src/config.js` |
| Change Vercel proxy | `deploy/vercel-proxy/api/proxy.js` |
| Change Akash deployment | `deploy/akash/deploy-tier*.yaml` |
| Change Docker build | `deploy/docker/Dockerfile` |
| Change deployment script | `scripts/trinity-deploy-production.sh` |
| Change ICP canister | `trinity-icp/src/backend_canister/src/lib.rs` |

---

## 🔄 Workflow Checklists (CRITICAL)

> **AI ASSISTANT RULE:** Before making ANY change, identify which section(s) are affected and complete the FULL checklist for each. This prevents broken deployments and missed dependencies.

### Section Dependency Map

```
Frontend ←→ Config ←→ Backend ←→ Docker ←→ Akash
   ↓           ↓          ↓
  UI         ICP      Services
   ↓                     ↓
  CSS              Middleware
```

---

### 🐳 DOCKER Workflow Checklist

**When to use:** Any change to `backend/*.py`, `backend/**/`, or `deploy/docker/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ All Python files have valid syntax | `python3 -m py_compile backend/*.py` |
| 2 | ☐ All imports exist and are correct | Check `import` statements in changed files |
| 3 | ☐ Dockerfile COPY includes all needed files/dirs | `deploy/docker/Dockerfile` |
| 4 | ☐ requirements.txt includes all dependencies | `backend/requirements.txt` |
| 5 | ☐ Build passes locally | `docker build --platform linux/amd64 -t test .` |
| 6 | ☐ Container starts without import errors | Check startup logs |
| 7 | ☐ Push to Docker Hub | `docker push gdubx/trinity-inference:tag` |
| 8 | ☐ Update Akash YAML with new image tag | `deploy/akash/deploy-tier*.yaml` |

**Files that MUST be in Dockerfile COPY:**
```dockerfile
COPY backend/inference_server.py .
COPY backend/icp_auth.py .
COPY backend/config.py .
COPY backend/encryption.py .
COPY backend/storage.py .
COPY backend/lighthouse.py .
COPY backend/validation.py .
COPY backend/middleware/ ./middleware/
COPY backend/services/ ./services/
COPY backend/routes/ ./routes/
COPY deploy/docker/startup.sh .
```

**Common Docker Failures:**
- `ModuleNotFoundError` → Missing directory in COPY
- Container exits immediately → Check startup.sh permissions
- Port not accessible → EXPOSE 8000 missing

---

### 🖥️ BACKEND Workflow Checklist

**When to use:** Any change to `backend/inference_server.py` or `backend/services/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Python syntax valid | `python3 -m py_compile backend/inference_server.py` |
| 2 | ☐ All imports exist | Check import statements |
| 3 | ☐ All decorators applied correctly | `@require_auth`, `@rate_limit` |
| 4 | ☐ Route paths match frontend expectations | Compare with `trinity-icp/src/app.js` API calls |
| 5 | ☐ Request/response format matches frontend | JSON field names must match |
| 6 | ☐ Config variables used consistently | Check `backend/config.py` |
| 7 | ☐ Docker workflow completed | See Docker checklist above |

**Backend Module Structure:**
```
backend/
├── inference_server.py   # Main routes, Flask app
├── icp_auth.py           # Auth decorators, signature verification
├── config.py             # Environment config
├── encryption.py         # AES-256-GCM encryption
├── storage.py            # File storage operations
├── lighthouse.py         # IPFS/Filecoin uploads
├── validation.py         # Input validation functions
├── middleware/           # Rate limiting, caching
│   ├── __init__.py
│   ├── rate_limit.py
│   └── icp_cache.py
├── services/             # Business logic
│   ├── __init__.py
│   ├── prompts.py        # System prompts
│   ├── metrics.py        # Stats collection
│   └── akash.py          # Akash blockchain API
└── routes/               # (Reserved for future)
    └── __init__.py
```

---

### 🎨 FRONTEND Workflow Checklist

**When to use:** Any change to `trinity-icp/src/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ JavaScript syntax valid | Vite build will catch errors |
| 2 | ☐ All imports exist | Check import paths |
| 3 | ☐ API endpoints match backend | Compare with `backend/inference_server.py` |
| 4 | ☐ Zustand state uses setter methods | Never `State.prop = value` |
| 5 | ☐ Build succeeds | `cd trinity-icp && npm run build` |
| 6 | ☐ Test in browser | Check console for errors |
| 7 | ☐ Deploy to ICP | `dfx deploy --ic trinity_frontend` |

**Frontend Module Structure:**
```
trinity-icp/src/
├── app.js              # Main application entry
├── config.js           # Environment detection
├── index.html          # HTML template + CSP
├── styles.css          # All CSS
├── tools.js            # Tools dropdown
├── api/
│   └── canister-client.js  # ICP backend client
├── auth/
│   ├── authManager.js      # Keypair management (encrypts keys in localStorage)
│   └── keyExportModal.js   # Key display modal
├── state/
│   ├── store.js            # Zustand store
│   └── contextMemory.js    # Memory compression
├── storage/
│   ├── autosave.js         # Debounced save
│   └── lighthouse.js       # Filecoin client
├── ui/
│   ├── domCache.js         # DOM element refs
│   ├── messages.js         # Message rendering
│   ├── sidebar.js          # Chat list
│   ├── modals.js           # Dialog boxes
│   ├── notifications.js    # Toasts
│   └── rainbowBorder.js    # Effects
├── utils/
│   ├── validation.js       # Input validation
│   └── crypto.js           # AES-GCM encryption for localStorage
└── modules/                # Feature modules (empty - archive/funding removed in v3.7)
```

**UI Features:**
- **Live KaTeX Rendering:** Math formulas render with 300ms debounce for performance
- **Smooth Typing:** 3 chars per 15ms interval for natural feel
- **Rainbow Borders:** Hover effects on interactive elements
- **Dark Theme:** `#1a1a1a` background, `#ffffff` text
- **Request Cancellation:** AbortController allows stopping in-flight requests

---

### 🌐 AKASH Workflow Checklist

**When to use:** Deploying to Akash or changing `deploy/akash/*`

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Docker image pushed to Docker Hub | `docker push gdubx/trinity-inference:tag` |
| 2 | ☐ YAML has correct image tag | `deploy/akash/deploy-tier*.yaml` |
| 3 | ☐ YAML has correct environment variables | Check `env:` section |
| 4 | ☐ Deployment created successfully | Check for DSEQ |
| 5 | ☐ Bid accepted from reliable provider | Avoid `*.leet.haus` |
| 6 | ☐ Lease status shows URI | Note the ingress URL |
| 7 | ☐ Logs show "Server ready" | `provider-services lease-logs ...` |
| 8 | ☐ Health endpoint responds | `curl https://<url>/health` |
| 9 | ☐ Vercel proxy updated with new URL | `./scripts/switch-provider.sh` |
| 10 | ☐ Frontend ICP canister redeployed | `dfx deploy --ic trinity_frontend` |

**Provider Reliability:**
- ✅ GOOD: `*.pcgameservers.com`, `*.akash.pub`
- ❌ AVOID: `*.leet.haus`, `*.quanglong.org`

---

### 🔵 ICP Workflow Checklist

**When to use:** Changes to ICP canisters or frontend deployment

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ dfx.json has correct canister IDs | `trinity-icp/dfx.json` |
| 2 | ☐ canister_ids.json matches | `trinity-icp/canister_ids.json` |
| 3 | ☐ Frontend builds successfully | `npm run build` |
| 4 | ☐ For backend canister: Rust compiles | `cargo build --target wasm32-unknown-unknown` |
| 5 | ☐ Deploy command succeeds | `dfx deploy --ic <canister>` |
| 6 | ☐ Verify canister accessible | Test in browser |

**Canister IDs:**
- Frontend: `zc67k-kiaaa-aaaal-qtmiq-cai`
- Backend: `au5zq-2qaaa-aaaal-qtowa-cai`

---

### 🎭 CSS/UI Workflow Checklist

**When to use:** Visual changes to `styles.css` or UI components

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ CSS syntax valid | Browser dev tools will show errors |
| 2 | ☐ Colors match design system | See UI/UX section |
| 3 | ☐ Mobile responsive | Test at 375px width |
| 4 | ☐ Dark theme consistency | No jarring light elements |
| 5 | ☐ No console errors | Check browser console |
| 6 | ☐ Build and deploy | Frontend workflow |

**Design System:**
- Background: `#1a1a1a`, Surfaces: `#2d2d2d`
- Text: `#ffffff`, Secondary: `#bbb`
- Borders: `#3d3d3d`
- Border radius: 6px buttons, 8px modals

---

### 🧠 MEMORY Workflow Checklist

**When to use:** Changes to context memory or user memory

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Frontend contextMemory.js logic correct | `trinity-icp/src/state/contextMemory.js` |
| 2 | ☐ Backend prompt builder matches | `backend/services/prompts.py` |
| 3 | ☐ Memory window size consistent | 6 messages frontend, matches backend |
| 4 | ☐ Summarization triggers correctly | Every 15 messages |
| 5 | ☐ User memory endpoint works | `/user/memory` GET/POST |
| 6 | ☐ Test multi-turn conversation | Verify context is maintained |

---

### 💾 STORAGE Workflow Checklist

**When to use:** Changes to autosave, encryption, or Lighthouse

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ Frontend autosave.js correct | `trinity-icp/src/storage/autosave.js` |
| 2 | ☐ Backend storage.py matches | `backend/storage.py` |
| 3 | ☐ Encryption uses AES-256-GCM | `backend/encryption.py` |
| 4 | ☐ Lighthouse API key configured | `LIGHTHOUSE_API_KEY` env var |
| 5 | ☐ IPFS upload/download works | Test with real data |
| 6 | ☐ Debounce timing correct | 2-second debounce |

---

### 🤖 MODEL Workflow Checklist

**When to use:** Changes to prompts, model config, or reasoning

| Step | Check | Files |
|------|-------|-------|
| 1 | ☐ System prompt is clear | `backend/services/prompts.py` |
| 2 | ☐ Model name matches tier | `deploy/akash/deploy-tier*.yaml` |
| 3 | ☐ Token limits appropriate | Check `max_length` in frontend |
| 4 | ☐ Reasoning prompt forces thinking | `/think` command works |
| 5 | ☐ Prompt doesn't confuse small models | No role markers for TinyLlama |
| 6 | ☐ Test actual responses | Chat in production |

---

## 🎯 Feature Status

### ✅ Complete
- Self-custody Ed25519 authentication
- Encrypted autosave (AES-256-GCM)
- Filecoin archive via Lighthouse SDK
- Context memory (6-message window + summarization)
- Modular frontend architecture (Zustand)
- ICP backend canister (HTTPS Outcalls)
- Vercel SSL proxy
- Unified CLI deployment pipeline (`trinity-deploy-production.sh`)
- Custom domain (trinityai.cc)
- Funding transparency (Akash escrow balance + ICP cycles)

### ⏳ Planned
- Lightweight RAG (FastEmbed + BM25)
- Document attachments (browser-side PDF parsing)

---

## 🐛 Known Issues & Fixes

### TinyLlama Prompt Confusion (Critical - Jan 2026)

**Symptom:** Model echoes system prompt in responses, hallucinates fake user/assistant dialogue, produces garbage like:
```
"[System] You are Trinity... User: Wow, I didn't think... Assistant: Yes, I am Trinity..."
```

**Root Cause:** 
1. TinyLlama (1.1B params) is too small to properly follow multi-turn chat formatting
2. The prompt uses `[System]`, `User:`, `Assistant:` labels that confuse the model
3. Model sees these as patterns to continue/echo rather than role markers
4. Context memory saves garbage responses → fed back next turn → feedback loop

**Affected Files:**
- `backend/inference_server.py` lines 1261-1310 (system prompt + prompt building)
- `trinity-icp/src/state/contextMemory.js` (saves garbage to context)

**Fix Required:**
1. Strip all role markers (`[System]`, `User:`, `Assistant:`) for small models
2. Use simple prompt format: just the user's question
3. OR switch to a larger model (8B+) that handles chat formatting correctly

**Prompt Flow (Current - Broken for TinyLlama):**
```
[System]
You are Trinity, a decentralized AI assistant...

User: previous message
Assistant: previous response
User: current message
Assistant:
```

**Prompt Flow (Fixed for TinyLlama):**
```
{user's question}
```

---

## 🎨 UI/UX Design System

### Theme
- **Background:** `#1a1a1a` (main), `#2d2d2d` (surfaces)
- **Text:** `#ffffff` (primary), `#bbb` (secondary)
- **Borders:** `#3d3d3d`
- **Interactive Hover:** Rainbow gradient borders
- **Archive Indicator:** Purple `#9c27b0`

### Typography
- Font: System fonts (`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif`)
- Weights: 400, 500, 600
- Size range: 11px-18px

### Spacing
- Border radius: 6px (buttons), 8px (modals)
- Grid: 8px system

---

## 🔗 Quick Links

- **Production:** https://trinityai.cc
- **ICP Direct:** https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io
- **Vercel Proxy:** https://vercel-proxy-swart-nine.vercel.app
- **Docker Hub:** https://hub.docker.com/r/gdubx/trinity-inference
- **Akash Console:** https://console.akash.network

---

*This document is maintained for AI assistants to quickly understand Trinity without re-exploring files. Last updated January 31, 2026 (v3.8.0 security audit).*
