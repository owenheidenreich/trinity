"""
Trinity Backend - Vector Store Service
SQLite-VSS based vector database for RAG and semantic memory
Persists to user's IPFS via Lighthouse for cross-deployment survival
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
from config import CHATS_DIR, RAG_TOP_K

logger = logging.getLogger(__name__)


class VectorStore:
    """
    SQLite-based vector store with VSS extension for semantic search.

    Each user has their own vector database stored in their chat directory.
    The database is synced to IPFS via Lighthouse for persistence across
    Akash redeployments.
    """

    def __init__(self, principal_id: str):
        """
        Initialize vector store for a user.

        Args:
            principal_id: User's principal ID for isolation
        """
        self.principal_id = principal_id
        self.user_dir = Path(CHATS_DIR) / principal_id
        self.db_path = self.user_dir / "vectors.db"
        self.conn = None

        # Ensure user directory exists
        self.user_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with vector tables."""
        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.create_function("cosine_sim", 2, self._cosine_similarity_blob)

            # Try to load VSS extension
            try:
                self.conn.enable_load_extension(True)
                # VSS extension path varies by installation
                # On most systems it's in the Python site-packages
                import sqlite_vss

                sqlite_vss.load(self.conn)
                self._vss_available = True
                logger.info(f"✅ SQLite-VSS loaded for {self.principal_id}")
            except Exception as e:
                logger.warning(f"⚠️ SQLite-VSS not available, using fallback: {e}")
                self._vss_available = False

            # Create tables
            self.conn.executescript(
                """
                -- Document chunks for RAG
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    created_at REAL NOT NULL,
                    UNIQUE(doc_id, chunk_index)
                );
                
                -- Message embeddings for semantic memory
                CREATE TABLE IF NOT EXISTS message_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    timestamp REAL NOT NULL,
                    UNIQUE(chat_id, message_index)
                );
                
                -- Sync metadata
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks(doc_id);
                CREATE INDEX IF NOT EXISTS idx_msg_embed_chat_id ON message_embeddings(chat_id);
            """
            )

            self.conn.commit()
            logger.info(f"📦 Vector store initialized: {self.db_path}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize vector store: {e}")
            raise

    def add_document_chunks(
        self, doc_id: str, filename: str, chunks: List[str], embeddings: List[np.ndarray]
    ) -> bool:
        """
        Add document chunks with embeddings to the store.

        Args:
            doc_id: Unique document identifier
            filename: Original filename
            chunks: List of text chunks
            embeddings: List of embedding vectors

        Returns:
            True on success
        """
        if len(chunks) != len(embeddings):
            logger.error("Chunks and embeddings count mismatch")
            return False

        try:
            cursor = self.conn.cursor()
            now = time.time()

            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                # Store embedding as blob
                embedding_blob = embedding.tobytes() if embedding is not None else None

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO document_chunks 
                    (doc_id, filename, chunk_index, content, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (doc_id, filename, i, chunk, embedding_blob, now),
                )

            self.conn.commit()
            logger.info(f"📄 Added {len(chunks)} chunks for document: {filename}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to add document chunks: {e}")
            return False

    def search_documents(self, query_embedding: np.ndarray, k: int = RAG_TOP_K) -> List[Dict]:
        """
        Search for similar document chunks.

        Args:
            query_embedding: Query vector
            k: Number of results to return

        Returns:
            List of {content, filename, score} dicts
        """
        try:
            query_blob = np.array(query_embedding, dtype=np.float32).tobytes()
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT filename, content, cosine_sim(embedding, ?) AS score
                FROM document_chunks
                WHERE embedding IS NOT NULL
                ORDER BY score DESC
                LIMIT ?
                """,
                (query_blob, int(k)),
            )
            return [
                {
                    "content": row["content"],
                    "filename": row["filename"],
                    "score": float(row["score"] or 0.0),
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"❌ Document search error: {e}")
            return []

    def add_message_embedding(
        self, chat_id: str, message_index: int, role: str, content: str, embedding: np.ndarray
    ) -> bool:
        """
        Add a message embedding for semantic memory retrieval.

        Args:
            chat_id: Chat identifier
            message_index: Position in chat history
            role: 'user' or 'assistant'
            content: Message content
            embedding: Message embedding vector

        Returns:
            True on success
        """
        try:
            cursor = self.conn.cursor()
            embedding_blob = embedding.tobytes() if embedding is not None else None

            cursor.execute(
                """
                INSERT OR REPLACE INTO message_embeddings
                (chat_id, message_index, role, content, embedding, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (chat_id, message_index, role, content, embedding_blob, time.time()),
            )

            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"❌ Failed to add message embedding: {e}")
            return False

    def search_messages(
        self,
        query_embedding: np.ndarray,
        chat_id: str = None,
        k: int = 5,
        recency_weight: float = 0.3,
    ) -> List[Dict]:
        """
        Search for semantically similar messages with recency weighting.

        Args:
            query_embedding: Query vector
            chat_id: Optional filter by chat
            k: Number of results
            recency_weight: Weight for time decay (0-1)

        Returns:
            List of {role, content, score, timestamp} dicts
        """
        try:
            query_blob = np.array(query_embedding, dtype=np.float32).tobytes()
            now = float(time.time())
            max_age = 86400.0 * 7.0
            recency_weight = max(0.0, min(1.0, float(recency_weight)))
            similarity_weight = 1.0 - recency_weight

            cursor = self.conn.cursor()
            if chat_id:
                cursor.execute(
                    """
                    SELECT
                        role,
                        content,
                        timestamp,
                        chat_id,
                        cosine_sim(embedding, ?) AS similarity,
                        (
                            (? * cosine_sim(embedding, ?)) +
                            (? * MAX(0.0, 1.0 - ((? - timestamp) * 1.0 / ?)))
                        ) AS score
                    FROM message_embeddings
                    WHERE chat_id = ? AND embedding IS NOT NULL
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    (
                        query_blob,
                        similarity_weight,
                        query_blob,
                        recency_weight,
                        now,
                        max_age,
                        chat_id,
                        int(k),
                    ),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        role,
                        content,
                        timestamp,
                        chat_id,
                        cosine_sim(embedding, ?) AS similarity,
                        (
                            (? * cosine_sim(embedding, ?)) +
                            (? * MAX(0.0, 1.0 - ((? - timestamp) * 1.0 / ?)))
                        ) AS score
                    FROM message_embeddings
                    WHERE embedding IS NOT NULL
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    (
                        query_blob,
                        similarity_weight,
                        query_blob,
                        recency_weight,
                        now,
                        max_age,
                        int(k),
                    ),
                )

            return [
                {
                    "role": row["role"],
                    "content": row["content"],
                    "score": float(row["score"] or 0.0),
                    "similarity": float(row["similarity"] or 0.0),
                    "timestamp": row["timestamp"],
                    "chat_id": row["chat_id"],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"❌ Message search error: {e}")
            return []

    def get_recent_messages(self, chat_id: str, limit: int = 10) -> List[Dict]:
        """
        Get most recent messages from a chat.

        Args:
            chat_id: Chat identifier
            limit: Maximum messages to return

        Returns:
            List of messages ordered by timestamp
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT role, content, timestamp FROM message_embeddings
                WHERE chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (chat_id, limit),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]

        except Exception as e:
            logger.error(f"❌ Get recent messages error: {e}")
            return []

    def get_chat_messages(
        self,
        chat_id: str,
        start_index: int = 0,
        limit: int = 0,
    ) -> List[Dict]:
        """
        Get chat messages ordered by message_index.

        Args:
            chat_id: Chat identifier
            start_index: Inclusive starting message index
            limit: Optional max rows (0 = no limit)
        """
        try:
            cursor = self.conn.cursor()
            if limit and limit > 0:
                cursor.execute(
                    """
                    SELECT role, content, message_index, timestamp FROM message_embeddings
                    WHERE chat_id = ? AND message_index >= ?
                    ORDER BY message_index ASC
                    LIMIT ?
                """,
                    (chat_id, int(start_index), int(limit)),
                )
            else:
                cursor.execute(
                    """
                    SELECT role, content, message_index, timestamp FROM message_embeddings
                    WHERE chat_id = ? AND message_index >= ?
                    ORDER BY message_index ASC
                """,
                    (chat_id, int(start_index)),
                )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Get chat messages error: {e}")
            return []

    def get_next_message_index(self, chat_id: str) -> int:
        """
        Return the next available message_index for a chat.

        Uses MAX(message_index)+1 so callers without an explicit index do not
        overwrite the (chat_id, message_index) unique key at index 0.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT MAX(message_index) AS max_index
                FROM message_embeddings
                WHERE chat_id = ?
            """,
                (chat_id,),
            )
            row = cursor.fetchone()
            max_index = row["max_index"] if row else None
            if max_index is None:
                return 0
            return int(max_index) + 1
        except Exception as e:
            logger.error(f"❌ Get next message index error: {e}")
            return 0

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    def _cosine_similarity_blob(self, a_blob, b_blob) -> float:
        """SQLite scalar function wrapper for cosine similarity on float32 BLOB vectors."""
        try:
            if not a_blob or not b_blob:
                return 0.0
            a = np.frombuffer(a_blob, dtype=np.float32)
            b = np.frombuffer(b_blob, dtype=np.float32)
            if a.size == 0 or b.size == 0 or a.size != b.size:
                return 0.0
            return self._cosine_similarity(a, b)
        except Exception:
            return 0.0

    def export_for_ipfs(self) -> bytes:
        """
        Export vector database as bytes for IPFS storage.

        Returns:
            Database file contents as bytes
        """
        try:
            # Ensure all changes are committed
            self.conn.commit()

            with open(self.db_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"❌ Export for IPFS failed: {e}")
            return b""

    def import_from_ipfs(self, data: bytes) -> bool:
        """
        Import vector database from IPFS backup.

        Args:
            data: Database file contents

        Returns:
            True on success
        """
        try:
            # Close existing connection
            if self.conn:
                self.conn.close()

            # Write new database
            with open(self.db_path, "wb") as f:
                f.write(data)

            # Reinitialize
            self._init_db()
            logger.info(f"✅ Vector store imported from IPFS")
            return True

        except Exception as e:
            logger.error(f"❌ Import from IPFS failed: {e}")
            return False

    def get_stats(self) -> Dict:
        """Get statistics about the vector store."""
        try:
            cursor = self.conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM document_chunks")
            doc_chunks = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM message_embeddings")
            messages = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(DISTINCT doc_id) as count FROM document_chunks")
            documents = cursor.fetchone()["count"]

            return {
                "documents": documents,
                "document_chunks": doc_chunks,
                "message_embeddings": messages,
                "db_size_bytes": os.path.getsize(self.db_path) if self.db_path.exists() else 0,
            }

        except Exception as e:
            logger.error(f"❌ Stats error: {e}")
            return {}

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


# Cache of vector stores by principal
_vector_stores: Dict[str, VectorStore] = {}


def get_vector_store(principal_id: str) -> VectorStore:
    """
    Get or create a vector store for a user.

    Args:
        principal_id: User's principal ID

    Returns:
        VectorStore instance
    """
    if principal_id not in _vector_stores:
        _vector_stores[principal_id] = VectorStore(principal_id)

    return _vector_stores[principal_id]


# Alias for backwards compatibility
get_user_vector_store = get_vector_store


def close_all_stores():
    """Close all open vector stores (for graceful shutdown)."""
    for store in _vector_stores.values():
        store.close()
    _vector_stores.clear()


# Module availability flag for graceful degradation
V4_VECTOR_STORE_AVAILABLE = True
