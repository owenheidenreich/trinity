"""
Phase 3 Memory System Overhaul Tests
=====================================
Tests for:
- B1/B8: _format_user_memory() dict rendering fix
- B3: build_enhanced_context() tuple return type
- B4: _normalize_facts() schema migration
- B5: Context window size (frontend — verified by grep)
"""

import time
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# B1/B8: _format_user_memory
# ============================================================================

class TestFormatUserMemory:
    """Tests for agent.py _format_user_memory()."""

    def test_empty_memory_returns_empty(self):
        from services.agent import _format_user_memory

        assert _format_user_memory(None) == ""
        assert _format_user_memory({}) == ""
        assert _format_user_memory({"facts": []}) == ""

    def test_canonical_dict_facts(self):
        """Facts with 'text' key render correctly."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "User likes Python", "category": "preferences", "importance": 4, "embedding": [0.1] * 384},
            {"text": "User is a developer", "category": "general", "importance": 3, "embedding": [0.2] * 384},
        ]}
        result = _format_user_memory(memory)

        assert "## What you know about this user" in result
        assert "- [preferences] User likes Python" in result
        assert "- User is a developer" in result
        # Embeddings must NOT appear
        assert "0.1" not in result
        assert "embedding" not in result

    def test_legacy_fact_key_format(self):
        """Facts with 'fact' key (legacy REST API format) render correctly."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"fact": "User prefers dark mode", "category": "general"},
        ]}
        result = _format_user_memory(memory)

        assert "- User prefers dark mode" in result

    def test_plain_string_facts(self):
        """Plain string facts render correctly."""
        from services.agent import _format_user_memory

        memory = {"facts": ["Fact one", "Fact two"]}
        result = _format_user_memory(memory)

        assert "- Fact one" in result
        assert "- Fact two" in result

    def test_mixed_fact_formats(self):
        """Mix of dict and string facts all render."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "Dict fact", "category": "general"},
            "String fact",
            {"fact": "Legacy fact"},
        ]}
        result = _format_user_memory(memory)

        assert "- Dict fact" in result
        assert "- String fact" in result
        assert "- Legacy fact" in result

    def test_max_10_facts(self):
        """Only first 10 facts are included."""
        from services.agent import _format_user_memory

        memory = {"facts": [f"Fact {i}" for i in range(15)]}
        result = _format_user_memory(memory)

        assert "Fact 9" in result
        assert "Fact 10" not in result

    def test_category_display(self):
        """Non-general categories shown in brackets, general omitted."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "Likes Rust", "category": "preferences"},
            {"text": "Is tall", "category": "general"},
            {"text": "Uses vim", "category": "tools"},
        ]}
        result = _format_user_memory(memory)

        assert "- [preferences] Likes Rust" in result
        assert "- Is tall" in result  # No category prefix
        assert "- [tools] Uses vim" in result

    def test_skips_empty_text_facts(self):
        """Facts with empty text are skipped."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "", "category": "general"},
            {"fact": ""},
            {"text": "Real fact"},
        ]}
        result = _format_user_memory(memory)

        lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(lines) == 1
        assert "Real fact" in result


# ============================================================================
# B3: build_enhanced_context tuple return
# ============================================================================

class TestBuildEnhancedContext:
    """Tests for memory.py build_enhanced_context() returning tuple."""

    @patch("services.memory.get_semantic_memory")
    def test_returns_tuple(self, mock_get_mem):
        """build_enhanced_context returns (messages, semantic_items) tuple."""
        from services.memory import build_enhanced_context

        mock_mem = MagicMock()
        mock_mem.retrieve_context.return_value = {
            "working_memory": [],
            "semantic_memory": [{"role": "user", "content": "past msg", "score": 0.9}],
            "combined": [{"role": "user", "content": "past msg"}],
        }
        mock_get_mem.return_value = mock_mem

        result = build_enhanced_context(
            query="test query",
            principal_id="test-user",
            context_messages=[{"role": "user", "content": "recent"}],
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        enhanced, semantic = result
        # Enhanced is the fallback messages (passed through)
        assert isinstance(enhanced, list)
        # Semantic items returned from the memory system
        assert isinstance(semantic, list)
        assert len(semantic) == 1

    @patch("services.memory.get_semantic_memory")
    def test_returns_none_semantic_when_empty(self, mock_get_mem):
        """When no semantic results, second element is None."""
        from services.memory import build_enhanced_context

        mock_mem = MagicMock()
        mock_mem.retrieve_context.return_value = {
            "working_memory": [],
            "semantic_memory": [],
            "combined": [],
        }
        mock_get_mem.return_value = mock_mem

        enhanced, semantic = build_enhanced_context(
            query="test", principal_id="user", context_messages=[],
        )

        assert semantic is None

    @patch("services.memory.get_semantic_memory")
    def test_fallback_on_exception(self, mock_get_mem):
        """On semantic memory failure, returns fallback messages and None."""
        from services.memory import build_enhanced_context

        mock_get_mem.side_effect = Exception("DB error")
        fallback = [{"role": "user", "content": "hello"}]

        enhanced, semantic = build_enhanced_context(
            query="test", principal_id="user", context_messages=fallback,
        )

        assert enhanced == fallback
        assert semantic is None

    @patch("services.memory.get_semantic_memory")
    def test_recent_messages_alias(self, mock_get_mem):
        """recent_messages param works as alias for context_messages."""
        from services.memory import build_enhanced_context

        mock_get_mem.side_effect = Exception("skip")
        msgs = [{"role": "user", "content": "hello"}]

        enhanced, _ = build_enhanced_context(
            query="test", principal_id="user", recent_messages=msgs,
        )

        assert enhanced == msgs


# ============================================================================
# B4: _normalize_facts
# ============================================================================

class TestNormalizeFacts:
    """Tests for storage.py _normalize_facts()."""

    def test_normalizes_plain_strings(self):
        from storage import _normalize_facts

        memory = {"facts": ["Likes Python", "Is a developer"]}
        result = _normalize_facts(memory)

        assert len(result["facts"]) == 2
        assert result["facts"][0]["text"] == "Likes Python"
        assert result["facts"][0]["category"] == "general"
        assert result["facts"][0]["importance"] == 3
        assert "created_at" in result["facts"][0]

    def test_normalizes_legacy_rest_format(self):
        """Facts with 'fact' key converted to 'text' key."""
        from storage import _normalize_facts

        memory = {"facts": [
            {"fact": "Prefers dark mode", "addedAt": 1700000000000, "category": "ui"},
        ]}
        result = _normalize_facts(memory)

        fact = result["facts"][0]
        assert fact["text"] == "Prefers dark mode"
        assert fact["category"] == "ui"
        assert fact["created_at"] == 1700000000000
        assert "fact" not in fact  # Old key removed

    def test_canonical_format_passthrough(self):
        """Already-canonical facts pass through unchanged."""
        from storage import _normalize_facts

        canonical = {"text": "Test", "category": "general", "importance": 4,
                      "embedding": [0.1, 0.2], "created_at": 1700000000000}
        memory = {"facts": [canonical]}
        result = _normalize_facts(memory)

        assert result["facts"][0] == canonical

    def test_adds_missing_defaults(self):
        """Canonical facts with missing optional fields get defaults."""
        from storage import _normalize_facts

        memory = {"facts": [{"text": "Partial fact"}]}
        result = _normalize_facts(memory)

        fact = result["facts"][0]
        assert fact["category"] == "general"
        assert fact["importance"] == 3
        assert fact["embedding"] is None
        assert "created_at" in fact

    def test_mixed_formats(self):
        """Mix of string, legacy dict, and canonical dict all normalize."""
        from storage import _normalize_facts

        memory = {"facts": [
            "String fact",
            {"fact": "Legacy fact", "category": "test"},
            {"text": "Canonical fact", "category": "dev", "importance": 5,
             "embedding": None, "created_at": 1700000000000},
        ]}
        result = _normalize_facts(memory)

        assert len(result["facts"]) == 3
        assert all("text" in f for f in result["facts"])
        assert result["facts"][0]["text"] == "String fact"
        assert result["facts"][1]["text"] == "Legacy fact"
        assert result["facts"][2]["importance"] == 5

    def test_empty_facts_passthrough(self):
        from storage import _normalize_facts

        memory = {"facts": []}
        result = _normalize_facts(memory)
        assert result["facts"] == []

    def test_no_facts_key(self):
        from storage import _normalize_facts

        memory = {"preferences": {}}
        result = _normalize_facts(memory)
        assert "preferences" in result

    def test_idempotent(self):
        """Running normalize twice produces same result."""
        from storage import _normalize_facts

        memory = {"facts": ["String fact", {"fact": "Legacy"}]}
        first = _normalize_facts(memory)
        second = _normalize_facts(first)

        assert first["facts"] == second["facts"]
