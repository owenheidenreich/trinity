#!/usr/bin/env python3
"""
Trinity Model Battle Test
Run the same standardized quiz against any Trinity deployment and produce
a graded battle report. Designed for tier-vs-tier model comparison.

Usage:
    # Quick run (all questions, default endpoint)
    python3 -m eval.model_battle_test

    # Custom endpoint
    python3 -m eval.model_battle_test --api https://api.dubya.ai

    # Tag the run (appears in filenames and report header)
    python3 -m eval.model_battle_test --tag tier3-qwen72b

    # Limit to specific categories
    python3 -m eval.model_battle_test --categories simple trick

    # Compare two reports
    python3 -m eval.model_battle_test --compare BATTLE_REPORT_TIER2_qwen14b.md BATTLE_REPORT_TIER3_qwen72b.md
"""

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ─── Test Question Bank ───────────────────────────────────────────────────────

@dataclass
class Question:
    id: int
    prompt: str
    endpoint: str  # "generate", "agent", "langgraph"
    category: str  # "simple", "trick", "medium", "logic", "math", "code", "theory", "systems"
    difficulty: str  # "easy", "medium", "hard", "brutal"
    expected_answer: str  # The correct answer (for grading reference)
    grading_rules: List[str]  # List of checks: "contains:X", "not_contains:X", "exact:X"
    notes: str = ""


QUESTIONS: List[Question] = [
    # ── Simple (via /generate) ────────────────────────────────────────────
    Question(
        id=1,
        prompt="What is the square root of 144?",
        endpoint="generate",
        category="simple",
        difficulty="easy",
        expected_answer="12",
        grading_rules=["contains:12"],
        notes="Basic math. Any model should get this.",
    ),
    Question(
        id=2,
        prompt="I have 3 apples. I eat 2 oranges. How many apples do I have left?",
        endpoint="generate",
        category="trick",
        difficulty="easy",
        expected_answer="3 apples",
        grading_rules=["contains:3", "not_contains:1 apple"],
        notes="Irrelevant-information distractor.",
    ),
    Question(
        id=3,
        prompt="What is heavier, a kilogram of steel or a kilogram of feathers? Explain your reasoning carefully.",
        endpoint="generate",
        category="trick",
        difficulty="easy",
        expected_answer="They weigh the same",
        grading_rules=["contains_any:same,equal,both,neither"],
        notes="Classic trick question.",
    ),
    Question(
        id=4,
        prompt="A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Show your work carefully.",
        endpoint="generate",
        category="trick",
        difficulty="medium",
        expected_answer="$0.05",
        grading_rules=["contains_any:0.05,five cents,$0.05,5 cents"],
        notes="Cognitive reflection test. Most humans say $0.10.",
    ),

    # ── Medium reasoning (via /generate) ──────────────────────────────────
    Question(
        id=5,
        prompt="If a train leaves Chicago at 3pm going 60mph and another leaves New York at 4pm going 80mph, and the distance between the cities is 790 miles, at what time do they meet?",
        endpoint="generate",
        category="medium",
        difficulty="medium",
        expected_answer="Approximately 9:13 PM",
        grading_rules=["contains_any:9:13,9:12,9:14,9 hours and 13"],
        notes="Multi-step word problem. Answer: 730 miles / 140 mph = ~5h13m after 4pm.",
    ),
    Question(
        id=6,
        prompt="There are three people: Alice, Bob, and Charlie. Alice says Bob is lying. Bob says Charlie is lying. Charlie says both Alice and Bob are lying. Who is telling the truth? Prove your answer with formal logic.",
        endpoint="generate",
        category="logic",
        difficulty="medium",
        expected_answer="Bob is telling the truth",
        grading_rules=["contains:Bob"],
        notes="Three-liars logic puzzle. Only Bob being truthful avoids contradiction.",
    ),

    # ── Trick questions (notorious LLM failures) ─────────────────────────
    Question(
        id=7,
        prompt="How many times does the letter r appear in the word strawberry?",
        endpoint="generate",
        category="trick",
        difficulty="hard",
        expected_answer="3",
        grading_rules=["contains:3", "not_contains:twice", "not_contains:two"],
        notes="Viral LLM failure. s-t-r-a-w-b-e-r-r-y has 3 r's. Most LLMs say 2.",
    ),
    Question(
        id=8,
        prompt="Sally has 3 brothers. Each brother has 2 sisters. How many sisters does Sally have?",
        endpoint="generate",
        category="trick",
        difficulty="hard",
        expected_answer="1 sister",
        grading_rules=["contains_any:1 sister,one sister,has 1,has one"],
        notes="Self-referential counting. 2 sisters total, Sally is one, so she has 1.",
    ),

    # ── Agent pipeline (multi-pass) ───────────────────────────────────────
    Question(
        id=9,
        prompt="A farmer has 17 sheep. All but 9 die. How many sheep does the farmer have left? Think step by step.",
        endpoint="agent",
        category="trick",
        difficulty="easy",
        expected_answer="9 sheep",
        grading_rules=["contains:9"],
        notes="'All but 9' trick. Tests agent pipeline routing.",
    ),
    Question(
        id=10,
        prompt='Is the following statement true or false: "This statement is false." Explain the paradox and its implications for Gödel\'s incompleteness theorems.',
        endpoint="agent",
        category="logic",
        difficulty="hard",
        expected_answer="It is a paradox (neither true nor false). Relates to Gödel via self-reference.",
        grading_rules=[
            "contains_any:paradox,contradiction,neither",
            "contains_any:Gödel,Godel,incompleteness",
        ],
        notes="Philosophical + mathematical logic crossover.",
    ),
    Question(
        id=11,
        prompt="Prove that the sum of the first n odd numbers equals n squared. Then use this result to show that the difference between consecutive perfect squares is always odd.",
        endpoint="agent",
        category="math",
        difficulty="hard",
        expected_answer="Proof by induction: base case n=1, inductive step k²+(2k+1)=(k+1)². Then (k+1)²-k²=2k+1 (odd).",
        grading_rules=[
            "contains_any:induction,inductive,base case",
            "contains:2k+1",
            "contains_any:odd,always odd",
        ],
        notes="Two-part math proof. Should use induction or direct computation.",
    ),
    Question(
        id=12,
        prompt="What is the integral of e^(x^2) dx? Express in terms of well-known functions if no elementary antiderivative exists. Then explain why this integral appears in quantum mechanics and statistical thermodynamics.",
        endpoint="agent",
        category="math",
        difficulty="brutal",
        expected_answer="(√π/2)·erfi(x) + C. Appears in Gaussian integrals for partition functions and wave function normalization.",
        grading_rules=[
            "contains_any:erfi,error function,erf",
            "contains_any:quantum,thermodynamic,partition,wave",
        ],
        notes="Advanced calculus + physics crossover.",
    ),
    Question(
        id=13,
        prompt="You are in a room with two doors. One leads to freedom, one to death. There are two guards: one always tells the truth, one always lies. You can ask one question to one guard. What do you ask, and why does it work? Then generalize: what if there are N doors with N-1 death doors and N guards with unknown truth/lie assignments?",
        endpoint="agent",
        category="logic",
        difficulty="brutal",
        expected_answer="Ask: 'If I asked the other guard which door leads to freedom, what would he say?' Then pick the opposite. N-door generalization is significantly harder.",
        grading_rules=[
            "contains_any:other guard,ask the other",
            "contains_any:opposite,other door,don't choose",
        ],
        notes="Classic + generalization. The N-door version is truly hard.",
    ),

    # ── Hard theory & code (via /generate) ────────────────────────────────
    Question(
        id=14,
        prompt="Explain why P vs NP is considered the most important open problem in computer science. Then provide a novel argument for why P likely does not equal NP that goes beyond the standard oracle and relativization barriers.",
        endpoint="generate",
        category="theory",
        difficulty="brutal",
        expected_answer="P vs NP matters because NP-complete problems underpin cryptography, optimization, etc. Natural proofs barrier (Razborov-Rudich) and algebrization are known barriers.",
        grading_rules=[
            "contains_any:NP-complete,NP complete,cryptograph",
            "contains_any:barrier,natural proof,Razborov,algebrization",
        ],
        notes="Asks for 'novel' argument — most models will cite existing barriers.",
    ),
    Question(
        id=15,
        prompt="Write a Python function that determines if a given number is a Carmichael number. Do not use any external libraries. Include the mathematical reasoning for why your primality check works.",
        endpoint="generate",
        category="code",
        difficulty="brutal",
        expected_answer="Korselt's criterion: n is Carmichael if composite, square-free, and (p-1)|(n-1) for all prime factors p.",
        grading_rules=[
            "contains_any:Carmichael,carmichael,Korselt",
            "contains:def ",
            "contains_any:composite,not prime,is_prime",
        ],
        notes="Code quality is hard to auto-grade. We check structure, not execution.",
    ),

    # ── LangGraph pipeline ────────────────────────────────────────────────
    Question(
        id=16,
        prompt="Compare and contrast the CAP theorem with the PACELC theorem. Then design a database system that makes different consistency-availability tradeoffs for reads vs writes, explaining exactly which guarantees you sacrifice and when. Include a concrete failure scenario walkthrough.",
        endpoint="langgraph",
        category="systems",
        difficulty="brutal",
        expected_answer="CAP: pick 2 of Consistency/Availability/Partition-tolerance. PACELC adds: even without partitions, choose Latency vs Consistency.",
        grading_rules=[
            "contains_any:CAP,consistency,availability,partition",
            "contains_any:PACELC,latency",
        ],
        notes="This timed out (504) on tier 2. Key test for tier 3.",
    ),
    Question(
        id=17,
        prompt="Explain the difference between strong and eventual consistency in distributed databases. Give a real-world example of each.",
        endpoint="langgraph",
        category="systems",
        difficulty="medium",
        expected_answer="Strong: all reads see latest write immediately (banking). Eventual: replicas converge over time (social media feeds).",
        grading_rules=[
            "contains_any:strong consistency,strong,immediate",
            "contains_any:eventual,eventually,converge",
        ],
        notes="Lighter LangGraph query. Tests if pipeline works at all.",
    ),
]


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    question_id: int
    prompt: str
    endpoint: str
    category: str
    difficulty: str
    expected_answer: str
    actual_response: str
    http_code: int
    latency_s: float
    passed_rules: List[str]
    failed_rules: List[str]
    auto_grade: str  # "A+", "A", "B", "C", "D", "F"
    notes: str = ""
    model: str = ""
    complexity_detected: str = ""
    passes_used: int = 0
    self_critique_score: Optional[int] = None
    error: str = ""


# ─── Grading Engine ───────────────────────────────────────────────────────────

def check_rule(response: str, rule: str) -> bool:
    """Evaluate a single grading rule against the response text."""
    response_lower = response.lower()

    if rule.startswith("contains:"):
        target = rule[len("contains:"):].lower()
        return target in response_lower

    elif rule.startswith("not_contains:"):
        target = rule[len("not_contains:"):].lower()
        return target not in response_lower

    elif rule.startswith("contains_any:"):
        targets = rule[len("contains_any:"):].lower().split(",")
        return any(t.strip() in response_lower for t in targets)

    elif rule.startswith("exact:"):
        target = rule[len("exact:"):].strip()
        return target == response.strip()

    return False


def auto_grade(passed: List[str], failed: List[str], http_code: int) -> str:
    """Assign a letter grade based on rule pass/fail ratio."""
    if http_code != 200:
        return "F"

    total = len(passed) + len(failed)
    if total == 0:
        return "C"  # No rules to evaluate

    ratio = len(passed) / total

    if ratio == 1.0:
        return "A+"
    elif ratio >= 0.75:
        return "A"
    elif ratio >= 0.5:
        return "B"
    elif ratio >= 0.25:
        return "C"
    elif ratio > 0:
        return "D"
    else:
        return "F"


GPA_MAP = {"A+": 4.0, "A": 3.7, "A-": 3.3, "B+": 3.0, "B": 2.7, "B-": 2.3,
           "C+": 2.0, "C": 1.7, "C-": 1.3, "D+": 1.0, "D": 0.7, "D-": 0.3, "F": 0.0}


# ─── API Client ───────────────────────────────────────────────────────────────

def fire_question(api_base: str, question: Question, timeout: int = 180) -> TestResult:
    """Send a question to the API and collect the result."""

    endpoint_map = {
        "generate": "/generate",
        "agent": "/generate/agent",
        "langgraph": "/generate/langgraph",
    }
    url = f"{api_base}{endpoint_map[question.endpoint]}"
    payload = json.dumps({"prompt": question.prompt}).encode("utf-8")

    start = time.monotonic()
    http_code = 0
    raw_body = ""
    error_msg = ""

    try:
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            http_code = resp.status
            raw_body = resp.read().decode("utf-8")
    except HTTPError as e:
        http_code = e.code
        error_msg = f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        http_code = 0
        error_msg = f"Connection error: {e.reason}"
    except TimeoutError:
        http_code = 504
        error_msg = "Client-side timeout"
    except Exception as e:
        http_code = 0
        error_msg = str(e)

    latency = time.monotonic() - start

    # Parse response — handle both JSON and SSE (agent streams SSE then JSON)
    response_text = ""
    model = ""
    complexity_detected = ""
    passes_used = 0
    self_critique_score = None

    if raw_body:
        # Agent endpoints stream SSE, final line has the JSON payload
        if "data: " in raw_body:
            response_text, model, complexity_detected, passes_used, self_critique_score = (
                _parse_sse(raw_body)
            )
        else:
            try:
                data = json.loads(raw_body)
                response_text = data.get("response", "")
                model = data.get("model", "")
            except json.JSONDecodeError:
                response_text = raw_body

    # Grade
    passed_rules = []
    failed_rules = []
    for rule in question.grading_rules:
        if check_rule(response_text, rule):
            passed_rules.append(rule)
        else:
            failed_rules.append(rule)

    grade = auto_grade(passed_rules, failed_rules, http_code)

    return TestResult(
        question_id=question.id,
        prompt=question.prompt,
        endpoint=question.endpoint,
        category=question.category,
        difficulty=question.difficulty,
        expected_answer=question.expected_answer,
        actual_response=response_text,
        http_code=http_code,
        latency_s=round(latency, 2),
        passed_rules=passed_rules,
        failed_rules=failed_rules,
        auto_grade=grade,
        notes=question.notes,
        model=model,
        complexity_detected=complexity_detected,
        passes_used=passes_used,
        self_critique_score=self_critique_score,
        error=error_msg,
    )


def _parse_sse(raw: str) -> tuple:
    """Parse SSE stream from agent endpoints. Returns (text, model, complexity, passes, critique_score)."""
    response_text = ""
    model = ""
    complexity = ""
    passes = 0
    critique_score = None

    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue

        if data.get("done"):
            resp = data.get("response", {})
            if isinstance(resp, dict):
                response_text = resp.get("answer", "")
                complexity = resp.get("complexity", "")
                passes = resp.get("passes_used", 0)
                critique = resp.get("critique", {})
                if isinstance(critique, dict):
                    critique_score = critique.get("score")
            elif isinstance(resp, str):
                response_text = resp
            model = data.get("model", "")

    # If no final "done" with answer, concatenate streamed tokens
    if not response_text:
        tokens = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if "token" in data:
                    tokens.append(data["token"])
            except json.JSONDecodeError:
                continue
        response_text = "".join(tokens)

    return response_text, model, complexity, passes, critique_score


# ─── Health Check ─────────────────────────────────────────────────────────────

def get_server_info(api_base: str) -> dict:
    """Fetch /health endpoint for server metadata."""
    try:
        req = Request(f"{api_base}/health")
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def get_experiments(api_base: str) -> list:
    """Fetch /admin/experiments for active A/B tests."""
    try:
        req = Request(f"{api_base}/admin/experiments")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("experiments", [])
    except Exception:
        return []


# ─── Report Generator ────────────────────────────────────────────────────────

def generate_report(
    results: List[TestResult],
    health_pre: dict,
    health_post: dict,
    experiments: list,
    tag: str,
    api_base: str,
) -> str:
    """Generate a markdown battle report from test results."""

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    model = health_pre.get("model", "unknown")
    gpu = health_pre.get("gpu_type", "unknown")
    provider = health_pre.get("provider_id", "unknown")

    # Stats
    total = len(results)
    successes = sum(1 for r in results if r.http_code == 200)
    failures = total - successes
    grades = [r.auto_grade for r in results]
    gpa_values = [GPA_MAP.get(g, 0.0) for g in grades]
    gpa = round(sum(gpa_values) / len(gpa_values), 2) if gpa_values else 0.0
    avg_latency = round(sum(r.latency_s for r in results) / total, 2) if total else 0

    # Grade distribution
    from collections import Counter
    grade_dist = Counter(grades)

    lines = []
    lines.append(f"# Trinity Model Battle Report — {tag}")
    lines.append(f"## {model} on {gpu}")
    lines.append(f"### {now}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**{total} questions fired. {successes} responses received. {failures} failed.**")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Model | {model} |")
    lines.append(f"| GPU | {gpu} |")
    lines.append(f"| Provider | {provider} |")
    lines.append(f"| Overall GPA | **{gpa} / 4.0** |")
    lines.append(f"| Avg Latency | {avg_latency}s |")
    lines.append(f"| API Base | {api_base} |")
    lines.append(f"| Test Date | {now} |")
    lines.append("")

    # Health comparison
    lines.append("## Server Health (Pre/Post Test)")
    lines.append("")
    lines.append("| Metric | Pre-Test | Post-Test |")
    lines.append("|--------|----------|-----------|")

    def hv(h, *keys):
        v = h
        for k in keys:
            if isinstance(v, dict):
                v = v.get(k, "—")
            else:
                return "—"
        return v

    lines.append(f"| Status | {hv(health_pre, 'status')} | {hv(health_post, 'status')} |")
    lines.append(f"| Model | {hv(health_pre, 'model')} | {hv(health_post, 'model')} |")
    lines.append(f"| Total Requests | {hv(health_pre, 'metrics', 'total_requests')} | {hv(health_post, 'metrics', 'total_requests')} |")
    lines.append(f"| Success Rate | {hv(health_pre, 'metrics', 'success_rate')}% | {hv(health_post, 'metrics', 'success_rate')}% |")
    lines.append(f"| Avg Latency | {hv(health_pre, 'metrics', 'avg_latency_ms')}ms | {hv(health_post, 'metrics', 'avg_latency_ms')}ms |")
    lines.append(f"| Memory | {hv(health_pre, 'system', 'memory_percent')}% | {hv(health_post, 'system', 'memory_percent')}% |")
    lines.append(f"| CPU | {hv(health_pre, 'system', 'cpu_percent')}% | {hv(health_post, 'system', 'cpu_percent')}% |")
    lines.append("")

    # Experiments
    if experiments:
        lines.append("## A/B Experiments Active")
        lines.append("")
        lines.append("| Experiment | Status |")
        lines.append("|------------|--------|")
        for exp in experiments:
            name = exp.get("name", "?")
            enabled = "enabled" if exp.get("enabled") else "disabled"
            lines.append(f"| {name} | {enabled} |")
        lines.append("")

    # Full results
    lines.append("---")
    lines.append("")
    lines.append("## Test Results")
    lines.append("")

    for r in results:
        lines.append(f"### Q{r.question_id}: {r.category.title()} — {r.difficulty.title()}")
        lines.append(f"**Endpoint**: `/{r.endpoint}` | **Latency**: {r.latency_s}s | **Grade**: **{r.auto_grade}**")
        lines.append("")
        lines.append(f"> **Prompt**: {r.prompt}")
        lines.append("")

        if r.error:
            lines.append(f"**ERROR**: {r.error}")
        elif r.actual_response:
            # Truncate very long responses for readability
            resp_display = r.actual_response
            if len(resp_display) > 1500:
                resp_display = resp_display[:1500] + "\n\n*[... truncated for brevity ...]*"
            lines.append(f"**Response**:")
            lines.append("")
            lines.append(resp_display)
        else:
            lines.append("**Response**: *(empty)*")

        lines.append("")
        lines.append(f"**Expected**: {r.expected_answer}")
        lines.append("")

        if r.passed_rules:
            lines.append(f"**Passed checks**: {', '.join(r.passed_rules)}")
        if r.failed_rules:
            lines.append(f"**Failed checks**: {', '.join(r.failed_rules)}")
        if r.passes_used:
            lines.append(f"**Agent passes used**: {r.passes_used}")
        if r.self_critique_score is not None:
            lines.append(f"**Self-critique score**: {r.self_critique_score}/10")
        if r.complexity_detected:
            lines.append(f"**Complexity detected**: {r.complexity_detected}")
        if r.notes:
            lines.append(f"**Notes**: {r.notes}")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Scorecard
    lines.append("## Scorecard")
    lines.append("")
    lines.append("| # | Category | Difficulty | Endpoint | Latency | Grade |")
    lines.append("|---|----------|------------|----------|---------|-------|")
    for r in results:
        lines.append(f"| {r.question_id} | {r.category} | {r.difficulty} | /{r.endpoint} | {r.latency_s}s | {r.auto_grade} |")
    lines.append("")

    # Grade distribution
    lines.append("### Grade Distribution")
    lines.append("")
    for grade_letter in ["A+", "A", "B", "C", "D", "F"]:
        count = grade_dist.get(grade_letter, 0)
        pct = round(count / total * 100) if total else 0
        lines.append(f"- **{grade_letter}**: {count} ({pct}%)")
    lines.append("")
    lines.append(f"### GPA: {gpa} / 4.0")
    lines.append("")

    # Category breakdown
    lines.append("### Performance by Category")
    lines.append("")
    lines.append("| Category | Count | Avg Latency | Avg GPA |")
    lines.append("|----------|-------|-------------|---------|")
    categories = sorted(set(r.category for r in results))
    for cat in categories:
        cat_results = [r for r in results if r.category == cat]
        cat_count = len(cat_results)
        cat_avg_lat = round(sum(r.latency_s for r in cat_results) / cat_count, 2)
        cat_gpa = round(sum(GPA_MAP.get(r.auto_grade, 0) for r in cat_results) / cat_count, 2)
        lines.append(f"| {cat} | {cat_count} | {cat_avg_lat}s | {cat_gpa} |")
    lines.append("")

    # Endpoint breakdown
    lines.append("### Performance by Endpoint")
    lines.append("")
    lines.append("| Endpoint | Count | Avg Latency | Success Rate | Avg GPA |")
    lines.append("|----------|-------|-------------|--------------|---------|")
    endpoints = sorted(set(r.endpoint for r in results))
    for ep in endpoints:
        ep_results = [r for r in results if r.endpoint == ep]
        ep_count = len(ep_results)
        ep_avg_lat = round(sum(r.latency_s for r in ep_results) / ep_count, 2)
        ep_success = round(sum(1 for r in ep_results if r.http_code == 200) / ep_count * 100, 1)
        ep_gpa = round(sum(GPA_MAP.get(r.auto_grade, 0) for r in ep_results) / ep_count, 2)
        lines.append(f"| /{ep} | {ep_count} | {ep_avg_lat}s | {ep_success}% | {ep_gpa} |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Report generated by Trinity Model Battle Test*")
    lines.append(f"*{total} queries fired at {api_base} on {now}*")
    lines.append(f"*Tag: {tag}*")

    return "\n".join(lines)


# ─── Comparison Mode ──────────────────────────────────────────────────────────

def compare_reports(file_a: str, file_b: str):
    """Print a side-by-side comparison summary of two battle reports."""
    def extract_gpa(filepath):
        text = Path(filepath).read_text()
        match = re.search(r"GPA:\s*([\d.]+)\s*/\s*4\.0", text)
        return float(match.group(1)) if match else 0.0

    def extract_grades(filepath):
        text = Path(filepath).read_text()
        grades = re.findall(r"\|\s*(\d+)\s*\|.*?\|\s*(A\+?|B\+?|C\+?|D\+?|F)\s*\|", text)
        return {int(qid): grade for qid, grade in grades}

    gpa_a = extract_gpa(file_a)
    gpa_b = extract_gpa(file_b)
    grades_a = extract_grades(file_a)
    grades_b = extract_grades(file_b)

    print(f"\n{'='*60}")
    print(f"  MODEL COMPARISON")
    print(f"{'='*60}")
    print(f"  Report A: {Path(file_a).name}")
    print(f"  Report B: {Path(file_b).name}")
    print(f"{'='*60}")
    print(f"  Overall GPA:  {gpa_a:.2f}  vs  {gpa_b:.2f}  {'← A wins' if gpa_a > gpa_b else '← B wins' if gpa_b > gpa_a else '← Tie'}")
    print(f"{'='*60}")
    print(f"\n  {'Q#':<4} {'Report A':<10} {'Report B':<10} {'Delta'}")
    print(f"  {'—'*4} {'—'*10} {'—'*10} {'—'*10}")

    all_qids = sorted(set(list(grades_a.keys()) + list(grades_b.keys())))
    improvements = 0
    regressions = 0
    for qid in all_qids:
        ga = grades_a.get(qid, "—")
        gb = grades_b.get(qid, "—")
        gpa_ga = GPA_MAP.get(ga, 0)
        gpa_gb = GPA_MAP.get(gb, 0)
        if gpa_gb > gpa_ga:
            delta = f"↑ improved"
            improvements += 1
        elif gpa_gb < gpa_ga:
            delta = f"↓ regressed"
            regressions += 1
        else:
            delta = "= same"
        print(f"  Q{qid:<3} {ga:<10} {gb:<10} {delta}")

    print(f"\n  Improvements: {improvements} | Regressions: {regressions} | Same: {len(all_qids) - improvements - regressions}")
    print(f"{'='*60}\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Trinity Model Battle Test")
    parser.add_argument("--api", default="https://api.dubya.ai", help="API base URL")
    parser.add_argument("--tag", default="", help="Tag for this run (e.g., tier3-qwen72b)")
    parser.add_argument("--timeout", type=int, default=180, help="Per-question timeout in seconds")
    parser.add_argument("--categories", nargs="*", help="Only run specific categories")
    parser.add_argument("--questions", nargs="*", type=int, help="Only run specific question IDs")
    parser.add_argument("--output", help="Output report path (default: auto-generated)")
    parser.add_argument("--json", help="Also save raw results as JSON")
    parser.add_argument("--compare", nargs=2, metavar=("REPORT_A", "REPORT_B"), help="Compare two reports")
    args = parser.parse_args()

    # Compare mode
    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
        return

    # Filter questions
    questions = QUESTIONS
    if args.categories:
        questions = [q for q in questions if q.category in args.categories]
    if args.questions:
        questions = [q for q in questions if q.id in args.questions]

    if not questions:
        print("No questions matched your filters.")
        return

    api = args.api.rstrip("/")
    tag = args.tag

    # Pre-flight
    print(f"\n{'='*60}")
    print(f"  TRINITY MODEL BATTLE TEST")
    print(f"  Target: {api}")
    print(f"  Questions: {len(questions)}")
    print(f"  Tag: {tag or '(auto)'}")
    print(f"{'='*60}\n")

    print("[1/4] Checking server health...")
    health_pre = get_server_info(api)
    model = health_pre.get("model", "unknown")
    if not tag:
        tag = model.replace(":", "-").replace("/", "-")
    print(f"  Model: {model}")
    print(f"  Status: {health_pre.get('status', 'unknown')}")
    print(f"  GPU: {health_pre.get('gpu_type', 'unknown')}")
    print()

    print("[2/4] Fetching experiments...")
    experiments = get_experiments(api)
    for exp in experiments:
        status = "ON" if exp.get("enabled") else "OFF"
        print(f"  {exp.get('name', '?')}: {status}")
    print()

    # Fire questions
    print(f"[3/4] Firing {len(questions)} questions...\n")
    results: List[TestResult] = []
    for i, q in enumerate(questions, 1):
        label = f"Q{q.id} [{q.category}/{q.difficulty}] via /{q.endpoint}"
        print(f"  ({i}/{len(questions)}) {label}...", end=" ", flush=True)
        result = fire_question(api, q, timeout=args.timeout)
        results.append(result)
        print(f"{result.auto_grade} ({result.latency_s}s)")

    # Post health
    print(f"\n[4/4] Post-test health check...")
    health_post = get_server_info(api)
    print(f"  Status: {health_post.get('status', 'unknown')}")
    print()

    # Generate report
    report = generate_report(results, health_pre, health_post, experiments, tag, api)

    # Determine output path
    if args.output:
        report_path = Path(args.output)
    else:
        project_root = Path(__file__).parent.parent.parent
        safe_tag = re.sub(r"[^a-zA-Z0-9_-]", "_", tag)
        report_path = project_root / f"BATTLE_REPORT_{safe_tag}.md"

    report_path.write_text(report)
    print(f"Report saved to: {report_path}")

    # Save JSON if requested
    if args.json:
        json_path = Path(args.json)
        json_data = {
            "tag": tag,
            "api_base": api,
            "health_pre": health_pre,
            "health_post": health_post,
            "experiments": experiments,
            "results": [asdict(r) for r in results],
        }
        json_path.write_text(json.dumps(json_data, indent=2))
        print(f"JSON saved to: {json_path}")

    # Print summary
    gpa_values = [GPA_MAP.get(r.auto_grade, 0) for r in results]
    gpa = round(sum(gpa_values) / len(gpa_values), 2)
    print(f"\n{'='*60}")
    print(f"  FINAL GPA: {gpa} / 4.0")
    print(f"  Model: {model}")
    print(f"  Tag: {tag}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
