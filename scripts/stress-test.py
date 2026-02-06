#!/usr/bin/env python3
"""
⚔️ WAR OF THREE KINGS - Stress Test Runner ⚔️

This script runs Battle 3: The Strongest Man
Fires 50 concurrent complex requests at each king.

Usage:
    python3 stress-test.py [king]
    
Examples:
    python3 stress-test.py qwen     # Test only Qwen
    python3 stress-test.py all      # Test all kings
"""

import asyncio
import aiohttp
import time
import json
import sys
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

# Complex prompts requiring multi-step reasoning
COMPLEX_PROMPTS = [
    "A farmer has 17 sheep. All but 9 run away. Then he buys 5 more sheep, sells half of what he has, and 3 more sheep run away. How many sheep does he have now? Show your work step by step.",
    "Write a Python function that finds the longest palindromic substring in a given string. Include time complexity analysis.",
    "Explain the CAP theorem and give a real-world example of a system that sacrifices consistency for availability. Then explain when this tradeoff makes sense.",
    "A bat and ball cost $1.10. The bat costs $1 more than the ball. What does the ball cost? Now, if I have 10 bats and 10 balls, and I give away 3 bats to someone who pays me the cost of 2 balls for each bat, how much money do I have in total?",
    "Write a recursive function to generate all valid combinations of n pairs of parentheses. Explain why the time complexity is the nth Catalan number.",
    "Three people check into a hotel room that costs $30. They each pay $10. Later, the manager realizes the room should only cost $25 and gives $5 to the bellboy to return. The bellboy keeps $2 and gives $1 back to each person. Now each person paid $9, totaling $27. The bellboy has $2. That's only $29. Where is the missing dollar?",
    "Implement a thread-safe singleton pattern in Python. Explain why the naive implementation is not thread-safe and how your solution fixes it.",
    "You have 8 identical-looking balls. One is slightly heavier. You have a balance scale and can only use it twice. How do you find the heavy ball?",
    "Design a rate limiter that allows 100 requests per minute per user. Explain the token bucket vs sliding window approaches and implement one.",
    "Prove that the sum of the first n odd numbers equals n² using mathematical induction. Show the base case, inductive hypothesis, and inductive step clearly."
]


async def make_stress_request(session, url, model, prompt, request_id):
    """Make a single complex request and return results."""
    start = time.time()
    try:
        async with session.post(
            f"{url}/generate",
            json={
                "model": model, 
                "prompt": prompt, 
                "stream": False,
                "options": {"num_predict": 1000}  # Allow longer responses
            },
            timeout=aiohttp.ClientTimeout(total=120)  # 2 min timeout for complex
        ) as response:
            result = await response.json()
            elapsed = time.time() - start
            
            response_text = result.get("response", "")
            tokens = len(response_text.split())
            
            return {
                "id": request_id,
                "success": True,
                "time": elapsed,
                "tokens": tokens,
                "prompt_preview": prompt[:50],
                "response_preview": response_text[:200] if response_text else "",
                "status": response.status
            }
    except asyncio.TimeoutError:
        return {
            "id": request_id,
            "success": False,
            "time": time.time() - start,
            "tokens": 0,
            "error": "timeout (120s)"
        }
    except Exception as e:
        return {
            "id": request_id,
            "success": False,
            "time": time.time() - start,
            "tokens": 0,
            "error": str(e)[:100]
        }


async def run_stress_test(king_name, king_config, num_requests=50):
    """Run stress test with 50 concurrent complex requests."""
    url = king_config["url"]
    model = king_config["model"]
    emoji = king_config["emoji"]
    
    print(f"\n{'='*60}")
    print(f"{emoji} STRESS TEST: {king_name}")
    print(f"   URL: {url}")
    print(f"   Model: {model}")
    print(f"   Concurrent Requests: {num_requests}")
    print(f"{'='*60}")
    
    async with aiohttp.ClientSession() as session:
        # Create 50 concurrent tasks with rotating complex prompts
        tasks = []
        for i in range(num_requests):
            prompt = COMPLEX_PROMPTS[i % len(COMPLEX_PROMPTS)]
            task = make_stress_request(session, url, model, prompt, i)
            tasks.append(task)
        
        # Fire all at once!
        print(f"\n🔥 Firing {num_requests} concurrent requests...")
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
    
    # Analyze results
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    
    print(f"\n📊 RESULTS:")
    print(f"   ─────────────────────────────────")
    print(f"   Completed: {len(successes)}/{num_requests}")
    print(f"   Completion Rate: {len(successes)/num_requests*100:.1f}%")
    print(f"   Total Time: {total_time:.2f}s")
    
    if successes:
        times = [r["time"] for r in successes]
        total_tokens = sum(r["tokens"] for r in successes)
        
        print(f"   ─────────────────────────────────")
        print(f"   Avg Response Time: {sum(times)/len(times):.2f}s")
        print(f"   Fastest: {min(times):.2f}s")
        print(f"   Slowest: {max(times):.2f}s")
        print(f"   Total Tokens: {total_tokens}")
        print(f"   Tokens/Second: {total_tokens/total_time:.1f}")
    
    if failures:
        print(f"\n   ❌ FAILURES ({len(failures)}):")
        error_counts = {}
        for f in failures:
            err = f.get("error", "unknown")
            error_counts[err] = error_counts.get(err, 0) + 1
        for err, count in error_counts.items():
            print(f"      {err}: {count}")
    
    # Sample responses
    if successes:
        print(f"\n   📝 SAMPLE RESPONSES:")
        for r in successes[:3]:
            print(f"      [{r['id']:2d}] {r['response_preview'][:80]}...")
    
    return {
        "king": king_name,
        "total_requests": num_requests,
        "successes": len(successes),
        "failures": len(failures),
        "completion_rate": len(successes) / num_requests * 100,
        "total_time": total_time,
        "avg_time": sum(r["time"] for r in successes) / len(successes) if successes else 0,
        "tokens": sum(r["tokens"] for r in successes) if successes else 0
    }


async def run_all_stress_tests():
    """Run stress tests for all kings."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     ⚔️  BATTLE 3: THE STRONGEST MAN - STRESS TEST ⚔️          ║")
    print(f"║                     {datetime.now().strftime('%H:%M:%S')}                              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    results = {}
    for king_name, king_config in KINGS.items():
        results[king_name] = await run_stress_test(king_name, king_config)
    
    # Final summary
    print("\n" + "="*60)
    print("STRESS TEST SUMMARY")
    print("="*60)
    
    for king_name, stats in results.items():
        emoji = KINGS[king_name]["emoji"]
        print(f"\n{emoji} {king_name}:")
        print(f"   Completion: {stats['successes']}/50 ({stats['completion_rate']:.1f}%)")
        print(f"   Avg Time: {stats['avg_time']:.2f}s")
        print(f"   Total Tokens: {stats['tokens']}")
    
    # Determine winner
    print("\n" + "─"*60)
    sorted_kings = sorted(results.items(), key=lambda x: (x[1]['completion_rate'], -x[1]['avg_time']), reverse=True)
    print(f"🏆 STRONGEST: {sorted_kings[0][0]} ({sorted_kings[0][1]['completion_rate']:.1f}% completion)")
    
    return results


async def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "all":
            await run_all_stress_tests()
        elif arg in [k.lower() for k in KINGS.keys()]:
            king_name = arg.upper()
            await run_stress_test(king_name, KINGS[king_name])
        else:
            print("Usage: python3 stress-test.py [qwen|llama|mixtral|all]")
    else:
        await run_all_stress_tests()


if __name__ == "__main__":
    asyncio.run(main())
