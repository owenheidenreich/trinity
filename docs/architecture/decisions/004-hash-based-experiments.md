# ADR-004: Hash-Based Experiment Assignment

## Status
**Archived** — Experiments framework deleted (Feb 2026 Intelligence Overhaul).

`services/experiments.py`, `middleware/ab_test.py`, and all experiment tests were removed. The A/B testing infrastructure is no longer needed since the system uses a single agent pipeline.

## Date
February 2026

## Context
We need A/B testing capability to validate features like LangGraph routing, but want to avoid:
- Maintaining an assignment database (adds state, complexity, failure mode)
- Non-deterministic assignment (bad UX if user sees different variants)
- Complex infrastructure requirements

## Decision
Use deterministic hash-based assignment where the same user always receives the same variant.

### Algorithm
```python
import hashlib

def assign_variant(experiment_name: str, session_id: str, variants: list) -> Variant:
    """
    Deterministic variant assignment using SHA256 hash.
    Same (experiment, session) always returns same variant.
    """
    hash_input = f"{experiment_name}:{session_id}"
    hash_bytes = hashlib.sha256(hash_input.encode()).digest()
    hash_value = int.from_bytes(hash_bytes[:8], 'big')
    
    # Normalize to 0-1 range
    normalized = (hash_value % 10000) / 10000
    
    # Assign based on cumulative weights
    cumulative = 0.0
    for variant in variants:
        cumulative += variant.weight
        if normalized < cumulative:
            return variant
    
    return variants[-1]  # Fallback
```

### Session ID Priority
```python
def get_session_id() -> str:
    """
    Extract session identifier with priority:
    1. Principal ID (authenticated ICP users) - most reliable
    2. X-Session-ID header (frontend provided)
    3. Anonymous hash of IP + User-Agent
    """
```

## Rationale

1. **Stateless**: No database needed—assignment computed on every request
2. **Deterministic**: Same user always gets same variant (consistent UX)
3. **Uniform Distribution**: SHA256 hash provides statistically even distribution
4. **Simple**: Easy to implement, understand, and debug
5. **Scalable**: No shared state between servers, works with any replica count

## Consequences

### Positive
- No assignment state to manage or migrate
- Instant assignment (no database lookup latency)
- Can't accidentally change user's variant mid-experiment
- Works across server restarts/deployments
- Easy to reproduce assignment for debugging

### Negative
- Cannot manually override specific user's assignment
- Cannot rebalance weights mid-experiment (would change assignments)
- Changing variant weights requires new experiment name
- No way to exclude specific users from experiments

## Implementation

### Experiment Definition
```python
# services/experiments.py
EXPERIMENTS = {
    'agent_mode': Experiment(
        name='agent_mode',
        description='Route between legacy and LangGraph pipelines',
        variants=[
            Variant('control', 0.5, {'mode': 'legacy'}),
            Variant('langgraph', 0.5, {'mode': 'langgraph'})
        ],
        enabled=True
    ),
    'complexity_threshold': Experiment(
        name='complexity_threshold',
        description='Threshold for complexity routing',
        variants=[
            Variant('low', 0.33, {'threshold': 0.3}),
            Variant('medium', 0.34, {'threshold': 0.5}),
            Variant('high', 0.33, {'threshold': 0.7})
        ],
        enabled=True
    )
}
```

### Flask Integration
```python
# middleware/ab_test.py
from functools import wraps
from flask import g

def experiment(experiment_name: str):
    """Decorator to assign experiment variant before handler runs."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            session_id = get_session_id()
            variant = assign_variant(experiment_name, session_id)
            
            if not hasattr(g, 'experiments'):
                g.experiments = {}
            g.experiments[experiment_name] = {
                'variant': variant.name,
                'config': variant.config
            }
            
            return f(*args, **kwargs)
        return decorated
    return decorator
```

### Usage in Endpoint
```python
@app.route('/generate/langgraph', methods=['POST'])
@experiment('agent_mode')
def generate_langgraph():
    mode = get_experiment_config('agent_mode', 'mode', 'legacy')
    if mode == 'langgraph':
        return use_langgraph_pipeline()
    return use_legacy_pipeline()
```

## Alternatives Considered

1. **Database Assignment Table**
   - Pros: Manual overrides, rebalancing
   - Cons: Adds state, database dependency, migration complexity

2. **Random Per-Request**
   - Pros: Simple
   - Cons: Not deterministic, user sees different variants each request

3. **Cookie-Based**
   - Pros: Deterministic, allows override
   - Cons: Requires client-side storage, doesn't work for API-only users

4. **Feature Flag Service (LaunchDarkly)**
   - Pros: Full-featured, enterprise-grade
   - Cons: $500+/month, vendor dependency

## Validation

### Distribution Test
```python
def validate_distribution(experiment_name: str, sample_size: int = 10000):
    """Verify hash distribution is uniform."""
    counts = defaultdict(int)
    for i in range(sample_size):
        variant = assign_variant(experiment_name, f'test-{i}')
        counts[variant.name] += 1
    
    # Check each variant is within 5% of expected
    for name, count in counts.items():
        ratio = count / sample_size
        expected = 0.5  # For 50/50 split
        assert abs(ratio - expected) < 0.05
```

## References
- [services/experiments.py](../../backend/services/experiments.py) - Experiment framework
- [middleware/ab_test.py](../../backend/middleware/ab_test.py) - Flask integration
- [tests/unit/test_experiments.py](../../backend/tests/unit/test_experiments.py) - Validation tests
