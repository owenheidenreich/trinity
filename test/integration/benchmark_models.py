#!/usr/bin/env python3
"""
Trinity Model Benchmark Script

Compares production (2x A100 + Llama 70B) vs local testing (Mac + TinyLlama 1.1B)
"""

import requests
import time
import json
from typing import List, Dict
import statistics

# Test queries for benchmarking
TEST_QUERIES = [
    {
        "name": "Simple Code Function",
        "prompt": "Write a Python function to merge two sorted lists into one sorted list."
    },
    {
        "name": "Debug Task",
        "prompt": """Debug this code:
def fibonacci(n):
    if n <= 1:
        return n
    else:
        return fibonacci(n-1) + fibonacci(n+2)
"""
    },
    {
        "name": "Explanation Task",
        "prompt": "Explain how React hooks work, specifically useState and useEffect."
    },
    {
        "name": "System Design",
        "prompt": "Design a REST API for a todo application with user authentication."
    },
    {
        "name": "Complex Coding",
        "prompt": "Write a Python class that implements a LRU cache with O(1) operations."
    }
]

def test_endpoint(url: str, query: Dict, timeout: int = 60) -> Dict:
    """Test a single query against an endpoint"""
    try:
        start_time = time.time()
        
        response = requests.post(
            f"{url}/generate",
            json={"prompt": query["prompt"], "max_length": -1},
            timeout=timeout
        )
        
        latency = (time.time() - start_time) * 1000  # ms
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "latency_ms": latency,
                "response": data.get("generated_text", ""),
                "tokens_generated": data.get("tokens_generated", 0),
                "tokens_per_second": data.get("tokens_per_second", 0),
                "model": data.get("model", "unknown")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "latency_ms": latency
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency_ms": 0
        }

def run_benchmark(name: str, url: str, queries: List[Dict]) -> Dict:
    """Run all benchmark queries against an endpoint"""
    print(f"\n{'=' * 60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'=' * 60}\n")
    
    results = []
    
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query['name']}...", end=" ", flush=True)
        
        result = test_endpoint(url, query)
        results.append({
            "query": query["name"],
            **result
        })
        
        if result["success"]:
            print(f"✅ {result['latency_ms']:.0f}ms ({result['tokens_per_second']:.1f} tok/s)")
        else:
            print(f"❌ {result['error']}")
        
        # Brief pause between requests
        time.sleep(2)
    
    return {
        "name": name,
        "url": url,
        "results": results
    }

def calculate_statistics(benchmark_data: Dict) -> Dict:
    """Calculate statistics from benchmark results"""
    successful = [r for r in benchmark_data["results"] if r["success"]]
    
    if not successful:
        return {
            "success_rate": 0,
            "avg_latency_ms": 0,
            "avg_tokens_per_second": 0
        }
    
    latencies = [r["latency_ms"] for r in successful]
    tokens_per_sec = [r["tokens_per_second"] for r in successful if r["tokens_per_second"] > 0]
    
    return {
        "success_rate": (len(successful) / len(benchmark_data["results"])) * 100,
        "avg_latency_ms": statistics.mean(latencies),
        "median_latency_ms": statistics.median(latencies),
        "min_latency_ms": min(latencies),
        "max_latency_ms": max(latencies),
        "avg_tokens_per_second": statistics.mean(tokens_per_sec) if tokens_per_sec else 0,
        "total_queries": len(benchmark_data["results"]),
        "successful_queries": len(successful)
    }

def display_comparison(production_stats: Dict, test_stats: Dict):
    """Display side-by-side comparison"""
    print("\n" + "=" * 80)
    print("BENCHMARK COMPARISON")
    print("=" * 80)
    print()
    
    print(f"{'Metric':<30} {'Production (Llama 70B)':<25} {'Local (TinyLlama 1.1B)':<25}")
    print("-" * 80)
    
    metrics = [
        ("Success Rate", f"{production_stats['success_rate']:.1f}%", f"{test_stats['success_rate']:.1f}%"),
        ("Avg Latency", f"{production_stats['avg_latency_ms']:.0f}ms", f"{test_stats['avg_latency_ms']:.0f}ms"),
        ("Median Latency", f"{production_stats['median_latency_ms']:.0f}ms", f"{test_stats['median_latency_ms']:.0f}ms"),
        ("Min Latency", f"{production_stats['min_latency_ms']:.0f}ms", f"{test_stats['min_latency_ms']:.0f}ms"),
        ("Max Latency", f"{production_stats['max_latency_ms']:.0f}ms", f"{test_stats['max_latency_ms']:.0f}ms"),
        ("Avg Speed", f"{production_stats['avg_tokens_per_second']:.1f} tok/s", f"{test_stats['avg_tokens_per_second']:.1f} tok/s"),
    ]
    
    for metric, prod_val, test_val in metrics:
        print(f"{metric:<30} {prod_val:<25} {test_val:<25}")
    
    print()
    print("=" * 80)
    print()
    
    # Calculate cost efficiency
    if test_stats['success_rate'] > 0:
        quality_ratio = test_stats['avg_tokens_per_second'] / production_stats['avg_tokens_per_second']
        cost_ratio = 10 / 150  # $10 test vs $150 production monthly
        efficiency = quality_ratio / cost_ratio
        
        print(f"💰 Cost Efficiency Analysis:")
        print(f"   Test environment is {(1/cost_ratio):.1f}x cheaper (${10}/mo vs ${150}/mo)")
        print(f"   Test speed is {quality_ratio:.1%} of production speed")
        print(f"   Cost-adjusted efficiency: {efficiency:.2f}x")
        print()
        
        if test_stats['success_rate'] >= 80 and test_stats['avg_tokens_per_second'] >= 20:
            print("✅ RECOMMENDATION: Test environment is suitable for development & testing")
        elif test_stats['success_rate'] >= 60:
            print("⚠️  RECOMMENDATION: Test environment acceptable for basic testing only")
        else:
            print("❌ RECOMMENDATION: Test environment needs improvement")
    
    print()

def main():
    print("🧪 Trinity Model Benchmark Tool")
    print("=" * 60)
    
    # Get endpoints from user
    production_url = input("Enter PRODUCTION endpoint URL (or press Enter to skip): ").strip()
    test_url = input("Enter TEST endpoint URL: ").strip()
    
    if not test_url:
        print("❌ Test URL is required")
        return
    
    benchmarks = []
    
    # Test production if URL provided
    if production_url:
        prod_data = run_benchmark("Production (Llama 70B)", production_url, TEST_QUERIES)
        prod_stats = calculate_statistics(prod_data)
        benchmarks.append(("production", prod_stats))
    
    # Test environment (always)
    test_data = run_benchmark("Local Testing (TinyLlama 1.1B)", test_url, TEST_QUERIES)
    test_stats = calculate_statistics(test_data)
    benchmarks.append(("test", test_stats))
    
    # Display results
    if production_url:
        display_comparison(prod_stats, test_stats)
    else:
        print("\n" + "=" * 80)
        print("TEST ENVIRONMENT RESULTS")
        print("=" * 80)
        print()
        print(f"Success Rate:          {test_stats['success_rate']:.1f}%")
        print(f"Average Latency:       {test_stats['avg_latency_ms']:.0f}ms")
        print(f"Average Speed:         {test_stats['avg_tokens_per_second']:.1f} tok/s")
        print(f"Successful Queries:    {test_stats['successful_queries']}/{test_stats['total_queries']}")
        print()
    
    # Save results to file
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_file = f"benchmark_results_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "production": prod_data if production_url else None,
            "test": test_data,
            "statistics": {
                "production": prod_stats if production_url else None,
                "test": test_stats
            }
        }, f, indent=2)
    
    print(f"📊 Results saved to: {output_file}")
    print()

if __name__ == "__main__":
    main()
