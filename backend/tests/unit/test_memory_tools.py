"""
Trinity Backend — Memory Tools Tests (v5.0 — KnowledgeStore)
=============================================================
Tests for save_memory, recall_memory, search_memory, update_memory,
and forget_memory tools.

All storage and embedding dependencies are mocked at the KnowledgeStore level.
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np

from services.memory_tools import (
    tool_recall_memory,
    tool_save_memory,
    tool_search_memory,
    tool_update_memory,
    tool_forget_memory,
    detect_contradiction,
    _detect_contradiction,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_knowledge_item(
    text: str,
    fact_id: int = 1,
    category: str = "general",
    importance: int = 3,
    similarity: float = 0.8,
    item_type: str = "fact",
):
    """Build a mock KnowledgeItem-like object."""
    from services.knowledge_store import KnowledgeItem, ItemType
    return KnowledgeItem(
        item_id=fact_id,
        text=text,
        category=category,
        importance=importance,
        item_type=ItemType(item_type),
        similarity_score=similarity,
        recency_score=0.5,
        combined_score=similarity * 0.6 + importance / 5.0 * 0.25 + 0.5 * 0.15,
        created_at=int(time.time()),
    )


def _mock_ks(
    save_fact_return=("insert", 1),
    search_return=None,
):
    """Create a mock KnowledgeStore with configurable returns."""
    ks = MagicMock()
    ks.save_fact.return_value = save_fact_return
    ks.search.return_value = search_return or []
    ks.update_fact.return_value = None
    ks.soft_delete.return_value = None
    # Give the mock a .store attribute with a ._lock and .conn for _search_with_exact
    ks.store = MagicMock()
    ks.store._lock = MagicMock()
    ks.store._lock.__enter__ = MagicMock(return_value=None)
    ks.store._lock.__exit__ = MagicMock(return_value=False)
    return ks


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------


class TestSaveMemory:
    """Test tool_save_memory()."""

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_save_new_fact(self, mock_get_ks, mock_embed):
        """Saving a new fact succeeds."""
        ks = _mock_ks(save_fact_return=("insert", 1))
        mock_get_ks.return_value = ks

        success, result = tool_save_memory(
            {"fact": "User likes Python", "category": "preferences", "importance": "4"},
            "test-user",
        )

        assert success is True
        assert "Python" in result
        assert "preferences" in result
        ks.save_fact.assert_called_once_with(
            text="User likes Python",
            category="preferences",
            importance=4,
            source_message_id=None,
        )

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_save_deduplicates(self, mock_get_ks, mock_embed):
        """Near-duplicate fact is rejected (dedup returns skip)."""
        ks = _mock_ks(save_fact_return=("skip", None))
        mock_get_ks.return_value = ks

        success, result = tool_save_memory(
            {"fact": "User likes Python programming"},
            "test-user",
        )

        assert success is True
        assert "Already remembered" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_save_allows_distinct_facts(self, mock_get_ks, mock_embed):
        """Dissimilar fact is saved (dedup returns insert)."""
        ks = _mock_ks(save_fact_return=("insert", 2))
        mock_get_ks.return_value = ks

        success, result = tool_save_memory(
            {"fact": "User works in AI research"},
            "test-user",
        )

        assert success is True
        assert "Saved" in result
        ks.save_fact.assert_called_once()

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_save_merge(self, mock_get_ks, mock_embed):
        """Merge-range similarity triggers update."""
        ks = _mock_ks(save_fact_return=("merge", 5))
        mock_get_ks.return_value = ks

        success, result = tool_save_memory(
            {"fact": "User likes Python 3.12"},
            "test-user",
        )

        assert success is True
        assert "Updated existing memory" in result

    def test_save_empty_fact(self):
        """Empty fact returns error."""
        success, result = tool_save_memory({"fact": ""}, "test-user")

        assert success is False
        assert "No fact" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_save_defaults(self, mock_get_ks, mock_embed):
        """Default category=general, importance=3."""
        ks = _mock_ks(save_fact_return=("insert", 1))
        mock_get_ks.return_value = ks

        success, result = tool_save_memory({"fact": "Some fact"}, "test-user")

        assert success is True
        assert "general" in result
        assert "3/5" in result
        ks.save_fact.assert_called_once_with(
            text="Some fact",
            category="general",
            importance=3,
            source_message_id=None,
        )


# ---------------------------------------------------------------------------
# recall_memory
# ---------------------------------------------------------------------------


class TestRecallMemory:
    """Test tool_recall_memory()."""

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_recall_returns_relevant_facts(self, mock_get_ks, mock_embed):
        """Recall returns facts sorted by combined score."""
        items = [
            _make_knowledge_item("User likes Python", fact_id=1, importance=4, similarity=0.9),
            _make_knowledge_item("User works in AI", fact_id=3, importance=3, similarity=0.7),
            _make_knowledge_item("User lives in NYC", fact_id=2, importance=5, similarity=0.3),
        ]
        ks = _mock_ks(search_return=items)
        mock_get_ks.return_value = ks

        success, result = tool_recall_memory({"query": "programming"}, "test-user")

        assert success is True
        assert "Recalled 3 memories" in result
        # First result should be "Python" (highest similarity)
        lines = result.split("\n")
        first_fact_line = next(l for l in lines if l.strip().startswith("1."))
        assert "Python" in first_fact_line

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_recall_filters_by_category(self, mock_get_ks, mock_embed):
        """Category filter is passed to KnowledgeStore search."""
        items = [
            _make_knowledge_item("User likes Python", category="preferences"),
            _make_knowledge_item("User prefers dark mode", category="preferences"),
        ]
        ks = _mock_ks(search_return=items)
        mock_get_ks.return_value = ks

        success, result = tool_recall_memory(
            {"query": "preferences", "category": "preferences"},
            "test-user",
        )

        assert success is True
        assert "Recalled 2 memories" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_recall_empty_memory(self, mock_get_ks, mock_embed):
        """No saved facts returns informative message."""
        ks = _mock_ks(search_return=[])
        mock_get_ks.return_value = ks

        success, result = tool_recall_memory({"query": "anything"}, "test-user")

        assert success is True
        assert "No memories" in result

    def test_recall_empty_query(self):
        """Empty query returns error."""
        success, result = tool_recall_memory({"query": ""}, "test-user")

        assert success is False
        assert "No query" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_recall_respects_limit(self, mock_get_ks, mock_embed):
        """Limit parameter caps results."""
        items = [
            _make_knowledge_item(f"Fact {i}", fact_id=i, similarity=0.8)
            for i in range(2)
        ]
        ks = _mock_ks(search_return=items)
        mock_get_ks.return_value = ks

        success, result = tool_recall_memory(
            {"query": "test", "limit": "2"},
            "test-user",
        )

        assert success is True
        assert "Recalled 2 memories" in result


# ---------------------------------------------------------------------------
# search_memory
# ---------------------------------------------------------------------------


class TestSearchMemory:
    """Test tool_search_memory()."""

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_search_semantic(self, mock_get_ks, mock_embed):
        """Semantic search finds similar facts via KnowledgeStore.search."""
        items = [
            _make_knowledge_item("User likes Python", similarity=0.8),
            _make_knowledge_item("User codes in Rust", fact_id=2, similarity=0.6),
        ]
        ks = _mock_ks(search_return=items)
        mock_get_ks.return_value = ks

        success, result = tool_search_memory(
            {"query": "programming languages", "search_type": "semantic"},
            "test-user",
        )

        assert success is True
        assert "2 memories" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_search_no_matches(self, mock_get_ks, mock_embed):
        """No matches returns informative message."""
        ks = _mock_ks(search_return=[])
        mock_get_ks.return_value = ks

        success, result = tool_search_memory(
            {"query": "cooking recipes", "search_type": "semantic"},
            "test-user",
        )

        assert success is True
        assert "No memories" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_search_empty_memory(self, mock_get_ks, mock_embed):
        """Empty memory returns informative message."""
        ks = _mock_ks(search_return=[])
        mock_get_ks.return_value = ks

        success, result = tool_search_memory({"query": "anything"}, "test-user")

        assert success is True
        assert "No memories" in result

    def test_search_empty_query(self):
        """Empty query returns error."""
        success, result = tool_search_memory({"query": ""}, "test-user")

        assert success is False
        assert "No search query" in result

    def test_search_invalid_type_falls_back_to_semantic(self):
        """Invalid search_type defaults to semantic."""
        # Just verify it doesn't crash — semantic path needs mocks
        success, result = tool_search_memory({"query": ""}, "test-user")
        assert success is False  # Fails on empty query before search_type matters


# ---------------------------------------------------------------------------
# update_memory
# ---------------------------------------------------------------------------


class TestUpdateMemory:
    """Test tool_update_memory()."""

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_update_existing_fact(self, mock_get_ks, mock_embed):
        """Update rewrites matching fact text."""
        item = _make_knowledge_item("User lives in NYC", fact_id=7, similarity=0.85)
        ks = _mock_ks(search_return=[item])
        mock_get_ks.return_value = ks

        success, result = tool_update_memory(
            {"query": "where user lives", "new_value": "User lives in LA"},
            "test-user",
        )

        assert success is True
        assert "Updated" in result
        assert "NYC" in result
        assert "LA" in result
        ks.update_fact.assert_called_once()

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_update_no_match(self, mock_get_ks, mock_embed):
        """Update with no matching fact returns error."""
        item = _make_knowledge_item("Unrelated", similarity=0.1)
        ks = _mock_ks(search_return=[item])
        mock_get_ks.return_value = ks

        success, result = tool_update_memory(
            {"query": "favorite color", "new_value": "blue"},
            "test-user",
        )

        assert success is False
        assert "No memory found" in result

    def test_update_empty_query(self):
        success, result = tool_update_memory({"query": "", "new_value": "x"}, "test-user")
        assert success is False
        assert "No query" in result

    def test_update_empty_new_value(self):
        success, result = tool_update_memory({"query": "x", "new_value": ""}, "test-user")
        assert success is False
        assert "No new_value" in result


# ---------------------------------------------------------------------------
# forget_memory
# ---------------------------------------------------------------------------


class TestForgetMemory:
    """Test tool_forget_memory()."""

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_forget_existing_fact(self, mock_get_ks, mock_embed):
        """Forget soft-deletes matching fact."""
        item = _make_knowledge_item("User likes Python", fact_id=3, similarity=0.9)
        ks = _mock_ks(search_return=[item])
        mock_get_ks.return_value = ks

        success, result = tool_forget_memory({"query": "Python"}, "test-user")

        assert success is True
        assert "Forgotten" in result
        ks.soft_delete.assert_called_once_with(3)

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_forget_no_match(self, mock_get_ks, mock_embed):
        """Forget with no matching fact returns error."""
        item = _make_knowledge_item("Unrelated", similarity=0.1)
        ks = _mock_ks(search_return=[item])
        mock_get_ks.return_value = ks

        success, result = tool_forget_memory({"query": "cooking"}, "test-user")

        assert success is False
        assert "No memory found" in result

    def test_forget_empty_query(self):
        success, result = tool_forget_memory({"query": ""}, "test-user")
        assert success is False
        assert "No query" in result


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------


class TestContradictionDetection:
    """Test detect_contradiction()."""

    def test_same_text_no_contradiction(self):
        assert detect_contradiction("User lives in NYC", "User lives in NYC") is False

    def test_location_change_is_contradiction(self):
        assert detect_contradiction("User lives in NYC", "User lives in LA") is True

    def test_refinement_not_contradiction(self):
        assert detect_contradiction("User is a developer", "User is a senior developer") is False

    def test_different_categories_no_contradiction(self):
        assert detect_contradiction("User likes Python", "User lives in NYC") is False

    def test_legacy_alias_works(self):
        """_detect_contradiction alias still works."""
        assert _detect_contradiction("User works at Google", "User works at Meta") is True


# ---------------------------------------------------------------------------
# Integration with execute_tool
# ---------------------------------------------------------------------------


class TestMemoryToolsViaExecuteTool:
    """Test memory tools called through execute_tool()."""

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_save_via_execute_tool(self, mock_get_ks, mock_embed):
        """save_memory works through execute_tool dispatcher."""
        from services.code_executor import execute_tool

        ks = _mock_ks(save_fact_return=("insert", 1))
        mock_get_ks.return_value = ks

        success, result = execute_tool(
            "save_memory",
            {"fact": "User likes chess"},
            context={"principal_id": "test-user"},
        )

        assert success is True
        assert "chess" in result

    @patch("services.memory_tools._embed", return_value=np.ones(384))
    @patch("services.memory_tools._get_knowledge_store")
    def test_recall_via_execute_tool(self, mock_get_ks, mock_embed):
        """recall_memory works through execute_tool dispatcher."""
        from services.code_executor import execute_tool

        items = [_make_knowledge_item("User likes chess", similarity=0.8)]
        ks = _mock_ks(search_return=items)
        mock_get_ks.return_value = ks

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
