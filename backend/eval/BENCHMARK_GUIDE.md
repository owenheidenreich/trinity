# Trinity Pipeline Benchmark Guide
## Phase 5.5C: Legacy vs LangGraph Performance Analysis

### Overview

This directory contains the benchmark suite for comparing Trinity's legacy agent pipeline against the LangGraph multi-agent system.

**Purpose**: Provide data-driven insights to decide routing strategy:
- **Option A**: Keep 80/20 split (simple/medium→legacy, complex→LangGraph)
- **Option B**: Adjust complexity threshold
- **Option C**: Migrate all traffic to LangGraph
- **Option D**: Retire LangGraph, keep legacy only

---

## Quick Start

### Prerequisites

1. **Ollama running** with models loaded:
   ```bash
   ollama serve
   ollama pull llama3.1:8b
   ollama pull qwen2.5:32b  # For reasoning agent
   ```

2. **Backend dependencies installed**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Sufficient resources**:
   - 16GB+ RAM (LangGraph can be memory-intensive)
   - 10-20 minutes for full benchmark (300 queries × 2 pipelines)

### Running Benchmarks

**Quick Test** (10 queries per complexity, ~5 minutes):
```bash
python3 -m eval.benchmark_legacy_vs_langgraph --sample-size 10
```

**Full Benchmark** (100 queries per complexity, ~30 minutes):
```bash
python3 -m eval.benchmark_legacy_vs_langgraph --sample-size 100
```

**Custom Output**:
```bash
python3 -m eval.benchmark_legacy_vs_langgraph --sample-size 20 --output my_results.json
```

---

## Understanding Results

### Key Metrics

| Metric | Description | Good Value |
|--------|-------------|------------|
| **Success Rate** | % of queries that returned a response | >95% |
| **Mean Latency** | Average response time | <5000ms |
| **P95 Latency** | 95th percentile latency (outliers excluded) | <8000ms |
| **P99 Latency** | 99th percentile latency | <15000ms |
| **Tokens/Query** | Average output length | Varies by complexity |
| **Passes Used** | Agent iterations (legacy) or graph nodes (LangGraph) | 1-5 |

### Interpreting Performance Deltas

**LangGraph vs Legacy Latency Delta**:
- **<20% slower**: ✅ Acceptable overhead, complexity routing is optimal
- **20-50% slower**: ⚠️ Monitor; may need threshold tuning
- **>50% slower**: ❌ Consider retiring LangGraph

**Example Output**:
```
Performance Comparison (Latency in milliseconds)
--------------------------------------------------------------------------------
Pipeline        Complexity  Queries Success   Mean      P95       P99
--------------------------------------------------------------------------------
legacy          simple      10      100.0%     450ms     620ms     780ms
langgraph       simple      10      100.0%     890ms    1240ms    1580ms
legacy          medium      10      100.0%    1820ms    2450ms    3100ms
langgraph       medium      10      100.0%    2340ms    3200ms    4100ms
legacy          complex     10      100.0%    5620ms    8100ms   10200ms
langgraph       complex     10      100.0%    6840ms   10400ms   12800ms
```

**Analysis**:
- Simple queries: LangGraph 2x slower (routing overhead) → Use legacy ✅
- Medium queries: LangGraph 28% slower → Use legacy ✅
- Complex queries: LangGraph 28% slower but with better multi-agent reasoning → Current 80/20 split optimal ✅

---

## Decision Framework

### When to Keep 80/20 Split (Current State)

✅ **Keep if**:
- LangGraph is <30% slower on complex queries
- LangGraph provides better quality responses (subjective, requires manual review)
- Both pipelines have >95% success rate
- System resources are sufficient for both pipelines

### When to Adjust Threshold

⚠️ **Adjust if**:
- Medium queries show significant LangGraph benefit (lower latency or better quality)
- Complex query classification is too conservative (many medium queries misclassified)
- Want to increase LangGraph usage for more data

**Options**:
- Lower threshold: Route medium+complex to LangGraph (50/50 split)
- Raise threshold: Only route ultra-complex to LangGraph (95/5 split)

### When to Retire LangGraph

❌ **Retire if**:
- LangGraph is >50% slower with no quality improvement
- Memory usage is unsustainable
- LangGraph failure rate is >10%
- Maintenance burden outweighs benefits

### When to Retire Legacy

🚀 **Migrate to LangGraph-only if**:
- LangGraph matches or beats legacy latency on all complexities
- LangGraph provides significantly better response quality
- You want unified pipeline for easier maintenance

---

## Benchmark Output Files

### benchmark_results.json

Raw benchmark data including:
- Individual query results (latency, success, tokens, etc.)
- Aggregated metrics by pipeline and complexity
- Success/failure details

**Sample Structure**:
```json
{
  "raw_results": [
    {
      "query": "What is 2+2?",
      "complexity": "simple",
      "pipeline": "legacy",
      "success": true,
      "latency_ms": 456.2,
      "tokens_generated": 12,
      "passes_used": 1
    }
  ],
  "aggregations": {
    "legacy_simple": {
      "pipeline": "legacy",
      "complexity": "simple",
      "num_queries": 10,
      "success_rate": 100.0,
      "mean_latency_ms": 450.3,
      "p95_latency_ms": 620.1,
      "p99_latency_ms": 780.5
    }
  }
}
```

---

## Next Steps After Benchmarking

### 1. Review Results
- Compare P95 latencies for complex queries (primary decision factor)
- Check success rates (must be >95% for production)
- Review token generation (quality proxy)

### 2. Manual Quality Assessment
Benchmarks measure speed, not quality. For critical decision:
- Pick 10 complex queries
- Generate responses with both pipelines
- Compare quality, accuracy, completeness
- Factor into routing decision

### 3. Update Routing Configuration

**Keep 80/20 split** (no changes needed):
```python
# services/complexity.py - Already configured correctly
if complexity == 'complex':
    return 'langgraph'
else:
    return 'legacy'
```

**Adjust to 50/50 split** (route medium+complex):
```python
# services/complexity.py
if complexity in ['medium', 'complex']:
    return 'langgraph'
else:
    return 'legacy'
```

**Retire LangGraph** (legacy only):
```python
# services/complexity.py
return 'legacy'  # Always use legacy
```

### 4. Update Master Plan
Document your decision and reasoning in:
- `docs/plans/trinity-production-upgrade-master-plan.md`
- Update Phase 5.5C with your chosen routing strategy

---

## Troubleshooting

### Ollama Not Running
```
Error: Failed to connect to Ollama
Solution: Start Ollama with `ollama serve`
```

### Out of Memory
```
Error: Memory allocation failed
Solution: Reduce --sample-size or close other applications
```

### High Failure Rate
```
If success rate <80%:
1. Check Ollama logs for model errors
2. Verify all dependencies installed
3. Increase timeout values in benchmark script
```

### Import Errors
```
Error: ModuleNotFoundError
Solution: Run from backend/ directory with `python3 -m eval.benchmark_legacy_vs_langgraph`
```

---

## Performance Optimization Tips

If benchmarks show poor performance:

### For Legacy Pipeline
- Reduce max passes in `services/agent.py`
- Use faster model (llama3.1:8b instead of qwen2.5:32b)
- Disable semantic memory lookups for simple queries

### For LangGraph Pipeline
- Optimize node execution (reduce LLM calls per node)
- Adjust `MAX_ITERATIONS` in `services/graph/edges.py`
- Use faster models for routing decisions

---

## Appendix: Test Query Distribution

The benchmark suite includes:

**Simple Queries (100)**:
- Factual questions ("What is X?")
- Definitions ("Define Y")
- One-step reasoning
- Expected latency: 300-800ms

**Medium Queries (100)**:
- Comparisons ("Compare X and Y")
- Explanations ("Explain how Z works")
- Multi-step reasoning
- Expected latency: 1500-3500ms

**Complex Queries (100)**:
- System design ("Design distributed system for X")
- Code implementation ("Implement Y with Z constraints")
- Deep technical analysis
- Expected latency: 5000-12000ms

---

## Contact

For questions about benchmarking or routing decisions:
- Review [ADR-001: Complexity Routing](../../docs/decisions/001-complexity-routing.md)
- Check master plan Phase 5.5C section
- Run benchmarks with `--sample-size 10` for quick validation

**Last Updated**: February 5, 2026
**Phase**: 5.5C - Legacy vs LangGraph Benchmarking
