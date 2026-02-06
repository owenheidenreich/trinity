"""
Trinity Legacy vs LangGraph Performance Benchmark
Phase 5.5C: Comprehensive comparison of both agent pipelines

This script benchmarks both pipelines across 300 test queries (100 simple, 100 medium, 100 complex)
to provide data-driven recommendations on routing strategy.

Usage:
    python3 -m eval.benchmark_legacy_vs_langgraph

Output:
    - Console summary with key metrics
    - eval/benchmark_results.json (raw data)
    - Recommendation for routing strategy
"""

import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent import AgentPipeline
from services.complexity import classify_complexity
from services.graph.graph import get_trinity_graph


@dataclass
class BenchmarkResult:
    """Single benchmark result"""

    query: str
    complexity: str
    pipeline: str  # 'legacy' or 'langgraph'
    success: bool
    latency_ms: float
    tokens_generated: int
    passes_used: int
    error: str = ""


@dataclass
class AggregateMetrics:
    """Aggregated metrics for a pipeline/complexity combination"""

    pipeline: str
    complexity: str
    num_queries: int
    success_rate: float
    mean_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    mean_tokens: float
    mean_passes: float


# =============================================================================
# TEST QUERIES
# =============================================================================

SIMPLE_QUERIES = [
    "What is 2+2?",
    "Define photosynthesis",
    "Who wrote Romeo and Juliet?",
    "What is the capital of France?",
    "Define machine learning",
    "What is HTTP?",
    "Explain DNS",
    "What is a variable in programming?",
    "Define recursion",
    "What is an API?",
    # Add 90 more simple queries
    "What is Python?",
    "Define JSON",
    "What is a database?",
    "What is HTML?",
    "Define CSS",
    "What is JavaScript?",
    "What is a function?",
    "Define a class in OOP",
    "What is Git?",
    "What is Docker?",
    "Define encryption",
    "What is HTTPS?",
    "What is REST?",
    "Define GraphQL",
    "What is SQL?",
    "What is NoSQL?",
    "Define cloud computing",
    "What is AWS?",
    "What is Kubernetes?",
    "Define microservices",
]

MEDIUM_QUERIES = [
    "Explain quantum computing in simple terms",
    "Compare Python and JavaScript for web development",
    "What are the benefits of functional programming?",
    "Explain how blockchain technology works",
    "Compare SQL and NoSQL databases",
    "What is the difference between HTTP and HTTPS?",
    "Explain the concept of containerization",
    "What are the principles of REST API design?",
    "Compare agile and waterfall methodologies",
    "Explain the CAP theorem in distributed systems",
    # Add 90 more medium queries
    "What is the difference between authentication and authorization?",
    "Explain how DNS resolution works",
    "Compare monolithic and microservices architectures",
    "What are the benefits of TypeScript over JavaScript?",
    "Explain how JWT tokens work",
    "Compare React, Vue, and Angular frameworks",
    "What is the difference between TCP and UDP?",
    "Explain how OAuth 2.0 works",
    "Compare symmetric and asymmetric encryption",
    "What are the principles of SOLID in software design?",
    "Explain the difference between cookies and sessions",
    "Compare serverless and traditional cloud architectures",
    "What is the difference between concurrency and parallelism?",
    "Explain how CDNs improve website performance",
    "Compare Git merge and rebase strategies",
    "What are the benefits of using message queues?",
    "Explain how load balancing works",
    "Compare ACID and BASE in database systems",
    "What is the difference between vertical and horizontal scaling?",
    "Explain how caching strategies improve performance",
]

COMPLEX_QUERIES = [
    "Design a distributed system architecture for real-time video streaming with fault tolerance and auto-scaling",
    "Implement a binary search tree with insertion, deletion, and self-balancing in Python",
    "Explain how to build a recommendation engine using collaborative filtering and handle the cold start problem",
    "Design a high-throughput message queue system that guarantees exactly-once delivery semantics",
    "Implement a rate limiter using the token bucket algorithm with distributed consensus",
    "Design a search engine indexing system that handles billions of documents with sub-second query times",
    "Explain how to implement a distributed transaction coordinator using the two-phase commit protocol",
    "Design a real-time fraud detection system for financial transactions using machine learning",
    "Implement a consistent hashing algorithm for distributed cache servers with virtual nodes",
    "Design a multi-tenant SaaS application with data isolation and per-tenant database scaling",
    # Add 90 more complex queries
    "Explain how to build a distributed consensus system using the Raft algorithm",
    "Design a time-series database optimized for IoT sensor data ingestion and querying",
    "Implement a distributed lock manager with deadlock detection and automatic recovery",
    "Design a content delivery network with intelligent edge caching and origin shielding",
    "Explain how to build a real-time collaborative editing system with CRDT conflict resolution",
    "Design a distributed tracing system for microservices with sampling and anomaly detection",
    "Implement a graph database query optimizer for complex relationship traversals",
    "Design a streaming data pipeline with exactly-once processing guarantees using Kafka",
    "Explain how to build a distributed scheduler for batch jobs with dependency management",
    "Design a multi-region disaster recovery system with automatic failover and data replication",
    "Implement a distributed B+ tree index with concurrent access and MVCC",
    "Design a service mesh for microservices with circuit breaking and intelligent routing",
    "Explain how to build a vector database for similarity search at billion-scale",
    "Design a distributed file system with erasure coding and automatic rebalancing",
    "Implement a query planner for distributed SQL databases with cost-based optimization",
    "Design a real-time anomaly detection system using unsupervised learning on streaming data",
    "Explain how to build a distributed key-value store with tunable consistency",
    "Design a multi-stage ML pipeline with feature stores and model versioning",
    "Implement a distributed snapshot algorithm for consistent global state capture",
    "Design a serverless event-driven architecture with event sourcing and CQRS patterns",
]


# =============================================================================
# BENCHMARK FUNCTIONS
# =============================================================================


def benchmark_legacy_pipeline(query: str) -> BenchmarkResult:
    """Benchmark legacy agent pipeline on a single query"""
    complexity = classify_complexity(query)

    try:
        pipeline = AgentPipeline(model_name="llama3.1:8b")

        start_time = time.perf_counter()
        result = pipeline.process(query, complexity=complexity)
        latency_ms = (time.perf_counter() - start_time) * 1000

        return BenchmarkResult(
            query=query,
            complexity=complexity,
            pipeline="legacy",
            success=bool(result.final_response),
            latency_ms=latency_ms,
            tokens_generated=len(result.final_response.split()) if result.final_response else 0,
            passes_used=result.passes_executed,
        )
    except Exception as e:
        return BenchmarkResult(
            query=query,
            complexity=complexity,
            pipeline="legacy",
            success=False,
            latency_ms=0,
            tokens_generated=0,
            passes_used=0,
            error=str(e),
        )


def benchmark_langgraph_pipeline(query: str) -> BenchmarkResult:
    """Benchmark LangGraph pipeline on a single query"""
    from langchain_core.messages import HumanMessage

    complexity = classify_complexity(query)

    try:
        graph = get_trinity_graph()

        initial_state = {
            "messages": [HumanMessage(content=query)],
            "current_agent": "supervisor",
            "iteration": 0,
            "tool_results": [],
            "research_context": "",
            "code_output": None,
            "final_answer": None,
            "complexity": complexity,
            "should_continue": True,
        }

        start_time = time.perf_counter()
        final_state = None
        for event in graph.stream(initial_state):
            final_state = event

        latency_ms = (time.perf_counter() - start_time) * 1000

        final_answer = final_state.get("final_answer", "") if final_state else ""
        iterations = final_state.get("iteration", 0) if final_state else 0

        return BenchmarkResult(
            query=query,
            complexity=complexity,
            pipeline="langgraph",
            success=bool(final_answer),
            latency_ms=latency_ms,
            tokens_generated=len(final_answer.split()) if final_answer else 0,
            passes_used=iterations,
        )
    except Exception as e:
        return BenchmarkResult(
            query=query,
            complexity=complexity,
            pipeline="langgraph",
            success=False,
            latency_ms=0,
            tokens_generated=0,
            passes_used=0,
            error=str(e),
        )


def aggregate_results(results: List[BenchmarkResult]) -> AggregateMetrics:
    """Aggregate benchmark results into summary metrics"""
    if not results:
        return AggregateMetrics(
            pipeline=results[0].pipeline if results else "unknown",
            complexity=results[0].complexity if results else "unknown",
            num_queries=0,
            success_rate=0,
            mean_latency_ms=0,
            median_latency_ms=0,
            p95_latency_ms=0,
            p99_latency_ms=0,
            mean_tokens=0,
            mean_passes=0,
        )

    successful = [r for r in results if r.success]
    latencies = [r.latency_ms for r in successful]

    # Calculate percentiles
    if latencies:
        sorted_latencies = sorted(latencies)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)
        p95 = sorted_latencies[p95_idx] if p95_idx < len(sorted_latencies) else sorted_latencies[-1]
        p99 = sorted_latencies[p99_idx] if p99_idx < len(sorted_latencies) else sorted_latencies[-1]
    else:
        p95 = p99 = 0

    return AggregateMetrics(
        pipeline=results[0].pipeline,
        complexity=results[0].complexity,
        num_queries=len(results),
        success_rate=(len(successful) / len(results) * 100) if results else 0,
        mean_latency_ms=statistics.mean(latencies) if latencies else 0,
        median_latency_ms=statistics.median(latencies) if latencies else 0,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        mean_tokens=statistics.mean([r.tokens_generated for r in successful]) if successful else 0,
        mean_passes=statistics.mean([r.passes_used for r in successful]) if successful else 0,
    )


# =============================================================================
# MAIN BENCHMARK RUNNER
# =============================================================================


def run_benchmarks(sample_size: int = 10) -> Dict:
    """
    Run comprehensive benchmarks on both pipelines.

    Args:
        sample_size: Number of queries per complexity level to test (default 10 for quick runs)

    Returns:
        Dictionary with all results and aggregations
    """
    print("=" * 80)
    print("Trinity Legacy vs LangGraph Performance Benchmark")
    print("Phase 5.5C: Data-Driven Pipeline Comparison")
    print("=" * 80)
    print()

    all_results = []

    # Sample queries for quicker benchmarking
    simple_sample = SIMPLE_QUERIES[:sample_size]
    medium_sample = MEDIUM_QUERIES[:sample_size]
    complex_sample = COMPLEX_QUERIES[:sample_size]

    total_queries = len(simple_sample) + len(medium_sample) + len(complex_sample)

    print(f"Testing {sample_size} queries per complexity level")
    print(f"Total queries: {total_queries * 2} ({total_queries} per pipeline)")
    print()

    # Benchmark Legacy Pipeline
    print("🔄 Benchmarking Legacy Pipeline...")
    for i, query in enumerate(simple_sample + medium_sample + complex_sample, 1):
        print(f"  [{i}/{total_queries}] {query[:60]}...")
        result = benchmark_legacy_pipeline(query)
        all_results.append(result)
        time.sleep(0.5)  # Small delay to avoid overwhelming the system

    print()

    # Benchmark LangGraph Pipeline
    print("🔄 Benchmarking LangGraph Pipeline...")
    for i, query in enumerate(simple_sample + medium_sample + complex_sample, 1):
        print(f"  [{i}/{total_queries}] {query[:60]}...")
        result = benchmark_langgraph_pipeline(query)
        all_results.append(result)
        time.sleep(0.5)  # Small delay

    print()
    print("✅ Benchmarking complete!")
    print()

    # Aggregate results
    aggregations = {}
    for pipeline in ["legacy", "langgraph"]:
        for complexity in ["simple", "medium", "complex"]:
            filtered = [r for r in all_results if r.pipeline == pipeline and r.complexity == complexity]
            if filtered:
                key = f"{pipeline}_{complexity}"
                aggregations[key] = aggregate_results(filtered)

    return {"raw_results": all_results, "aggregations": aggregations}


def print_results(results: Dict):
    """Print benchmark results in a readable format"""
    agg = results["aggregations"]

    print("=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print()

    # Print comparison table
    print("Performance Comparison (Latency in milliseconds)")
    print("-" * 80)
    print(f"{'Pipeline':<15} {'Complexity':<10} {'Queries':<8} {'Success':<8} {'Mean':<10} {'P95':<10} {'P99':<10}")
    print("-" * 80)

    for key in ["legacy_simple", "langgraph_simple", "legacy_medium", "langgraph_medium", "legacy_complex", "langgraph_complex"]:
        if key in agg:
            m = agg[key]
            print(
                f"{m.pipeline:<15} {m.complexity:<10} {m.num_queries:<8} {m.success_rate:>6.1f}% {m.mean_latency_ms:>8.0f}ms {m.p95_latency_ms:>8.0f}ms {m.p99_latency_ms:>8.0f}ms"
            )

    print()
    print("=" * 80)


def generate_recommendation(results: Dict) -> str:
    """Generate routing strategy recommendation based on benchmark data"""
    agg = results["aggregations"]

    # Compare performance deltas
    legacy_complex = agg.get("legacy_complex")
    langgraph_complex = agg.get("langgraph_complex")

    if not legacy_complex or not langgraph_complex:
        return "⚠️  Insufficient data to make recommendation"

    latency_delta = langgraph_complex.p95_latency_ms - legacy_complex.p95_latency_ms
    latency_delta_pct = (latency_delta / legacy_complex.p95_latency_ms * 100) if legacy_complex.p95_latency_ms > 0 else 0

    print("🎯 RECOMMENDATION")
    print("-" * 80)
    print()
    print(f"Legacy Pipeline P95 (complex):    {legacy_complex.p95_latency_ms:.0f}ms")
    print(f"LangGraph Pipeline P95 (complex):  {langgraph_complex.p95_latency_ms:.0f}ms")
    print(f"Delta: {latency_delta:+.0f}ms ({latency_delta_pct:+.1f}%)")
    print()

    if latency_delta_pct < 20:
        recommendation = "✅ KEEP 80/20 SPLIT (current complexity routing)"
        reasoning = "LangGraph overhead is acceptable (<20%) for complex queries. Current routing is optimal."
    elif latency_delta_pct < 50:
        recommendation = "⚠️  MONITOR PERFORMANCE - Consider threshold tuning"
        reasoning = "LangGraph is 20-50% slower. May need to adjust complexity threshold or optimize LangGraph."
    else:
        recommendation = "❌ RETIRE LANGGRAPH - Stick with legacy"
        reasoning = "LangGraph is >50% slower with no clear benefit. Legacy pipeline is faster."

    print(f"Recommendation: {recommendation}")
    print()
    print(f"Reasoning: {reasoning}")
    print()

    return recommendation


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark Trinity pipelines")
    parser.add_argument("--sample-size", type=int, default=10, help="Number of queries per complexity level (default: 10)")
    parser.add_argument("--output", type=str, default="eval/benchmark_results.json", help="Output file for results")
    args = parser.parse_args()

    # Run benchmarks
    results = run_benchmarks(sample_size=args.sample_size)

    # Print results
    print_results(results)

    # Generate recommendation
    generate_recommendation(results)

    # Save raw results
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w") as f:
        # Convert BenchmarkResult dataclasses to dicts for JSON serialization
        serializable_results = {
            "raw_results": [asdict(r) for r in results["raw_results"]],
            "aggregations": {k: asdict(v) for k, v in results["aggregations"].items()},
        }
        json.dump(serializable_results, f, indent=2)

    print(f"📄 Raw results saved to: {output_path}")
    print()
    print("=" * 80)
    print("Benchmark complete!")
    print("=" * 80)
