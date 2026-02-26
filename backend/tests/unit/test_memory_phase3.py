"""
Memory System Tests — Conversation Summaries, Fact Normalization, Profile Migration
"""

import time
from unittest.mock import MagicMock, patch

import pytest


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
# _normalize_fact + _migrate_to_structured_profile
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
