#!/usr/bin/env python3
"""
Trinity LLM Response Test
Verifies that the full stack returns valid LLM responses

Tests:
1. Direct Akash backend (if accessible)
2. Via Vercel proxy
3. Health endpoint
4. Generate endpoint with actual prompt

Usage:
    python test/integration/test_llm_response.py [backend_url]
    
    # Test via Vercel proxy (default):
    python test/integration/test_llm_response.py
    
    # Test direct Akash:
    python test/integration/test_llm_response.py http://xyz.ingress.akash.pub
"""

import sys
import os
import json
import time
import requests
from datetime import datetime

# Default to Vercel proxy
DEFAULT_URL = "https://vercel-proxy-swart-nine.vercel.app"

# Test prompts - simple queries that any model can answer
TEST_PROMPTS = [
    {
        "name": "Simple Math",
        "prompt": "What is 2 + 2? Answer with just the number.",
        "expected_contains": "4"
    },
    {
        "name": "Basic Greeting",
        "prompt": "Say hello in one word.",
        "min_length": 2
    },
    {
        "name": "Code Generation",
        "prompt": "Write a Python function that adds two numbers. Keep it simple.",
        "expected_contains": "def"
    }
]


def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")


def test_health(url):
    """Test health endpoint"""
    print_header("Health Check")
    
    try:
        start = time.time()
        r = requests.get(f"{url}/health", timeout=30)
        latency = (time.time() - start) * 1000
        
        if r.status_code == 200:
            health = r.json()
            print_result(True, f"Backend healthy ({latency:.0f}ms)")
            print(f"   Provider: {health.get('provider_id', 'unknown')}")
            print(f"   Model: {health.get('model', 'unknown')}")
            print(f"   Ollama: {'connected' if health.get('ollama_connected') else 'disconnected'}")
            
            if 'metrics' in health:
                uptime = health['metrics'].get('uptime_seconds', 0)
                print(f"   Uptime: {uptime:.1f}s")
            
            return True, health
        else:
            print_result(False, f"Health check returned {r.status_code}")
            print(f"   Response: {r.text[:200]}")
            return False, None
            
    except requests.exceptions.Timeout:
        print_result(False, "Health check timed out (30s)")
        return False, None
    except requests.exceptions.ConnectionError as e:
        print_result(False, f"Connection failed: {e}")
        return False, None
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False, None


def test_generate(url, prompt_config, timeout=120):
    """Test generate endpoint with a prompt"""
    name = prompt_config["name"]
    prompt = prompt_config["prompt"]
    
    print(f"\n📝 Test: {name}")
    print(f"   Prompt: {prompt[:50]}...")
    
    try:
        start = time.time()
        r = requests.post(
            f"{url}/generate",
            json={"prompt": prompt, "max_length": 100},
            timeout=timeout
        )
        latency = (time.time() - start) * 1000
        
        if r.status_code == 200:
            data = r.json()
            # API returns "response" not "generated_text"
            text = data.get("response", data.get("generated_text", ""))
            tokens = data.get("tokens_generated", 0)
            tps = data.get("tokens_per_second", 0)
            
            print(f"   Response ({latency:.0f}ms, {tokens} tokens, {tps:.1f} tok/s):")
            suffix = '...' if len(text) > 100 else '"'
            print(f'   "{text[:100]}{suffix}')            
            # Validation checks
            success = True
            
            if "expected_contains" in prompt_config:
                if prompt_config["expected_contains"].lower() not in text.lower():
                    print(f"   ⚠️  Expected '{prompt_config['expected_contains']}' not found")
                    success = False
            
            if "min_length" in prompt_config:
                if len(text) < prompt_config["min_length"]:
                    print(f"   ⚠️  Response too short ({len(text)} < {prompt_config['min_length']})")
                    success = False
            
            if len(text.strip()) == 0:
                print(f"   ⚠️  Empty response!")
                success = False
            
            print_result(success, f"{name} - {'passed' if success else 'failed'}")
            return success, data
            
        else:
            print_result(False, f"Generate returned {r.status_code}")
            print(f"   Response: {r.text[:200]}")
            return False, None
            
    except requests.exceptions.Timeout:
        print_result(False, f"Generate timed out ({timeout}s)")
        return False, None
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False, None


def run_all_tests(url):
    """Run all LLM response tests"""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + "  Trinity LLM Response Test".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"\nTarget: {url}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "tests": []
    }
    
    # Test 1: Health check
    health_ok, health_data = test_health(url)
    results["health"] = health_ok
    if health_data:
        results["model"] = health_data.get("model", "unknown")
        results["provider"] = health_data.get("provider_id", "unknown")
    
    if not health_ok:
        print_header("FAILED - Backend not reachable")
        print("\nTroubleshooting:")
        print("1. Check if Akash container is running")
        print("2. Verify Vercel proxy AKASH_URL is correct")
        print("3. Try both HTTP and HTTPS for Akash URL")
        print("4. Run: ./scripts/switch-provider.sh <correct-url>")
        return False, results
    
    # Test 2: Generate endpoints
    print_header("LLM Generate Tests")
    
    passed = 0
    failed = 0
    
    for prompt_config in TEST_PROMPTS:
        success, data = test_generate(url, prompt_config)
        results["tests"].append({
            "name": prompt_config["name"],
            "success": success,
            "response": data.get("generated_text", "") if data else None
        })
        if success:
            passed += 1
        else:
            failed += 1
    
    # Summary
    print_header("Summary")
    total = passed + failed
    print(f"   Passed: {passed}/{total}")
    print(f"   Failed: {failed}/{total}")
    
    all_passed = failed == 0
    if all_passed:
        print("\n🎉 All tests passed! LLM is responding correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
    
    results["passed"] = passed
    results["failed"] = failed
    results["success"] = all_passed
    
    return all_passed, results


def main():
    # Get URL from command line or use default
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = DEFAULT_URL
    
    # Remove trailing slash
    url = url.rstrip("/")
    
    success, results = run_all_tests(url)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
