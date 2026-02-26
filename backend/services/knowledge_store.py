"""
Trinity Backend — Unified Knowledge Store

Single retrieval layer for all persistent knowledge: facts, past messages,
and entity relationships. Replaces the scattered logic across memory.py,
agent.py (formatting), state_store.py (graph search), and memory_tools.py.

Architecture:
  - All knowledge items (facts, messages, relationships) live in one vector index
  - ANN search via sqlite-vec when available, brute-force fallback otherwise
  - Dedup uses KNN query (O(log n)) instead of loading all facts (O(n))
  - Single scoring function: similarity * 0.6 + importance * 0.25 + recency * 0.15
  - Graph triples stored as facts with category="relationship"
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import ARCHIVE_RETRIEVAL_WEIGHT, EMBEDDING_DIM

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEDUP_SKIP_THRESHOLD = 0.95  # Skip — identical fact
DEDUP_MERGE_THRESHOLD = 0.85  # Merge — update existing fact text
KNOWLEDGE_TOP_K = 20  # Default retrieval limit
RECENCY_DECAY_DAYS = 30  # Linear recency decay window

# Scoring weights (unified across all retrieval)
WEIGHT_SIMILARITY = 0.60
WEIGHT_IMPORTANCE = 0.25
WEIGHT_RECENCY = 0.15


class ItemType(str, Enum):
    """Types of knowledge items in the unified store."""

    FACT = "fact"
    MESSAGE = "message"
    RELATIONSHIP = "relationship"


@dataclass
class KnowledgeItem:
    """A scored knowledge item returned from search."""

    item_id: int
    text: str
    category: str
    importance: int
    item_type: ItemType
    similarity_score: float = 0.0
    recency_score: float = 0.0
    combined_score: float = 0.0
    source_chat_id: Optional[str] = None
    created_at: int = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class DedupResult:
    """Result of deduplication check."""

    action: str  # "skip", "merge", "insert"
    existing_fact_id: Optional[int] = None
    similarity: float = 0.0


# ---------------------------------------------------------------------------
# KnowledgeStore
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """
    Unified vector-indexed store for all persistent knowledge.

    Wraps a PrincipalStateStore and provides:
    - search(): single ANN query across facts + messages + relationships
    - save_fact(): embed + dedup via KNN (not full table scan)
    - save_relationship(): store triple as a relationship-category fact
    - index_message(): embed and store for semantic retrieval
    - update_fact() / soft_delete(): standard mutations
    """

    def __init__(self, store):
        """
        Args:
            store: A PrincipalStateStore instance (from state_store.py).
        """
        self.store = store
        self.principal_id = store.principal_id

    # ------------------------------------------------------------------
    # Search — unified retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def _get_source_weight(
        source_chat_id: Optional[str],
        current_chat_id: Optional[str],
    ) -> float:
        """Return a multiplier for cross-conversation demotion.

        Items from the current chat get weight 1.0.
        Items from other chats get ``ARCHIVE_RETRIEVAL_WEIGHT`` (default 0.6).
        Items without a source chat (e.g. global facts) are unpenalised.
        """
        if current_chat_id is None or source_chat_id is None:
            return 1.0
        if source_chat_id == current_chat_id:
            return 1.0
        return ARCHIVE_RETRIEVAL_WEIGHT

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = KNOWLEDGE_TOP_K,
        item_types: Optional[List[ItemType]] = None,
        category_filter: Optional[str] = None,
        current_chat_id: Optional[str] = None,
    ) -> List[KnowledgeItem]:
        """
        Search all knowledge items by embedding similarity.

        Uses sqlite-vec ANN when available, falls back to brute-force.

        Args:
            query_embedding: 384-dim query vector.
            top_k: Maximum results to return.
            item_types: Filter by item type (default: all types).
            category_filter: Filter by category (optional).
            current_chat_id: Active chat — items from other chats are demoted.

        Returns:
            List of KnowledgeItem sorted by combined_score descending.
        """
        from services.db import SQLITE_VEC_AVAILABLE

        if SQLITE_VEC_AVAILABLE:
            return self._search_vec(query_embedding, top_k, item_types, category_filter, current_chat_id)
        return self._search_brute_force(query_embedding, top_k, item_types, category_filter, current_chat_id)

    def _search_vec(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        item_types: Optional[List[ItemType]],
        category_filter: Optional[str],
        current_chat_id: Optional[str] = None,
    ) -> List[KnowledgeItem]:
        """ANN search via sqlite-vec vec0 virtual table."""
        blob = np.array(query_embedding, dtype=np.float32).tobytes()
        now_ms = int(time.time() * 1000)

        # Fetch more than top_k from ANN to allow post-filtering + re-scoring
        fetch_k = min(top_k * 3, 100)

        try:
            with self.store._lock:
                rows = self.store.conn.execute(
                    """
                    SELECT v.item_id, v.item_type, v.category, v.distance
                    FROM vec_knowledge v
                    WHERE v.embedding MATCH ? AND v.k = ?
                      AND v.principal_id = ?
                    """,
                    (blob, fetch_k, self.principal_id),
                ).fetchall()
        except Exception as e:
            logger.warning(f"vec search failed, falling back to brute-force: {e}")
            return self._search_brute_force(query_embedding, top_k, item_types, category_filter)

        if not rows:
            return []

        # Post-filter and score
        items = []
        for row in rows:
            item_type_str = row["item_type"]
            if item_types and item_type_str not in [t.value for t in item_types]:
                continue
            if category_filter and row["category"] != category_filter:
                continue

            # sqlite-vec returns distance (lower = closer), convert to similarity
            distance = float(row["distance"])
            similarity = max(0.0, 1.0 - distance)

            # Look up the full item from the appropriate table
            item = self._hydrate_item(
                int(row["item_id"]),
                ItemType(item_type_str),
                similarity,
                now_ms,
                current_chat_id=current_chat_id,
            )
            if item:
                items.append(item)

        items.sort(key=lambda x: x.combined_score, reverse=True)
        return items[:top_k]

    def _search_brute_force(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        item_types: Optional[List[ItemType]],
        category_filter: Optional[str],
        current_chat_id: Optional[str] = None,
    ) -> List[KnowledgeItem]:
        """Brute-force cosine similarity search (fallback when sqlite-vec unavailable)."""
        from services.embeddings import cosine_similarity

        now_ms = int(time.time() * 1000)
        items = []

        # Search facts
        if not item_types or ItemType.FACT in item_types or ItemType.RELATIONSHIP in item_types:
            facts = self.store.list_facts(
                include_deleted=False, include_invalid=False, with_embeddings=True
            )
            for fact in facts:
                if category_filter and fact.get("category") != category_filter:
                    continue

                fact_type = ItemType.RELATIONSHIP if fact.get("category") == "relationship" else ItemType.FACT
                if item_types and fact_type not in item_types:
                    continue

                embedding = fact.get("embedding")
                if not embedding:
                    continue

                fact_vec = np.array(embedding, dtype=np.float32)
                similarity = cosine_similarity(query_embedding, fact_vec)

                sw = self._get_source_weight(
                    fact.get("source_chat_id"), current_chat_id
                )
                item = self._score_item(
                    item_id=fact["fact_id"],
                    text=fact.get("text", ""),
                    category=fact.get("category", "general"),
                    importance=fact.get("importance", 3),
                    item_type=fact_type,
                    similarity=similarity,
                    created_at=fact.get("created_at", 0),
                    now_ms=now_ms,
                    source_weight=sw,
                    source_chat_id=fact.get("source_chat_id"),
                )
                items.append(item)

        # Search message embeddings
        if not item_types or ItemType.MESSAGE in item_types:
            try:
                msg_results = self.store.search_message_embeddings(
                    query_embedding=query_embedding,
                    k=top_k * 2,
                    recency_weight=WEIGHT_RECENCY,
                )
                for msg in msg_results:
                    sw = self._get_source_weight(
                        msg.get("chat_id"), current_chat_id
                    )
                    item = self._score_item(
                        item_id=msg.get("message_id", 0),
                        text=msg.get("content", ""),
                        category="conversation",
                        importance=2,
                        item_type=ItemType.MESSAGE,
                        similarity=msg.get("similarity", 0),
                        created_at=msg.get("timestamp", 0),
                        now_ms=now_ms,
                        source_weight=sw,
                        source_chat_id=msg.get("chat_id"),
                    )
                    items.append(item)
            except Exception as e:
                logger.debug(f"Message embedding search failed: {e}")

        items.sort(key=lambda x: x.combined_score, reverse=True)
        return items[:top_k]

    def _hydrate_item(
        self,
        item_id: int,
        item_type: ItemType,
        similarity: float,
        now_ms: int,
        current_chat_id: Optional[str] = None,
    ) -> Optional[KnowledgeItem]:
        """Look up full item data from the source table."""
        if item_type in (ItemType.FACT, ItemType.RELATIONSHIP):
            fact = self.store.get_fact(item_id)
            if not fact:
                return None
            if fact.get("deleted_at") or fact.get("invalid_at"):
                return None
            sw = self._get_source_weight(
                fact.get("source_chat_id"), current_chat_id
            )
            return self._score_item(
                item_id=item_id,
                text=fact.get("text", ""),
                category=fact.get("category", "general"),
                importance=fact.get("importance", 3),
                item_type=item_type,
                similarity=similarity,
                created_at=fact.get("created_at", 0),
                now_ms=now_ms,
                source_weight=sw,
                source_chat_id=fact.get("source_chat_id"),
            )

        if item_type == ItemType.MESSAGE:
            # For messages, we need to look up from the messages table
            try:
                with self.store._lock:
                    row = self.store.conn.execute(
                        "SELECT content_enc, chat_id, role, created_at FROM messages WHERE message_id = ?",
                        (item_id,),
                    ).fetchone()
                if not row:
                    return None
                content = self.store._decrypt_text(row["content_enc"])
                sw = self._get_source_weight(row["chat_id"], current_chat_id)
                return self._score_item(
                    item_id=item_id,
                    text=content,
                    category="conversation",
                    importance=2,
                    item_type=ItemType.MESSAGE,
                    similarity=similarity,
                    created_at=int(row["created_at"]),
                    now_ms=now_ms,
                    source_weight=sw,
                    source_chat_id=row["chat_id"],
                )
            except Exception:
                return None

        return None

    @staticmethod
    def _score_item(
        item_id: int,
        text: str,
        category: str,
        importance: int,
        item_type: ItemType,
        similarity: float,
        created_at: int,
        now_ms: int,
        source_chat_id: Optional[str] = None,
        source_weight: float = 1.0,
    ) -> KnowledgeItem:
        """Unified scoring: (sim×0.6 + importance×0.25 + recency×0.15) × source_weight.

        Every retrieval path — ANN, brute-force facts, brute-force messages —
        MUST call this function.  No direct ``KnowledgeItem`` construction
        outside this method.  This is the single scoring function.

        ``source_weight`` (default 1.0) demotes cross-conversation items via
        ``ARCHIVE_RETRIEVAL_WEIGHT`` when the item originates from a different
        chat than the one currently active.
        """
        age_days = max(0.0, (now_ms - created_at) / (1000 * 86400))
        recency = max(0.0, 1.0 - (age_days / RECENCY_DECAY_DAYS))
        importance_norm = min(1.0, importance / 5.0)

        combined = (
            WEIGHT_SIMILARITY * similarity
            + WEIGHT_IMPORTANCE * importance_norm
            + WEIGHT_RECENCY * recency
        )
        combined *= source_weight

        return KnowledgeItem(
            item_id=item_id,
            text=text,
            category=category,
            importance=importance,
            item_type=item_type,
            similarity_score=round(similarity, 4),
            recency_score=round(recency, 4),
            combined_score=round(combined, 4),
            source_chat_id=source_chat_id,
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Save fact — with O(log n) dedup via KNN
    # ------------------------------------------------------------------

    def save_fact(
        self,
        text: str,
        category: str = "general",
        importance: int = 3,
        source_message_id: Optional[int] = None,
    ) -> Tuple[str, Optional[int]]:
        """
        Save a fact with embedding-based deduplication.

        Returns:
            Tuple of (action, fact_id) where action is "skip", "merge", or "insert".
        """
        from services.embeddings import embed_text

        text = (text or "").strip()
        if not text:
            return ("skip", None)

        embedding = embed_text(text)
        if embedding is None:
            logger.warning("Failed to embed fact — saving without dedup")
            fact_id = self._insert_fact_raw(text, category, importance, source_message_id)
            return ("insert", fact_id)

        # Dedup check via KNN (top 3 nearest facts)
        dedup = self._check_dedup(embedding, category)

        if dedup.action == "skip":
            logger.debug(f"Fact dedup: skip (sim={dedup.similarity:.3f})")
            return ("skip", dedup.existing_fact_id)

        if dedup.action == "merge" and dedup.existing_fact_id is not None:
            logger.debug(f"Fact dedup: merge into {dedup.existing_fact_id} (sim={dedup.similarity:.3f})")
            self._merge_fact(dedup.existing_fact_id, text, embedding, importance)
            return ("merge", dedup.existing_fact_id)

        # Insert new fact
        fact_id = self._insert_fact(text, category, importance, source_message_id, embedding)
        return ("insert", fact_id)

    def _check_dedup(self, embedding: np.ndarray, category: str) -> DedupResult:
        """Check if a fact is a duplicate using KNN search."""
        from services.db import SQLITE_VEC_AVAILABLE

        if SQLITE_VEC_AVAILABLE:
            return self._check_dedup_vec(embedding)
        return self._check_dedup_brute_force(embedding)

    def _check_dedup_vec(self, embedding: np.ndarray) -> DedupResult:
        """KNN dedup via sqlite-vec — O(log n)."""
        blob = np.array(embedding, dtype=np.float32).tobytes()

        try:
            with self.store._lock:
                rows = self.store.conn.execute(
                    """
                    SELECT v.item_id, v.distance
                    FROM vec_knowledge v
                    WHERE v.embedding MATCH ? AND v.k = 3
                      AND v.principal_id = ?
                      AND v.item_type IN ('fact', 'relationship')
                    """,
                    (blob, self.principal_id),
                ).fetchall()
        except Exception:
            return DedupResult(action="insert")

        if not rows:
            return DedupResult(action="insert")

        best = rows[0]
        similarity = max(0.0, 1.0 - float(best["distance"]))

        if similarity >= DEDUP_SKIP_THRESHOLD:
            # Verify the fact is still active — a deleted fact must not
            # block re-insertion of the same content.
            fact = self.store.get_fact(int(best["item_id"]))
            if fact and not fact.get("deleted_at") and not fact.get("invalid_at"):
                return DedupResult(
                    action="skip",
                    existing_fact_id=int(best["item_id"]),
                    similarity=similarity,
                )

        if similarity >= DEDUP_MERGE_THRESHOLD:
            # Verify the fact is still active
            fact = self.store.get_fact(int(best["item_id"]))
            if fact and not fact.get("deleted_at") and not fact.get("invalid_at"):
                return DedupResult(
                    action="merge",
                    existing_fact_id=int(best["item_id"]),
                    similarity=similarity,
                )

        return DedupResult(action="insert")

    def _check_dedup_brute_force(self, embedding: np.ndarray) -> DedupResult:
        """Brute-force dedup fallback — load active facts with embeddings."""
        from services.embeddings import cosine_similarity

        facts = self.store.list_facts(
            include_deleted=False, include_invalid=False, with_embeddings=True
        )

        best_sim = 0.0
        best_fact_id = None

        for fact in facts:
            fact_emb = fact.get("embedding")
            if not fact_emb:
                continue
            fact_vec = np.array(fact_emb, dtype=np.float32)
            sim = cosine_similarity(embedding, fact_vec)
            if sim > best_sim:
                best_sim = sim
                best_fact_id = fact.get("fact_id")

        if best_sim >= DEDUP_SKIP_THRESHOLD:
            return DedupResult(action="skip", existing_fact_id=best_fact_id, similarity=best_sim)
        if best_sim >= DEDUP_MERGE_THRESHOLD and best_fact_id is not None:
            return DedupResult(action="merge", existing_fact_id=best_fact_id, similarity=best_sim)
        return DedupResult(action="insert")

    def _insert_fact(
        self,
        text: str,
        category: str,
        importance: int,
        source_message_id: Optional[int],
        embedding: np.ndarray,
    ) -> int:
        """Insert a new fact and its embedding."""
        fact_id = self.store.create_fact(
            text=text,
            category=category,
            importance=importance,
            source_message_id=source_message_id,
        )
        # Store embedding
        self._store_fact_embedding(fact_id, embedding)
        # Index in vec_knowledge
        self._index_in_vec(fact_id, ItemType.FACT if category != "relationship" else ItemType.RELATIONSHIP, embedding, category)
        return fact_id

    def _insert_fact_raw(
        self,
        text: str,
        category: str,
        importance: int,
        source_message_id: Optional[int],
    ) -> int:
        """Insert a fact without embedding (fallback)."""
        return self.store.create_fact(
            text=text,
            category=category,
            importance=importance,
            source_message_id=source_message_id,
        )

    def _merge_fact(
        self,
        fact_id: int,
        new_text: str,
        new_embedding: np.ndarray,
        importance: int,
    ):
        """Update an existing fact with newer, more specific text."""
        self.store.update_fact(fact_id, {"text": new_text, "importance": importance})
        self._store_fact_embedding(fact_id, new_embedding)
        # Update vec index
        fact = self.store.get_fact(fact_id)
        category = fact.get("category", "general") if fact else "general"
        item_type = ItemType.RELATIONSHIP if category == "relationship" else ItemType.FACT
        self._update_vec_index(fact_id, item_type, new_embedding, category)

    def _store_fact_embedding(self, fact_id: int, embedding: np.ndarray):
        """Store embedding in the embeddings_facts table."""
        blob = np.array(embedding, dtype=np.float32).tobytes()
        try:
            with self.store._lock:
                self.store.conn.execute(
                    "INSERT OR REPLACE INTO embeddings_facts (fact_id, principal_id, vector) VALUES (?, ?, ?)",
                    (fact_id, self.principal_id, blob),
                )
                self.store.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to store fact embedding: {e}")

    # ------------------------------------------------------------------
    # Save relationship — triple as a fact
    # ------------------------------------------------------------------

    def save_relationship(
        self,
        subject: str,
        predicate: str,
        obj: str,
        source_message_id: Optional[int] = None,
    ) -> Tuple[str, Optional[int]]:
        """
        Store a knowledge graph triple as a relationship-category fact.

        The triple is formatted as "subject predicate object" and receives
        the same embedding + dedup treatment as any other fact.
        """
        text = f"{subject} {predicate} {obj}".strip()
        if not text or len(text) < 5:
            return ("skip", None)

        return self.save_fact(
            text=text,
            category="relationship",
            importance=3,
            source_message_id=source_message_id,
        )

    # ------------------------------------------------------------------
    # Index message — for semantic retrieval
    # ------------------------------------------------------------------

    def index_message(
        self,
        chat_id: str,
        message_id: int,
        role: str,
        content: str,
    ) -> bool:
        """
        Embed and index a message for later semantic retrieval.

        Stores in both embeddings_messages (legacy) and vec_knowledge (new).
        """
        from services.embeddings import embed_text

        content_for_embedding = content[:2000] if len(content) > 2000 else content
        embedding = embed_text(content_for_embedding)
        if embedding is None:
            return False

        # Legacy: store in embeddings_messages
        success = self.store.set_message_embedding(message_id=message_id, embedding=embedding)

        # New: index in vec_knowledge
        self._index_in_vec(message_id, ItemType.MESSAGE, embedding, "conversation")

        return success

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def update_fact(
        self,
        fact_id: int,
        new_text: str,
        importance: Optional[int] = None,
    ) -> bool:
        """Update a fact's text and re-embed."""
        from services.embeddings import embed_text

        kwargs = {"text": new_text}
        if importance is not None:
            kwargs["importance"] = importance

        success = self.store.update_fact(fact_id, kwargs)
        if not success:
            return False

        # Re-embed
        embedding = embed_text(new_text)
        if embedding is not None:
            self._store_fact_embedding(fact_id, embedding)
            fact = self.store.get_fact(fact_id)
            category = fact.get("category", "general") if fact else "general"
            item_type = ItemType.RELATIONSHIP if category == "relationship" else ItemType.FACT
            self._update_vec_index(fact_id, item_type, embedding, category)

        return True

    def soft_delete(self, fact_id: int) -> bool:
        """Soft-delete a fact (sets deleted_at, preserves for audit).

        Also removes the embedding from vec_knowledge so ANN search
        no longer returns deleted items.
        """
        success = self.store.soft_delete_fact(fact_id)
        if success:
            from services.db import SQLITE_VEC_AVAILABLE

            if SQLITE_VEC_AVAILABLE:
                try:
                    with self.store._lock:
                        self.store.conn.execute(
                            "DELETE FROM vec_knowledge WHERE item_id = ? AND principal_id = ?",
                            (fact_id, self.principal_id),
                        )
                        self.store.conn.commit()
                except Exception:
                    pass  # vec table may not exist yet
        return success

    # ------------------------------------------------------------------
    # Vec index management
    # ------------------------------------------------------------------

    def _index_in_vec(
        self,
        item_id: int,
        item_type: ItemType,
        embedding: np.ndarray,
        category: str,
    ):
        """Insert into the vec_knowledge virtual table."""
        from services.db import SQLITE_VEC_AVAILABLE

        if not SQLITE_VEC_AVAILABLE:
            return

        blob = np.array(embedding, dtype=np.float32).tobytes()
        try:
            with self.store._lock:
                self.store.conn.execute(
                    """
                    INSERT INTO vec_knowledge (embedding, item_id, item_type, principal_id, category)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (blob, item_id, item_type.value, self.principal_id, category),
                )
                self.store.conn.commit()
        except Exception as e:
            logger.debug(f"vec_knowledge insert failed: {e}")

    def _update_vec_index(
        self,
        item_id: int,
        item_type: ItemType,
        embedding: np.ndarray,
        category: str,
    ):
        """Update an item in the vec_knowledge virtual table (delete + re-insert)."""
        from services.db import SQLITE_VEC_AVAILABLE

        if not SQLITE_VEC_AVAILABLE:
            return

        try:
            with self.store._lock:
                self.store.conn.execute(
                    "DELETE FROM vec_knowledge WHERE item_id = ? AND item_type = ? AND principal_id = ?",
                    (item_id, item_type.value, self.principal_id),
                )
                self.store.conn.commit()
        except Exception:
            pass

        self._index_in_vec(item_id, item_type, embedding, category)

    # ------------------------------------------------------------------
    # Convenience: get all active facts (for API / export)
    # ------------------------------------------------------------------

    def get_active_facts(self) -> List[Dict]:
        """Return all active (non-deleted, non-invalidated) facts."""
        return self.store.list_facts(include_deleted=False, include_invalid=False)

    def get_all_facts(self) -> List[Dict]:
        """Return all facts including deleted/invalid (for API responses)."""
        return self.store.list_facts(include_deleted=True, include_invalid=True)


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

_stores: Dict[str, KnowledgeStore] = {}
_stores_lock = __import__("threading").Lock()


def get_knowledge_store(principal_id: str) -> KnowledgeStore:
    """Get or create a KnowledgeStore for a principal."""
    store = _stores.get(principal_id)
    if store is not None:
        return store
    with _stores_lock:
        store = _stores.get(principal_id)
        if store is None:
            from services.state_store import get_state_store

            state_store = get_state_store(principal_id)
            store = KnowledgeStore(state_store)
            _stores[principal_id] = store
        return store


def reset_knowledge_stores():
    """Clear all cached stores. For testing."""
    with _stores_lock:
        _stores.clear()
