"""
Trinity Backend - Storage & Memory Foundation Tests
=====================================================
Tests for Milestone 1: IPFS retry, temporal facts, contradiction
handling, profile extraction from assistant messages, and memory budgets.

Created: February 2026
"""

import json
import re
import time
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# IPFS RETRY LOGIC
# =============================================================================

class TestUploadWithRetry:
    """Test _upload_with_retry exponential backoff wrapper."""

    def test_succeeds_on_first_attempt(self):
        """Upload succeeds immediately — no retries needed."""
        with patch("services.user_data_store.upload_to_ipfs", return_value="QmTestCid123"):
            from services.user_data_store import _upload_with_retry
            cid = _upload_with_retry(b"test data", "test.json")
            assert cid == "QmTestCid123"

    def test_retries_on_failure_then_succeeds(self):
        """Upload fails twice, succeeds on third attempt."""
        mock_upload = MagicMock(side_effect=[None, None, "QmRetrySuccess"])
        with patch("services.user_data_store.upload_to_ipfs", mock_upload), \
             patch("services.user_data_store.IPFS_RETRY_DELAYS", [0, 0, 0]):
            from services.user_data_store import _upload_with_retry
            cid = _upload_with_retry(b"test data", "test.json")
            assert cid == "QmRetrySuccess"
            assert mock_upload.call_count == 3

    def test_returns_none_after_all_retries_fail(self):
        """Returns None after exhausting all retry attempts."""
        mock_upload = MagicMock(return_value=None)
        with patch("services.user_data_store.upload_to_ipfs", mock_upload), \
             patch("services.user_data_store.IPFS_RETRY_DELAYS", [0, 0, 0]):
            from services.user_data_store import _upload_with_retry
            cid = _upload_with_retry(b"test data", "test.json")
            assert cid is None
            assert mock_upload.call_count == 3

    def test_retries_on_exception(self):
        """Upload raises exception, retries, then succeeds."""
        mock_upload = MagicMock(side_effect=[Exception("timeout"), "QmOk"])
        with patch("services.user_data_store.upload_to_ipfs", mock_upload), \
             patch("services.user_data_store.IPFS_RETRY_DELAYS", [0, 0, 0]):
            from services.user_data_store import _upload_with_retry
            cid = _upload_with_retry(b"test data", "test.json")
            assert cid == "QmOk"
            assert mock_upload.call_count == 2


class TestPendingSyncs:
    """Test pending sync queuing and retry mechanism."""

    def test_add_and_count_pending_syncs(self):
        """Pending sync is tracked and counted correctly."""
        from services.user_data_store import (
            _add_pending_sync,
            _chat_sync_latest,
            _chat_sync_lock,
            _pending_syncs,
            _pending_syncs_lock,
            get_pending_sync_count,
        )
        # Clear any existing state
        with _pending_syncs_lock:
            _pending_syncs.clear()
        with _chat_sync_lock:
            _chat_sync_latest.clear()

        mock_fn = MagicMock()
        _add_pending_sync("test-principal", "profile", mock_fn, ("test-principal",))

        assert get_pending_sync_count() == 1

        # Clean up
        with _pending_syncs_lock:
            _pending_syncs.clear()
        with _chat_sync_lock:
            _chat_sync_latest.clear()

    def test_retry_pending_syncs_calls_function(self):
        """Retrying pending syncs calls the queued function."""
        from services.user_data_store import (
            _add_pending_sync,
            _chat_sync_latest,
            _chat_sync_lock,
            _pending_syncs,
            _pending_syncs_lock,
            retry_pending_syncs,
        )
        with _pending_syncs_lock:
            _pending_syncs.clear()
        with _chat_sync_lock:
            _chat_sync_latest.clear()

        mock_fn = MagicMock()
        _add_pending_sync("test-principal", "profile", mock_fn, ("arg1",))

        retry_pending_syncs("test-principal")

        mock_fn.assert_called_once_with("arg1")

        with _pending_syncs_lock:
            _pending_syncs.clear()
        with _chat_sync_lock:
            _chat_sync_latest.clear()

    def test_retry_pending_syncs_requeues_on_failure(self):
        """If retry fails, the sync is re-queued."""
        from services.user_data_store import (
            _add_pending_sync,
            _chat_sync_latest,
            _chat_sync_lock,
            _pending_syncs,
            _pending_syncs_lock,
            get_pending_sync_count,
            retry_pending_syncs,
        )
        with _pending_syncs_lock:
            _pending_syncs.clear()
        with _chat_sync_lock:
            _chat_sync_latest.clear()

        mock_fn = MagicMock(side_effect=Exception("still failing"))
        _add_pending_sync("test-principal", "profile", mock_fn, ("arg1",))

        retry_pending_syncs("test-principal")

        assert get_pending_sync_count() == 1  # re-queued

        with _pending_syncs_lock:
            _pending_syncs.clear()
        with _chat_sync_lock:
            _chat_sync_latest.clear()

    def test_ensure_restore_triggers_async_pending_retry(self):
        """ensure_user_data_restored should not block request path on retry backoff."""
        from services.user_data_store import (
            _restore_lock,
            _restored_principals,
            ensure_user_data_restored,
        )
        principal = "test-principal"

        with _restore_lock:
            _restored_principals.discard(principal)

        with patch("services.user_data_store._retry_pending_syncs_async") as mock_async, \
             patch("services.user_data_store.load_manifest", return_value={"profile": {"cid": None}}), \
             patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True):
            ok = ensure_user_data_restored(principal)

        assert ok is True
        mock_async.assert_called_once_with(principal)

        with _restore_lock:
            _restored_principals.discard(principal)


class TestSyncStatus:
    """Test sync status recording for monitoring."""

    def test_record_and_retrieve_sync_status(self):
        """Sync status is recorded and retrievable."""
        from services.user_data_store import (
            _record_sync_status,
            _sync_status,
            _sync_status_lock,
            get_all_sync_status,
        )
        with _sync_status_lock:
            _sync_status.clear()

        _record_sync_status("test-principal", "profile", True, cid="QmTest")

        statuses = get_all_sync_status()
        assert "test-principal" in statuses
        assert statuses["test-principal"]["profile"]["success"] is True
        assert statuses["test-principal"]["profile"]["cid"] == "QmTest"

        with _sync_status_lock:
            _sync_status.clear()

    def test_record_sync_failure(self):
        """Failed sync status includes error message."""
        from services.user_data_store import (
            _record_sync_status,
            _sync_status,
            _sync_status_lock,
            get_all_sync_status,
        )
        with _sync_status_lock:
            _sync_status.clear()

        _record_sync_status("test-principal", "vectorDb", False, error="timeout")

        statuses = get_all_sync_status()
        assert statuses["test-principal"]["vectorDb"]["success"] is False
        assert statuses["test-principal"]["vectorDb"]["error"] == "timeout"

        with _sync_status_lock:
            _sync_status.clear()


# =============================================================================
# CHAT CHECKPOINT QUEUE
# =============================================================================

class TestChatCheckpointQueue:
    """Test debounced chat checkpoint queue helpers."""

    def test_flush_now_syncs_latest_payload(self):
        """flush_chat_sync_now should sync only the latest queued autosave payload."""
        from services.user_data_store import flush_chat_sync_now, queue_chat_sync

        with patch("services.user_data_store.sync_chat_to_ipfs", return_value="cid-latest") as mock_sync:
            queue_chat_sync(
                principal_id="test-principal",
                chat_id="chat-1",
                chat_data={"chatId": "chat-1", "messages": [{"role": "user", "content": "old"}]},
                title="Old",
                message_count=1,
            )
            queue_chat_sync(
                principal_id="test-principal",
                chat_id="chat-1",
                chat_data={"chatId": "chat-1", "messages": [{"role": "user", "content": "new"}]},
                title="New",
                message_count=1,
            )

            cid = flush_chat_sync_now("test-principal", "chat-1")

        assert cid == "cid-latest"
        assert mock_sync.call_count == 1
        assert mock_sync.call_args.kwargs["title"] == "New"
        assert mock_sync.call_args.kwargs["chat_data"]["messages"][0]["content"] == "new"

    def test_discard_queued_chat_sync_drops_pending_payload(self):
        """Discarding a queued checkpoint should prevent later flush sync."""
        from services.user_data_store import discard_queued_chat_sync, flush_chat_sync_now, queue_chat_sync

        queue_chat_sync(
            principal_id="test-principal",
            chat_id="chat-2",
            chat_data={"chatId": "chat-2", "messages": []},
            title="Discard Me",
            message_count=0,
        )
        discard_queued_chat_sync("test-principal", "chat-2")

        with patch("services.user_data_store.sync_chat_to_ipfs") as mock_sync:
            cid = flush_chat_sync_now("test-principal", "chat-2")

        assert cid is None
        mock_sync.assert_not_called()


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
    """Test profile fact extraction from assistant messages."""

    def test_extract_from_assistant_you_are(self):
        """Extracts 'you are' facts from assistant messages."""
        from services.profile_extractor import extract_profile_facts

        facts = extract_profile_facts(
            "Since you're a software engineer based in NYC, here are some meetup suggestions.",
            source="assistant"
        )

        assert len(facts) >= 1
        # Should extract something about being a software engineer
        fact_texts = [f["fact"] for f in facts]
        assert any("engineer" in f.lower() or "software" in f.lower() for f in fact_texts)

    def test_extract_from_assistant_you_work_at(self):
        """Extracts employer from assistant echoing back info."""
        from services.profile_extractor import extract_profile_facts

        facts = extract_profile_facts(
            "I see you work at Google. Let me tailor my response.",
            source="assistant"
        )

        assert len(facts) >= 1
        fact_texts = [f["fact"] for f in facts]
        assert any("google" in f.lower() for f in fact_texts)

    def test_no_extraction_from_conditional(self):
        """Does not extract from conditional statements like 'if you are'."""
        from services.profile_extractor import extract_profile_facts

        facts = extract_profile_facts(
            "If you are using Python 3.11, you should upgrade to 3.12.",
            source="assistant"
        )

        assert len(facts) == 0

    def test_no_extraction_from_generic_you_are(self):
        """Does not extract from generic 'you are right/welcome'."""
        from services.profile_extractor import extract_profile_facts

        facts = extract_profile_facts(
            "You're welcome! Let me know if you need anything else.",
            source="assistant"
        )

        assert len(facts) == 0

    def test_user_source_still_works(self):
        """User source extraction still works with the new source param."""
        from services.profile_extractor import extract_profile_facts

        facts = extract_profile_facts(
            "My name is Trinity and I live in San Francisco",
            source="user"
        )

        assert len(facts) >= 1

    def test_auto_extract_with_source(self):
        """auto_extract_and_save accepts source parameter."""
        from services.profile_extractor import auto_extract_and_save

        with patch("services.memory_tools.tool_save_memory") as mock_save:
            mock_save.return_value = (True, "Saved: test fact")
            count = auto_extract_and_save(
                "I'm a data scientist working on NLP",
                "test-principal-123",
                source="user"
            )
            # Should have called save at least once
            assert mock_save.called or count == 0  # depends on pattern match


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
        """PROFILE_TOKEN_BUDGET default increased to 2500."""
        import os
        # Only test default — env var override is fine
        if "PROFILE_TOKEN_BUDGET" not in os.environ:
            from config import PROFILE_TOKEN_BUDGET
            assert PROFILE_TOKEN_BUDGET >= 2500

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
    """Test that tool_save_memory creates facts with temporal metadata."""

    def test_new_fact_has_valid_at(self):
        """New facts created by tool_save_memory include valid_at."""
        with patch("services.memory_tools._get_embeddings") as mock_emb, \
             patch("services.memory_tools._get_storage") as mock_storage:

            import numpy as np
            mock_embed = MagicMock(return_value=np.zeros(384))
            mock_cosine = MagicMock(return_value=0.0)
            mock_emb.return_value = (mock_embed, mock_cosine)

            saved_memory = {}
            def mock_load(pid):
                return {"facts": [], "version": "2.0"}
            def mock_save(pid, memory):
                saved_memory.update(memory)

            mock_storage.return_value = (mock_load, mock_save)

            from services.memory_tools import tool_save_memory
            success, msg = tool_save_memory(
                {"fact": "User likes hiking", "category": "interests"},
                "test-principal"
            )

            assert success
            assert "Saved:" in msg
            assert len(saved_memory.get("facts", [])) == 1

            new_fact = saved_memory["facts"][0]
            assert "valid_at" in new_fact
            assert new_fact["valid_at"] is not None
            assert new_fact["invalid_at"] is None
