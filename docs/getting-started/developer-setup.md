# Trinity Developer Setup Guide

This guide will help you set up a local development environment for Trinity.

## Prerequisites

- **Python 3.11+** (macOS: `brew install python@3.11`, Linux: `apt install python3.11`)
- **Git** for version control
- **Node.js 18+** for frontend development (optional)

## Quick Start (5 minutes)

### 1. Clone and Setup Backend

```bash
# Clone the repository
git clone https://github.com/your-org/trinity.git
cd trinity

# Create Python virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import flask; print('Flask OK')"
python -c "import pytest; print('Pytest OK')"
```

### 2. Configure Environment

Create a `.env` file in the `backend/` directory:

```bash
# backend/.env
MODEL_BACKEND=llama-server
MODEL_NAME=qwen3:32b
LLAMA_SERVER_CHAT_PORT=8081
LLAMA_SERVER_INGEST_PORT=8082
CHAT_DIR=/tmp/trinity/chats
LOG_LEVEL=DEBUG

# Optional: For production testing
# DEPLOYMENT_TIER=production
```

### 3. Run Tests

```bash
# Run all tests
pytest tests/ --no-cov -q

# Run specific test file
pytest tests/unit/test_encryption.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html  # View coverage report
```

### 4. Start Development Server

```bash
# Start the Flask server
python inference_server.py

# Server runs at http://localhost:5000
# Health check: http://localhost:5000/health
# Metrics: http://localhost:5000/metrics
```

## Project Structure

```
trinity/
├── backend/                    # Python Flask backend
│   ├── inference_server.py     # App factory + blueprint registration
│   ├── config.py               # All constants, env vars, defaults
│   ├── routes/                 # 7 API blueprints (31 endpoints)
│   │   ├── health.py           # /health, /metrics, /stats
│   │   ├── generate.py         # /generate, /generate/agent
│   │   ├── chat.py             # /chat/*
│   │   ├── memory.py           # /user/memory/*
│   │   ├── user.py             # /user/status, /user/export, /user/stats
│   │   ├── tools.py            # /tools/*
│   │   └── passphrase.py       # /api/passphrase/*
│   ├── middleware/             # Request middleware
│   │   ├── observability.py    # Prometheus metrics
│   │   ├── rate_limit.py       # Per-principal rate limiting
│   │   └── icp_cache.py        # ICP idempotency cache
│   ├── services/               # ~25 modules + state_store package
│   │   ├── pipeline.py         # StreamingPipeline (main entry point)
│   │   ├── context_loader.py   # Query classification + context loading
│   │   ├── react_loop.py       # ReAct agentic loop (tool calling)
│   │   ├── tools.py            # Tool definitions (14 tools)
│   │   ├── code_executor.py    # Tool dispatcher
│   │   ├── knowledge_store.py  # Unified retrieval (facts + messages)
│   │   ├── state_store/        # Per-principal encrypted SQLite (8 mixins)
│   │   └── ...                 # embeddings, search, caching, etc.
│   └── tests/                  # 934+ tests
│       ├── unit/               # Unit tests
│       ├── integration/        # Integration tests
│       └── e2e/                # End-to-end tests
├── trinity-icp/                # ICP frontend canister
│   ├── src-react/              # Active: React 19 + TypeScript
│   └── src/                    # Legacy: Vanilla JS (still buildable)
├── deploy/                     # Deployment configs
│   ├── akash/                  # Akash YAML manifests
│   ├── docker/                 # Dockerfile + scripts
│   └── cloudflare-worker/      # SSL termination proxy
└── docs/                       # Documentation
    ├── architecture/           # System architecture docs
    └── getting-started/        # This guide!
```

## Development Workflow

### Running Tests Before Committing

```bash
# Quick syntax check
python -m py_compile inference_server.py

# Run relevant tests
pytest tests/unit/test_encryption.py tests/unit/test_validation.py -v

# Run full suite (takes ~7 seconds)
pytest tests/ --no-cov -q
```

### Accessing Metrics

```bash
# View Prometheus metrics
curl http://localhost:5000/metrics | grep trinity_

# Key metrics to watch:
# - trinity_http_request_duration_seconds (latency)
# - trinity_inference_duration_seconds (LLM speed)
# - trinity_embedding_cache_hits_total (cache effectiveness)
```

## IDE Setup

### VS Code (Recommended)

Install these extensions:
- **Python** (ms-python.python)
- **Pylance** (ms-python.vscode-pylance)
- **Python Test Explorer** (littlefoxteam.vscode-python-test-adapter)

Recommended settings (`.vscode/settings.json`):
```json
{
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/", "--no-cov"],
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true
}
```

### PyCharm

1. Open the `backend/` folder as project root
2. Configure Python interpreter to use your venv
3. Mark `tests/` as Test Sources Root
4. Configure pytest as test runner

## Common Issues

### "Module not found" errors

```bash
# Make sure you're in the right directory with venv activated
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

### Tests failing with "Prometheus registry" errors

```bash
# This happens when running tests in certain orders
# Use pytest with fresh process:
pytest tests/ --forked
```

### Rate limit errors during testing

```bash
# The test fixtures handle this, but if you see 429 errors:
# Wait 60 seconds, or restart the server
```

## Next Steps

- Check [Common Tasks](common-tasks.md) for development workflows
- Read the [AI Context Reference](../ai-context/CLAUDE.md) for system overview
- Review the [architecture docs](../architecture/) for design rationale
