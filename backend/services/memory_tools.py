"""
Trinity MemGPT Memory Tools

LLM-callable tools for managing user memory:
- save_memory: Store important facts about the user (with merge on near-match)
- recall_memory: Retrieve relevant facts by semantic similarity
- search_memory: Search through saved memories (exact, semantic, or hybrid)
- update_memory: Find and update an existing fact
- forget_memory: Soft-delete a fact (excluded from prompts, preserved in exports)

Facts are stored with embeddings for semantic retrieval and deduplicated
using cosine similarity. Near-matches (>0.85) trigger a merge/update
rather than a new entry.
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


def _get_thresholds():
    """Get dedup thresholds from config."""
    try:
        from config import DEDUP_MERGE_THRESHOLD, DEDUP_SKIP_THRESHOLD
        return DEDUP_MERGE_THRESHOLD, DEDUP_SKIP_THRESHOLD
    except ImportError:
        return 0.85, 0.95


def _detect_contradiction(old_text: str, new_text: str) -> bool:
    """
    Heuristic contradiction detection between two similar facts.

    Returns True if the new fact likely contradicts (replaces) the old one.
    Only uses regex/string heuristics — no LLM calls.

    Examples of contradictions:
        "User lives in NYC" vs "User lives in LA"
        "User works at Google" vs "User works at Meta"
        "User's name is John" vs "User's name is James"

    Examples of non-contradictions (refinements):
        "User is a developer" vs "User is a senior developer"
        "User likes Python" vs "User likes Python and Rust"
    """
    import re

    old_lower = old_text.lower().strip()
    new_lower = new_text.lower().strip()

    # If the texts are very similar (only differ in minor words), not a contradiction
    if old_lower == new_lower:
        return False

    # Check patterns that indicate value substitution.
    # These patterns extract the "subject" and "value" parts.
    # If subjects match but values differ, it's a contradiction.
    value_patterns = [
        # "User lives in X" — extract X
        (r"(?:user(?:'s)?|i) (?:live|lives|lived) in (.+)", "location"),
        # "User works at/for X"
        (r"(?:user(?:'s)?|i) (?:work|works|worked) (?:at|for) (.+)", "employer"),
        # "User's name is X"
        (r"(?:user(?:'s)?|my) name is (.+)", "name"),
        # "User is from X"
        (r"(?:user(?:'s)?|i am|i'm) from (.+)", "origin"),
        # "User's role/job/title is X"
        (r"(?:user(?:'s)?|my) (?:role|job|title|position) is (.+)", "role"),
        # "User's project/app/company is X"
        (r"(?:user(?:'s)?|my) (?:project|app|product|startup|company) (?:is called |is |called )(.+)", "project"),
        # "User is a X" (profession)
        (r"(?:user|i) (?:is|am|'m) (?:a |an )(.+)", "identity"),
    ]

    for pattern, _label in value_patterns:
        old_match = re.search(pattern, old_lower)
        new_match = re.search(pattern, new_lower)

        if old_match and new_match:
            old_value = old_match.group(1).strip().rstrip(".,!")
            new_value = new_match.group(1).strip().rstrip(".,!")

            # If the extracted values are different, it's a contradiction
            if old_value != new_value:
                # But check if the new value is a superset (refinement, not contradiction)
                if old_value in new_value:
                    return False  # "developer" → "senior developer" = refinement
                return True

    return False


def tool_save_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """
    Save a fact about the user to persistent memory.
    Near-duplicates (cosine > merge_threshold) update the existing fact.
    Exact duplicates (cosine > skip_threshold) are silently skipped.

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
        merge_threshold, skip_threshold = _get_thresholds()

        # Generate embedding for the new fact
        fact_embedding = embed_text(fact)
        if fact_embedding is None:
            return False, "Failed to generate embedding for fact"

        # Load existing memory
        memory = load_user_memory(principal_id)
        facts = memory.get("facts", [])

        # Find best-matching existing fact (only among non-deleted)
        best_match = None
        best_similarity = 0.0
        best_index = -1

        for i, existing in enumerate(facts):
            if existing.get("deleted", False):
                continue
            existing_emb = existing.get("embedding")
            if existing_emb is not None:
                existing_arr = np.array(existing_emb)
                similarity = cosine_similarity(fact_embedding, existing_arr)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = existing
                    best_index = i

        now_ms = int(time.time() * 1000)

        if best_similarity > skip_threshold:
            # Too similar — skip entirely
            return True, f"Already remembered something similar: \"{best_match['text']}\""

        if best_similarity > merge_threshold and best_match is not None:
            # Near-match: check for contradiction vs. refinement
            old_text = best_match["text"]

            # Heuristic contradiction detection:
            # If both facts are in the same category and the new fact
            # replaces a key value (e.g., "lives in NYC" → "lives in LA"),
            # invalidate the old fact and create a new one instead of merging.
            is_contradiction = _detect_contradiction(old_text, fact)

            if is_contradiction:
                # Invalidate old fact, add new one
                best_match["invalid_at"] = now_ms
                best_match["last_mentioned"] = now_ms
                facts[best_index] = best_match

                new_fact = {
                    "text": fact,
                    "category": category if category != "general" else best_match.get("category", "general"),
                    "importance": max(best_match.get("importance", 3), importance),
                    "embedding": fact_embedding.tolist(),
                    "created_at": now_ms,
                    "deleted": False,
                    "source_chat_id": None,
                    "last_mentioned": now_ms,
                    "valid_at": now_ms,
                    "invalid_at": None,
                }
                facts.append(new_fact)
                memory["facts"] = facts
                save_user_memory(principal_id, memory)
                logger.info(f"🔄 Contradiction detected: \"{old_text}\" → \"{fact}\"")
                return True, f"Updated memory: \"{old_text}\" → \"{fact}\" (old fact invalidated)"

            # Not a contradiction — merge/update in place
            best_match["text"] = fact
            best_match["embedding"] = fact_embedding.tolist()
            best_match["importance"] = max(best_match.get("importance", 3), importance)
            best_match["last_mentioned"] = now_ms
            if category != "general":
                best_match["category"] = category
            facts[best_index] = best_match
            memory["facts"] = facts

            save_user_memory(principal_id, memory)
            return True, f"Updated memory: \"{old_text}\" → \"{fact}\""

        # Add the new fact
        new_fact = {
            "text": fact,
            "category": category,
            "importance": importance,
            "embedding": fact_embedding.tolist(),
            "created_at": now_ms,
            "deleted": False,
            "source_chat_id": None,
            "last_mentioned": now_ms,
            "valid_at": now_ms,
            "invalid_at": None,
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
        active_facts = [f for f in facts if not f.get("deleted", False)]

        if not active_facts:
            return True, "No memories saved yet."

        # Embed query
        query_embedding = embed_text(query)
        if query_embedding is None:
            return False, "Failed to generate query embedding"

        # Score each fact: 0.7 * similarity + 0.3 * (importance/5)
        scored = []
        for fact in active_facts:
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
        active_facts = [f for f in facts if not f.get("deleted", False)]

        if not active_facts:
            return True, "No memories saved yet."

        results = []

        if search_type in ("exact", "hybrid"):
            # Exact substring match
            query_lower = query.lower()
            for fact in active_facts:
                text = fact.get("text", "")
                if query_lower in text.lower():
                    results.append((1.0, fact, "exact"))

        if search_type in ("semantic", "hybrid"):
            # Semantic similarity search
            query_embedding = embed_text(query)
            if query_embedding is not None:
                for fact in active_facts:
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


def tool_update_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """
    Find and update an existing fact about the user.

    Finds the closest semantic match to `query`, then replaces its text with
    `new_value`. This is how "User moved from NYC to SF" updates are handled.

    Params:
        query: What fact to find (required)
        new_value: The updated text (required)
        category: Optional new category
        importance: Optional new importance (1-5)
    """
    query = params.get("query", "").strip()
    new_value = params.get("new_value", "").strip()
    if not query:
        return False, "No query provided to find the memory to update"
    if not new_value:
        return False, "No new_value provided for the update"

    try:
        embed_text, cosine_similarity = _get_embeddings()
        load_user_memory, save_user_memory = _get_storage()

        memory = load_user_memory(principal_id)
        facts = memory.get("facts", [])

        if not facts:
            return False, "No memories saved yet — nothing to update."

        # Find best match
        query_embedding = embed_text(query)
        if query_embedding is None:
            return False, "Failed to generate query embedding"

        best_idx = -1
        best_sim = 0.0
        for i, fact in enumerate(facts):
            if fact.get("deleted", False):
                continue
            emb = fact.get("embedding")
            if emb is None:
                continue
            sim = cosine_similarity(query_embedding, np.array(emb))
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_idx < 0 or best_sim < 0.3:
            return False, f"No memory found matching: \"{query}\""

        # Update the fact
        old_text = facts[best_idx]["text"]
        new_embedding = embed_text(new_value)
        facts[best_idx]["text"] = new_value
        if new_embedding is not None:
            facts[best_idx]["embedding"] = new_embedding.tolist()
        facts[best_idx]["last_mentioned"] = int(time.time() * 1000)

        # Optional category/importance update
        new_cat = params.get("category", "").strip().lower()
        if new_cat:
            facts[best_idx]["category"] = new_cat
        new_imp = params.get("importance")
        if new_imp is not None:
            try:
                facts[best_idx]["importance"] = max(1, min(5, int(new_imp)))
            except (ValueError, TypeError):
                pass

        memory["facts"] = facts
        save_user_memory(principal_id, memory)

        return True, f"Updated: \"{old_text}\" → \"{new_value}\" (match: {best_sim:.2f})"

    except Exception as e:
        logger.error(f"update_memory error: {e}")
        return False, f"Failed to update memory: {e}"


def tool_forget_memory(params: Dict, principal_id: str) -> Tuple[bool, str]:
    """
    Soft-delete a fact about the user.

    The fact is marked as deleted — it won't appear in prompts or recall,
    but it's preserved in data exports so the user can review what was
    forgotten. This respects user data ownership.

    Params:
        query: What fact to forget (required)
    """
    query = params.get("query", "").strip()
    if not query:
        return False, "No query provided — what should I forget?"

    try:
        embed_text, cosine_similarity = _get_embeddings()
        load_user_memory, save_user_memory = _get_storage()

        memory = load_user_memory(principal_id)
        facts = memory.get("facts", [])

        if not facts:
            return True, "No memories saved yet — nothing to forget."

        query_embedding = embed_text(query)
        if query_embedding is None:
            return False, "Failed to generate query embedding"

        best_idx = -1
        best_sim = 0.0
        for i, fact in enumerate(facts):
            if fact.get("deleted", False):
                continue
            emb = fact.get("embedding")
            if emb is None:
                continue
            sim = cosine_similarity(query_embedding, np.array(emb))
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_idx < 0 or best_sim < 0.3:
            return False, f"No memory found matching: \"{query}\""

        # Soft delete
        forgotten_text = facts[best_idx]["text"]
        facts[best_idx]["deleted"] = True
        facts[best_idx]["deleted_at"] = int(time.time() * 1000)
        memory["facts"] = facts
        save_user_memory(principal_id, memory)

        return True, f"Forgotten: \"{forgotten_text}\" (match: {best_sim:.2f})"

    except Exception as e:
        logger.error(f"forget_memory error: {e}")
        return False, f"Failed to forget memory: {e}"
