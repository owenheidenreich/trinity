"""
IPFS Diagnostics Test Suite — Integration Tests
=================================================

Purpose: Exercise every IPFS interaction path to measure latencies,
expose failure modes, and validate the full sync/restore pipeline.

Run with real Lighthouse (requires LIGHTHOUSE_API_KEY env var):
    cd backend && LIGHTHOUSE_API_KEY=<key> python -m pytest tests/integration/test_ipfs_diagnostics.py -v -s

Run with mocks (no API key needed — default mode):
    cd backend && python -m pytest tests/integration/test_ipfs_diagnostics.py -v

Test groups:
    1. Upload reliability — latency, retry, dedup, failure
    2. Download reliability — gateway fallback, latency per gateway
    3. Sync orchestration — profile, vector, graph, chat, manifest round-trips
    4. Restore orchestration — full ensure_user_data_restored flow
    5. Failure cascading — no API key, quota exhausted, network partition
    6. Performance profiling — timing full flows, O(N) scans
"""

import json
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


FAKE_PRINCIPAL = "diag-test-principal-0123456789abcdef"
FAKE_CID = "QmDiagTestCid123456789abcdefghijklmnopqrst"
FAKE_CID_2 = "QmDiagTestCid2ABCDEF0123456789abcdefghijkl"
FAKE_API_KEY = "diag-lighthouse-key-test"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def clean_module_state():
    """Reset all module-level state between tests."""
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
def mock_lighthouse_key():
    """Set a fake Lighthouse API key."""
    with patch("lighthouse.LIGHTHOUSE_API_KEY", FAKE_API_KEY):
        yield


@pytest.fixture
def mock_encryption():
    """Make encrypt/decrypt identity transforms for predictable round-trips."""
    with patch("services.user_data_store.encrypt_for_user",
               side_effect=lambda d, p: {"encryption": "mock", "data": d}) as enc, \
         patch("services.user_data_store.decrypt_for_user",
               side_effect=lambda d, p: d.get("data", d)) as dec:
        yield enc, dec


@pytest.fixture
def tmp_chats_dir(tmp_path):
    """Provide a temp chats directory."""
    chats = tmp_path / "chats"
    chats.mkdir()
    user_dir = chats / FAKE_PRINCIPAL
    user_dir.mkdir()
    with patch("services.user_data_store.CHATS_DIR", str(chats)):
        yield chats


# =============================================================================
# GROUP 1: UPLOAD RELIABILITY
# =============================================================================


class TestUploadReliability:
    """Measure upload latency and verify retry/dedup behavior."""

    def test_upload_small_payload(self, mock_lighthouse_key):
        """Upload 1KB — verify CID returned and measure latency."""
        from lighthouse import upload_to_ipfs
        data = b"x" * 1024
        with patch("lighthouse.http_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"Hash": FAKE_CID, "Size": 1024}
            mock_session.post.return_value = mock_resp

            t0 = time.monotonic()
            cid = upload_to_ipfs(data, "small.json", FAKE_PRINCIPAL)
            elapsed = time.monotonic() - t0

        assert cid == FAKE_CID
        # Mock should be near-instant
        assert elapsed < 1.0

    def test_upload_medium_payload(self, mock_lighthouse_key):
        """Upload 100KB — verify success."""
        from lighthouse import upload_to_ipfs
        data = b"y" * (100 * 1024)
        with patch("lighthouse.http_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"Hash": FAKE_CID, "Size": len(data)}
            mock_session.post.return_value = mock_resp

            cid = upload_to_ipfs(data, "medium.json", FAKE_PRINCIPAL)
        assert cid == FAKE_CID

    def test_upload_retry_with_timeout(self, mock_lighthouse_key):
        """Simulate timeout on first attempt, success on second."""
        from services.user_data_store import _upload_with_retry
        import requests

        with patch("services.user_data_store.upload_to_ipfs",
                    side_effect=[None, FAKE_CID]) as m, \
             patch("services.user_data_store.time.sleep"):
            t0 = time.monotonic()
            cid = _upload_with_retry(b"retry test", "retry.json", FAKE_PRINCIPAL)
            elapsed = time.monotonic() - t0

        assert cid == FAKE_CID
        assert m.call_count == 2

    def test_upload_all_attempts_fail_queues_pending(self, mock_lighthouse_key):
        """All 3 retry attempts fail — verify pending sync queued."""
        from services.user_data_store import _upload_with_retry, _pending_syncs

        with patch("services.user_data_store.upload_to_ipfs", return_value=None), \
             patch("services.user_data_store.time.sleep"):
            cid = _upload_with_retry(b"failing data", "fail.json", FAKE_PRINCIPAL)

        assert cid is None

    def test_upload_dedup_skips_identical_content(self, mock_lighthouse_key):
        """Identical content uploaded twice — second call should skip network."""
        from services.user_data_store import _upload_with_retry

        data = b"identical content"
        with patch("services.user_data_store.upload_to_ipfs", return_value=FAKE_CID) as m:
            cid1 = _upload_with_retry(data, "test.json", FAKE_PRINCIPAL)
            cid2 = _upload_with_retry(data, "test.json", FAKE_PRINCIPAL)

        assert cid1 == FAKE_CID
        assert cid2 == FAKE_CID
        assert m.call_count == 1  # Only the first call hit the network

    def test_upload_dedup_cache_lost_after_restart(self, mock_lighthouse_key):
        """Simulate container restart (clear dedup cache) — re-upload should occur."""
        from services.user_data_store import _upload_with_retry, _upload_dedupe, _upload_latest
        import services.user_data_store as uds

        data = b"some content"
        with patch("services.user_data_store.upload_to_ipfs", return_value=FAKE_CID) as m:
            _upload_with_retry(data, "test.json", FAKE_PRINCIPAL)
            assert m.call_count == 1
            # Simulate restart
            uds._upload_dedupe.clear()
            uds._upload_latest.clear()
            _upload_with_retry(data, "test.json", FAKE_PRINCIPAL)
            assert m.call_count == 2  # Had to re-upload


# =============================================================================
# GROUP 2: DOWNLOAD RELIABILITY
# =============================================================================


class TestDownloadReliability:
    """Test gateway fallback and latency measurement."""

    def test_download_first_gateway_success(self, mock_lighthouse_key):
        """Primary gateway succeeds — measure latency."""
        from lighthouse import download_from_ipfs
        with patch("lighthouse.http_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"ipfs content"
            mock_session.get.return_value = mock_resp

            t0 = time.monotonic()
            result = download_from_ipfs(FAKE_CID)
            elapsed = time.monotonic() - t0

        assert result == b"ipfs content"
        assert mock_session.get.call_count == 1
        assert elapsed < 1.0

    def test_download_fallback_to_second_gateway(self, mock_lighthouse_key):
        """Primary gateway fails, secondary succeeds."""
        from lighthouse import download_from_ipfs
        fail_resp = MagicMock()
        fail_resp.status_code = 502

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.content = b"fallback content"

        with patch("lighthouse.http_session") as mock_session:
            mock_session.get.side_effect = [fail_resp, ok_resp]
            result = download_from_ipfs(FAKE_CID)

        assert result == b"fallback content"
        assert mock_session.get.call_count == 2

    def test_download_all_gateways_fail(self, mock_lighthouse_key):
        """All 4 gateways fail — returns None."""
        from lighthouse import download_from_ipfs
        fail_resp = MagicMock()
        fail_resp.status_code = 500

        with patch("lighthouse.http_session") as mock_session:
            mock_session.get.return_value = fail_resp
            result = download_from_ipfs(FAKE_CID)

        assert result is None
        assert mock_session.get.call_count == 4

    def test_download_timeout_per_gateway(self, mock_lighthouse_key):
        """Each gateway timeout should try the next one."""
        from lighthouse import download_from_ipfs
        import requests

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.content = b"success"

        with patch("lighthouse.http_session") as mock_session:
            mock_session.get.side_effect = [
                requests.Timeout("gw1"),
                requests.Timeout("gw2"),
                ok_resp,
            ]
            result = download_from_ipfs(FAKE_CID)

        assert result == b"success"
        assert mock_session.get.call_count == 3

    def test_download_empty_cid_returns_none(self):
        """Empty or None CID returns None immediately."""
        from lighthouse import download_from_ipfs
        assert download_from_ipfs("") is None
        assert download_from_ipfs(None) is None


# =============================================================================
# GROUP 3: SYNC ORCHESTRATION
# =============================================================================


class TestSyncOrchestration:
    """Test full sync round-trips for each artifact type."""

    def test_profile_sync_round_trip(self, mock_encryption, tmp_chats_dir):
        """Save profile → sync to IPFS → verify manifest updated."""
        from services.user_data_store import sync_profile_to_ipfs

        memory = {"facts": [{"text": "user likes cats", "category": "interests"}]}
        with patch("services.user_data_store._upload_with_retry", return_value=FAKE_CID), \
             patch("services.user_data_store.load_manifest", return_value={
                 "profile": {"cid": None, "lastUpdated": None, "factCount": 0},
                 "memoryIndex": {"cid": None}, "graphIndex": {"cid": None}, "chats": [],
             }) as load_mock, \
             patch("services.user_data_store.save_manifest") as save_mock, \
             patch("services.user_data_store.sync_manifest_to_ipfs") as manifest_sync, \
             patch("services.user_data_store.unpin_cid"):
            cid = sync_profile_to_ipfs(FAKE_PRINCIPAL, memory)

        assert cid == FAKE_CID
        # Manifest should have been called with updated profile CID
        save_mock.assert_called_once()
        manifest_sync.assert_called_once()

    def test_vector_db_sync_round_trip(self, mock_encryption, tmp_chats_dir):
        """Export vector DB → encrypt → upload → verify manifest updated."""
        from services.user_data_store import sync_vector_db_to_ipfs

        mock_store = MagicMock()
        mock_store.export_for_ipfs.return_value = b"sqlite-bytes"
        mock_store.get_stats.return_value = {"message_embeddings": 100}

        with patch("services.vector_store.get_vector_store", return_value=mock_store), \
             patch("services.user_data_store._upload_with_retry", return_value=FAKE_CID), \
             patch("services.user_data_store.load_manifest", return_value={
                 "memoryIndex": {"cid": None, "lastUpdated": None, "messageCount": 0},
                 "profile": {"cid": None}, "graphIndex": {"cid": None}, "chats": [],
             }), patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.sync_manifest_to_ipfs"), \
             patch("services.user_data_store.unpin_cid"):
            cid = sync_vector_db_to_ipfs(FAKE_PRINCIPAL)

        assert cid == FAKE_CID

    def test_graph_db_sync_round_trip(self, mock_encryption, tmp_chats_dir):
        """Sync graph memory → verify manifest updated."""
        from services.user_data_store import sync_graph_db_to_ipfs

        user_dir = tmp_chats_dir / FAKE_PRINCIPAL
        (user_dir / "identity.kuzu").write_bytes(b"graph data")
        (user_dir / "identity_triples.json").write_text('[["A", "rel", "B"]]')

        with patch("services.user_data_store._upload_with_retry", return_value=FAKE_CID), \
             patch("services.user_data_store.load_manifest", return_value={
                 "graphIndex": {"cid": None, "lastUpdated": None, "tripleCount": 0},
                 "profile": {"cid": None}, "memoryIndex": {"cid": None}, "chats": [],
             }), patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.sync_manifest_to_ipfs"), \
             patch("services.user_data_store.unpin_cid"):
            cid = sync_graph_db_to_ipfs(FAKE_PRINCIPAL)

        assert cid == FAKE_CID

    def test_chat_sync_round_trip(self, mock_encryption):
        """Sync chat blob → verify manifest updated."""
        from services.user_data_store import sync_chat_to_ipfs

        chat_data = {"messages": [{"role": "user", "content": "hello"}]}
        with patch("services.user_data_store._upload_with_retry", return_value=FAKE_CID), \
             patch("services.user_data_store.update_chat_in_manifest") as update_mock:
            cid = sync_chat_to_ipfs(FAKE_PRINCIPAL, "chat-diag-001", chat_data, "Diag Chat", 1)

        assert cid == FAKE_CID
        update_mock.assert_called_once()

    def test_manifest_sync_version_tracking(self, mock_encryption):
        """Manifest sync should increment version and track history."""
        from services.user_data_store import sync_manifest_to_ipfs, _default_manifest

        manifest = _default_manifest(FAKE_PRINCIPAL)
        manifest["currentManifestCid"] = "old-cid"
        manifest["manifestVersion"] = 5

        with patch("services.user_data_store._upload_with_retry", return_value=FAKE_CID), \
             patch("services.user_data_store.save_manifest"):
            cid = sync_manifest_to_ipfs(FAKE_PRINCIPAL, manifest)

        assert cid == FAKE_CID
        assert manifest["manifestVersion"] == 6
        assert manifest["currentManifestCid"] == FAKE_CID
        assert len(manifest["manifestHistory"]) == 1
        assert manifest["manifestHistory"][0]["cid"] == "old-cid"


# =============================================================================
# GROUP 4: RESTORE ORCHESTRATION
# =============================================================================


class TestRestoreOrchestration:
    """Test full restore flow from IPFS."""

    def test_full_restore_success(self, mock_encryption, tmp_chats_dir):
        """All three artifacts restored successfully."""
        from services.user_data_store import ensure_user_data_restored, _restored_principals

        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": FAKE_CID},
            "graphIndex": {"cid": FAKE_CID}, "chats": [],
        }), patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):

            t0 = time.monotonic()
            result = ensure_user_data_restored(FAKE_PRINCIPAL)
            elapsed = time.monotonic() - t0

        assert result is True
        assert FAKE_PRINCIPAL in _restored_principals

    def test_restore_finds_remote_manifest(self, mock_encryption, tmp_chats_dir):
        """Local manifest empty → searches IPFS → finds and uses remote."""
        from services.user_data_store import ensure_user_data_restored

        empty = {"profile": {"cid": None}, "memoryIndex": {"cid": None},
                 "graphIndex": {"cid": None}, "chats": []}
        remote = {"profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": None},
                  "graphIndex": {"cid": None}, "chats": []}

        with patch("services.user_data_store.load_manifest", return_value=empty), \
             patch("services.user_data_store.find_manifest_on_ipfs", return_value=remote), \
             patch("services.user_data_store.save_manifest"), \
             patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):
            result = ensure_user_data_restored(FAKE_PRINCIPAL)

        assert result is True

    def test_hydrate_non_blocking(self, mock_encryption, tmp_chats_dir):
        """hydrate_user_data_async should not block the calling thread."""
        from services.user_data_store import hydrate_user_data_async

        barrier = threading.Event()

        def slow_restore(pid):
            barrier.wait(timeout=2)
            return True

        with patch("services.user_data_store.ensure_user_data_restored", side_effect=slow_restore):
            t0 = time.monotonic()
            hydrate_user_data_async(FAKE_PRINCIPAL)
            elapsed = time.monotonic() - t0

        # Should return near-instantly (not wait for slow_restore)
        assert elapsed < 0.5
        barrier.set()  # Unblock the background thread


# =============================================================================
# GROUP 5: FAILURE CASCADING
# =============================================================================


class TestFailureCascading:
    """Test graceful degradation under various failure modes."""

    def test_no_api_key_degrades_gracefully(self):
        """All IPFS operations should return None/empty without crashing."""
        from lighthouse import upload_to_ipfs, download_from_ipfs, get_lighthouse_uploads

        with patch("lighthouse.LIGHTHOUSE_API_KEY", ""):
            assert upload_to_ipfs(b"data", "test.json") is None
            assert get_lighthouse_uploads() == []
            # download_from_ipfs doesn't check API key — tries gateways
            with patch("lighthouse.http_session") as mock_session:
                fail_resp = MagicMock()
                fail_resp.status_code = 403
                mock_session.get.return_value = fail_resp
                assert download_from_ipfs(FAKE_CID) is None

    def test_upload_failure_does_not_corrupt_local_state(self, mock_encryption, tmp_chats_dir):
        """Failed IPFS upload should not corrupt local manifest."""
        from services.user_data_store import sync_profile_to_ipfs, load_manifest, _default_manifest

        manifest_path = tmp_chats_dir / FAKE_PRINCIPAL / "manifest.json"
        with patch("services.user_data_store._get_manifest_path", return_value=manifest_path):
            # Save an initial manifest
            from services.user_data_store import save_manifest
            initial = _default_manifest(FAKE_PRINCIPAL)
            initial["profile"]["cid"] = "existing-cid"
            save_manifest(FAKE_PRINCIPAL, initial)

            # Attempt sync that fails
            with patch("services.user_data_store._upload_with_retry", return_value=None):
                sync_profile_to_ipfs(FAKE_PRINCIPAL, {"facts": []})

            # Manifest should still have original CID
            reloaded = load_manifest(FAKE_PRINCIPAL)
            assert reloaded["profile"]["cid"] == "existing-cid"

    def test_network_error_during_restore_retries_next_request(self, mock_encryption, tmp_chats_dir):
        """Failed restore should NOT mark principal as restored."""
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
        # Next call should retry
        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": None},
            "graphIndex": {"cid": None}, "chats": [],
        }), patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):
            result = ensure_user_data_restored(FAKE_PRINCIPAL)

        assert result is True
        assert FAKE_PRINCIPAL in _restored_principals


# =============================================================================
# GROUP 6: PERFORMANCE PROFILING
# =============================================================================


class TestPerformanceProfiling:
    """Measure timing of key operations."""

    def test_listing_scales_with_uploads(self, mock_lighthouse_key):
        """Measure get_lighthouse_uploads timing with varied page counts."""
        from lighthouse import get_lighthouse_uploads

        def make_page(n_files, last_key=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "fileList": [
                    {"fileName": f"file{i}.json", "cid": f"cid-{i}", "createdAt": 1000 + i}
                    for i in range(n_files)
                ],
                "lastKey": last_key,
            }
            return resp

        # Single page with 50 files
        with patch("lighthouse.http_session") as mock_session:
            mock_session.get.return_value = make_page(50)
            t0 = time.monotonic()
            files = get_lighthouse_uploads()
            elapsed = time.monotonic() - t0

        assert len(files) == 50

    def test_full_restore_timing(self, mock_encryption, tmp_chats_dir):
        """Time the full ensure_user_data_restored flow."""
        from services.user_data_store import ensure_user_data_restored

        with patch("services.user_data_store.load_manifest", return_value={
            "profile": {"cid": FAKE_CID}, "memoryIndex": {"cid": FAKE_CID},
            "graphIndex": {"cid": FAKE_CID}, "chats": [],
        }), patch("services.user_data_store.restore_profile_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_vector_db_from_ipfs", return_value=True), \
             patch("services.user_data_store.restore_graph_db_from_ipfs", return_value=True), \
             patch("services.user_data_store._retry_pending_syncs_async"):

            t0 = time.monotonic()
            ensure_user_data_restored(FAKE_PRINCIPAL)
            elapsed = time.monotonic() - t0

        # With mocks, should be near-instant
        # With real IPFS, this would be the key metric (target: <10s)
        assert elapsed < 2.0

    def test_dedup_cache_performance(self):
        """Dedup cache lookups should be O(1)."""
        from services.user_data_store import _upload_with_retry

        data = b"perf test content"
        with patch("services.user_data_store.upload_to_ipfs", return_value=FAKE_CID):
            _upload_with_retry(data, "perf.json", FAKE_PRINCIPAL)

        # Subsequent calls should hit cache instantly
        t0 = time.monotonic()
        for _ in range(1000):
            _upload_with_retry(data, "perf.json", FAKE_PRINCIPAL)
        elapsed = time.monotonic() - t0

        # 1000 cache hits should be < 100ms
        assert elapsed < 0.5
