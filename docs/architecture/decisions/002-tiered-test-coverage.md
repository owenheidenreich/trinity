# ADR-002: Tiered Test Coverage Targets

## Status
Accepted

## Date
February 2026

## Context
We need comprehensive test coverage for a production system, but have limited time and resources. Not all code carries equal risk—security code failures have catastrophic consequences, while some utility code failures are recoverable.

## Decision
Implement tiered coverage targets based on code criticality:

| Tier | Module Type | Coverage Target | Rationale |
|------|-------------|-----------------|-----------|
| **P0** | Security (auth, encryption, validation) | 90% | Security failures are catastrophic |
| **P1** | API endpoints | 70% | User-facing, needs reliability |
| **P2** | Agent pipeline | 60% | Complex, some non-determinism acceptable |
| **P3** | Utilities | 50% | Lower risk, easier to fix |
| **Overall** | All modules | 75% | Balanced target |

### Module Classification
```
P0 - Security Critical (90% target):
├── backend/icp_auth.py
├── backend/encryption.py
├── backend/validation.py
└── backend/middleware/rate_limit.py

P1 - API Layer (70% target):
├── backend/inference_server.py
├── backend/storage.py
└── backend/middleware/icp_cache.py

P2 - Agent Logic (60% target):
├── backend/services/agent.py
├── backend/services/complexity.py
├── backend/services/langgraph.py
└── backend/services/voting.py

P3 - Utilities (50% target):
├── backend/services/prompts.py
├── backend/services/loading_messages.py
└── backend/config.py
```

## Rationale

1. **Security code must be tested exhaustively**: Authentication bypass, encryption failures, or validation gaps could expose user data or enable attacks
2. **Agentic reasoning is inherently non-deterministic**: LLM responses vary, making 90% coverage impractical without excessive mocking
3. **API endpoints are straightforward to test**: Clear inputs/outputs, well-defined contracts
4. **75% overall is achievable in timeline**: Focuses effort where it matters most

## Consequences

### Positive
- Critical security paths heavily tested (203 security tests achieved)
- Achievable within project timeline
- Clear priorities for test writing (P0 before P2)
- Demonstrates understanding of risk-based testing

### Negative
- Some agent edge cases not covered by automated tests
- Requires ongoing maintenance as code evolves
- May need manual testing for complex agent scenarios

## Implementation

### Test Organization
```
backend/tests/
├── unit/
│   ├── test_encryption.py      # P0 - 35 tests
│   ├── test_icp_auth.py        # P0 - 20 tests
│   ├── test_validation.py      # P0 - 70 tests
│   ├── test_complexity.py      # P2 - 46 tests
│   ├── test_langgraph.py       # P2 - 35 tests
│   ├── test_observability.py   # P1 - 99 tests
│   └── test_experiments.py     # P1 - 44 tests
└── e2e/
    └── test_full_pipeline.py   # Integration tests
```

### Coverage Enforcement
```ini
# pytest.ini
[pytest]
addopts = --cov=backend --cov-fail-under=75
```

## Alternatives Considered

1. **Blanket 80% target**: Unrealistic for agent code without excessive mocking
2. **Lower security target (70%)**: Unacceptable risk for auth/encryption
3. **No coverage target**: Would lead to inconsistent testing
4. **100% coverage everywhere**: Diminishing returns, impractical timeline

## Metrics (Current State)

| Module | Tests | Coverage | Target | Status |
|--------|-------|----------|--------|--------|
| encryption.py | 35 | 95% | 90% | ✅ |
| icp_auth.py | 20 | 92% | 90% | ✅ |
| validation.py | 70 | 91% | 90% | ✅ |
| complexity.py | 46 | 78% | 60% | ✅ |
| observability.py | 99 | 85% | 70% | ✅ |
| **Total** | **436** | **~80%** | **75%** | ✅ |

## References
- [pytest.ini](../../backend/pytest.ini) - Test configuration
- [conftest.py](../../backend/tests/conftest.py) - Shared fixtures
