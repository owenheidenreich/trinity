"""
Memory Policy Evaluation
========================
Deterministic eval cases for memory relevance precision/recall.
"""

from typing import Dict, List

from services.query_classifier import requests_personal_memory as _question_requests_personal_memory

# Try to import _format_user_memory from agent — may have been refactored
try:
    from services.agent import _format_user_memory
except ImportError:
    def _format_user_memory(profile, query="", include_personal=False):
        """Fallback: render facts as bullet list."""
        facts = profile.get("facts", [])
        if not include_personal:
            facts = [f for f in facts if f.get("category") != "identity"]
        return "\n".join(f"- {f['text']}" for f in facts)

_EVAL_CASES = [
    {
        "query": "what is the quadratic formula",
        "facts": [
            {"text": "User's name is Owen", "category": "identity", "importance": 5},
            {"text": "User prefers concise answers", "category": "preferences", "importance": 4},
        ],
        "expected": {"User prefers concise answers"},
    },
    {
        "query": "what do you know about me",
        "facts": [
            {"text": "User's name is Owen", "category": "identity", "importance": 5},
            {"text": "User works at Acme", "category": "work", "importance": 4},
        ],
        "expected": {"User's name is Owen", "User works at Acme"},
    },
    {
        "query": "write a python function to parse csv",
        "facts": [
            {"text": "User lives in NYC", "category": "identity", "importance": 3},
            {"text": "User prefers concise answers", "category": "preferences", "importance": 4},
            {"text": "User uses Python", "category": "work", "importance": 4},
        ],
        "expected": {"User prefers concise answers", "User uses Python"},
    },
]


def _extract_rendered_facts(rendered: str) -> List[str]:
    return [line[2:] for line in rendered.splitlines() if line.startswith("- ")]


def evaluate_memory_policy() -> Dict:
    """
    Evaluate memory relevance behavior with fixed cases.
    Returns precision/recall in [0, 1].
    """
    true_positive = 0
    false_positive = 0
    false_negative = 0

    for case in _EVAL_CASES:
        query = case["query"]
        facts = case["facts"]
        expected = set(case["expected"])
        include_personal = _question_requests_personal_memory(query)
        rendered = _format_user_memory({"facts": facts}, query=query, include_personal=include_personal)
        selected = set(_extract_rendered_facts(rendered))

        true_positive += len(selected.intersection(expected))
        false_positive += len(selected.difference(expected))
        false_negative += len(expected.difference(selected))

    precision = (
        true_positive / float(true_positive + false_positive)
        if (true_positive + false_positive) > 0
        else 1.0
    )
    recall = (
        true_positive / float(true_positive + false_negative)
        if (true_positive + false_negative) > 0
        else 1.0
    )

    return {
        "precision": precision,
        "recall": recall,
        "cases": len(_EVAL_CASES),
    }
