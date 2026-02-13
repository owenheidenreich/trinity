"""
Trinity Backend - MemGPT Memory Tools Tests
============================================
Tests for save_memory, recall_memory, and search_memory tools.

All storage and embedding dependencies are mocked.
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np

from services.memory_tools import tool_recall_memory, tool_save_memory, tool_search_memory


def _mock_memory(facts=None):
    """Create a mock user memory dict."""
    return {
        "principalId": "test-user",
        "version": "1.0",
        "facts": facts or [],
        "preferences": {},
        "createdAt": int(time.time() * 1000),
        "lastUpdated": int(time.time() * 1000),
    }


def _make_fact(text, category="general", importance=3, embedding=None):
    """Helper to create a fact dict."""
    if embedding is None:
        embedding = np.random.randn(384).tolist()
    return {
        "text": text,
        "category": category,
        "importance": importance,
        "embedding": embedding,
        "created_at": int(time.time() * 1000),
    }


# ============================================================================
# save_memory
# ============================================================================


class TestSaveMemory:
    """Test tool_save_memory()."""

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_save_new_fact(self, mock_get_emb, mock_get_storage):
        """Saving a new fact succeeds and calls save_user_memory."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.0)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        mock_load = MagicMock(return_value=_mock_memory())
        mock_save = MagicMock()
        mock_get_storage.return_value = (mock_load, mock_save)

        success, result = tool_save_memory(
            {"fact": "User likes Python", "category": "preferences", "importance": "4"},
            "test-user",
        )

        assert success is True
        assert "Python" in result
        assert "preferences" in result
        mock_save.assert_called_once()

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_save_deduplicates(self, mock_get_emb, mock_get_storage):
        """Near-duplicate fact is rejected (cosine > 0.95)."""
        existing_emb = np.ones(384).tolist()
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.98)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        existing_fact = _make_fact("User likes Python", embedding=existing_emb)
        mock_load = MagicMock(return_value=_mock_memory(facts=[existing_fact]))
        mock_save = MagicMock()
        mock_get_storage.return_value = (mock_load, mock_save)

        success, result = tool_save_memory(
            {"fact": "User likes Python programming"},
            "test-user",
        )

        assert success is True
        assert "Already remembered" in result
        mock_save.assert_not_called()

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_save_allows_distinct_facts(self, mock_get_emb, mock_get_storage):
        """Dissimilar fact is saved (cosine < 0.95)."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.4)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        existing_fact = _make_fact("User lives in NYC")
        mock_load = MagicMock(return_value=_mock_memory(facts=[existing_fact]))
        mock_save = MagicMock()
        mock_get_storage.return_value = (mock_load, mock_save)

        success, result = tool_save_memory(
            {"fact": "User works in AI research"},
            "test-user",
        )

        assert success is True
        assert "Saved" in result
        mock_save.assert_called_once()

    def test_save_empty_fact(self):
        """Empty fact returns error."""
        success, result = tool_save_memory({"fact": ""}, "test-user")

        assert success is False
        assert "No fact" in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_save_defaults(self, mock_get_emb, mock_get_storage):
        """Default category=general, importance=3."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.0)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        mock_load = MagicMock(return_value=_mock_memory())
        mock_save = MagicMock()
        mock_get_storage.return_value = (mock_load, mock_save)

        success, result = tool_save_memory({"fact": "Some fact"}, "test-user")

        assert success is True
        assert "general" in result
        assert "3/5" in result


# ============================================================================
# recall_memory
# ============================================================================


class TestRecallMemory:
    """Test tool_recall_memory()."""

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_recall_returns_relevant_facts(self, mock_get_emb, mock_get_storage):
        """Recall returns facts sorted by combined score."""
        query_emb = np.ones(384)
        mock_embed = MagicMock(return_value=query_emb)
        # Return different similarities for different facts
        mock_cosine = MagicMock(side_effect=[0.9, 0.3, 0.7])
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [
            _make_fact("User likes Python", importance=4),
            _make_fact("User lives in NYC", importance=5),
            _make_fact("User works in AI", importance=3),
        ]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_recall_memory({"query": "programming"}, "test-user")

        assert success is True
        assert "Recalled 3 memories" in result
        # First result should be highest combined score
        lines = result.split("\n")
        first_fact_line = next(l for l in lines if l.strip().startswith("1."))
        assert "Python" in first_fact_line

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_recall_filters_by_category(self, mock_get_emb, mock_get_storage):
        """Category filter excludes non-matching facts."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.8)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [
            _make_fact("User likes Python", category="preferences"),
            _make_fact("User lives in NYC", category="personal"),
            _make_fact("User prefers dark mode", category="preferences"),
        ]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_recall_memory(
            {"query": "preferences", "category": "preferences"},
            "test-user",
        )

        assert success is True
        assert "Recalled 2 memories" in result
        assert "NYC" not in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_recall_empty_memory(self, mock_get_emb, mock_get_storage):
        """No saved facts returns informative message."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock()
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        mock_load = MagicMock(return_value=_mock_memory())
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_recall_memory({"query": "anything"}, "test-user")

        assert success is True
        assert "No memories" in result

    def test_recall_empty_query(self):
        """Empty query returns error."""
        success, result = tool_recall_memory({"query": ""}, "test-user")

        assert success is False
        assert "No query" in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_recall_respects_limit(self, mock_get_emb, mock_get_storage):
        """Limit parameter caps results."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.8)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [_make_fact(f"Fact {i}") for i in range(10)]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_recall_memory(
            {"query": "test", "limit": "2"},
            "test-user",
        )

        assert success is True
        assert "Recalled 2 memories" in result


# ============================================================================
# search_memory
# ============================================================================


class TestSearchMemory:
    """Test tool_search_memory()."""

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_search_exact_match(self, mock_get_emb, mock_get_storage):
        """Exact search finds substring matches."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.5)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [
            _make_fact("User likes Python"),
            _make_fact("User works with JavaScript"),
            _make_fact("User prefers PyCharm for Python"),
        ]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_search_memory(
            {"query": "Python", "search_type": "exact"},
            "test-user",
        )

        assert success is True
        assert "2 memories" in result
        assert "JavaScript" not in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_search_semantic(self, mock_get_emb, mock_get_storage):
        """Semantic search finds similar facts."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(side_effect=[0.8, 0.2, 0.6])
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [
            _make_fact("User likes Python"),
            _make_fact("User lives in NYC"),
            _make_fact("User codes in Rust"),
        ]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_search_memory(
            {"query": "programming languages", "search_type": "semantic"},
            "test-user",
        )

        assert success is True
        # Should find 2 results (0.8 and 0.6 are above 0.3 threshold)
        assert "2 memories" in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_search_hybrid(self, mock_get_emb, mock_get_storage):
        """Hybrid search combines exact + semantic without duplicates."""
        mock_embed = MagicMock(return_value=np.ones(384))
        # Cosine called for all 3 facts in semantic phase (before dedup check)
        mock_cosine = MagicMock(side_effect=[0.9, 0.8, 0.7])
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [
            _make_fact("User likes Python"),  # exact + semantic match
            _make_fact("User lives in NYC"),  # no exact, semantic only
            _make_fact("Python is their favorite"),  # exact + semantic match
        ]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_search_memory(
            {"query": "Python", "search_type": "hybrid"},
            "test-user",
        )

        assert success is True
        # Should have exact matches + semantic non-duplicates
        assert "memories" in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_search_no_matches(self, mock_get_emb, mock_get_storage):
        """No matches returns informative message."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.1)  # Below threshold
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [_make_fact("User likes Python")]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_search_memory(
            {"query": "cooking recipes", "search_type": "semantic"},
            "test-user",
        )

        assert success is True
        assert "No memories match" in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_search_empty_memory(self, mock_get_emb, mock_get_storage):
        """Empty memory returns informative message."""
        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock()
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        mock_load = MagicMock(return_value=_mock_memory())
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = tool_search_memory({"query": "anything"}, "test-user")

        assert success is True
        assert "No memories" in result

    def test_search_empty_query(self):
        """Empty query returns error."""
        success, result = tool_search_memory({"query": ""}, "test-user")

        assert success is False
        assert "No search query" in result


# ============================================================================
# Integration with execute_tool
# ============================================================================


class TestMemoryToolsViaExecuteTool:
    """Test memory tools called through execute_tool()."""

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_save_via_execute_tool(self, mock_get_emb, mock_get_storage):
        """save_memory works through execute_tool dispatcher."""
        from services.code_executor import execute_tool

        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.0)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        mock_load = MagicMock(return_value=_mock_memory())
        mock_save = MagicMock()
        mock_get_storage.return_value = (mock_load, mock_save)

        success, result = execute_tool(
            "save_memory",
            {"fact": "User likes chess"},
            context={"principal_id": "test-user"},
        )

        assert success is True
        assert "chess" in result

    @patch("services.memory_tools._get_storage")
    @patch("services.memory_tools._get_embeddings")
    def test_recall_via_execute_tool(self, mock_get_emb, mock_get_storage):
        """recall_memory works through execute_tool dispatcher."""
        from services.code_executor import execute_tool

        mock_embed = MagicMock(return_value=np.ones(384))
        mock_cosine = MagicMock(return_value=0.8)
        mock_get_emb.return_value = (mock_embed, mock_cosine)

        facts = [_make_fact("User likes chess")]
        mock_load = MagicMock(return_value=_mock_memory(facts=facts))
        mock_get_storage.return_value = (mock_load, MagicMock())

        success, result = execute_tool(
            "recall_memory",
            {"query": "hobbies"},
            context={"principal_id": "test-user"},
        )

        assert success is True
        assert "chess" in result

    def test_memory_tool_without_principal_id(self):
        """Memory tools fail without principal_id in context."""
        from services.code_executor import execute_tool

        success, result = execute_tool(
            "save_memory",
            {"fact": "test"},
            context={},
        )

        assert success is False
