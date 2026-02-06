#!/usr/bin/env python3
"""
⚔️ WAR OF THREE KINGS - Throughput Test Runner ⚔️

This script runs Battle 2: The Crowd Pleaser
Tests throughput at various concurrency levels.

Usage:
    python3 throughput-test.py [concurrency]
    
Examples:
    python3 throughput-test.py 5      # Test at 5 concurrent
    python3 throughput-test.py 25     # Test at 25 concurrent
    python3 throughput-test.py all    # Run all levels (5,10,25,50)
"""

import asyncio
import aiohttp
import time
import json
import sys
import statistics
from datetime import datetime

# King endpoints and models
KINGS = {
    "QWEN": {
        "url": "https://sptj5nup2lc939i2h4bhq532gs.ingress.quanglong.org",
        "model": "qwen2.5:72b",
        "emoji": "👑"
    },
    "LLAMA": {
        "url": "http://56oqg7o6n9fu53ijan3udmmb5o.ingress.h4i-dedicated.eu-sw-2.digitalfrontier.so",
        "model": "llama3.3:70b",
        "emoji": "🦙"
    },
    "MIXTRAL": {
        "url": "https://bnivii01v9bcbchrqtej5pmd0k.ingress.4090.akashgpu.com",
        "model": "mixtral:8x22b",
        "emoji": "🔮"
    }
}

# Simple prompts for throughput testing (control for complexity)
SIMPLE_PROMPTS = [
    "What is 2 + 2?",
    "Name the capital of France.",
    "What color is the sky?",
    "How many days in a week?",
    "What is the opposite of hot?",
    "Name a mammal.",
    "What comes after 9?",
    "Is water wet?",
    "What season follows summer?",
    "How many legs does a dog have?"
]


async def make_request(session, url, model, prompt, request_id):
    """Make a single request and return timing/status."""
    start = time.time()
    try:
        async with session.post(
            f"{url}/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            result = await response.json()
            elapsed = time.time() - start
            
            # Extract response text and estimate tokens
            response_text = result.get("response", "")
            tokens = len(response_text.split())  # Rough estimate
            
            return {
                "id": request_id,
                "success": True,
                "time": elapsed,
                "tokens": tokens,
                "status": response.status
            }
    except asyncio.TimeoutError:
        return {
            "id": request_id,
            "success": False,
            "time": time.time() - start,
            "tokens": 0,
            "error": "timeout"
        }
    except Exception as e:
        return {
            "id": request_id,
            "success": False,
            "time": time.time() - start,
            "tokens": 0,
            "error": str(e)
        }


async def run_throughput_test(king_name, king_config, concurrency, num_requests=None):
    """Run throughput test for a single king at given concurrency."""
    if num_requests is None:
        num_requests = concurrency * 2  # 2 requests per concurrent slot
    
    url = king_config["url"]
    model = king_config["model"]
    emoji = king_config["emoji"]
    
    print(f"\n{emoji} {king_name} @ Concurrency {concurrency}")
    print("─" * 50)
    
    async with aiohttp.ClientSession() as session:
        # Create tasks with rotating prompts
        tasks = []
        for i in range(num_requests):
            prompt = SIMPLE_PROMPTS[i % len(SIMPLE_PROMPTS)]
            task = make_request(session, url, model, prompt, i)
            tasks.append(task)
        
        # Run with limited concurrency
        semaphore = asyncio.Semaphore(concurrency)
        
        async def bounded_request(task):
            async with semaphore:
                return await task
        
        start_time = time.time()
        results = await asyncio.gather(*[bounded_request(t) for t in tasks])
        total_time = time.time() - start_time
    
    # Analyze results
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    
    if successes:
        times = [r["time"] for r in successes]
        tokens = sum(r["tokens"] for r in successes)
        
        stats = {
            "total_requests": num_requests,
            "successful": len(successes),
            "failed": len(failures),
            "success_rate": len(successes) / num_requests * 100,
            "total_time": total_time,
            "avg_time": statistics.mean(times),
            "p50": statistics.median(times),
            "p95": sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0],
            "total_tokens": tokens,
            "tokens_per_second": tokens / total_time if total_time > 0 else 0
        }
        
        print(f"  Requests: {stats['successful']}/{stats['total_requests']} ({stats['success_rate']:.1f}%)")
        print(f"  Total Time: {stats['total_time']:.2f}s")
        print(f"  Avg Response: {stats['avg_time']:.2f}s")
        print(f"  P50 Latency: {stats['p50']:.2f}s")
        print(f"  P95 Latency: {stats['p95']:.2f}s")
        print(f"  Tokens/sec: {stats['tokens_per_second']:.1f}")
        
        if failures:
            error_types = {}
            for f in failures:
                err = f.get("error", "unknown")
                error_types[err] = error_types.get(err, 0) + 1
            print(f"  Errors: {error_types}")
        
        return stats
    else:
        print(f"  ❌ All {num_requests} requests failed!")
        return None


async def run_all_tests(concurrency_levels=None):
    """Run throughput tests for all kings at all concurrency levels."""
    if concurrency_levels is None:
        concurrency_levels = [5, 10, 25, 50]
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      ⚔️  BATTLE 2: THE CROWD PLEASER - THROUGHPUT TEST ⚔️     ║")
    print(f"║                     {datetime.now().strftime('%H:%M:%S')}                              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    all_results = {}
    
    for level in concurrency_levels:
        print(f"\n{'='*60}")
        print(f"CONCURRENCY LEVEL: {level}")
        print(f"{'='*60}")
        
        for king_name, king_config in KINGS.items():
            result = await run_throughput_test(king_name, king_config, level)
            if king_name not in all_results:
                all_results[king_name] = {}
            all_results[king_name][level] = result
    
    # Print summary
    print("\n" + "="*60)
    print("THROUGHPUT TEST SUMMARY")
    print("="*60)
    
    for king_name, levels in all_results.items():
        emoji = KINGS[king_name]["emoji"]
        print(f"\n{emoji} {king_name}:")
        for level, stats in levels.items():
            if stats:
                print(f"   @{level:2d}: {stats['tokens_per_second']:6.1f} tok/s, {stats['success_rate']:5.1f}% success")
            else:
                print(f"   @{level:2d}: FAILED")
    
    return all_results


async def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "all":
            await run_all_tests()
        elif arg.isdigit():
            level = int(arg)
            for king_name, king_config in KINGS.items():
                await run_throughput_test(king_name, king_config, level)
        else:
            print("Usage: python3 throughput-test.py [5|10|25|50|all]")
    else:
        # Default: run single test at concurrency 5
        for king_name, king_config in KINGS.items():
            await run_throughput_test(king_name, king_config, 5)


if __name__ == "__main__":
    asyncio.run(main())
