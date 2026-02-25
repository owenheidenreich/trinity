"""
Trinity — LLM-callable Memory Tools

Thin tool layer that maps tool-call params to KnowledgeStore operations.
Replaces the 901-line dual-path version with ~200 lines that delegate
everything to KnowledgeStore.

Public tool functions (called from code_executor.py):
  tool_save_memory(params, principal_id) → (bool, str)
  tool_recall_memory(params, principal_id) → (bool, str)
  tool_search_memory(params, principal_id) → (bool, str)
  tool_update_memory(params, principal_id) → (bool, str)
  tool_forget_memory(params, principal_id) → (bool, str)

Also exports:
  detect_contradiction(old_text, new_text) → bool
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# KnowledgeStore accessor (lazy to avoid circular imports at module load)
# ---------------------------------------------------------------------------

def _get_knowledge_store(principal_id: str):
    """Get or create a KnowledgeStore for the given principal."""
    from services.state_store import get_state_store
    from services.knowledge_store import KnowledgeStore

    store = get_state_store(principal_id)
    return KnowledgeStore(store)


def _embed(text: str):
    """Embed text — returns np.ndarray or None."""
    from services.embeddings import embed_text
    return embed_text(text)


# ---------------------------------------------------------------------------
# Contradiction detection (kept — valuable heuristic)
# ---------------------------------------------------------------------------

_VALUE_PATTERNS = [
    (r"(?:user(?:'s)?|i) (?:live|lives|lived) in (.+)", "location"),
    (r"(?:user(?:'s)?|i) (?:work|works|worked) (?:at|for) (.+)", "employer"),
    (r"(?:user(?:'s)?|my) name is (.+)", "name"),
    (r"(?:user(?:'s)?|i am|i'm) from (.+)", "origin"),
    (r"(?:user(?:'s)?|my) (?:role|job|title|position) is (.+)", "role"),
    (
        r"(?:user(?:'s)?|my) (?:project|app|product|startup|company) "
        r"(?:is called |is |called )(.+)",
        "project",
    ),
    (r"(?:user|i) (?:is|am|'m) (?:a |an )(.+)", "identity"),
]


def detect_contradiction(old_text: str, new_text: str) -> bool:
    """Heuristic contradiction detection between two similar facts.

    Returns True if the new fact likely **replaces** the old one
    (e.g. "User lives in NYC" → "User lives in LA").

    Returns False for refinements ("developer" → "senior developer").
    """
    old_lower = old_text.lower().strip()
    new_lower = new_text.lower().strip()

    if old_lower == new_lower:
        return False

    for pattern, _label in _VALUE_PATTERNS:
        old_match = re.search(pattern, old_lower)
        new_match = re.search(pattern, new_lower)
        if old_match and new_match:
            old_val = old_match.group(1).strip().rstrip(".,!")
            new_val = new_match.group(1).strip().rstrip(".,!")
            if old_val != new_val:
                # "developer" → "senior developer" is a refinement, not a contradiction
                if old_val in new_val:
                    return False
                return True

    return False


# Legacy alias used by some tests
_detect_contradiction = detect_contradiction


# ---------------------------------------------------------------------------
# Tool functions — called by code_executor._execute_memory_tool()
# ---------------------------------------------------------------------------

def tool_save_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """Save a fact about the user to persistent memory.

    Params:
        fact: The fact to save (required)
        category: Category label (default: "general")
        importance: 1-5 importance rating (default: 3)
    """
    fact = (params.get("fact") or "").strip()
    if not fact:
        return False, "No fact provided to save"

    category = (params.get("category") or "general").strip().lower()
    try:
        importance = max(1, min(5, int(params.get("importance", "3"))))
    except (ValueError, TypeError):
        importance = 3

    try:
        ks = _get_knowledge_store(principal_id)
        source_msg_id = params.get("source_message_id")
        try:
            source_msg_id = int(source_msg_id) if source_msg_id is not None else None
        except (TypeError, ValueError):
            source_msg_id = None

        action, fact_id = ks.save_fact(
            text=fact,
            category=category,
            importance=importance,
            source_message_id=source_msg_id,
        )

        if action == "skip":
            return True, f'Already remembered something similar: "{fact}"'
        elif action == "merge":
            return True, f'Updated existing memory with: "{fact}"'
        else:
            return True, (
                f'Saved: "{fact}" '
                f"(category: {category}, importance: {importance}/5)"
            )
    except Exception as e:
        logger.error("save_memory error: %s", e, exc_info=True)
        return False, f"Failed to save memory: {e}"


def tool_recall_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """Recall facts about the user by semantic similarity.

    Params:
        query: What to recall (required)
        category: Optional category filter
        limit: Max results (default: 5)
    """
    query = (params.get("query") or "").strip()
    if not query:
        return False, "No query provided"

    category_filter = (params.get("category") or "").strip().lower() or None
    try:
        limit = max(1, min(20, int(params.get("limit", "5"))))
    except (ValueError, TypeError):
        limit = 5

    return _search_common(query, limit, category_filter, principal_id)


def tool_search_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """Search through saved memories.

    Params:
        query: Search query (required)
        search_type: "semantic" (default), "exact", or "hybrid"
        limit: Max results (default: 5)
    """
    query = (params.get("query") or "").strip()
    if not query:
        return False, "No search query provided"

    search_type = (params.get("search_type") or "semantic").strip().lower()
    if search_type not in ("semantic", "exact", "hybrid"):
        search_type = "semantic"

    try:
        limit = max(1, min(20, int(params.get("limit", "5"))))
    except (ValueError, TypeError):
        limit = 5

    category_filter = (params.get("category") or "").strip().lower() or None

    # Exact and hybrid modes: add a text-match pass before semantic search
    if search_type in ("exact", "hybrid"):
        return _search_with_exact(query, limit, search_type, category_filter, principal_id)

    return _search_common(query, limit, category_filter, principal_id)


def tool_update_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """Find and update an existing fact about the user.

    Params:
        query: What fact to find (required)
        new_value: The updated text (required)
        category: Optional new category
        importance: Optional new importance (1-5)
    """
    query = (params.get("query") or "").strip()
    new_value = (params.get("new_value") or "").strip()
    if not query:
        return False, "No query provided to find the memory to update"
    if not new_value:
        return False, "No new_value provided for the update"

    try:
        ks = _get_knowledge_store(principal_id)
        query_emb = _embed(query)
        if query_emb is None:
            return False, "Failed to generate query embedding"

        from services.knowledge_store import ItemType
        results = ks.search(query_emb, top_k=1, item_types=[ItemType.FACT])
        if not results or results[0].similarity_score < 0.3:
            return False, f'No memory found matching: "{query}"'

        best = results[0]
        old_text = best.text

        # Parse optional importance
        new_imp = None
        if params.get("importance") is not None:
            try:
                new_imp = max(1, min(5, int(params["importance"])))
            except (ValueError, TypeError):
                pass

        ks.update_fact(best.item_id, new_text=new_value, importance=new_imp)
        return True, f'Updated: "{old_text}" → "{new_value}" (match: {best.similarity_score:.2f})'
    except Exception as e:
        logger.error("update_memory error: %s", e, exc_info=True)
        return False, f"Failed to update memory: {e}"


def tool_forget_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """Soft-delete a fact about the user.

    Params:
        query: What fact to forget (required)
    """
    query = (params.get("query") or "").strip()
    if not query:
        return False, "No query provided — what should I forget?"

    try:
        ks = _get_knowledge_store(principal_id)
        query_emb = _embed(query)
        if query_emb is None:
            return False, "Failed to generate query embedding"

        from services.knowledge_store import ItemType
        results = ks.search(query_emb, top_k=1, item_types=[ItemType.FACT, ItemType.RELATIONSHIP])
        if not results or results[0].similarity_score < 0.3:
            return False, f'No memory found matching: "{query}"'

        best = results[0]
        ks.soft_delete(best.item_id)
        return True, f'Forgotten: "{best.text}" (match: {best.similarity_score:.2f})'
    except Exception as e:
        logger.error("forget_memory error: %s", e, exc_info=True)
        return False, f"Failed to forget memory: {e}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _search_common(
    query: str,
    limit: int,
    category_filter: str | None,
    principal_id: str,
) -> Tuple[bool, str]:
    """Shared semantic search used by recall_memory and search_memory."""
    try:
        ks = _get_knowledge_store(principal_id)
        query_emb = _embed(query)
        if query_emb is None:
            return False, "Failed to generate query embedding"

        from services.knowledge_store import ItemType
        results = ks.search(
            query_emb,
            top_k=limit,
            item_types=[ItemType.FACT, ItemType.RELATIONSHIP],
            category_filter=category_filter,
        )

        if not results:
            msg = "No memories saved yet." if not category_filter else f"No memories found in category '{category_filter}'"
            return True, msg

        lines = [f"Recalled {len(results)} memories:"]
        for i, item in enumerate(results, 1):
            lines.append(f'\n{i}. "{item.text}"')
            lines.append(
                f"   Category: {item.category} | "
                f"Importance: {item.importance}/5 | "
                f"Relevance: {item.similarity_score:.2f}"
            )
        return True, "\n".join(lines)
    except Exception as e:
        logger.error("recall/search_memory error: %s", e, exc_info=True)
        return False, f"Failed to search memory: {e}"


def _search_with_exact(
    query: str,
    limit: int,
    search_type: str,
    category_filter: str | None,
    principal_id: str,
) -> Tuple[bool, str]:
    """Search memories using semantic search.

    Previously attempted SQL LIKE exact-match, but fact text is stored
    encrypted (text_enc) so plaintext LIKE never worked.  Now delegates
    entirely to the semantic search path which handles all modes.
    """
    return _search_common(query, limit, category_filter, principal_id)
