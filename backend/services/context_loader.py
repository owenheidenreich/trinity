"""
Trinity Backend — Context Loader

Single function that replaces the scattered context assembly across
routes/generate.py and services/agent.py. Every request goes through
load_context() regardless of path (direct chat, ReAct, code intent).

Design: Every query gets full context (messages, knowledge, embedding,
tool detection). The tiny classifier's only remaining job is tool
detection (in tools.py). The LLM handles everything else naturally.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from config import (
    ARCHIVED_CONTEXT_SIZE,
    CROSS_CONVERSATION_MAX_CHATS,
    CROSS_CONVERSATION_SUMMARY_BUDGET,
)

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

    messages: List[Dict] = field(default_factory=list)
    conversation_summary: str = ""
    last_summarized_id: int = -1
    knowledge_items: list = field(default_factory=list)
    query_embedding: Optional[np.ndarray] = None
    is_disclosure: bool = False
    tools_needed: List[str] = field(default_factory=list)
    temperature: float = 0.7
    search_context: str = ""
    graph_context: Optional[list] = None  # Backwards compat during migration
    injection_detected: bool = False
    # Tiered memory — cross-conversation awareness
    cross_conversation_summaries: List[Dict] = field(default_factory=list)
    is_archived_chat: bool = False
    ctx_budget: int = 0  # reduced context budget for archived chats (0 = unlimited)


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------


def _extract_summary(summaries_map: dict, chat_id: str) -> tuple:
    """Extract (summary_text, last_message_id) from the summaries map for one chat.

    Pure helper — no side-effects, no logging, no I/O.
    """
    if not isinstance(summaries_map, dict) or chat_id not in summaries_map:
        return "", -1
    rec = summaries_map[chat_id]
    if isinstance(rec, dict):
        text = str(rec.get("summary", "")).strip()
        try:
            last_id = int(
                rec.get("last_message_id", rec.get("last_summarized_index", -1))
            )
        except (TypeError, ValueError):
            last_id = -1
        return text, last_id
    if isinstance(rec, str):
        return rec.strip(), -1
    return "", -1


def _collect_cross_conversation_summaries(
    all_chats: List[Dict],
    summaries_map: dict,
    current_chat_id: str,
    max_chats: int,
    char_budget: int,
) -> List[Dict]:
    """Build the cross-conversation summary list.

    Pure function: takes data in, returns data out.  No store access.
    Mirrors microgpt's composable-helper pattern (``linear``, ``softmax``, ``rmsnorm``).
    """
    results: List[Dict] = []
    for chat in all_chats:
        if len(results) >= max_chats:
            break
        cid = chat.get("chatId", "")
        if cid == current_chat_id:
            continue
        text, _ = _extract_summary(summaries_map, cid)
        if not text:
            continue
        results.append({
            "chat_id": cid,
            "title": chat.get("title", "Untitled"),
            "summary": text[:char_budget],
        })
    return results


def load_context(
    store,
    knowledge_store,
    prompt: str,
    chat_id: str,
    principal_id: str,
) -> RequestContext:
    """
    Load all context for a request in one call.

    Every query gets the same treatment:
    1. Load conversation messages (last 25)
    2. Load conversation summary
    3. Detect personal disclosure (for memory filtering)
    4. Embed the query (reused for knowledge search)
    5. Search the knowledge store
    6. Detect tools needed
    7. Compute temperature (code=0.1, tools=0.3, else=0.7)

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
        is_personal_disclosure,
    )

    ctx = RequestContext()

    # --- Load conversation summaries (once — reused for current and cross-conv) ---
    summaries_map: dict = {}
    try:
        summaries_map = store.list_conversation_summaries() or {}
    except Exception as e:
        logger.debug(f"Summary load failed: {e}")

    # --- Load conversation messages (25 for full context) ---
    try:
        persisted = store.get_messages(chat_id=chat_id, limit=25)
        ctx.messages = [
            {"role": m["role"], "content": m["content"], "message_id": m["message_id"]}
            for m in persisted
        ]
    except Exception as e:
        logger.warning(f"Context message load failed: {e}")

    # --- Current chat's conversation summary ---
    ctx.conversation_summary, ctx.last_summarized_id = _extract_summary(
        summaries_map, chat_id
    )

    # --- Disclosure detection — once ---
    ctx.is_disclosure = is_personal_disclosure(prompt)

    # --- Embed query — once, reused for knowledge search ---
    try:
        from services.embeddings import embed_text

        ctx.query_embedding = embed_text(prompt)
    except Exception as e:
        logger.debug(f"Query embedding failed: {e}")

    # --- Search knowledge store ---
    if ctx.query_embedding is not None:
        try:
            ctx.knowledge_items = knowledge_store.search(
                query_embedding=ctx.query_embedding,
                top_k=20,
                current_chat_id=chat_id,
            )
            logger.info(
                f"📚 Knowledge retrieval: {len(ctx.knowledge_items)} items"
            )
        except Exception as e:
            logger.warning(f"Knowledge search failed: {e}")

    # --- Detect tools needed ---
    try:
        from services.tools import detect_tools_needed

        ctx.tools_needed = detect_tools_needed(prompt) or []
    except Exception as e:
        logger.debug(f"Tool detection failed: {e}")

    # --- Compute temperature ---
    try:
        from services.query_classifier import classify_temperature

        ctx.temperature = classify_temperature(
            prompt, tools_needed=ctx.tools_needed
        )
    except Exception as e:
        logger.debug(f"Temperature classification failed: {e}")

    # --- Injection detection (ByteTransformer, <1ms) ---
    try:
        from services.tiny_classifier import detect_injection

        is_injection, confidence = detect_injection(prompt)
        ctx.injection_detected = is_injection
        if is_injection:
            logger.warning(
                "Injection detected (conf=%.3f), pipeline will refuse",
                confidence,
            )
    except Exception as e:
        logger.debug(f"Injection detection failed: {e}")

    # --- Cross-conversation summaries & archived-chat detection ---
    try:
        chat_meta = store.get_chat(chat_id)
        if chat_meta and chat_meta.get("archived"):
            ctx.is_archived_chat = True
            ctx.ctx_budget = ARCHIVED_CONTEXT_SIZE

        all_chats = store.list_chats(
            include_archived=True, limit=CROSS_CONVERSATION_MAX_CHATS + 1
        )
        ctx.cross_conversation_summaries = _collect_cross_conversation_summaries(
            all_chats=all_chats,
            summaries_map=summaries_map,
            current_chat_id=chat_id,
            max_chats=CROSS_CONVERSATION_MAX_CHATS,
            char_budget=CROSS_CONVERSATION_SUMMARY_BUDGET * 4,  # chars, not tokens
        )
    except Exception as e:
        logger.debug(f"Cross-conversation summary load failed: {e}")

    return ctx
