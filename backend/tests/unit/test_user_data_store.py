"""
Tests for services/user_data_store.py — IPFS Persistence Pipeline

Covers:
- _upload_with_retry (dedup, retry, all-fail)
- Manifest sync/find/rollback
- Profile sync/restore round-trip
- Vector DB sync/restore round-trip
- Graph DB sync/restore round-trip
- Chat checkpoint sync
- unpin_cid
- Pending sync queue + retry
- Debounce triggers (notify_message_indexed, notify_profile_changed, notify_graph_changed)
- ensure_user_data_restored orchestration
- hydrate_user_data_async threading
- Sync status recording
"""

import json
import hashlib
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


FAKE_PRINCIPAL = "abc123-test-principal-id-long-enough"
FAKE_CID = "QmTestCid123456789abcdefghijklmnopqrstuvwxyz"
FAKE_CID_2 = "QmSecondCidABCDEF0123456789abcdefghijklmno"
FAKE_PASSPHRASE = "test-passphrase-for-unit-tests"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def clean_module_state():
    """Reset module-level state between tests."""
    import services.user_data_store as uds
    uds._restored_principals.clear()
    uds._restore_inflight.clear()
    uds._pending_syncs.clear()
    uds._upload_dedupe.clear()
    uds._upload_latest.clear()
    uds._sync_status.clear()
    uds._vector_sync_counters.clear()
    uds._vector_sync_timestamps.clear()
    uds._profile_sync_timers.clear()
    uds._profile_sync_latest.clear()
    uds._graph_sync_timers.clear()
    uds._manifest_sync_timers.clear()
    uds._manifest_sync_latest.clear()
    uds._chat_sync_timers.clear()
    uds._chat_sync_latest.clear()
    uds._chat_sync_started_at.clear()
    yield


@pytest.fixture
def mock_upload():
    """Mock upload_to_ipfs to return a CID."""
    with patch("services.user_data_store.upload_to_ipfs", return_value=FAKE_CID) as m:
        yield m


@pytest.fixture
def mock_download():
    """Mock download_from_ipfs to return bytes."""
    with patch("services.user_data_store.download_from_ipfs") as m:
        yield m


@pytest.fixture
def mock_encryption():
    """Mock encrypt/decrypt to be identity functions.
    encrypt returns dict with 'encryption' key so load_manifest detects it as encrypted.
    decrypt extracts the original data."""
    with patch("services.user_data_store.encrypt_for_user",
               side_effect=lambda d, p: {"encryption": "mock", "data": d}) as enc, \
         patch("services.user_data_store.decrypt_for_user",
               side_effect=lambda d, p: d.get("data", d)) as dec:
        yield enc, dec


@pytest.fixture
def mock_session_passphrase():
    """Mock session passphrase."""
    with patch("services.user_data_store.get_session_passphrase", return_value=FAKE_PASSPHRASE):
        yield


@pytest.fixture
def tmp_chats_dir(tmp_path):
    """Create a temp CHATS_DIR and patch it."""
    chats = tmp_path / "chats"
    chats.mkdir()
    user_dir = chats / FAKE_PRINCIPAL
    user_dir.mkdir()
    with patch("services.user_data_store.CHATS_DIR", str(chats)):
        yield chats


# =============================================================================
# _upload_with_retry
# =============================================================================


class TestUploadWithRetry:
    """Test upload retry logic and content-hash deduplication."""

    def test_success_first_try(self, mock_upload):
        from services.user_data_store import _upload_with_retry
        cid = _upload_with_retry(b"hello", "test.json", FAKE_PRINCIPAL)
        assert cid == FAKE_CID
        mock_upload.assert_called_once()

    def test_retry_on_first_failure(self):
        from services.user_data_store import _upload_with_retry
        with patch("services.user_data_store.upload_to_ipfs", side_effect=[None, FAKE_CID]) as m, \
             patch("services.user_data_store.time.sleep"):
            cid = _upload_with_retry(b"hello", "test.json", FAKE_PRINCIPAL)
        assert cid == FAKE_CID
        assert m.call_count == 2

    def test_all_retries_fail(self):
        from services.user_data_store import _upload_with_retry
        with patch("services.user_data_store.upload_to_ipfs", return_value=None), \
             patch("services.user_data_store.time.sleep"):
            cid = _upload_with_retry(b"hello", "test.json", FAKE_PRINCIPAL)
        assert cid is None

    def test_content_hash_dedup_hit(self, mock_upload):
        from services.user_data_store import _upload_with_retry
        data = b"same content"
        # First call uploads
        cid1 = _upload_with_retry(data, "test.json", FAKE_PRINCIPAL)
        assert cid1 == FAKE_CID
        assert mock_upload.call_count == 1

        # Second call with same content should skip upload
        cid2 = _upload_with_retry(data, "test.json", FAKE_PRINCIPAL)
        assert cid2 == FAKE_CID
        assert mock_upload.call_count == 1  # no additional upload

    def test_different_content_uploads_again(self, mock_upload):
        from services.user_data_store import _upload_with_retry
        cid1 = _upload_with_retry(b"content A", "test.json", FAKE_PRINCIPAL)
        # Different content
        mock_upload.return_value = FAKE_CID_2
        cid2 = _upload_with_retry(b"content B", "test.json", FAKE_PRINCIPAL)
        assert mock_upload.call_count == 2

    def test_no_principal_skips_dedup(self):
        from services.user_data_store import _upload_with_retry
        with patch("services.user_data_store.upload_to_ipfs", return_value=FAKE_CID):
            cid = _upload_with_retry(b"data", "test.json")
        assert cid == FAKE_CID

    def test_exception_triggers_retry(self):
        from services.user_data_store import _upload_with_retry
        with patch("services.user_data_store.upload_to_ipfs",
                    side_effect=[Exception("network"), FAKE_CID]) as m, \
             patch("services.user_data_store.time.sleep"):
            cid = _upload_with_retry(b"hello", "test.json", FAKE_PRINCIPAL)
        assert cid == FAKE_CID
        assert m.call_count == 2


# =============================================================================
# SYNC STATUS
# =============================================================================


class TestSyncStatus:
    """Test sync status recording and retrieval."""

    def test_record_success(self):
        from services.user_data_store import _record_sync_status, get_all_sync_status
        _record_sync_status(FAKE_PRINCIPAL, "profile", True, cid=FAKE_CID)
        status = get_all_sync_status()
        assert FAKE_PRINCIPAL in status
        assert status[FAKE_PRINCIPAL]["profile"]["success"] is True
        assert status[FAKE_PRINCIPAL]["profile"]["cid"] == FAKE_CID

    def test_record_failure(self):
        from services.user_data_store import _record_sync_status, get_all_sync_status
        _record_sync_status(FAKE_PRINCIPAL, "profile", False, error="timeout")
        status = get_all_sync_status()
        assert status[FAKE_PRINCIPAL]["profile"]["success"] is False
        assert status[FAKE_PRINCIPAL]["profile"]["error"] == "timeout"


# =============================================================================
# PENDING SYNCS
# =============================================================================


class TestPendingSyncs:
    """Test pending sync queue and retry logic."""

    def test_add_and_retry_pending_sync(self):
        from services.user_data_store import _add_pending_sync, retry_pending_syncs, _pending_syncs

        called = []
        def dummy_sync(pid):
            called.append(pid)

        _add_pending_sync(FAKE_PRINCIPAL, "profile", dummy_sync, (FAKE_PRINCIPAL,))
        assert len(_pending_syncs) == 1

        retry_pending_syncs(FAKE_PRINCIPAL)
        assert len(called) == 1
        assert called[0] == FAKE_PRINCIPAL
        assert len(_pending_syncs) == 0

    def test_retry_requeues_on_failure(self):
        from services.user_data_store import _add_pending_sync, retry_pending_syncs, _pending_syncs

        def failing_sync(pid):
            raise Exception("still broken")

        _add_pending_sync(FAKE_PRINCIPAL, "profile", failing_sync, (FAKE_PRINCIPAL,))
        retry_pending_syncs(FAKE_PRINCIPAL)
        # Should be re-queued
        assert len(_pending_syncs) == 1

    def test_pending_sync_count(self):
        from services.user_data_store import _add_pending_sync, get_pending_sync_count
        _add_pending_sync(FAKE_PRINCIPAL, "profile", lambda: None, ())
        _add_pending_sync(FAKE_PRINCIPAL, "vectorDb", lambda: None, ())
        assert get_pending_sync_count() >= 2


# =============================================================================
# MANIFEST
# =============================================================================


class TestManifest:
    """Test manifest load/save/sync/find/rollback."""

    def test_default_manifest(self):
        from services.user_data_store import _default_manifest
        m = _default_manifest(FAKE_PRINCIPAL)
        assert m["principal"] == FAKE_PRINCIPAL
        assert m["version"] == 2
        assert m["profile"]["cid"] is None
        assert m["chats"] == []

    def test_save_and_load_manifest(self, tmp_chats_dir, mock_encryption):
        from services.user_data_store import save_manifest, load_manifest, _default_manifest
        with patch("services.user_data_store._get_manifest_path",
                    return_value=tmp_chats_dir / FAKE_PRINCIPAL / "manifest.json"):
            manifest = _default_manifest(FAKE_PRINCIPAL)
            manifest["profile"]["cid"] = FAKE_CID
            save_manifest(FAKE_PRINCIPAL, manifest)
            loaded = load_manifest(FAKE_PRINCIPAL)
        assert loaded["profile"]["cid"] == FAKE_CID

    def test_sync_manifest_to_ipfs_success(self, mock_upload, mock_encryption):
        from services.user_data_store import sync_manifest_to_ipfs, _default_manifest
        manifest = _default_manifest(FAKE_PRINCIPAL)
        with patch("services.user_data_store.save_manifest"):
            cid = sync_manifest_to_ipfs(FAKE_PRINCIPAL, manifest)
        assert cid == FAKE_CID
        assert manifest["currentManifestCid"] == FAKE_CID

    def test_sync_manifest_to_ipfs_failure_queues_pending(self, mock_encryption):
        from services.user_data_store import sync_manifest_to_ipfs, _default_manifest, _pending_syncs
        with patch("services.user_data_store._upload_with_retry", return_value=None), \
             patch("services.user_data_store.save_manifest"):
            manifest = _default_manifest(FAKE_PRINCIPAL)
            cid = sync_manifest_to_ipfs(FAKE_PRINCIPAL, manifest)
        assert cid is None
        assert any(k[1] == "manifest" for k in _pending_syncs)

    def test_find_manifest_on_ipfs(self, mock_download, mock_encryption):
        from services.user_data_store import find_manifest_on_ipfs
        manifest_data = {"version": 2, "principal": FAKE_PRINCIPAL, "profile": {"cid": FAKE_CID}}
        encrypted = {"encryption": "mock", "data": manifest_data}
        mock_download.return_value = json.dumps(encrypted).encode("utf-8")
        with patch("services.user_data_store.get_lighthouse_uploads", return_value=[
            {"fileName": f"{FAKE_PRINCIPAL[:16]}_manifest.json", "cid": FAKE_CID}
        ]):
            result = find_manifest_on_ipfs(FAKE_PRINCIPAL)
        assert result is not None

    def test_find_manifest_no_uploads(self):
        from services.user_data_store import find_manifest_on_ipfs
        with patch("services.user_data_store.get_lighthouse_uploads", return_value=[]):
            result = find_manifest_on_ipfs(FAKE_PRINCIPAL)
        assert result is None

    def test_rollback_manifest_success(self, mock_download, mock_encryption, tmp_chats_dir):
        from services.user_data_store import rollback_manifest, save_manifest, load_manifest
        manifest_path = tmp_chats_dir / FAKE_PRINCIPAL / "manifest.json"
        with patch("services.user_data_store._get_manifest_path", return_value=manifest_path):
            # Save a manifest with history
            manifest = {
                "version": 2, "principal": FAKE_PRINCIPAL, "manifestVersion": 3,
                "manifestHistory": [
                    {"version": 1, "cid": FAKE_CID, "updatedAt": 1000},
                    {"version": 2, "cid": FAKE_CID_2, "updatedAt": 2000},
                ],
                "profile": {"cid": None}, "memoryIndex": {"cid": None},
                "graphIndex": {"cid": None}, "chats": [],
                "currentManifestCid": None, "totalBytes": 0,
                "createdAt": 1000, "lastUpdated": 3000,
            }
            save_manifest(FAKE_PRINCIPAL, manifest)

            old_manifest = {"version": 2, "principal": FAKE_PRINCIPAL, "profile": {"cid": "old-profile"}}
            encrypted_old = {"encryption": "mock", "data": old_manifest}
            mock_download.return_value = json.dumps(encrypted_old).encode("utf-8")

            result = rollback_manifest(FAKE_PRINCIPAL)
        assert result is True

    def test_rollback_manifest_no_history(self, tmp_chats_dir, mock_encryption):
        from services.user_data_store import rollback_manifest, save_manifest
        manifest_path = tmp_chats_dir / FAKE_PRINCIPAL / "manifest.json"
        with patch("services.user_data_store._get_manifest_path", return_value=manifest_path):
            manifest = {
                "version": 2, "principal": FAKE_PRINCIPAL, "manifestHistory": [],
                "profile": {"cid": None}, "memoryIndex": {"cid": None},
                "graphIndex": {"cid": None}, "chats": [],
                "currentManifestCid": None, "manifestVersion": 1,
                "totalBytes": 0, "createdAt": 1000, "lastUpdated": 1000,
            }
            save_manifest(FAKE_PRINCIPAL, manifest)
            result = rollback_manifest(FAKE_PRINCIPAL)
        assert result is False


# =============================================================================
# PROFILE SYNC
# =============================================================================


class TestProfileSync:
    """Test profile sync/restore round-trip."""

    def test_sync_profile_success(self, mock_upload, mock_encryption):
        from services.user_data_store import sync_profile_to_ipfs
        memory = {"facts": [{"text": "likes Python", "category": "interests"}]}
        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": None, "lastUpdated": None, "factCount": 0},
            "memoryIndex": {"cid": None}, "graphIndex": {"cid": None}, "chats": [],
        }), patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.sync_manifest_to_ipfs"), \
             patch("services.user_data_store.unpin_cid"):
            cid = sync_profile_to_ipfs(FAKE_PRINCIPAL, memory)
        assert cid == FAKE_CID

    def test_sync_profile_failure_queues_pending(self, mock_encryption):
        from services.user_data_store import sync_profile_to_ipfs, _pending_syncs
        with patch("services.user_data_store._upload_with_retry", return_value=None):
            cid = sync_profile_to_ipfs(FAKE_PRINCIPAL, {"facts": []})
        assert cid is None
        assert any("profile" in k[1] for k in _pending_syncs)

    def test_restore_profile_from_ipfs(self, mock_download, mock_encryption, tmp_chats_dir):
        from services.user_data_store import restore_profile_from_ipfs
        memory = {"facts": [{"text": "likes cats"}]}
        encrypted = {"encryption": "mock", "data": memory}
        mock_download.return_value = json.dumps(encrypted).encode("utf-8")

        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID},
            "memoryIndex": {"cid": None}, "graphIndex": {"cid": None}, "chats": [],
        }):
            # Make local path not exist
            with patch("storage.get_user_memory_path", return_value=tmp_chats_dir / "nonexistent" / "user_memory.json"), \
                 patch("storage.save_user_memory") as save_mock:
                result = restore_profile_from_ipfs(FAKE_PRINCIPAL)
        assert result is True

    def test_restore_profile_local_exists_skips(self, tmp_chats_dir):
        from services.user_data_store import restore_profile_from_ipfs
        mem_path = tmp_chats_dir / FAKE_PRINCIPAL / "user_memory.json"
        mem_path.write_text("{}")
        with patch("storage.get_user_memory_path", return_value=mem_path):
            result = restore_profile_from_ipfs(FAKE_PRINCIPAL)
        assert result is True

    def test_restore_profile_no_cid_new_user(self):
        from services.user_data_store import restore_profile_from_ipfs
        with patch("storage.get_user_memory_path", return_value=Path("/nonexistent/path")), \
             patch("services.user_data_store.load_manifest", return_value={
                 "profile": {"cid": None},
             }):
            result = restore_profile_from_ipfs(FAKE_PRINCIPAL)
        assert result is True


# =============================================================================
# VECTOR DB SYNC
# =============================================================================


class TestVectorDbSync:
    """Test vector DB sync/restore."""

    def test_sync_vector_db_success(self, mock_upload, mock_encryption):
        from services.user_data_store import sync_vector_db_to_ipfs
        mock_store = MagicMock()
        mock_store.export_for_ipfs.return_value = b"sqlite-data"
        mock_store.get_stats.return_value = {"message_embeddings": 42}
        with patch("services.vector_store.get_vector_store", return_value=mock_store), \
             patch("services.user_data_store.load_manifest", return_value={
                 "memoryIndex": {"cid": None, "lastUpdated": None, "messageCount": 0},
                 "profile": {"cid": None}, "graphIndex": {"cid": None}, "chats": [],
             }), patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.sync_manifest_to_ipfs"), \
             patch("services.user_data_store.unpin_cid"):
            cid = sync_vector_db_to_ipfs(FAKE_PRINCIPAL)
        assert cid == FAKE_CID

    def test_sync_vector_db_empty_data(self, mock_encryption):
        from services.user_data_store import sync_vector_db_to_ipfs
        mock_store = MagicMock()
        mock_store.export_for_ipfs.return_value = b""
        with patch("services.vector_store.get_vector_store", return_value=mock_store):
            cid = sync_vector_db_to_ipfs(FAKE_PRINCIPAL)
        assert cid is None


# =============================================================================
# GRAPH DB SYNC
# =============================================================================


class TestGraphDbSync:
    """Test graph memory sync/restore."""

    def test_sync_graph_db_success(self, mock_upload, mock_encryption, tmp_chats_dir):
        from services.user_data_store import sync_graph_db_to_ipfs
        user_dir = tmp_chats_dir / FAKE_PRINCIPAL
        (user_dir / "identity.kuzu").write_bytes(b"kuzu data")
        (user_dir / "identity_triples.json").write_text('[["A", "knows", "B"]]')

        with patch("services.user_data_store.load_manifest", return_value={
            "graphIndex": {"cid": None, "lastUpdated": None, "tripleCount": 0},
            "profile": {"cid": None}, "memoryIndex": {"cid": None}, "chats": [],
        }), patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.sync_manifest_to_ipfs"), \
             patch("services.user_data_store.unpin_cid"):
            cid = sync_graph_db_to_ipfs(FAKE_PRINCIPAL)
        assert cid == FAKE_CID

    def test_restore_graph_db_success(self, mock_download, mock_encryption, tmp_chats_dir):
        from services.user_data_store import restore_graph_db_from_ipfs
        import base64
        payload = {
            "type": "identity_graph",
            "graph_db_b64": base64.b64encode(b"kuzu bytes").decode("utf-8"),
            "triples": [["X", "likes", "Y"]],
        }
        encrypted = {"encryption": "mock", "data": payload}
        mock_download.return_value = json.dumps(encrypted).encode("utf-8")

        manifest = {"graphIndex": {"cid": FAKE_CID}}
        result = restore_graph_db_from_ipfs(FAKE_PRINCIPAL, manifest)
        assert result is True
        # Verify files were written
        user_dir = tmp_chats_dir / FAKE_PRINCIPAL
        assert (user_dir / "identity.kuzu").exists()
        assert (user_dir / "identity_triples.json").exists()

    def test_restore_graph_db_no_cid(self):
        from services.user_data_store import restore_graph_db_from_ipfs
        manifest = {"graphIndex": {"cid": None}}
        with patch("services.user_data_store.CHATS_DIR", "/tmp/test"):
            result = restore_graph_db_from_ipfs(FAKE_PRINCIPAL, manifest)
        assert result is True  # No graph = OK for new users


# =============================================================================
# CHAT CHECKPOINT SYNC
# =============================================================================


class TestChatCheckpointSync:
    """Test chat blob sync and queue/debounce."""

    def test_sync_chat_success(self, mock_upload, mock_encryption):
        from services.user_data_store import sync_chat_to_ipfs
        chat_data = {"messages": [{"role": "user", "content": "hi"}]}
        with patch("services.user_data_store.update_chat_in_manifest"):
            cid = sync_chat_to_ipfs(FAKE_PRINCIPAL, "chat-001", chat_data, "Test Chat", 1)
        assert cid == FAKE_CID

    def test_sync_chat_failure_queues_pending(self, mock_encryption):
        from services.user_data_store import sync_chat_to_ipfs, _pending_syncs
        with patch("services.user_data_store._upload_with_retry", return_value=None):
            cid = sync_chat_to_ipfs(FAKE_PRINCIPAL, "chat-001", {}, "Title", 1)
        assert cid is None
        assert any("chat" in k[1] for k in _pending_syncs)

    def test_queue_chat_sync_debounces(self, mock_encryption):
        from services.user_data_store import queue_chat_sync, _chat_sync_latest
        queue_chat_sync(FAKE_PRINCIPAL, "chat-001", {"v": 1}, "Title", 1)
        queue_chat_sync(FAKE_PRINCIPAL, "chat-001", {"v": 2}, "Title", 2)
        # Both should coalesce — latest wins
        key = (FAKE_PRINCIPAL, "chat-001")
        assert key in _chat_sync_latest
        assert _chat_sync_latest[key]["message_count"] == 2

    def test_discard_queued_chat_sync(self, mock_encryption):
        from services.user_data_store import queue_chat_sync, discard_queued_chat_sync, _chat_sync_latest
        queue_chat_sync(FAKE_PRINCIPAL, "chat-001", {}, "Title", 1)
        discard_queued_chat_sync(FAKE_PRINCIPAL, "chat-001")
        key = (FAKE_PRINCIPAL, "chat-001")
        assert key not in _chat_sync_latest


# =============================================================================
# UNPIN CID
# =============================================================================


class TestUnpinCid:
    """Test CID unpinning on Lighthouse."""

    def test_unpin_success(self):
        from services.user_data_store import unpin_cid
        with patch("config.http_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_session.delete.return_value = mock_resp
            with patch("config.LIGHTHOUSE_API_KEY", "test-key"):
                unpin_cid(FAKE_CID)
            mock_session.delete.assert_called_once()

    def test_unpin_no_api_key(self):
        from services.user_data_store import unpin_cid
        with patch("config.http_session") as mock_session:
            with patch("config.LIGHTHOUSE_API_KEY", ""):
                unpin_cid(FAKE_CID)
            mock_session.delete.assert_not_called()

    def test_unpin_network_error_silent(self):
        from services.user_data_store import unpin_cid
        with patch("config.http_session") as mock_session:
            mock_session.delete.side_effect = Exception("network error")
            with patch("config.LIGHTHOUSE_API_KEY", "test-key"):
                # Should not raise
                unpin_cid(FAKE_CID)

    def test_unpin_404_silent(self):
        from services.user_data_store import unpin_cid
        with patch("config.http_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_session.delete.return_value = mock_resp
            with patch("config.LIGHTHOUSE_API_KEY", "test-key"):
                unpin_cid(FAKE_CID)  # Should not raise


# =============================================================================
# ENSURE USER DATA RESTORED
# =============================================================================


class TestEnsureUserDataRestored:
    """Test the full restore orchestration."""

    def test_restore_all_success(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import ensure_user_data_restored, _restored_principals
        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": FAKE_CID},
            "graphIndex": {"cid": FAKE_CID}, "chats": [],
        }), patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):
            result = ensure_user_data_restored(FAKE_PRINCIPAL)
        assert result is True
        assert FAKE_PRINCIPAL in _restored_principals

    def test_restore_idempotent(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import ensure_user_data_restored, _restored_principals
        _restored_principals.add(FAKE_PRINCIPAL)
        with patch("services.user_data_store._retry_pending_syncs_async"):
            result = ensure_user_data_restored(FAKE_PRINCIPAL)
        assert result is True  # immediate return

    def test_partial_restore_marks_restored_if_profile_ok(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import ensure_user_data_restored, _restored_principals
        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": None},
            "graphIndex": {"cid": None}, "chats": [],
        }), patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=False), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=False), \
             patch("services.user_data_store._retry_pending_syncs_async"):
            result = ensure_user_data_restored(FAKE_PRINCIPAL)
        assert result is True
        assert FAKE_PRINCIPAL in _restored_principals

    def test_profile_fail_does_not_mark_restored(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import ensure_user_data_restored, _restored_principals
        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": None},
            "graphIndex": {"cid": None}, "chats": [],
        }), patch("services.user_data_store.restore_profile_from_ipfs", return_value=False), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):
            result = ensure_user_data_restored(FAKE_PRINCIPAL)
        assert result is False
        assert FAKE_PRINCIPAL not in _restored_principals

    def test_searches_ipfs_when_local_manifest_empty(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import ensure_user_data_restored
        empty_manifest = {
            "profile": {"cid": None}, "memoryIndex": {"cid": None},
            "graphIndex": {"cid": None}, "chats": [],
        }
        remote_manifest = {
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": None},
            "graphIndex": {"cid": None}, "chats": [],
        }
        with patch("services.user_data_store.load_manifest", return_value=empty_manifest), \
             patch("services.user_data_store.find_manifest_on_ipfs", return_value=remote_manifest) as find_mock, \
             patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):
            ensure_user_data_restored(FAKE_PRINCIPAL)
        find_mock.assert_called_once()


# =============================================================================
# HYDRATE USER DATA ASYNC
# =============================================================================


class TestHydrateUserDataAsync:
    """Test async hydration threading."""

    def test_hydrate_runs_in_background(self, mock_encryption):
        from services.user_data_store import hydrate_user_data_async, _restored_principals
        done = threading.Event()

        def mock_ensure(pid):
            _restored_principals.add(pid)
            done.set()
            return True

        with patch("services.user_data_store.ensure_user_data_restored", side_effect=mock_ensure):
            hydrate_user_data_async(FAKE_PRINCIPAL)
            done.wait(timeout=5)
        assert FAKE_PRINCIPAL in _restored_principals

    def test_hydrate_concurrent_guard(self, mock_encryption):
        from services.user_data_store import hydrate_user_data_async, _restore_inflight
        # Manually add to inflight to simulate concurrent call
        _restore_inflight.add(FAKE_PRINCIPAL)
        with patch("services.user_data_store.ensure_user_data_restored") as mock_ensure:
            hydrate_user_data_async(FAKE_PRINCIPAL)
            # Should not call ensure since it's inflight
            mock_ensure.assert_not_called()

    def test_hydrate_skips_already_restored(self, mock_encryption):
        from services.user_data_store import hydrate_user_data_async, _restored_principals
        _restored_principals.add(FAKE_PRINCIPAL)
        with patch("services.user_data_store.ensure_user_data_restored") as mock_ensure:
            hydrate_user_data_async(FAKE_PRINCIPAL)
            mock_ensure.assert_not_called()


# =============================================================================
# CHAT MANIFEST TRACKING
# =============================================================================


class TestChatManifestTracking:
    """Test update_chat_in_manifest and remove_chat_from_manifest."""

    def test_update_chat_adds_entry(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import update_chat_in_manifest, load_manifest
        manifest = {
            "version": 2, "chats": [],
            "profile": {"cid": None}, "memoryIndex": {"cid": None},
            "graphIndex": {"cid": None}, "lastUpdated": 0,
        }
        manifest_path = tmp_chats_dir / FAKE_PRINCIPAL / "manifest.json"
        with patch("services.user_data_store._get_manifest_path", return_value=manifest_path), \
             patch("services.user_data_store.load_manifest", return_value=manifest), \
             patch("services.user_data_store.save_manifest") as save_mock, \
             patch("services.user_data_store._debounce_manifest_sync"), \
             patch("services.user_data_store.unpin_cid"):
            update_chat_in_manifest(FAKE_PRINCIPAL, "chat-001", FAKE_CID, "Test Chat", 5)
        assert len(manifest["chats"]) == 1
        assert manifest["chats"][0]["chatId"] == "chat-001"
        assert manifest["chats"][0]["cid"] == FAKE_CID

    def test_remove_chat_from_manifest(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import remove_chat_from_manifest
        manifest = {
            "version": 2,
            "chats": [{"chatId": "chat-001", "cid": FAKE_CID}],
            "lastUpdated": 0,
        }
        manifest_path = tmp_chats_dir / FAKE_PRINCIPAL / "manifest.json"
        with patch("services.user_data_store._get_manifest_path", return_value=manifest_path), \
             patch("services.user_data_store.load_manifest", return_value=manifest), \
             patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.sync_manifest_to_ipfs"):
            remove_chat_from_manifest(FAKE_PRINCIPAL, "chat-001")
        assert len(manifest["chats"]) == 0


# =============================================================================
# STORAGE STATS
# =============================================================================


class TestStorageStats:
    """Test storage stats computation."""

    def test_get_storage_stats(self, mock_encryption, tmp_chats_dir):
        from services.user_data_store import get_storage_stats
        manifest = {
            "profile": {"cid": FAKE_CID, "factCount": 5},
            "memoryIndex": {"cid": FAKE_CID, "messageCount": 42},
            "graphIndex": {"cid": None, "tripleCount": 0},
            "chats": [{"chatId": "c1"}, {"chatId": "c2"}],
            "lastUpdated": 1000,
        }
        with patch("services.user_data_store.load_manifest", return_value=manifest):
            stats = get_storage_stats(FAKE_PRINCIPAL)
        assert stats["chatCount"] == 2
        assert stats["hasProfile"] is True
        assert stats["hasVectors"] is True
        assert stats["hasGraph"] is False
        assert stats["factCount"] == 5
        assert stats["messageEmbeddings"] == 42


# =============================================================================
# NOTIFY TRIGGERS (debounce)
# =============================================================================


class TestNotifyTriggers:
    """Test auto-sync trigger debounce behavior."""

    def test_notify_message_indexed_threshold(self):
        from services.user_data_store import (
            notify_message_indexed, VECTOR_SYNC_MESSAGE_THRESHOLD,
            _vector_sync_counters, _vector_sync_timestamps,
        )
        import time as _time
        # Pre-seed timestamp so elapsed-time trigger doesn't fire early
        _vector_sync_counters[FAKE_PRINCIPAL] = 0
        _vector_sync_timestamps[FAKE_PRINCIPAL] = _time.time()

        with patch("services.user_data_store.sync_vector_db_to_ipfs") as sync_mock, \
             patch("services.user_data_store.threading.Thread") as thread_mock:
            # Index fewer than threshold
            for _ in range(VECTOR_SYNC_MESSAGE_THRESHOLD - 1):
                notify_message_indexed(FAKE_PRINCIPAL)
            thread_mock.assert_not_called()

            # Hit threshold
            notify_message_indexed(FAKE_PRINCIPAL)
            thread_mock.assert_called_once()

    def test_notify_profile_changed_debounce(self):
        from services.user_data_store import notify_profile_changed, _profile_sync_timers
        memory = {"facts": [{"text": "test"}]}
        notify_profile_changed(FAKE_PRINCIPAL, memory)
        assert FAKE_PRINCIPAL in _profile_sync_timers
        # Cancel the timer to avoid side effects
        _profile_sync_timers[FAKE_PRINCIPAL].cancel()

    def test_notify_graph_changed_debounce(self):
        from services.user_data_store import notify_graph_changed, _graph_sync_timers
        notify_graph_changed(FAKE_PRINCIPAL)
        assert FAKE_PRINCIPAL in _graph_sync_timers
        # Cancel the timer to avoid side effects
        _graph_sync_timers[FAKE_PRINCIPAL].cancel()
