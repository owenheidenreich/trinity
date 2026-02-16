"""
Graph Extractor
===============
Heuristic extraction of user-centric relationship triples.
"""

import re
from typing import Dict, List

_USER_PATTERNS = [
    (re.compile(r"\bmy name is ([\w\s]{2,40})", re.I), "name_is", "person"),
    (re.compile(r"\bi(?:'m| am) (?:a |an )?([\w\s]{2,40})", re.I), "is_a", "role"),
    (re.compile(r"\bi live in ([\w\s,]{2,60})", re.I), "lives_in", "location"),
    (re.compile(r"\bi(?:'m| am) from ([\w\s,]{2,60})", re.I), "from", "location"),
    (re.compile(r"\bi work (?:at|for) ([\w\s&.]{2,60})", re.I), "works_at", "company"),
    (re.compile(r"\bmy (?:job|role|title) is ([\w\s]{2,60})", re.I), "has_role", "role"),
    (re.compile(r"\bi(?:'m| am) (?:building|developing|working on) ([\w\s]{2,80})", re.I), "building", "project"),
    (re.compile(r"\bi (?:like|love|enjoy) ([\w\s]{2,80})(?:\.|,|$)", re.I), "likes", "interest"),
    (re.compile(r"\bi prefer ([\w\s]{2,80})(?:\.|,|$)", re.I), "prefers", "preference"),
]


def _clean_value(value: str) -> str:
    cleaned = (value or "").strip().rstrip(".,!?")
    cleaned = " ".join(cleaned.split())
    return cleaned[:120]


def extract_graph_triples(message: str, source: str = "user") -> List[Dict]:
    """
    Extract user relationship triples from text.

    Returns:
        List of {subject, predicate, object, object_kind, confidence, source}
    """
    if source != "user":
        # Assistant-origin triples are intentionally suppressed until a confidence framework exists.
        return []

    text = (message or "").strip()
    if len(text) < 4:
        return []

    triples: List[Dict] = []
    seen = set()
    for pattern, predicate, object_kind in _USER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = _clean_value(match.group(1))
        if len(value) < 2:
            continue

        key = ("user", predicate, value.lower())
        if key in seen:
            continue
        seen.add(key)
        triples.append(
            {
                "subject": "user",
                "predicate": predicate,
                "object": value,
                "object_kind": object_kind,
                "confidence": 0.72,
                "source": source,
            }
        )

    return triples
