# Trinity Common Development Tasks

This guide covers frequent development workflows for Trinity contributors.

## Testing

### Run All Tests

```bash
cd backend

# Quick run (no coverage, ~7 seconds)
pytest tests/ --no-cov -q

# With coverage report
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html
```

### Run Specific Test Categories

```bash
# Security tests only (highest priority)
pytest tests/unit/test_encryption.py tests/unit/test_icp_auth.py tests/unit/test_validation.py -v

# Agent/ReAct tests
pytest tests/unit/test_react_loop.py tests/unit/test_tools_real.py -v

# Observability tests
pytest tests/unit/test_observability.py -v

# Caching tests
pytest tests/unit/test_caching.py -v

# Memory tests
pytest tests/unit/test_memory_tools.py tests/unit/test_memory_phase3.py -v

# Phase tests (architecture, stability, quality, agentic)
pytest tests/unit/test_phase1_security.py tests/unit/test_phase2_stability.py \
  tests/unit/test_phase3_architecture.py tests/unit/test_phase4_quality.py \
  tests/unit/test_phase5_agentic.py -v
```

### Run Single Test

```bash
# Run one test function
pytest tests/unit/test_encryption.py::TestEncryption::test_encrypt_decrypt_roundtrip -v

# Run tests matching a pattern
pytest tests/ -k "test_encrypt" -v
```

### Debug Failing Test

```bash
# Show full output on failure
pytest tests/unit/test_encryption.py -v --tb=long

# Drop into debugger on failure
pytest tests/unit/test_encryption.py --pdb

# Print statements visible
pytest tests/unit/test_encryption.py -s
```

---

## Adding New Code

### Adding a New Endpoint

1. **Create or add to a route blueprint** in `backend/routes/`:
```python
# routes/my_routes.py
from flask import Blueprint, request, jsonify
from middleware.rate_limit import rate_limit
from icp_auth import require_auth

my_bp = Blueprint('my', __name__)

@my_bp.route('/my-endpoint', methods=['POST'])
@require_auth  # If authentication needed
@rate_limit    # If rate limiting needed
def my_endpoint():
    data = request.get_json()
    # ... implementation
    return jsonify({'result': 'success'})
```

2. **Register the blueprint** in `inference_server.py`:
```python
from routes.my_routes import my_bp
app.register_blueprint(my_bp)
```

2. **Add tests in `tests/unit/`**:
```python
# tests/unit/test_my_endpoint.py
def test_my_endpoint_success(flask_client, auth_headers):
    response = flask_client.post('/my-endpoint', 
        json={'input': 'test'},
        headers=auth_headers
    )
    assert response.status_code == 200
```

3. **Run tests**:
```bash
pytest tests/unit/test_my_endpoint.py -v
```

### Adding a New Service Module

1. **Create the module**:
```python
# services/my_service.py
"""
Trinity Backend - My Service
Description of what this service does
"""

import logging
logger = logging.getLogger(__name__)

def my_function():
    """Docstring explaining the function."""
    pass
```

2. **Export in `services/__init__.py`**:
```python
from .my_service import my_function

__all__ = [
    # ... existing exports
    'my_function',
]
```

3. **Add tests**:
```python
# tests/unit/test_my_service.py
def test_my_function():
    from services.my_service import my_function
    result = my_function()
    assert result is not None
```

---

## Observability

### Adding a New Prometheus Metric

1. **Define the metric in `middleware/observability.py`**:
```python
MY_NEW_COUNTER = Counter(
    'trinity_my_metric_total',
    'Description of what this counts',
    ['label1', 'label2']  # Labels for filtering
) if PROMETHEUS_AVAILABLE else NoOpMetric()
```

2. **Export in `middleware/__init__.py`**:
```python
from .observability import (
    # ... existing imports
    MY_NEW_COUNTER,
)
```

3. **Use in code**:
```python
from middleware import MY_NEW_COUNTER

def some_function():
    MY_NEW_COUNTER.labels(label1='value1', label2='value2').inc()
```

4. **Verify**:
```bash
curl http://localhost:5000/metrics | grep trinity_my_metric
```

### Viewing Metrics Locally

```bash
# Raw Prometheus format
curl http://localhost:5000/metrics

# Filter for specific metric
curl http://localhost:5000/metrics | grep trinity_inference

# Pretty JSON format (admin endpoint)
curl http://localhost:5000/admin/cache/stats | jq
```

---

## Debugging Production Issues

### Check Health

```bash
# Basic health
curl https://api.dubya.ai/health

# Detailed status (when available)
curl https://api.dubya.ai/status | jq
```

### View Recent Errors

```bash
# Check metrics for error rates
curl https://api.dubya.ai/metrics | grep trinity_errors

# Check specific error types
curl https://api.dubya.ai/metrics | grep -E "trinity_errors.*error_type"
```

### Token Usage

```bash
# View total token usage
curl http://localhost:5000/admin/tokens/usage | jq

# View per-user quotas
curl http://localhost:5000/admin/quota/usage | jq
```

### Reproduce a User's Issue

```bash
# Check their token usage
curl http://localhost:5000/admin/tokens/usage | jq

# Check their quota
curl http://localhost:5000/admin/quota/usage | jq
```

---

## Deployment

### Local Docker Build

```bash
cd deploy/docker
./build.sh

# Test locally
docker run -p 5000:5000 trinity-backend:latest
```

### Deploy to Akash

```bash
# Full production deployment (interactive)
./scripts/trinity-deploy-production.sh

# Auto-select production tier (Qwen2.5-Coder 32B)
./scripts/trinity-deploy-production.sh production

# Smoke-test tier (Qwen2.5-Coder 7B, cheaper)
./scripts/trinity-deploy-production.sh test
```

### Update Cloudflare Worker

```bash
cd deploy/cloudflare-worker
npm install
npx wrangler deploy
```

---

## Git Workflow

### Before Committing

```bash
# Run tests
pytest tests/ --no-cov -q

# Check for syntax errors
python -m py_compile inference_server.py
python -m py_compile services/*.py

# Check imports work
python -c "from services import *; print('OK')"
```

### Commit Message Format

```
<type>: <short description>

[optional body with details]

Types:
- feat: New feature
- fix: Bug fix
- test: Adding tests
- docs: Documentation
- refactor: Code refactoring
- perf: Performance improvement
```

Example:
```
feat: Add semantic response caching

- Implement SemanticResponseCache with cosine similarity
- Add 95% similarity threshold for cache hits
- Include 37 unit tests for caching infrastructure
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Run all tests | `pytest tests/ --no-cov -q` |
| Run with coverage | `pytest tests/ --cov=.` |
| Start dev server | `python inference_server.py` |
| View metrics | `curl localhost:5000/metrics` |
| Clear caches | `curl -X POST localhost:5000/admin/cache/clear` |
| Check health | `curl localhost:5000/health` |
