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

# Agent/LangGraph tests
pytest tests/unit/test_langgraph.py tests/unit/test_complexity.py -v

# Observability tests
pytest tests/unit/test_observability.py -v

# Experiment/A/B tests
pytest tests/unit/test_experiments.py -v

# Caching tests
pytest tests/unit/test_caching.py -v
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

1. **Add the route in `inference_server.py`**:
```python
@app.route('/my-endpoint', methods=['POST'])
@require_auth  # If authentication needed
@rate_limit    # If rate limiting needed
def my_endpoint():
    data = request.get_json()
    # ... implementation
    return jsonify({'result': 'success'})
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

## A/B Testing

### Adding a New Experiment

1. **Define in `services/experiments.py`**:
```python
EXPERIMENTS['my_experiment'] = Experiment(
    name='my_experiment',
    description='Test feature X vs feature Y',
    variants=[
        Variant('control', 0.5, {'feature': 'old'}),
        Variant('treatment', 0.5, {'feature': 'new'})
    ],
    enabled=True
)
```

2. **Use in endpoint**:
```python
from middleware.ab_test import experiment, get_experiment_config

@app.route('/my-endpoint')
@experiment('my_experiment')
def my_endpoint():
    feature = get_experiment_config('my_experiment', 'feature', 'old')
    if feature == 'new':
        return new_implementation()
    return old_implementation()
```

3. **Test assignment**:
```bash
curl http://localhost:5000/admin/experiments/assignment/test-user-123 | jq
```

### Enable/Disable Experiments

```bash
# Disable
curl -X POST http://localhost:5000/admin/experiments/my_experiment/disable

# Enable
curl -X POST http://localhost:5000/admin/experiments/my_experiment/enable

# List all
curl http://localhost:5000/admin/experiments | jq
```

---

## Caching

### Clear Caches

```bash
# Clear all caches (embedding, semantic, resets stats)
curl -X POST http://localhost:5000/admin/cache/clear

# View cache statistics
curl http://localhost:5000/admin/cache/stats | jq
```

### Debug Cache Behavior

```python
# In code or Python shell
from services.caching import get_embedding_cache, get_semantic_cache

# Check embedding cache
cache = get_embedding_cache()
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']}")
print(f"Size: {stats['size']}/{stats['max_size']}")

# Invalidate specific entry
cache.invalidate("specific text to remove")
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

### Reproduce User's Experiment Assignment

```bash
# Get what variant a specific user would see
curl http://localhost:5000/admin/experiments/assignment/{user-session-id} | jq
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

# Auto-select tier 2 (Llama 8B)
./scripts/trinity-deploy-production.sh 2
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
| List experiments | `curl localhost:5000/admin/experiments` |
| Check health | `curl localhost:5000/health` |
