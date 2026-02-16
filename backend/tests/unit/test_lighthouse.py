"""
Tests for lighthouse.py — IPFS Storage Module

Tests upload, download, listing, vector DB sync — all with mocked HTTP.
"""

import pytest
from unittest.mock import patch, MagicMock

# All tests mock LIGHTHOUSE_API_KEY so no real calls are made
FAKE_API_KEY = "test-lighthouse-key-abc123"
FAKE_CID = "QmTestCid123456789abcdefghijklmnopqrstuvwxyz"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def mock_lighthouse_key():
    """Ensure LIGHTHOUSE_API_KEY is set for all tests."""
    with patch("lighthouse.LIGHTHOUSE_API_KEY", FAKE_API_KEY):
        yield


@pytest.fixture
def mock_upload_success():
    """Mock a successful Lighthouse upload."""
    with patch("lighthouse.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"Hash": FAKE_CID, "Size": 1024}
        mock_post.return_value = mock_resp
        yield mock_post


@pytest.fixture
def mock_upload_failure():
    """Mock a failed Lighthouse upload."""
    with patch("lighthouse.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp
        yield mock_post


@pytest.fixture
def mock_listing_success():
    """Mock successful file listing from Lighthouse."""
    with patch("lighthouse.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "fileList": [
                {"fileName": "user1_vectors.db", "cid": FAKE_CID, "createdAt": 1700000000},
                {"fileName": "chat_backup.json", "cid": "QmOther123", "createdAt": 1699000000},
            ]
        }
        mock_get.return_value = mock_resp
        yield mock_get


# =============================================================================
# upload_to_ipfs TESTS
# =============================================================================


class TestUploadToIpfs:
    """Test IPFS upload functionality."""

    def test_upload_success(self, mock_upload_success):
        from lighthouse import upload_to_ipfs

        cid = upload_to_ipfs(b"test data", "test.json", "principal-123")

        assert cid == FAKE_CID
        mock_upload_success.assert_called_once()

        # Verify correct endpoint and auth header
        call_kwargs = mock_upload_success.call_args
        assert "Authorization" in call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))

    def test_upload_failure_returns_none(self, mock_upload_failure):
        from lighthouse import upload_to_ipfs

        cid = upload_to_ipfs(b"test data", "test.json")
        assert cid is None

    def test_upload_timeout_returns_none(self):
        from lighthouse import upload_to_ipfs
        import requests

        with patch("lighthouse.requests.post", side_effect=requests.Timeout("timed out")):
            cid = upload_to_ipfs(b"test data", "test.json")
            assert cid is None

    def test_upload_no_api_key_returns_none(self):
        from lighthouse import upload_to_ipfs

        with patch("lighthouse.LIGHTHOUSE_API_KEY", ""):
            cid = upload_to_ipfs(b"test data", "test.json")
            assert cid is None

    def test_upload_network_error_returns_none(self):
        from lighthouse import upload_to_ipfs
        import requests

        with patch("lighthouse.requests.post", side_effect=requests.ConnectionError("refused")):
            cid = upload_to_ipfs(b"test data", "test.json")
            assert cid is None

    def test_upload_passes_correct_filename(self, mock_upload_success):
        from lighthouse import upload_to_ipfs

        upload_to_ipfs(b"data", "my_backup.json", "principal-456")

        call_kwargs = mock_upload_success.call_args
        files = call_kwargs.kwargs.get("files", call_kwargs[1].get("files", {}))
        assert "file" in files
        # files={"file": ("filename", data, content_type)}
        assert files["file"][0] == "my_backup.json"


# =============================================================================
# download_from_ipfs TESTS
# =============================================================================


class TestDownloadFromIpfs:
    """Test IPFS download with gateway fallback."""

    def test_download_success_first_gateway(self):
        from lighthouse import download_from_ipfs

        with patch("lighthouse.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"downloaded data"
            mock_get.return_value = mock_resp

            result = download_from_ipfs(FAKE_CID)

        assert result == b"downloaded data"
        # Only first gateway should be tried if it succeeds
        assert mock_get.call_count == 1

    def test_download_falls_back_to_second_gateway(self):
        from lighthouse import download_from_ipfs
        import requests

        fail_resp = MagicMock()
        fail_resp.status_code = 404

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b"fallback data"

        with patch("lighthouse.requests.get", side_effect=[fail_resp, success_resp]):
            result = download_from_ipfs(FAKE_CID)

        assert result == b"fallback data"

    def test_download_all_gateways_fail_returns_none(self):
        from lighthouse import download_from_ipfs

        fail_resp = MagicMock()
        fail_resp.status_code = 500

        with patch("lighthouse.requests.get", return_value=fail_resp):
            result = download_from_ipfs(FAKE_CID)

        assert result is None

    def test_download_empty_cid_returns_none(self):
        from lighthouse import download_from_ipfs

        assert download_from_ipfs("") is None
        assert download_from_ipfs(None) is None

    def test_download_timeout_tries_next_gateway(self):
        from lighthouse import download_from_ipfs
        import requests

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b"success"

        with patch("lighthouse.requests.get", side_effect=[requests.Timeout, success_resp]):
            result = download_from_ipfs(FAKE_CID)

        assert result == b"success"


# =============================================================================
# get_lighthouse_uploads TESTS
# =============================================================================


class TestGetLighthouseUploads:
    """Test listing uploaded files."""

    def test_listing_success(self, mock_listing_success):
        from lighthouse import get_lighthouse_uploads

        files = get_lighthouse_uploads("principal-123")

        assert len(files) == 2
        # Should be sorted by createdAt descending (newest first)
        assert files[0]["createdAt"] >= files[1]["createdAt"]

    def test_listing_empty(self):
        from lighthouse import get_lighthouse_uploads

        with patch("lighthouse.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"fileList": []}
            mock_get.return_value = mock_resp

            files = get_lighthouse_uploads()

        assert files == []

    def test_listing_no_api_key(self):
        from lighthouse import get_lighthouse_uploads

        with patch("lighthouse.LIGHTHOUSE_API_KEY", ""):
            files = get_lighthouse_uploads()
            assert files == []

    def test_listing_timeout(self):
        from lighthouse import get_lighthouse_uploads
        import requests

        with patch("lighthouse.requests.get", side_effect=requests.Timeout):
            files = get_lighthouse_uploads()
            assert files == []

    def test_listing_paginates_with_last_key(self):
        from lighthouse import get_lighthouse_uploads

        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "fileList": [
                {"fileName": "page1.json", "cid": "cid-1", "createdAt": 1000},
            ],
            "lastKey": "cursor-1",
        }

        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "fileList": [
                {"fileName": "page2.json", "cid": "cid-2", "createdAt": 2000},
            ],
        }

        with patch("lighthouse.requests.get", side_effect=[page1, page2]) as mock_get:
            files = get_lighthouse_uploads("principal-123")

        assert len(files) == 2
        assert files[0]["cid"] == "cid-2"  # sorted newest first
        assert files[1]["cid"] == "cid-1"
        assert mock_get.call_count == 2
        second_call = mock_get.call_args_list[1]
        params = second_call.kwargs.get("params", second_call[1].get("params", {}))
        assert params.get("lastKey") == "cursor-1"

    def test_listing_stops_on_repeated_cursor(self):
        from lighthouse import get_lighthouse_uploads

        repeated = MagicMock()
        repeated.status_code = 200
        repeated.json.return_value = {
            "fileList": [
                {"fileName": "one.json", "cid": "cid-1", "createdAt": 1000},
            ],
            "lastKey": "same-cursor",
        }

        with patch("lighthouse.requests.get", side_effect=[repeated, repeated]) as mock_get:
            files = get_lighthouse_uploads("principal-123")

        assert len(files) == 2  # both pages were consumed before cursor-stability stop
        assert mock_get.call_count == 2


# =============================================================================
# get_user_vector_cid TESTS
# =============================================================================


class TestGetUserVectorCid:
    """Test finding a user's vector DB CID from uploads."""

    def test_finds_matching_vector_cid(self, mock_listing_success):
        from lighthouse import get_user_vector_cid

        cid = get_user_vector_cid("user1")
        assert cid == FAKE_CID

    def test_no_match_returns_none(self):
        from lighthouse import get_user_vector_cid

        with patch("lighthouse.get_lighthouse_uploads", return_value=[]):
            cid = get_user_vector_cid("nonexistent")
            assert cid is None


# =============================================================================
# upload_vector_db / download_vector_db TESTS
# =============================================================================


class TestVectorDbSync:
    """Test vector database upload/download to IPFS."""

    def test_upload_vector_db(self, mock_upload_success):
        from lighthouse import upload_vector_db

        mock_store = MagicMock()
        mock_store.export_for_ipfs.return_value = b"sqlite-db-bytes"

        with patch("services.vector_store.get_vector_store", return_value=mock_store):
            cid = upload_vector_db("principal-123")

        assert cid == FAKE_CID

    def test_upload_vector_db_empty_data(self):
        from lighthouse import upload_vector_db

        mock_store = MagicMock()
        mock_store.export_for_ipfs.return_value = b""

        with patch("services.vector_store.get_vector_store", return_value=mock_store):
            cid = upload_vector_db("principal-123")

        assert cid is None

    def test_download_vector_db_success(self):
        from lighthouse import download_vector_db

        mock_store = MagicMock()
        mock_store.import_from_ipfs.return_value = True

        with patch("lighthouse.download_from_ipfs", return_value=b"db-data"):
            with patch("services.vector_store.get_vector_store", return_value=mock_store):
                result = download_vector_db("principal-123", FAKE_CID)

        assert result is True
        mock_store.import_from_ipfs.assert_called_once_with(b"db-data")

    def test_download_vector_db_download_fails(self):
        from lighthouse import download_vector_db

        with patch("lighthouse.download_from_ipfs", return_value=None):
            result = download_vector_db("principal-123", FAKE_CID)

        assert result is False


# =============================================================================
# sync_vector_db_on_login TESTS
# =============================================================================


class TestSyncVectorDbOnLogin:
    """Test login vector sync logic."""

    def test_local_db_exists_skips_download(self, tmp_path):
        from lighthouse import sync_vector_db_on_login

        # Create a local DB file
        principal = "test-user"
        db_dir = tmp_path / principal
        db_dir.mkdir()
        db_file = db_dir / "vectors.db"
        db_file.write_bytes(b"local-db")

        with patch("config.CHATS_DIR", str(tmp_path)):
            result = sync_vector_db_on_login(principal)

        assert result is True

    def test_no_local_or_remote_returns_true(self, tmp_path):
        from lighthouse import sync_vector_db_on_login

        with patch("config.CHATS_DIR", str(tmp_path)):
            with patch("lighthouse.get_user_vector_cid", return_value=None):
                result = sync_vector_db_on_login("new-user")

        # New user with no vectors — still returns True
        assert result is True

    def test_restores_from_ipfs_when_no_local(self, tmp_path):
        from lighthouse import sync_vector_db_on_login

        with patch("config.CHATS_DIR", str(tmp_path)):
            with patch("lighthouse.get_user_vector_cid", return_value=FAKE_CID):
                with patch("lighthouse.download_vector_db", return_value=True) as mock_dl:
                    result = sync_vector_db_on_login("returning-user")

        assert result is True
        mock_dl.assert_called_once_with("returning-user", FAKE_CID)
