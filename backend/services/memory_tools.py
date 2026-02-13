"""
Trinity MemGPT Memory Tools

LLM-callable tools for managing user memory:
- save_memory: Store important facts about the user
- recall_memory: Retrieve relevant facts by semantic similarity
- search_memory: Search through saved memories (exact, semantic, or hybrid)

Facts are stored with embeddings for semantic retrieval and deduplicated
using cosine similarity to prevent near-duplicate entries.
"""

import logging
import time
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _get_embeddings():
    """Lazy import embeddings to avoid circular imports."""
    from .embeddings import cosine_similarity, embed_text
    return embed_text, cosine_similarity


def _get_storage():
    """Lazy import storage to avoid circular imports."""
    from storage import load_user_memory, save_user_memory
    return load_user_memory, save_user_memory


def tool_save_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """
    Save a fact about the user to persistent memory.

    Params:
        fact: The fact to save (required)
        category: Category label (default: "general")
        importance: 1-5 importance rating (default: 3)
    """
    fact = params.get("fact", "").strip()
    if not fact:
        return False, "No fact provided to save"

    category = params.get("category", "general").strip().lower()
    try:
        importance = max(1, min(5, int(params.get("importance", "3"))))
    except (ValueError, TypeError):
        importance = 3

    try:
        embed_text, cosine_similarity = _get_embeddings()
        load_user_memory, save_user_memory = _get_storage()

        # Generate embedding for the new fact
        fact_embedding = embed_text(fact)
        if fact_embedding is None:
            return False, "Failed to generate embedding for fact"

        # Load existing memory
        memory = load_user_memory(principal_id)
        facts = memory.get("facts", [])

        # Deduplication: check if a near-duplicate exists
        for existing in facts:
            existing_emb = existing.get("embedding")
            if existing_emb is not None:
                existing_arr = np.array(existing_emb)
                similarity = cosine_similarity(fact_embedding, existing_arr)
                if similarity > 0.95:
                    return True, f"Already remembered something similar: \"{existing['text']}\""

        # Add the new fact
        new_fact = {
            "text": fact,
            "category": category,
            "importance": importance,
            "embedding": fact_embedding.tolist(),
            "created_at": int(time.time() * 1000),
        }
        facts.append(new_fact)
        memory["facts"] = facts

        save_user_memory(principal_id, memory)

        return True, f"Saved: \"{fact}\" (category: {category}, importance: {importance}/5)"

    except Exception as e:
        logger.error(f"save_memory error: {e}")
        return False, f"Failed to save memory: {e}"


def tool_recall_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """
    Recall facts about the user by semantic similarity.

    Params:
        query: What to recall (required)
        category: Optional category filter
        limit: Max results (default: 5)
    """
    query = params.get("query", "").strip()
    if not query:
        return False, "No query provided"

    category_filter = params.get("category", "").strip().lower() or None
    try:
        limit = max(1, min(20, int(params.get("limit", "5"))))
    except (ValueError, TypeError):
        limit = 5

    try:
        embed_text, cosine_similarity = _get_embeddings()
        load_user_memory, _ = _get_storage()

        memory = load_user_memory(principal_id)
        facts = memory.get("facts", [])

        if not facts:
            return True, "No memories saved yet."

        # Embed query
        query_embedding = embed_text(query)
        if query_embedding is None:
            return False, "Failed to generate query embedding"

        # Score each fact: 0.7 * similarity + 0.3 * (importance/5)
        scored = []
        for fact in facts:
            if category_filter and fact.get("category", "general") != category_filter:
                continue

            emb = fact.get("embedding")
            if emb is None:
                continue

            similarity = cosine_similarity(query_embedding, np.array(emb))
            importance = fact.get("importance", 3)
            score = 0.7 * similarity + 0.3 * (importance / 5.0)
            scored.append((score, similarity, fact))

        if not scored:
            msg = f"No memories found"
            if category_filter:
                msg += f" in category '{category_filter}'"
            return True, msg

        # Sort by combined score, take top K
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        lines = [f"Recalled {len(top)} memories:"]
        for i, (score, sim, fact) in enumerate(top, 1):
            lines.append(f"\n{i}. \"{fact['text']}\"")
            lines.append(f"   Category: {fact.get('category', 'general')} | Importance: {fact.get('importance', 3)}/5 | Relevance: {sim:.2f}")

        return True, "\n".join(lines)

    except Exception as e:
        logger.error(f"recall_memory error: {e}")
        return False, f"Failed to recall memory: {e}"


def tool_search_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """
    Search through saved memories with multiple modes.

    Params:
        query: Search query (required)
        search_type: "semantic" (default), "exact", or "hybrid"
        limit: Max results (default: 5)
    """
    query = params.get("query", "").strip()
    if not query:
        return False, "No search query provided"

    search_type = params.get("search_type", "semantic").strip().lower()
    if search_type not in ("semantic", "exact", "hybrid"):
        search_type = "semantic"

    try:
        limit = max(1, min(20, int(params.get("limit", "5"))))
    except (ValueError, TypeError):
        limit = 5

    try:
        embed_text, cosine_similarity = _get_embeddings()
        load_user_memory, _ = _get_storage()

        memory = load_user_memory(principal_id)
        facts = memory.get("facts", [])

        if not facts:
            return True, "No memories saved yet."

        results = []

        if search_type in ("exact", "hybrid"):
            # Exact substring match
            query_lower = query.lower()
            for fact in facts:
                text = fact.get("text", "")
                if query_lower in text.lower():
                    results.append((1.0, fact, "exact"))

        if search_type in ("semantic", "hybrid"):
            # Semantic similarity search
            query_embedding = embed_text(query)
            if query_embedding is not None:
                for fact in facts:
                    emb = fact.get("embedding")
                    if emb is None:
                        continue

                    similarity = cosine_similarity(query_embedding, np.array(emb))
                    # Skip if already found by exact match in hybrid mode
                    if search_type == "hybrid":
                        already_found = any(
                            f.get("text") == fact.get("text") for _, f, _ in results
                        )
                        if already_found:
                            continue
                    if similarity > 0.3:  # Minimum relevance threshold
                        results.append((similarity, fact, "semantic"))

        if not results:
            return True, f"No memories match '{query}'"

        # Sort by score, take top K
        results.sort(key=lambda x: x[0], reverse=True)
        top = results[:limit]

        lines = [f"Found {len(top)} memories ({search_type} search):"]
        for i, (score, fact, match_type) in enumerate(top, 1):
            lines.append(f"\n{i}. \"{fact['text']}\"")
            lines.append(f"   Match: {match_type} | Score: {score:.2f} | Category: {fact.get('category', 'general')}")

        return True, "\n".join(lines)

    except Exception as e:
        logger.error(f"search_memory error: {e}")
        return False, f"Failed to search memory: {e}"
