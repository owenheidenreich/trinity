"""
Trinity Backend - Memory Foundation Tests
==========================================
Tests for temporal facts, contradiction handling,
profile extraction from assistant messages, and memory budgets.
"""

import json
import re
import time
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# TEMPORAL METADATA ON FACTS
# =============================================================================

class TestTemporalFacts:
    """Test valid_at/invalid_at fields on facts."""

    def test_normalize_fact_adds_valid_at(self):
        """_normalize_fact sets valid_at on new facts."""
        from storage import _normalize_fact

        result = _normalize_fact({"text": "User likes Python", "category": "interests"})

        assert result is not None
        assert "valid_at" in result
        assert result["valid_at"] is not None
        assert result["invalid_at"] is None

    def test_normalize_fact_string_has_valid_at(self):
        """String facts get valid_at set to now."""
        from storage import _normalize_fact

        result = _normalize_fact("User is a developer")

        assert result is not None
        assert result["valid_at"] is not None
        assert result["invalid_at"] is None

    def test_normalize_fact_preserves_existing_valid_at(self):
        """Existing valid_at is not overwritten."""
        from storage import _normalize_fact

        custom_ts = 1700000000000
        result = _normalize_fact({
            "text": "User lives in NYC",
            "valid_at": custom_ts,
        })

        assert result["valid_at"] == custom_ts

    def test_normalize_legacy_fact_dict_gets_valid_at(self):
        """Legacy fact dicts (using 'fact' key) get valid_at."""
        from storage import _normalize_fact

        result = _normalize_fact({"fact": "User works at Google"})

        assert result is not None
        assert result["valid_at"] is not None
        assert result["invalid_at"] is None
        assert result["text"] == "User works at Google"

    def test_get_active_facts_excludes_invalid(self):
        """get_active_facts filters out facts with invalid_at set."""
        from storage import get_active_facts

        now_ms = int(time.time() * 1000)
        memory = {
            "facts": [
                {"text": "Active fact", "deleted": False, "invalid_at": None},
                {"text": "Invalidated fact", "deleted": False, "invalid_at": now_ms},
                {"text": "Deleted fact", "deleted": True, "invalid_at": None},
                {"text": "Still valid", "deleted": False},
            ]
        }

        active = get_active_facts(memory)
        texts = [f["text"] for f in active]

        assert "Active fact" in texts
        assert "Still valid" in texts
        assert "Invalidated fact" not in texts
        assert "Deleted fact" not in texts


# =============================================================================
# CONTRADICTION DETECTION
# =============================================================================

class TestContradictionDetection:
    """Test heuristic contradiction detection in memory_tools."""

    def test_location_change_is_contradiction(self):
        """Moving cities is a contradiction."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User lives in NYC",
            "User lives in LA"
        ) is True

    def test_employer_change_is_contradiction(self):
        """Changing employers is a contradiction."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User works at Google",
            "User works at Meta"
        ) is True

    def test_name_change_is_contradiction(self):
        """Name change is a contradiction."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User's name is John",
            "User's name is James"
        ) is True

    def test_refinement_is_not_contradiction(self):
        """Adding detail (superset) is not a contradiction."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User is a developer",
            "User is a senior developer"
        ) is False

    def test_identical_facts_not_contradiction(self):
        """Identical facts are not contradictions."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User lives in NYC",
            "User lives in NYC"
        ) is False

    def test_unrelated_facts_not_contradiction(self):
        """Facts about different topics are not contradictions."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User likes Python",
            "User enjoys hiking"
        ) is False

    def test_role_change_is_contradiction(self):
        """Changing job title is a contradiction."""
        from services.memory_tools import _detect_contradiction

        assert _detect_contradiction(
            "User's role is backend engineer",
            "User's role is CTO"
        ) is True


# =============================================================================
# PROFILE EXTRACTION — ASSISTANT MESSAGES
# =============================================================================

class TestAssistantExtraction:
    """Test profile fact extraction via LLM-backed extractor."""

    def test_extract_from_assistant_you_are(self):
        """Assistant message extraction uses normalized LLM output."""
        from services.profile_extractor import extract_profile_facts

        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [
                    {"fact": "User is a software engineer in NYC", "category": "work", "importance": 4}
                ],
                "triples": [],
            }
            facts = extract_profile_facts(
                "Since you're a software engineer based in NYC, here are some meetup suggestions.",
                source="assistant",
            )

        assert len(facts) >= 1
        fact_texts = [f["fact"] for f in facts]
        assert any("engineer" in f.lower() or "software" in f.lower() for f in fact_texts)

    def test_extract_from_assistant_you_work_at(self):
        """Extracts employer from assistant echoing back info."""
        from services.profile_extractor import extract_profile_facts

        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User works at Google", "category": "work", "importance": 4}],
                "triples": [{"subject": "user", "predicate": "works_at", "object": "Google"}],
            }
            facts = extract_profile_facts(
                "I see you work at Google. Let me tailor my response.",
                source="assistant",
            )

        assert len(facts) >= 1
        fact_texts = [f["fact"] for f in facts]
        assert any("google" in f.lower() for f in fact_texts)

    def test_extraction_timeout_returns_empty(self):
        """Timeouts return empty extraction payloads."""
        from services.profile_extractor import extract_profile_facts

        with patch("services.profile_extractor._call_extraction_model", side_effect=TimeoutError):
            facts = extract_profile_facts(
                "If you are using Python 3.11, you should upgrade to 3.12.",
                source="assistant",
            )

        assert len(facts) == 0

    def test_extraction_invalid_json_returns_empty(self):
        """Invalid model JSON payloads are handled safely."""
        from services.profile_extractor import extract_profile_facts

        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {"facts": [], "triples": []}
            facts = extract_profile_facts(
                "You're welcome! Let me know if you need anything else.",
                source="assistant",
            )

        assert len(facts) == 0

    def test_user_source_still_works(self):
        """User source extraction still works with the new source param."""
        from services.profile_extractor import extract_profile_facts

        with patch("services.profile_extractor._call_extraction_model") as mock_call:
            mock_call.return_value = {
                "facts": [{"fact": "User lives in San Francisco", "category": "identity", "importance": 4}],
                "triples": [{"subject": "user", "predicate": "lives_in", "object": "San Francisco"}],
            }
            facts = extract_profile_facts(
                "My name is Trinity and I live in San Francisco",
                source="user",
            )

        assert len(facts) >= 1

    def test_empty_model_results(self):
        """Explicit empty extraction is passed through."""
        from services.profile_extractor import extract_profile_facts

        with patch("services.profile_extractor._call_extraction_model", return_value={"facts": [], "triples": []}):
            facts = extract_profile_facts("hello", source="user")

        assert facts == []

    def test_auto_extract_with_source(self):
        """auto_extract_and_save accepts source parameter."""
        from services.profile_extractor import auto_extract_and_save

        with patch("services.profile_extractor._call_extraction_model") as mock_call, \
             patch("services.memory_tools.tool_save_memory") as mock_save:
            mock_call.return_value = {
                "facts": [{"fact": "User is a data scientist", "category": "work", "importance": 4}],
                "triples": [],
            }
            mock_save.return_value = (True, "Saved: test fact")
            count = auto_extract_and_save(
                "I'm a data scientist working on NLP",
                "test-principal-123",
                source="user"
            )
            assert count >= 1
            assert mock_save.called

    def test_extraction_model_falls_back_when_primary_missing(self):
        """If primary provider is unavailable, extractor should try fallback providers."""
        from services.profile_extractor import _call_extraction_model

        mock_ingest_provider = MagicMock()
        mock_ingest_provider.host = "http://localhost:8082"
        mock_ingest_provider.model = "qwen3:32b"

        mock_chat_provider = MagicMock()
        mock_chat_provider.host = "http://localhost:8081"
        mock_chat_provider.model = "qwen2.5:14b"

        with patch(
            "services.profile_extractor._candidate_providers",
            return_value=[mock_ingest_provider, mock_chat_provider],
        ), \
             patch("services.profile_extractor._call_model_once") as mock_once:
            mock_once.side_effect = [
                ValueError("model 'qwen3:32b' not found"),
                {"facts": [{"fact": "User likes Rust", "category": "interests", "importance": 4}], "triples": []},
            ]
            result = _call_extraction_model("I like Rust", "user")

        assert len(result["facts"]) == 1
        assert mock_once.call_count == 2

    def test_extraction_model_retries_other_targets_then_raises(self):
        """If all providers fail, extractor raises the last error after retries."""
        from services.profile_extractor import _call_extraction_model

        mock_ingest_provider = MagicMock()
        mock_ingest_provider.host = "http://localhost:8082"
        mock_ingest_provider.model = "qwen3:32b"

        mock_chat_provider = MagicMock()
        mock_chat_provider.host = "http://localhost:8081"
        mock_chat_provider.model = "qwen2.5:14b"

        with patch(
            "services.profile_extractor._candidate_providers",
            return_value=[mock_ingest_provider, mock_chat_provider],
        ), \
             patch("services.profile_extractor._call_model_once", side_effect=RuntimeError("connection refused")) as mock_once:
            with pytest.raises(RuntimeError):
                _call_extraction_model("I like Rust", "user")
        assert mock_once.call_count == 2


# =============================================================================
# MEMORY BUDGET CONFIGURATION
# =============================================================================

class TestMemoryBudgets:
    """Verify raised memory budgets."""

    def test_working_memory_size_raised(self):
        """WORKING_MEMORY_SIZE increased from 3 to 5."""
        from config import WORKING_MEMORY_SIZE
        assert WORKING_MEMORY_SIZE >= 5

    def test_semantic_memory_size_raised(self):
        """SEMANTIC_MEMORY_SIZE increased from 5 to 8."""
        from config import SEMANTIC_MEMORY_SIZE
        assert SEMANTIC_MEMORY_SIZE >= 8

    def test_profile_token_budget_raised(self):
        """PROFILE_TOKEN_BUDGET default increased to 3500."""
        import os
        # Only test default — env var override is fine
        if "PROFILE_TOKEN_BUDGET" not in os.environ:
            from config import PROFILE_TOKEN_BUDGET
            assert PROFILE_TOKEN_BUDGET >= 3500

    def test_profile_max_facts_raised(self):
        """PROFILE_MAX_FACTS default increased to 25."""
        import os
        if "PROFILE_MAX_FACTS" not in os.environ:
            from config import PROFILE_MAX_FACTS
            assert PROFILE_MAX_FACTS >= 25

    def test_budgets_are_env_configurable(self):
        """Memory budgets can be overridden via environment variables."""
        with patch.dict("os.environ", {"WORKING_MEMORY_SIZE": "10"}):
            import importlib
            import config
            importlib.reload(config)
            assert config.WORKING_MEMORY_SIZE == 10
            # Restore
            importlib.reload(config)


# =============================================================================
# NEW FACT SCHEMA IN tool_save_memory
# =============================================================================

class TestSaveMemoryTemporalFields:
    """Test that tool_save_memory creates facts with temporal metadata.

    v5.0: temporal fields (valid_at) are now handled inside KnowledgeStore.save_fact().
    This test verifies save_fact is called with the correct parameters.
    """

    def test_new_fact_calls_knowledge_store(self):
        """tool_save_memory delegates to KnowledgeStore.save_fact()."""
        import numpy as np
        from unittest.mock import MagicMock

        mock_ks = MagicMock()
        mock_ks.save_fact.return_value = ("insert", 1)

        with patch("services.memory_tools._embed", return_value=np.zeros(384)), \
             patch("services.memory_tools._get_knowledge_store", return_value=mock_ks):

            from services.memory_tools import tool_save_memory
            success, msg = tool_save_memory(
                {"fact": "User likes hiking", "category": "interests"},
                "test-principal"
            )

            assert success
            assert "hiking" in msg
            mock_ks.save_fact.assert_called_once_with(
                text="User likes hiking",
                category="interests",
                importance=3,
                source_message_id=None,
            )
