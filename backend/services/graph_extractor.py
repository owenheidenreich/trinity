"""
Graph extractor compatibility layer.

Graph triples are now produced by the unified LLM extraction call in
`profile_extractor.extract_memory_candidates`.
"""

from typing import Dict, List


def extract_graph_triples(message: str, source: str = "user") -> List[Dict]:
    """Return graph triples extracted from a single unified LLM call."""
    from .profile_extractor import extract_memory_candidates

    result = extract_memory_candidates(message, source=source)
    return result.get("triples", [])
