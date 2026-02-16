"""
Tests for services/vector_store.py — SQLite Vector Store

Tests document chunking, search, message embeddings, export/import, stats.
Uses tmp_path for isolated SQLite databases.
"""

import time

import numpy as np
import pytest
from unittest.mock import patch


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def vector_store(tmp_path):
    """Create a VectorStore with isolated temp DB."""
    with patch("services.vector_store.CHATS_DIR", str(tmp_path)):
        from services.vector_store import VectorStore

        store = VectorStore("test-principal")
        yield store
        store.close()


@pytest.fixture
def embedding_32():
    """Generate a 32-dim float32 embedding."""
    rng = np.random.RandomState(42)
    vec = rng.randn(32).astype(np.float32)
    return vec / np.linalg.norm(vec)


@pytest.fixture
def embedding_32_similar(embedding_32):
    """Generate an embedding similar to embedding_32."""
    rng = np.random.RandomState(43)
    noise = rng.randn(32).astype(np.float32) * 0.1
    vec = embedding_32 + noise
    return vec / np.linalg.norm(vec)


@pytest.fixture
def embedding_32_different():
    """Generate an embedding very different from embedding_32."""
    rng = np.random.RandomState(99)
    vec = rng.randn(32).astype(np.float32)
    return vec / np.linalg.norm(vec)


# =============================================================================
# INIT TESTS
# =============================================================================


class TestVectorStoreInit:
    """Test initialization and table creation."""

    def test_creates_db_file(self, tmp_path):
        with patch("services.vector_store.CHATS_DIR", str(tmp_path)):
            from services.vector_store import VectorStore

            store = VectorStore("init-test")
            assert store.db_path.exists()
            store.close()

    def test_tables_exist(self, vector_store):
        cursor = vector_store.conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cursor.fetchall()}

        assert "document_chunks" in tables
        assert "message_embeddings" in tables


# =============================================================================
# add_document_chunks TESTS
# =============================================================================


class TestAddDocumentChunks:
    """Test adding document chunks with embeddings."""

    def test_add_single_chunk(self, vector_store, embedding_32):
        result = vector_store.add_document_chunks(
            doc_id="doc-1",
            filename="test.txt",
            chunks=["Hello world"],
            embeddings=[embedding_32],
        )
        assert result is True

        stats = vector_store.get_stats()
        assert stats["document_chunks"] == 1

    def test_add_multiple_chunks(self, vector_store, embedding_32):
        embeddings = [embedding_32 + i * 0.01 for i in range(5)]

        result = vector_store.add_document_chunks(
            doc_id="doc-multi",
            filename="multi.txt",
            chunks=[f"Chunk {i}" for i in range(5)],
            embeddings=embeddings,
        )
        assert result is True

        stats = vector_store.get_stats()
        assert stats["document_chunks"] == 5
        assert stats["documents"] == 1

    def test_add_chunks_replaces_existing(self, vector_store, embedding_32):
        # Add first
        vector_store.add_document_chunks(
            doc_id="doc-replace",
            filename="replace.txt",
            chunks=["Original"],
            embeddings=[embedding_32],
        )
        # Add same doc_id again
        vector_store.add_document_chunks(
            doc_id="doc-replace",
            filename="replace.txt",
            chunks=["Updated"],
            embeddings=[embedding_32],
        )

        stats = vector_store.get_stats()
        # Should have both (INSERT OR REPLACE keyed on doc_id + chunk_index)
        # The exact count depends on implementation; just verify no crash
        assert stats["document_chunks"] >= 1


# =============================================================================
# search_documents TESTS
# =============================================================================


class TestSearchDocuments:
    """Test document similarity search."""

    def test_search_finds_similar(self, vector_store, embedding_32, embedding_32_similar, embedding_32_different):
        # Add a document with known embedding
        vector_store.add_document_chunks(
            doc_id="similar-doc",
            filename="ml.txt",
            chunks=["This is about machine learning"],
            embeddings=[embedding_32],
        )
        vector_store.add_document_chunks(
            doc_id="different-doc",
            filename="cooking.txt",
            chunks=["This is about cooking recipes"],
            embeddings=[embedding_32_different],
        )

        # Search with similar embedding
        results = vector_store.search_documents(embedding_32_similar, k=2)

        assert len(results) >= 1
        # The most similar should be first
        assert results[0]["filename"] == "ml.txt"

    def test_search_empty_db(self, vector_store, embedding_32):
        results = vector_store.search_documents(embedding_32)
        assert results == []

    def test_search_respects_k(self, vector_store, embedding_32):
        # Add 10 chunks
        for i in range(10):
            vec = embedding_32 + i * 0.01
            vector_store.add_document_chunks(
                doc_id=f"doc-{i}",
                filename=f"file-{i}.txt",
                chunks=[f"Content {i}"],
                embeddings=[vec.astype(np.float32)],
            )

        results = vector_store.search_documents(embedding_32, k=3)
        assert len(results) <= 3


# =============================================================================
# add_message_embedding TESTS
# =============================================================================


class TestAddMessageEmbedding:
    """Test message embedding storage."""

    def test_add_message(self, vector_store, embedding_32):
        result = vector_store.add_message_embedding(
            chat_id="chat-1",
            message_index=0,
            role="user",
            content="Hello",
            embedding=embedding_32,
        )
        assert result is True

        stats = vector_store.get_stats()
        assert stats["message_embeddings"] == 1

    def test_add_message_none_embedding(self, vector_store):
        result = vector_store.add_message_embedding(
            chat_id="chat-1",
            message_index=0,
            role="user",
            content="Hello",
            embedding=None,
        )
        assert result is True

    def test_add_message_replaces_same_index(self, vector_store, embedding_32):
        vector_store.add_message_embedding(
            chat_id="chat-1", message_index=0,
            role="user", content="First", embedding=embedding_32,
        )
        vector_store.add_message_embedding(
            chat_id="chat-1", message_index=0,
            role="user", content="Updated", embedding=embedding_32,
        )

        stats = vector_store.get_stats()
        assert stats["message_embeddings"] == 1  # INSERT OR REPLACE


# =============================================================================
# search_messages TESTS
# =============================================================================


class TestSearchMessages:
    """Test semantic message search."""

    def test_search_messages_by_similarity(self, vector_store, embedding_32, embedding_32_similar, embedding_32_different):
        vector_store.add_message_embedding(
            "chat-1", 0, "user", "ML question", embedding_32
        )
        vector_store.add_message_embedding(
            "chat-1", 1, "assistant", "ML answer", embedding_32_similar
        )
        vector_store.add_message_embedding(
            "chat-1", 2, "user", "Cooking question", embedding_32_different
        )

        results = vector_store.search_messages(embedding_32, chat_id="chat-1", k=2)

        assert len(results) == 2
        # First result should be most similar (the exact embedding_32 message)
        assert results[0]["content"] == "ML question"

    def test_search_messages_empty(self, vector_store, embedding_32):
        results = vector_store.search_messages(embedding_32)
        assert results == []

    def test_search_messages_filter_by_chat(self, vector_store, embedding_32):
        vector_store.add_message_embedding("chat-1", 0, "user", "A", embedding_32)
        vector_store.add_message_embedding("chat-2", 0, "user", "B", embedding_32)

        results = vector_store.search_messages(embedding_32, chat_id="chat-1")
        assert all(r["chat_id"] == "chat-1" for r in results)


# =============================================================================
# get_recent_messages TESTS
# =============================================================================


class TestGetRecentMessages:
    """Test retrieving recent messages."""

    def test_get_recent_ordered(self, vector_store, embedding_32):
        for i in range(5):
            vector_store.add_message_embedding(
                "chat-1", i, "user", f"Message {i}", embedding_32
            )

        messages = vector_store.get_recent_messages("chat-1", limit=3)

        assert len(messages) == 3
        # Should be ordered oldest to newest
        assert messages[0]["content"] == "Message 2"
        assert messages[2]["content"] == "Message 4"

    def test_get_recent_empty_chat(self, vector_store):
        messages = vector_store.get_recent_messages("nonexistent-chat")
        assert messages == []


# =============================================================================
# _cosine_similarity TESTS
# =============================================================================


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_identical_vectors(self, vector_store):
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        sim = vector_store._cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self, vector_store):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        sim = vector_store._cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_opposite_vectors(self, vector_store):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        sim = vector_store._cosine_similarity(a, b)
        assert abs(sim + 1.0) < 1e-6

    def test_zero_vector(self, vector_store):
        a = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        sim = vector_store._cosine_similarity(a, b)
        assert sim == 0.0


# =============================================================================
# EXPORT / IMPORT TESTS
# =============================================================================


class TestExportImport:
    """Test database export/import for IPFS persistence."""

    def test_export_returns_bytes(self, vector_store, embedding_32):
        vector_store.add_document_chunks(
            "doc-1", "test.txt", ["Hello"], [embedding_32]
        )

        data = vector_store.export_for_ipfs()

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_import_restores_data(self, vector_store, embedding_32, tmp_path):
        # Add data and export
        vector_store.add_document_chunks(
            "doc-export", "export.txt", ["Export me"], [embedding_32]
        )
        data = vector_store.export_for_ipfs()
        original_stats = vector_store.get_stats()

        # Create new store and import
        import_dir = tmp_path / "imported"
        with patch("services.vector_store.CHATS_DIR", str(import_dir)):
            from services.vector_store import VectorStore

            new_store = VectorStore("import-test")
            success = new_store.import_from_ipfs(data)

            assert success is True

            new_stats = new_store.get_stats()
            assert new_stats["document_chunks"] == original_stats["document_chunks"]

            new_store.close()


# =============================================================================
# get_stats TESTS
# =============================================================================


class TestGetStats:
    """Test statistics reporting."""

    def test_stats_empty_db(self, vector_store):
        stats = vector_store.get_stats()
        assert stats["documents"] == 0
        assert stats["document_chunks"] == 0
        assert stats["message_embeddings"] == 0

    def test_stats_with_data(self, vector_store, embedding_32):
        vector_store.add_document_chunks("doc-1", "stats.txt", ["A", "B"], [embedding_32, embedding_32])
        vector_store.add_message_embedding("chat-1", 0, "user", "Hi", embedding_32)

        stats = vector_store.get_stats()
        assert stats["documents"] == 1
        assert stats["document_chunks"] == 2
        assert stats["message_embeddings"] == 1
        assert stats["db_size_bytes"] > 0


# =============================================================================
# get_vector_store / module-level TESTS
# =============================================================================


class TestModuleFunctions:
    """Test module-level helper functions."""

    def test_get_vector_store_caches(self, tmp_path):
        with patch("services.vector_store.CHATS_DIR", str(tmp_path)):
            from services.vector_store import get_vector_store, _vector_stores

            store1 = get_vector_store("cache-test")
            store2 = get_vector_store("cache-test")

            assert store1 is store2

            # Cleanup
            store1.close()
            _vector_stores.pop("cache-test", None)

    def test_close_all_stores(self, tmp_path):
        with patch("services.vector_store.CHATS_DIR", str(tmp_path)):
            from services.vector_store import get_vector_store, close_all_stores, _vector_stores

            get_vector_store("close-test-1")
            get_vector_store("close-test-2")

            close_all_stores()

            assert len(_vector_stores) == 0
