"""
Trinity Backend — Context Loader

Single function that replaces the scattered context assembly across
routes/generate.py and services/agent.py. Every request goes through
load_context() regardless of path (direct chat, ReAct, code intent).

Fixes:
  - Five divergent context-loading paths → one function with ContextLevel enum
  - Smalltalk detected three times → evaluated once, passed as result
  - Disclosure detected twice → evaluated once, stored as flag
  - Double query embedding → computed once, reused everywhere
  - Ingestion on lightweight path → only enqueued when level == FULL
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from services.query_classifier import ContextLevel  # canonical location

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request context — everything the pipeline needs
# ---------------------------------------------------------------------------


@dataclass
class RequestContext:
    """
    All context for a single request, loaded once and passed through the pipeline.

    Replaces the scattered variables in generate_agent() and the kwargs dict
    passed to AgentPipeline.process_streaming().
    """

    level: ContextLevel = ContextLevel.FULL
    messages: List[Dict] = field(default_factory=list)
    conversation_summary: str = ""
    last_summarized_id: int = -1
    knowledge_items: list = field(default_factory=list)
    query_embedding: Optional[np.ndarray] = None
    is_disclosure: bool = False
    tools_needed: List[str] = field(default_factory=list)
    search_context: str = ""
    graph_context: Optional[list] = None  # Backwards compat during migration


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------


def load_context(
    store,
    knowledge_store,
    prompt: str,
    chat_id: str,
    principal_id: str,
) -> RequestContext:
    """
    Load all context for a request in one call.

    This is the single entry point for context assembly. It:
    1. Classifies the request (NONE / MINIMAL / FULL)
    2. Loads appropriate data from state_store
    3. Embeds the query once (reused for knowledge search AND profile scoring)
    4. Searches the knowledge store
    5. Detects tools needed

    Args:
        store: PrincipalStateStore for this principal.
        knowledge_store: KnowledgeStore for this principal.
        prompt: The user's current message.
        chat_id: Current chat ID.
        principal_id: Current principal ID.

    Returns:
        RequestContext with all data the pipeline needs.
    """
    from services.query_classifier import (
        classify_context_level,
        is_personal_disclosure,
    )

    ctx = RequestContext()

    # --- Step 1: Classify ---
    ctx.level = classify_context_level(prompt)

    if ctx.level == ContextLevel.NONE:
        return ctx

    # --- Step 2: Load conversation messages ---
    if ctx.level == ContextLevel.MINIMAL:
        try:
            persisted = store.get_messages(chat_id=chat_id, limit=5)
            ctx.messages = [
                {"role": m["role"], "content": m["content"], "message_id": m["message_id"]}
                for m in persisted
            ]
        except Exception as e:
            logger.debug(f"Minimal context load failed: {e}")
        return ctx

    # --- DISCLOSURE path: last 5 messages, no embedding/knowledge ---
    if ctx.level == ContextLevel.DISCLOSURE:
        ctx.is_disclosure = True
        try:
            persisted = store.get_messages(chat_id=chat_id, limit=5)
            ctx.messages = [
                {"role": m["role"], "content": m["content"], "message_id": m["message_id"]}
                for m in persisted
            ]
        except Exception as e:
            logger.debug(f"Disclosure context load failed: {e}")
        return ctx

    # --- FULL path ---

    # Load messages (25 for full context)
    try:
        persisted = store.get_messages(chat_id=chat_id, limit=25)
        ctx.messages = [
            {"role": m["role"], "content": m["content"], "message_id": m["message_id"]}
            for m in persisted
        ]
    except Exception as e:
        logger.warning(f"Context message load failed: {e}")

    # Load conversation summary
    try:
        summaries = store.list_conversation_summaries()
        if isinstance(summaries, dict) and chat_id in summaries:
            summary_record = summaries[chat_id]
            if isinstance(summary_record, dict):
                ctx.conversation_summary = str(summary_record.get("summary", "")).strip()
                try:
                    ctx.last_summarized_id = int(
                        summary_record.get(
                            "last_message_id",
                            summary_record.get("last_summarized_index", -1),
                        )
                    )
                except (TypeError, ValueError):
                    ctx.last_summarized_id = -1
    except Exception as e:
        logger.debug(f"Summary load failed: {e}")

    # Disclosure detection — once
    ctx.is_disclosure = is_personal_disclosure(prompt)

    # Embed query — once, reused for knowledge search
    try:
        from services.embeddings import embed_text

        ctx.query_embedding = embed_text(prompt)
    except Exception as e:
        logger.debug(f"Query embedding failed: {e}")

    # Search knowledge store
    if ctx.query_embedding is not None:
        try:
            ctx.knowledge_items = knowledge_store.search(
                query_embedding=ctx.query_embedding,
                top_k=20,
            )
            logger.info(
                f"📚 Knowledge retrieval: {len(ctx.knowledge_items)} items"
            )
        except Exception as e:
            logger.warning(f"Knowledge search failed: {e}")

    # Detect tools needed
    try:
        from services.tools import detect_tools_needed

        ctx.tools_needed = detect_tools_needed(prompt) or []
    except Exception as e:
        logger.debug(f"Tool detection failed: {e}")

    return ctx
