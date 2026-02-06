# ADR-001: Complexity-Based LangGraph Routing

## Status
Accepted

## Date
February 2026

## Context
We need to integrate LangGraph to demonstrate framework proficiency for principal-level engineering roles, but must minimize risk to our production system that serves real users. The existing legacy pipeline is battle-tested with proven reliability.

## Decision
Route queries to LangGraph ONLY when the complexity classifier determines a query is "complex" (~10-20% of traffic). Simple and medium complexity queries continue using the proven legacy pipeline.

### Complexity Classification Criteria
- **Simple**: Direct questions, greetings, basic lookups → Legacy pipeline
- **Medium**: Multi-step reasoning, moderate context → Legacy pipeline  
- **Complex**: Multi-domain synthesis, code generation, research tasks → LangGraph multi-agent

### Implementation
```python
from services.complexity import classify_complexity

complexity = classify_complexity(query)
if complexity == 'complex':
    return langgraph_pipeline.process(query)
else:
    return legacy_pipeline.process(query)
```

## Rationale

1. **Risk Mitigation**: Only 10-20% of traffic exposed to new code paths
2. **Performance**: Fast queries stay fast (no multi-agent overhead for simple questions)
3. **Natural A/B Test**: Built-in comparison between approaches via parallel mode
4. **Gradual Rollout**: Can adjust complexity threshold without code changes
5. **Fallback Safety**: LangGraph failures automatically fall back to legacy

## Consequences

### Positive
- Minimal production risk during LangGraph adoption
- Performance maintained for 80%+ of queries
- Easy rollback (disable LangGraph entirely via experiment flag)
- Clear metrics comparison between pipelines
- Demonstrates principal-level risk management

### Negative
- LangGraph not battle-tested on all query types initially
- Additional complexity in routing logic
- Two code paths to maintain during transition

## Alternatives Considered

1. **All queries through LangGraph**: Too risky, performance characteristics unknown at scale
2. **Parallel execution always**: 2x compute cost, unnecessary overhead for simple queries
3. **Manual flag per request**: Too cumbersome for users, doesn't scale
4. **Random sampling**: Not deterministic, harder to debug user issues

## Related Decisions
- ADR-004: Hash-Based Experiment Assignment (for A/B testing the routing)

## References
- [services/complexity.py](../../backend/services/complexity.py) - Complexity classifier implementation
- [services/agent.py](../../backend/services/agent.py) - LangGraph integration
