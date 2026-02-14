"""
Trinity Backend - Semantic Memory Service
Hierarchical memory retrieval with semantic search and recency weighting
"""

import logging
from typing import Dict, List

from config import RECENCY_WEIGHT, SEMANTIC_MEMORY_SIZE, WORKING_MEMORY_SIZE
from services.embeddings import embed_batch, embed_text
from services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class SemanticMemory:
    """
    Hierarchical memory system combining:
    - Working memory: Most recent messages (always included)
    - Semantic memory: Relevant past messages (retrieved by similarity)
    - User memory: Persistent facts (stored separately)

    This replaces the fixed 6-message window with intelligent retrieval.
    """

    def __init__(self, principal_id: str):
        """
        Initialize semantic memory for a user.

        Args:
            principal_id: User's principal ID
        """
        self.principal_id = principal_id
        self.vector_store = get_vector_store(principal_id)

    def index_message(self, chat_id: str, message_index: int, role: str, content: str) -> bool:
        """
        Index a message for future retrieval.

        Should be called after each message is added to chat history.

        Args:
            chat_id: Chat identifier
            message_index: Position in chat (0-indexed)
            role: 'user' or 'assistant'
            content: Message text

        Returns:
            True on success
        """
        # Truncate very long messages for embedding
        content_for_embedding = content[:2000] if len(content) > 2000 else content

        embedding = embed_text(content_for_embedding)
        if embedding is None:
            logger.warning(f"Failed to embed message {message_index} in chat {chat_id}")
            return False

        return self.vector_store.add_message_embedding(
            chat_id=chat_id,
            message_index=message_index,
            role=role,
            content=content,
            embedding=embedding,
        )

    def index_chat_history(self, chat_id: str, messages: List[Dict]) -> int:
        """
        Bulk index all messages in a chat history.

        Used when loading a chat for the first time or recovering from IPFS.

        Args:
            chat_id: Chat identifier
            messages: List of {role, content} dicts

        Returns:
            Number of successfully indexed messages
        """
        if not messages:
            return 0

        indexed = 0

        # Batch embed for efficiency
        contents = [m.get("content", "")[:2000] for m in messages]
        embeddings = embed_batch(contents)

        if len(embeddings) != len(messages):
            logger.warning("Embedding batch size mismatch, falling back to individual")
            for i, msg in enumerate(messages):
                if self.index_message(chat_id, i, msg.get("role", "user"), msg.get("content", "")):
                    indexed += 1
            return indexed

        # Store all embeddings
        for i, (msg, embedding) in enumerate(zip(messages, embeddings)):
            if self.vector_store.add_message_embedding(
                chat_id=chat_id,
                message_index=i,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                embedding=embedding,
            ):
                indexed += 1

        logger.info(f"📝 Indexed {indexed}/{len(messages)} messages for chat {chat_id}")
        return indexed

    def retrieve_context(
        self,
        query: str,
        chat_id: str = None,
        working_memory_size: int = WORKING_MEMORY_SIZE,
        semantic_memory_size: int = SEMANTIC_MEMORY_SIZE,
    ) -> Dict:
        """
        Retrieve relevant context for a query.

        Combines:
        1. Working memory: Last N messages from current chat
        2. Semantic memory: Top-K similar messages from all chats

        Args:
            query: Current user query
            chat_id: Current chat ID (for working memory)
            working_memory_size: Number of recent messages to include
            semantic_memory_size: Number of semantic matches to include

        Returns:
            Dict with 'working_memory', 'semantic_memory', and 'combined' lists
        """
        result = {"working_memory": [], "semantic_memory": [], "combined": []}

        # Get working memory (most recent messages from this chat)
        if chat_id:
            result["working_memory"] = self.vector_store.get_recent_messages(
                chat_id, limit=working_memory_size
            )

        # Get semantic memory (similar messages across all chats)
        query_embedding = embed_text(query)
        if query_embedding is not None:
            # Retrieve more than needed to filter duplicates with working memory
            semantic_results = self.vector_store.search_messages(
                query_embedding=query_embedding,
                chat_id=None,  # Search all chats
                k=semantic_memory_size * 2,  # Get extras for deduplication
                recency_weight=RECENCY_WEIGHT,
            )

            # Filter out messages already in working memory
            working_contents = {m["content"] for m in result["working_memory"]}

            for msg in semantic_results:
                if msg["content"] not in working_contents:
                    result["semantic_memory"].append(msg)
                    if len(result["semantic_memory"]) >= semantic_memory_size:
                        break

        # Combine: working memory first (chronological), then semantic (by relevance)
        result["combined"] = result["working_memory"] + result["semantic_memory"]

        return result

    def format_context_for_prompt(self, context: Dict) -> str:
        """
        Format retrieved context for inclusion in LLM prompt.

        Args:
            context: Output from retrieve_context()

        Returns:
            Formatted string for prompt
        """
        parts = []

        # Working memory (recent conversation)
        if context.get("working_memory"):
            parts.append("[Recent Conversation]")
            for msg in context["working_memory"]:
                role = "User" if msg["role"] == "user" else "Assistant"
                content = msg["content"][:500]  # Truncate for prompt
                parts.append(f"{role}: {content}")

        # Semantic memory (relevant past messages)
        if context.get("semantic_memory"):
            parts.append("\n[Relevant Past Context]")
            for msg in context["semantic_memory"]:
                role = "User" if msg["role"] == "user" else "Assistant"
                content = msg["content"][:300]  # Shorter for semantic matches
                score = msg.get("score", 0)
                parts.append(f"{role} (relevance: {score:.2f}): {content}")

        return "\n".join(parts)

    def get_stats(self) -> Dict:
        """Get memory statistics."""
        return self.vector_store.get_stats()


# Cache of semantic memory instances by principal
_memory_instances: Dict[str, SemanticMemory] = {}


def get_semantic_memory(principal_id: str) -> SemanticMemory:
    """
    Get or create semantic memory for a user.

    Args:
        principal_id: User's principal ID

    Returns:
        SemanticMemory instance
    """
    if principal_id not in _memory_instances:
        _memory_instances[principal_id] = SemanticMemory(principal_id)

    return _memory_instances[principal_id]


def build_enhanced_context(
    query: str,
    principal_id: str,
    chat_id: str = None,
    context_messages: List[Dict] = None,
    user_memory: Dict = None,
    recent_messages: List[Dict] = None,
) -> tuple:
    """
    Build enhanced context for LLM prompt using semantic retrieval.

    This is the main entry point for the enhanced memory system.
    Falls back gracefully if semantic memory is unavailable.

    Args:
        query: Current user query
        principal_id: User's principal ID
        chat_id: Current chat ID
        context_messages: Fallback messages if semantic retrieval fails
        user_memory: User's persistent memory (facts, preferences)
        recent_messages: Alias for context_messages (backward compat)

    Returns:
        Tuple of (enhanced_context_messages, semantic_summary_or_None)
    """
    # Support both param names for backward compatibility
    fallback_messages = context_messages or recent_messages or []
    semantic_items = None

    try:
        memory = get_semantic_memory(principal_id)
        context = memory.retrieve_context(query, chat_id)

        if context["semantic_memory"]:
            semantic_items = context["semantic_memory"]
            logger.info(f"📚 Semantic retrieval: {len(semantic_items)} items")

    except Exception as e:
        logger.warning(f"Semantic memory retrieval failed, using fallback: {e}")

    return fallback_messages, semantic_items


# Module availability flag for graceful degradation
V4_MEMORY_AVAILABLE = True
