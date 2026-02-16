"""
Passphrase route tests.

Focus: degraded behavior when Lighthouse/IPFS upload fails.
"""

from unittest.mock import patch

from encryption import EncryptionUtils
from services.session_manager import clear_all_sessions, get_session_passphrase, has_passphrase


class TestPassphraseRoutes:
    """Route-level tests for /api/passphrase/* endpoints."""

    def setup_method(self):
        clear_all_sessions()

    def teardown_method(self):
        clear_all_sessions()

    @patch("routes.passphrase.upload_to_ipfs", return_value=None)
    @patch("routes.passphrase._find_canary_on_ipfs", return_value=None)
    def test_setup_degrades_to_local_session_when_ipfs_upload_fails(
        self,
        _mock_find_canary,
        _mock_upload,
        client,
        auth_headers,
    ):
        endpoint = "/api/passphrase/setup"
        headers = auth_headers(endpoint)
        principal = headers["ICP-Principal"]

        response = client.post(
            endpoint,
            headers=headers,
            json={"passphrase": "test-passphrase-123"},
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["canary_cid"] is None
        assert payload["storage"] == "local_session_only"
        assert has_passphrase(principal) is True

    @patch("routes.passphrase._find_canary_on_ipfs", return_value={"encryptedContent": "exists"})
    def test_setup_still_rejects_when_canary_exists(self, _mock_find_canary, client, auth_headers):
        endpoint = "/api/passphrase/setup"
        headers = auth_headers(endpoint)

        response = client.post(
            endpoint,
            headers=headers,
            json={"passphrase": "test-passphrase-123"},
        )

        assert response.status_code == 409
        payload = response.get_json()
        assert payload["success"] is False

    @patch("routes.passphrase.upload_to_ipfs", return_value=None)
    def test_change_degrades_to_local_session_when_ipfs_upload_fails(
        self,
        _mock_upload,
        client,
        auth_headers,
    ):
        endpoint = "/api/passphrase/change"
        headers = auth_headers(endpoint)
        principal = headers["ICP-Principal"]
        old_passphrase = "old-passphrase-123"
        new_passphrase = "new-passphrase-456"
        canary = EncryptionUtils.create_passphrase_canary(old_passphrase)

        with patch("routes.passphrase._find_canary_on_ipfs", return_value=canary):
            response = client.post(
                endpoint,
                headers=headers,
                json={
                    "old_passphrase": old_passphrase,
                    "new_passphrase": new_passphrase,
                },
            )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["canary_cid"] is None
        assert payload["storage"] == "local_session_only"
        assert get_session_passphrase(principal) == new_passphrase
