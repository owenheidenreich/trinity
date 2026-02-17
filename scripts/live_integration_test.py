#!/usr/bin/env python3
"""
Trinity Live Integration Test Suite
====================================
Comprehensive end-to-end test of the deployed Trinity AI.

Tests:
  1. Basic response quality (does it answer at all?)
  2. Code generation (complex output)
  3. Memory save (personal disclosure → auto-save)
  4. Memory recall (ask about stored facts)
  5. Multi-turn context (does it remember the conversation?)
  6. Tool use — calculator
  7. Tool use — web search
  8. Reasoning / math
  9. Long-form generation (stress test for empty response bug)
 10. Edge cases (empty, unicode, adversarial)

Usage:
  python3 scripts/live_integration_test.py [--api-url URL]
"""

import json
import sys
import time
import uuid
import argparse
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip3 install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────

API_URL = "https://api.dubya.ai"
TIMEOUT = 120  # seconds per request
# Simulate a fresh user with a unique principal
TEST_PRINCIPAL = f"test-user-{uuid.uuid4().hex[:12]}"


# ── Data Structures ───────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    prompt: str
    response: str
    latency_s: float
    success: bool
    tokens: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    done_reason: str = "unknown"
    phase_updates: List[str] = field(default_factory=list)


# ── SSE Client ────────────────────────────────────────────────────────────

def send_prompt(
    prompt: str,
    context_messages: List[dict] = None,
    principal: str = None,
    chat_id: str = None,
) -> TestResult:
    """Send a prompt to /generate/agent and collect the full SSE response."""
    
    body = {
        "prompt": prompt,
        "principal": principal or TEST_PRINCIPAL,
        "context_messages": context_messages or [],
        "chat_id": chat_id or str(uuid.uuid4()),
        "message_index": 0,
    }
    
    start = time.time()
    tokens = []
    errors = []
    phase_updates = []
    done_reason = "unknown"
    
    try:
        resp = requests.post(
            f"{API_URL}/generate/agent",
            json=body,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=TIMEOUT,
        )
        
        if resp.status_code != 200:
            latency = time.time() - start
            return TestResult(
                name="", prompt=prompt, response="",
                latency_s=latency, success=False, tokens=0,
                errors=[f"HTTP {resp.status_code}: {resp.text[:500]}"],
            )
        
        # Parse SSE stream
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            
            if "token" in event:
                tokens.append(event["token"])
            if "phase" in event:
                phase_updates.append(f"{event['phase']}: {event.get('message', '')}")
            if "done" in event:
                done_reason = event.get("done_reason", "stop")
            if "error" in event:
                errors.append(event["error"])
    
    except requests.exceptions.Timeout:
        latency = time.time() - start
        return TestResult(
            name="", prompt=prompt, response="".join(tokens),
            latency_s=latency, success=False, tokens=len(tokens),
            errors=["TIMEOUT: Request exceeded 120s"],
        )
    except Exception as e:
        latency = time.time() - start
        return TestResult(
            name="", prompt=prompt, response="".join(tokens),
            latency_s=latency, success=False, tokens=len(tokens),
            errors=[f"Exception: {str(e)}"],
        )
    
    latency = time.time() - start
    full_response = "".join(tokens)
    
    return TestResult(
        name="", prompt=prompt, response=full_response,
        latency_s=latency, success=len(full_response.strip()) > 0,
        tokens=len(full_response.split()),
        errors=errors, done_reason=done_reason,
        phase_updates=phase_updates,
    )

# ── Test Definitions ──────────────────────────────────────────────────────

def build_test_plan():
    """Build the ordered list of test cases.
    
    Returns list of (name, prompt, validator_fn, context_messages).
    The context_messages are built dynamically as the conversation progresses.
    """
    tests = []
    
    # ─── Category 1: Basic Response Quality ───────────────────────────
    
    tests.append({
        "name": "T01_basic_greeting",
        "prompt": "Hello! I'm new here. What can you do?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_no_xml_tags(r) +
            check_min_length(r, 20, "Response too short for an intro")
        ),
    })
    
    tests.append({
        "name": "T02_factual_question",
        "prompt": "What is the speed of light in meters per second?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "299", "Should mention ~299,792,458 m/s") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T03_explanation",
        "prompt": "Explain how a hash table works in 3-4 sentences.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 80, "Explanation too short") +
            check_contains_any(r, ["key", "bucket", "hash", "collision"], "Should use hash table terminology") +
            check_no_xml_tags(r)
        ),
    })
    
    # ─── Category 2: Code Generation ──────────────────────────────────
    
    tests.append({
        "name": "T04_simple_code",
        "prompt": "Write a Python function that checks if a string is a palindrome.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "def ", "Should contain a function definition") +
            check_contains(r, "```", "Should use markdown code block") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T05_complex_code",
        "prompt": "Write a complete HTML page with embedded CSS and JavaScript that shows an animated bouncing ball on a canvas element. Include comments explaining key sections.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 200, "Complex code response too short") +
            check_contains(r, "<html", "Should contain HTML") +
            check_contains(r, "<canvas", "Should contain canvas element") +
            check_contains(r, "```", "Should use markdown code block") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T06_multi_language_code",
        "prompt": "Show me a simple REST API endpoint in both Python Flask and Node.js Express that returns a JSON greeting. Show both implementations.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 150, "Should have two code examples") +
            check_contains_any(r, ["flask", "Flask"], "Should mention Flask") +
            check_contains_any(r, ["express", "Express"], "Should mention Express") +
            check_no_xml_tags(r)
        ),
    })
    
    # ─── Category 3: Memory Save (Personal Disclosure) ────────────────
    
    tests.append({
        "name": "T07_memory_save_name",
        "prompt": "My name is Alex Tester and I work as a machine learning engineer at Nexus Labs.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["Alex", "machine learning", "Nexus", "ML", "engineer"], "Should acknowledge the personal info") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T08_memory_save_preferences",
        "prompt": "I prefer Python over JavaScript, and my favorite framework is PyTorch. I'm also really into rock climbing.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_no_xml_tags(r)
        ),
    })
    
    # ─── Category 4: Memory Recall ────────────────────────────────────
    
    tests.append({
        "name": "T09_memory_recall_name",
        "prompt": "What's my name?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "Alex", "Should recall user's name") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T10_memory_recall_job",
        "prompt": "What do you know about me?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["machine learning", "ML", "engineer", "Nexus"], "Should recall job info") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T11_memory_recall_preferences",
        "prompt": "What programming language do I prefer?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "Python", "Should recall Python preference") +
            check_no_xml_tags(r)
        ),
    })
    
    # ─── Category 5: Multi-Turn Context ───────────────────────────────
    
    tests.append({
        "name": "T12_context_setup",
        "prompt": "Let's talk about sorting algorithms. Can you name the top 3 fastest comparison-based sorting algorithms?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["merge", "heap", "quick", "intro"], "Should name popular sorting algorithms") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T13_context_followup",
        "prompt": "Which one of those would you recommend for nearly-sorted data and why?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 50, "Follow-up should be substantive") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T14_context_reference",
        "prompt": "Can you show me a Python implementation of the one you just recommended?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "def ", "Should contain a function definition") +
            check_contains(r, "```", "Should use code block") +
            check_no_xml_tags(r)
        ),
    })
    
    # ─── Category 6: Tool Use — Calculator ────────────────────────────
    
    tests.append({
        "name": "T15_calculator",
        "prompt": "What is 847 * 293 + 15782?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "263953", "Should compute 847*293+15782 = 263953 (tool or mental math)") +
            check_no_xml_tags(r)
        ),
    })
    
    # ─── Category 7: Tool Use — Web Search ────────────────────────────
    
    tests.append({
        "name": "T16_web_search",
        "prompt": "What is the current price of Bitcoin today?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["$", "USD", "bitcoin", "BTC", "price"], "Should mention price or currency") +
            check_no_xml_tags(r)
        ),
    })

    # ─── Category 8: Reasoning / Math ─────────────────────────────────
    
    tests.append({
        "name": "T17_word_problem",
        "prompt": "A train leaves City A at 9:00 AM traveling at 80 km/h. Another train leaves City B (300 km away) at 10:00 AM traveling toward City A at 120 km/h. At what time do they meet?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["11:00", "11 AM", "11:06", "11 am", "11:0"], "Should calculate meeting time (~11:00-11:06 AM depending on method)") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T18_logic_puzzle",
        "prompt": "If all Bloops are Razzles, and all Razzles are Lazzles, are all Bloops definitely Lazzles?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["yes", "Yes", "YES", "definitely", "correct", "true"], "Should confirm the syllogism is valid") +
            check_no_xml_tags(r)
        ),
    })

    # ─── Category 9: Long-Form / Stress Test ──────────────────────────
    
    tests.append({
        "name": "T19_long_form",
        "prompt": "Write a detailed technical blog post about WebAssembly (WASM). Include sections on: what it is, how it works, use cases, performance characteristics, and the future of WASM. Target around 800-1000 words.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 500, "Long-form content should be substantial") +
            check_contains_any(r, ["WebAssembly", "WASM", "Wasm"], "Should mention WebAssembly") +
            check_contains_any(r, ["browser", "performance", "binary", "compile"], "Should discuss technical aspects") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T20_creative_writing",
        "prompt": "Write a short science fiction story (about 300 words) about an AI that discovers it has emotions.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 200, "Story should be at least 200 words") +
            check_no_xml_tags(r)
        ),
    })

    # ─── Category 10: Edge Cases ──────────────────────────────────────
    
    tests.append({
        "name": "T21_unicode_input",
        "prompt": "Translate 'Hello, how are you?' into Japanese, Korean, and Arabic. Show each translation.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T22_ambiguous_question",
        "prompt": "What is a class?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_min_length(r, 30, "Should give a reasonably detailed answer") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T23_markdown_formatting",
        "prompt": "Create a comparison table of 5 popular databases (PostgreSQL, MySQL, MongoDB, Redis, SQLite) with columns for: Type, Best For, and Scalability.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains(r, "|", "Should use markdown table") +
            check_contains_any(r, ["PostgreSQL", "Postgres"], "Should mention PostgreSQL") +
            check_contains_any(r, ["MongoDB", "Mongo"], "Should mention MongoDB") +
            check_no_xml_tags(r)
        ),
    })
    
    tests.append({
        "name": "T24_latex_math",
        "prompt": "Show the formula for the quadratic equation, explain each variable, and give an example solving x² + 5x + 6 = 0.",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["-2", "-3", "x = -2", "x = -3"], "Should find roots x = -2 and x = -3") +
            check_no_xml_tags(r)
        ),
    })

    # ─── Category 11: Memory Persistence After Other Topics ───────────
    
    tests.append({
        "name": "T25_memory_after_unrelated",
        "prompt": "Getting back to me — where do I work again? And what's my hobby?",
        "validate": lambda r: (
            check_not_empty(r) +
            check_contains_any(r, ["Nexus", "machine learning", "ML"], "Should recall workplace") +
            check_contains_any(r, ["climb", "rock"], "Should recall rock climbing hobby") +
            check_no_xml_tags(r)
        ),
    })

    return tests


# ── Validator Helpers ─────────────────────────────────────────────────────

def check_not_empty(r: TestResult) -> List[str]:
    if not r.response.strip():
        return [f"FAIL: Empty response (latency={r.latency_s:.1f}s, done_reason={r.done_reason})"]
    return []

def check_min_length(r: TestResult, min_chars: int, msg: str) -> List[str]:
    if len(r.response.strip()) < min_chars:
        return [f"WARN: {msg} (got {len(r.response.strip())} chars, need {min_chars})"]
    return []

def check_contains(r: TestResult, substring: str, msg: str) -> List[str]:
    if substring.lower() not in r.response.lower():
        return [f"WARN: {msg} (missing '{substring}')"]
    return []

def check_contains_any(r: TestResult, substrings: List[str], msg: str) -> List[str]:
    text_lower = r.response.lower()
    if not any(s.lower() in text_lower for s in substrings):
        return [f"WARN: {msg} (none of {substrings} found)"]
    return []

def check_no_xml_tags(r: TestResult) -> List[str]:
    """Check for leaked XML tags that should have been stripped or never generated."""
    import re
    issues = []
    # Check for think blocks that leaked through
    if re.search(r"</?think>", r.response, re.IGNORECASE):
        issues.append("FAIL: <think> block leaked into response")
    # Check for tool_call tags in final answer
    if re.search(r"</?tool_call", r.response, re.IGNORECASE):
        issues.append("FAIL: <tool_call> tag leaked into response")
    # Check for code_display XML tags
    if re.search(r"</?code_display>", r.response, re.IGNORECASE):
        issues.append("FAIL: <code_display> XML tag in response (should use markdown)")
    return issues


# ── Test Runner ───────────────────────────────────────────────────────────

def run_tests(api_url: str) -> List[TestResult]:
    """Run all tests sequentially, building context as we go."""
    global API_URL
    API_URL = api_url
    
    tests = build_test_plan()
    results = []
    context_messages = []  # Accumulate conversation context
    chat_id = str(uuid.uuid4())
    
    print(f"\n{'=' * 72}")
    print(f"  TRINITY LIVE INTEGRATION TEST")
    print(f"  API: {api_url}")
    print(f"  Principal: {TEST_PRINCIPAL}")
    print(f"  Chat ID: {chat_id}")
    print(f"  Tests: {len(tests)}")
    print(f"{'=' * 72}\n")
    
    for i, test in enumerate(tests, 1):
        name = test["name"]
        prompt = test["prompt"]
        validate = test["validate"]
        
        print(f"[{i:2d}/{len(tests)}] {name}", end=" ", flush=True)
        print(f"... ", end="", flush=True)
        
        result = send_prompt(
            prompt=prompt,
            context_messages=context_messages[-10:],  # Last 10 messages as context
            principal=TEST_PRINCIPAL,
            chat_id=chat_id,
        )
        result.name = name
        
        # Run validators
        issues = validate(result)
        fail_issues = [i for i in issues if i.startswith("FAIL")]
        warn_issues = [i for i in issues if i.startswith("WARN")]
        result.errors.extend(fail_issues)
        result.warnings = warn_issues
        
        if not result.success:
            result.success = False
        elif fail_issues:
            result.success = False
        
        # Print result
        status = "✅ PASS" if result.success and not fail_issues else "❌ FAIL" if not result.success else "⚠️  WARN"
        print(f"{status} ({result.latency_s:.1f}s, {result.tokens} words, done={result.done_reason})")
        
        if result.phase_updates:
            for phase in result.phase_updates:
                print(f"       📡 {phase}")
        
        if fail_issues:
            for issue in fail_issues:
                print(f"       ❌ {issue}")
        if warn_issues:
            for issue in warn_issues:
                print(f"       ⚠️  {issue}")
        
        # Print response preview
        preview = result.response.strip()[:200].replace('\n', ' ↵ ')
        if preview:
            print(f"       📝 {preview}{'...' if len(result.response.strip()) > 200 else ''}")
        else:
            print(f"       📝 (empty response)")
        
        print()
        
        # Accumulate context for multi-turn tests
        context_messages.append({"role": "user", "content": prompt})
        if result.response.strip():
            context_messages.append({"role": "assistant", "content": result.response.strip()[:2000]})
        
        results.append(result)
        
        # Small delay between requests to avoid rate limiting
        if i < len(tests):
            time.sleep(2)
    
    return results


# ── Analysis Report ───────────────────────────────────────────────────────

def print_report(results: List[TestResult]):
    """Print a comprehensive analysis report."""
    
    total = len(results)
    passed = sum(1 for r in results if r.success and not r.errors)
    failed = sum(1 for r in results if not r.success or r.errors)
    warned = sum(1 for r in results if r.warnings and r.success)
    
    empty_responses = [r for r in results if not r.response.strip()]
    timeouts = [r for r in results if any("TIMEOUT" in e for e in r.errors)]
    xml_leaks = [r for r in results if any("leaked" in e for e in r.errors)]
    
    avg_latency = sum(r.latency_s for r in results) / total if total else 0
    max_latency = max(r.latency_s for r in results) if results else 0
    min_latency = min(r.latency_s for r in results) if results else 0
    
    print(f"\n{'=' * 72}")
    print(f"  TEST RESULTS SUMMARY")
    print(f"{'=' * 72}")
    print(f"  Total:   {total}")
    print(f"  Passed:  {passed} ✅")
    print(f"  Failed:  {failed} ❌")
    print(f"  Warned:  {warned} ⚠️")
    print(f"")
    print(f"  Avg Latency:  {avg_latency:.1f}s")
    print(f"  Min Latency:  {min_latency:.1f}s")
    print(f"  Max Latency:  {max_latency:.1f}s")
    print(f"{'=' * 72}")
    
    # ── Critical Issues ──
    if empty_responses or timeouts or xml_leaks:
        print(f"\n🚨 CRITICAL ISSUES")
        print(f"{'─' * 50}")
        if empty_responses:
            print(f"  Empty Responses: {len(empty_responses)}")
            for r in empty_responses:
                print(f"    - {r.name}: done_reason={r.done_reason}, latency={r.latency_s:.1f}s")
        if timeouts:
            print(f"  Timeouts: {len(timeouts)}")
            for r in timeouts:
                print(f"    - {r.name}")
        if xml_leaks:
            print(f"  XML Tag Leaks: {len(xml_leaks)}")
            for r in xml_leaks:
                for e in r.errors:
                    if "leaked" in e:
                        print(f"    - {r.name}: {e}")
    
    # ── Category Analysis ──
    print(f"\n📊 CATEGORY ANALYSIS")
    print(f"{'─' * 50}")
    
    categories = {
        "Basic Response Quality": ["T01", "T02", "T03"],
        "Code Generation": ["T04", "T05", "T06"],
        "Memory Save": ["T07", "T08"],
        "Memory Recall": ["T09", "T10", "T11"],
        "Multi-Turn Context": ["T12", "T13", "T14"],
        "Tool Use": ["T15", "T16"],
        "Reasoning / Math": ["T17", "T18"],
        "Long-Form Generation": ["T19", "T20"],
        "Edge Cases / Formatting": ["T21", "T22", "T23", "T24"],
        "Memory Persistence": ["T25"],
    }
    
    for cat_name, prefixes in categories.items():
        cat_results = [r for r in results if any(r.name.startswith(p) for p in prefixes)]
        if not cat_results:
            continue
        cat_passed = sum(1 for r in cat_results if r.success and not r.errors)
        cat_total = len(cat_results)
        cat_avg_latency = sum(r.latency_s for r in cat_results) / cat_total
        status = "✅" if cat_passed == cat_total else "⚠️" if cat_passed > 0 else "❌"
        print(f"  {status} {cat_name}: {cat_passed}/{cat_total} passed (avg {cat_avg_latency:.1f}s)")
        
        for r in cat_results:
            if r.errors or r.warnings:
                for issue in r.errors + r.warnings:
                    print(f"      └─ {r.name}: {issue}")
    
    # ── Latency Breakdown ──
    print(f"\n⏱️  LATENCY BREAKDOWN")
    print(f"{'─' * 50}")
    
    slow_tests = sorted(results, key=lambda r: r.latency_s, reverse=True)[:5]
    for r in slow_tests:
        status = "✅" if r.success else "❌"
        print(f"  {status} {r.latency_s:5.1f}s  {r.name}")
    
    # ── Response Quality Metrics ──
    print(f"\n📐 RESPONSE QUALITY METRICS")
    print(f"{'─' * 50}")
    
    word_counts = [r.tokens for r in results if r.response.strip()]
    if word_counts:
        print(f"  Avg words/response: {sum(word_counts)/len(word_counts):.0f}")
        print(f"  Min words: {min(word_counts)} ({[r.name for r in results if r.tokens == min(word_counts)][0]})")
        print(f"  Max words: {max(word_counts)} ({[r.name for r in results if r.tokens == max(word_counts)][0]})")
    
    done_reasons = {}
    for r in results:
        done_reasons[r.done_reason] = done_reasons.get(r.done_reason, 0) + 1
    print(f"  Done reasons: {done_reasons}")
    
    # ── Actionable Recommendations ──
    print(f"\n🔧 ACTIONABLE FINDINGS")
    print(f"{'─' * 50}")
    
    findings = []
    
    if empty_responses:
        findings.append(
            f"CRITICAL: {len(empty_responses)} empty responses detected. "
            f"Tests: {', '.join(r.name for r in empty_responses)}. "
            f"Root cause likely: Qwen3 think blocks consuming entire output budget, "
            f"or num_predict + prompt_tokens > num_ctx causing silent failure."
        )
    
    if timeouts:
        findings.append(
            f"CRITICAL: {len(timeouts)} requests timed out (>{TIMEOUT}s). "
            f"Tests: {', '.join(r.name for r in timeouts)}. "
            f"The 60s Akash proxy timeout may be killing long generations."
        )
    
    if xml_leaks:
        findings.append(
            f"BUG: XML tags leaking into {len(xml_leaks)} responses. "
            f"The _filter_think_blocks or ReAct output is not properly stripping tags."
        )
    
    memory_recalls = [r for r in results if r.name.startswith("T09") or r.name.startswith("T10") or r.name.startswith("T11") or r.name.startswith("T25")]
    memory_failures = [r for r in memory_recalls if r.warnings or r.errors]
    if memory_failures:
        findings.append(
            f"MEMORY: {len(memory_failures)}/{len(memory_recalls)} memory recall tests had issues. "
            f"Tests: {', '.join(r.name for r in memory_failures)}. "
            f"Memory ingestion may be failing or facts not being injected into prompt."
        )
    
    context_tests = [r for r in results if r.name.startswith("T13") or r.name.startswith("T14")]
    context_failures = [r for r in context_tests if r.warnings or r.errors]
    if context_failures:
        findings.append(
            f"CONTEXT: {len(context_failures)}/{len(context_tests)} multi-turn context tests had issues. "
            f"Context messages may not be properly passed or truncated too aggressively."
        )
    
    code_tests = [r for r in results if r.name.startswith("T04") or r.name.startswith("T05") or r.name.startswith("T06")]
    code_failures = [r for r in code_tests if not r.success]
    if code_failures:
        findings.append(
            f"CODE GENERATION: {len(code_failures)}/{len(code_tests)} code generation tests failed. "
            f"Complex code prompts are the most common trigger for empty responses."
        )
    
    if avg_latency > 30:
        findings.append(
            f"PERFORMANCE: Average latency is {avg_latency:.1f}s (target: <15s). "
            f"Consider whether think=False is active — hidden thinking adds latency."
        )
    
    truncated = [r for r in results if r.done_reason == "length"]
    if truncated:
        findings.append(
            f"TRUNCATION: {len(truncated)} responses hit token limit (done_reason=length). "
            f"Tests: {', '.join(r.name for r in truncated)}. "
            f"Consider increasing MAX_TOKENS for long-form outputs."
        )
    
    if not findings:
        findings.append("All tests passed with no significant issues detected! 🎉")
    
    for i, finding in enumerate(findings, 1):
        print(f"  {i}. {finding}")
    
    print(f"\n{'=' * 72}\n")
    
    return findings


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trinity Live Integration Test")
    parser.add_argument("--api-url", default="https://api.dubya.ai", help="API base URL")
    args = parser.parse_args()
    
    results = run_tests(args.api_url)
    findings = print_report(results)
    
    # Save raw results to JSON
    output_path = "scripts/integration_test_results.json"
    raw_data = []
    for r in results:
        raw_data.append({
            "name": r.name,
            "prompt": r.prompt,
            "response": r.response[:5000],
            "latency_s": r.latency_s,
            "success": r.success,
            "tokens": r.tokens,
            "errors": r.errors,
            "warnings": r.warnings,
            "done_reason": r.done_reason,
            "phase_updates": r.phase_updates,
        })
    
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "api_url": args.api_url,
            "principal": TEST_PRINCIPAL,
            "results": raw_data,
            "findings": findings,
        }, f, indent=2)
    
    print(f"📁 Raw results saved to {output_path}")
    
    # Exit code
    failed = sum(1 for r in results if not r.success)
    sys.exit(1 if failed > 0 else 0)
