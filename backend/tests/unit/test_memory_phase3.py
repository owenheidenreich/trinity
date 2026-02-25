"""
Phase 3 Memory System Overhaul Tests
=====================================
Tests for:
- B1/B8: _format_user_memory() token-budget profile rendering
- B3: build_enhanced_context() tuple return type
- B4: _normalize_fact() + _migrate_to_structured_profile() schema migration
- B5: Context window size (frontend — verified by grep)
"""

import time
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# B1/B8: _format_user_memory — SKIPPED (v5.0: replaced by PromptAssembler)
# ============================================================================

@pytest.mark.skip(reason="_format_user_memory removed in v5.0 memory rewrite — replaced by PromptAssembler")
class TestFormatUserMemory:
    """Tests for agent.py _format_user_memory() — SKIPPED."""

    def test_empty_memory_returns_empty(self):
        from services.agent import _format_user_memory

        assert _format_user_memory(None) == ""
        assert _format_user_memory({}) == ""
        assert _format_user_memory({"facts": []}) == ""

    def test_canonical_dict_facts(self):
        """Facts with 'text' key render correctly with category headers."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "User likes Python", "category": "preferences", "importance": 4, "embedding": [0.1] * 384},
            {"text": "User is a developer", "category": "general", "importance": 3, "embedding": [0.2] * 384},
        ]}
        result = _format_user_memory(memory)

        assert "## What you know about this user" in result
        assert "### Preferences" in result
        assert "- User likes Python" in result
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

    def test_token_budget_limits_facts(self):
        """Facts beyond token budget are excluded."""
        from services.agent import _format_user_memory

        # Create many long facts that exceed the 1500-token budget
        memory = {"facts": [{"text": f"Very long fact number {i} " * 20, "category": "general",
                             "importance": 3} for i in range(50)]}
        result = _format_user_memory(memory)

        # Should not include all 50 facts
        fact_lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(fact_lines) < 50

    def test_category_headers(self):
        """Facts are grouped under category headers."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "Likes Rust", "category": "preferences"},
            {"text": "Is tall", "category": "general"},
            {"text": "Uses vim", "category": "work"},
        ]}
        result = _format_user_memory(memory)

        assert "### Preferences" in result
        assert "- Likes Rust" in result
        assert "### General" in result
        assert "- Is tall" in result
        assert "### Work" in result
        assert "- Uses vim" in result

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

    def test_deleted_facts_excluded(self):
        """Soft-deleted facts are not included in the output."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "Active fact", "category": "general", "deleted": False},
            {"text": "Deleted fact", "category": "general", "deleted": True},
        ]}
        result = _format_user_memory(memory)

        assert "Active fact" in result
        assert "Deleted fact" not in result

    def test_identity_facts_prioritized(self):
        """Identity facts get priority (score boost)."""
        from services.agent import _format_user_memory

        memory = {"facts": [
            {"text": "Random general fact", "category": "general", "importance": 1},
            {"text": "User's name is Alice", "category": "identity", "importance": 5},
        ]}
        result = _format_user_memory(memory)

        # Identity should appear first (before general)
        identity_pos = result.find("### Identity")
        general_pos = result.find("### General")
        if identity_pos >= 0 and general_pos >= 0:
            assert identity_pos < general_pos

    def test_non_personal_queries_filter_identity_facts(self):
        """Neutral factual prompts omit identity and style preferences."""
        from services.agent import _format_user_memory

        memory = {
            "facts": [
                {"text": "User's name is Owen", "category": "identity", "importance": 5},
                {"text": "User prefers concise answers", "category": "preferences", "importance": 4},
            ]
        }
        result = _format_user_memory(
            memory,
            query="what is the quadratic formula",
            include_personal=False,
        )

        assert "User's name is Owen" not in result
        assert "User prefers concise answers" not in result

    def test_personal_memory_detector_is_explicit(self):
        """Only explicit profile recall prompts should trigger full personal memory injection."""
        from services.query_classifier import requests_personal_memory

        assert requests_personal_memory("what do you know about me")
        assert requests_personal_memory("what is my name")
        assert not requests_personal_memory("what is the quadratic formula")

    def test_personal_disclosure_detector(self):
        """First-person disclosures should be detected without matching generic help requests."""
        from services.query_classifier import is_personal_disclosure

        assert is_personal_disclosure("my favorite games are zelda and melee")
        assert is_personal_disclosure("i like sci-fi books")
        assert not is_personal_disclosure("what is the quadratic formula")
        assert not is_personal_disclosure("can you help me with python")


# ============================================================================
# Rolling summary prompt injection
# ============================================================================

class TestConversationSummaryPrompt:
    def test_injects_summary_and_uses_unsummarized_tail(self):
        from services.agent_prompts import build_chat_messages

        context = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"message-{i}", "message_index": i}
            for i in range(30)
        ]

        messages = build_chat_messages(
            question="What were we discussing?",
            context_messages=context,
            user_memory="",
            chat_id="chat-1",
            conversation_summary="Summary of older context",
            last_summarized_index=20,
        )

        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert "Summary of older context" in messages[1]["content"]

        history_contents = [m["content"] for m in messages if m["role"] in ("user", "assistant")]
        assert "message-20" not in history_contents
        assert "message-21" in history_contents
        assert "message-29" in history_contents

    def test_without_summary_keeps_last_twenty_messages(self):
        from services.agent_prompts import build_chat_messages

        context = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"message-{i}", "message_index": i}
            for i in range(30)
        ]

        messages = build_chat_messages(
            question="continue",
            context_messages=context,
            user_memory="",
        )

        history = [m for m in messages if m["role"] in ("user", "assistant")]
        # 20 historical messages + current user question
        assert len(history) == 21
        assert any(m["content"] == "message-10" for m in history)
        assert not any(m["content"] == "message-9" for m in history)

    def test_summary_without_message_indexes_keeps_recent_tail(self):
        from services.agent_prompts import build_chat_messages

        # Frontend request shape: role/content only (no message_index fields).
        context = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"message-{i}"}
            for i in range(20)
        ]

        messages = build_chat_messages(
            question="continue",
            context_messages=context,
            user_memory="",
            chat_id="chat-1",
            conversation_summary="Older summary",
            last_summarized_index=200,  # absolute index outside this 20-message local window
            current_message_index=220,
        )

        history = [m for m in messages if m["role"] in ("user", "assistant")]
        # 15 historical tail + current user question
        assert len(history) == 16
        assert history[-1]["content"] == "continue"
        historical = history[:-1]
        assert historical[0]["content"] == "message-5"
        assert historical[-1]["content"] == "message-19"


# ============================================================================
# B3: build_enhanced_context tuple return
# ============================================================================

@pytest.mark.skip(reason="services.memory module removed in v5.0 — replaced by KnowledgeStore")
class TestBuildEnhancedContext:
    """Tests for memory.py build_enhanced_context() returning tuple — SKIPPED."""

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

    @patch("services.memory.get_semantic_memory")
    def test_filters_irrelevant_semantic_items(self, mock_get_mem):
        """Low-similarity semantic matches are excluded from prompt context."""
        from services.memory import build_enhanced_context

        mock_mem = MagicMock()
        mock_mem.retrieve_context.return_value = {
            "working_memory": [],
            "semantic_memory": [
                {"role": "user", "content": "unrelated", "similarity": 0.12, "score": 0.40},
                {"role": "assistant", "content": "relevant", "similarity": 0.80, "score": 0.85},
            ],
            "combined": [],
        }
        mock_get_mem.return_value = mock_mem

        _, semantic = build_enhanced_context(
            query="math formula",
            principal_id="user",
            context_messages=[],
        )

        assert semantic is not None
        assert len(semantic) == 1
        assert semantic[0]["content"] == "relevant"


# ============================================================================
# B4: _normalize_fact + _migrate_to_structured_profile
# ============================================================================

class TestNormalizeFact:
    """Tests for storage.py _normalize_fact() and _migrate_to_structured_profile()."""

    def test_normalizes_plain_string(self):
        from storage import _normalize_fact

        result = _normalize_fact("Likes Python")

        assert result["text"] == "Likes Python"
        assert result["category"] == "general"
        assert result["importance"] == 3
        assert result["deleted"] is False
        assert "created_at" in result

    def test_normalizes_legacy_rest_format(self):
        """Facts with 'fact' key converted to 'text' key."""
        from storage import _normalize_fact

        result = _normalize_fact(
            {"fact": "Prefers dark mode", "addedAt": 1700000000000, "category": "ui"}
        )

        assert result["text"] == "Prefers dark mode"
        assert result["category"] == "ui"
        assert result["created_at"] == 1700000000000
        assert result["deleted"] is False

    def test_canonical_format_passthrough(self):
        """Already-canonical facts pass through with defaults set."""
        from storage import _normalize_fact

        result = _normalize_fact(
            {"text": "Test", "category": "general", "importance": 4,
             "embedding": [0.1, 0.2], "created_at": 1700000000000}
        )

        assert result["text"] == "Test"
        assert result["importance"] == 4
        assert result["deleted"] is False

    def test_adds_missing_defaults(self):
        """Canonical facts with missing optional fields get defaults."""
        from storage import _normalize_fact

        result = _normalize_fact({"text": "Partial fact"})

        assert result["category"] == "general"
        assert result["importance"] == 3
        assert result["embedding"] is None
        assert result["deleted"] is False
        assert "created_at" in result

    def test_returns_none_for_invalid(self):
        """Non-string, non-dict entries return None."""
        from storage import _normalize_fact

        assert _normalize_fact(42) is None
        assert _normalize_fact(None) is None

    def test_returns_none_for_empty_dict(self):
        """Dict without 'text' or 'fact' returns None."""
        from storage import _normalize_fact

        assert _normalize_fact({"random": "value"}) is None


class TestMigrateToStructuredProfile:
    """Tests for storage.py _migrate_to_structured_profile()."""

    def test_v1_migration_creates_profile(self):
        from storage import _migrate_to_structured_profile

        memory = {
            "version": "1.0",
            "facts": [
                {"text": "User likes Python", "category": "general"},
                {"text": "User works at Acme", "category": "general"},
            ],
        }
        result = _migrate_to_structured_profile(memory)

        assert result["version"] == "2.0"
        assert "profile" in result
        assert isinstance(result["profile"], dict)
        assert "identity" in result["profile"]
        assert "work" in result["profile"]

    def test_v2_passthrough(self):
        """Already v2.0 memories pass through unchanged."""
        from storage import _migrate_to_structured_profile

        memory = {
            "version": "2.0",
            "facts": [{"text": "Test", "category": "general"}],
            "profile": {"identity": {}, "work": {}},
        }
        result = _migrate_to_structured_profile(memory)

        assert result["version"] == "2.0"

    def test_idempotent(self):
        """Running migrate twice produces same result."""
        from storage import _migrate_to_structured_profile

        memory = {"version": "1.0", "facts": ["String fact", {"fact": "Legacy"}]}
        first = _migrate_to_structured_profile(memory)
        second = _migrate_to_structured_profile(first)

        assert first["version"] == second["version"] == "2.0"
        assert len(first["facts"]) == len(second["facts"])

    def test_classifies_work_facts(self):
        """Facts about work get classified into the work category."""
        from storage import _migrate_to_structured_profile

        memory = {
            "version": "1.0",
            "facts": [{"text": "I work at Google", "category": "general"}],
        }
        result = _migrate_to_structured_profile(memory)

        assert result["facts"][0]["category"] == "work"

    def test_empty_facts_ok(self):
        """Migration handles empty facts list."""
        from storage import _migrate_to_structured_profile

        memory = {"version": "1.0", "facts": []}
        result = _migrate_to_structured_profile(memory)

        assert result["version"] == "2.0"
        assert result["facts"] == []
        assert "profile" in result
