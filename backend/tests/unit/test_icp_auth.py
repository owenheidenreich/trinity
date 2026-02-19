"""
Trinity ICP Authentication Tests

Tests for Ed25519 signature verification and authentication middleware.
Target: 90% coverage on icp_auth.py

Created: February 5, 2026
Phase 1: Testing Foundation - Week 1

Test Priority Legend:
- P0: Critical security tests (MUST pass)
- P1: Important edge cases
- P2: Nice to have coverage
"""

# Import the module under test
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from icp_auth import CRYPTO_AVAILABLE, verify_icp_signature, verify_request_auth


class TestVerifyICPSignature:
    """
    Unit tests for verify_icp_signature function.

    This is the core cryptographic verification function.
    Security-critical: All P0 tests MUST pass.
    """

    # =========================================================================
    # P0 TESTS - Critical Security (MUST PASS)
    # =========================================================================

    @pytest.mark.p0
    @pytest.mark.security
    def test_valid_signature_verifies(self, test_keypair, create_signature):
        """
        P0: A properly signed message should verify successfully.

        This is the happy path - if this fails, auth is completely broken.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        signature = create_signature(principal, timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is True, f"Valid signature should verify. Error: {error}"
        assert error is None

    @pytest.mark.p0
    @pytest.mark.security
    def test_expired_timestamp_rejected(self, test_keypair, create_signature):
        """
        P0: Signatures with timestamps >60 seconds old MUST be rejected.

        This prevents replay attacks where an attacker captures a valid
        request and replays it later.
        """
        principal = test_keypair["principal"]
        # 120 seconds ago - well past the 60s window
        old_timestamp = str(int((time.time() - 120) * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        signature = create_signature(principal, old_timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=old_timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False, "Expired timestamp should be rejected"
        assert error is not None
        assert "expired" in error.lower(), f"Error should mention expiry: {error}"

    @pytest.mark.p0
    @pytest.mark.security
    def test_invalid_signature_rejected(self, test_keypair):
        """
        P0: Malformed/invalid signature bytes MUST be rejected.

        This catches attackers sending garbage signatures.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        # Invalid signature - wrong length (should be 64 bytes = 128 hex chars)
        invalid_signature = "deadbeef" * 8  # Only 32 bytes

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=invalid_signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False, "Invalid signature should be rejected"
        assert error is not None

    @pytest.mark.p0
    @pytest.mark.security
    def test_wrong_key_rejected(self, test_keypair, second_keypair):
        """
        P0: A signature from a different key MUST be rejected.

        This is critical - ensures principal A cannot forge auth for principal B.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        # Sign with second_keypair but try to verify with test_keypair's public key
        message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
        signed = second_keypair["signing_key"].sign(message.encode("utf-8"))
        wrong_signature = signed.signature.hex()

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=wrong_signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],  # Different key!
            nonce=nonce,
        )

        assert success is False, "Signature from wrong key should be rejected"
        assert error is not None
        assert "invalid" in error.lower(), f"Error should mention invalid: {error}"

    @pytest.mark.p0
    @pytest.mark.security
    def test_principal_mismatch_rejected(self, test_keypair, second_keypair, create_signature):
        """
        P0: Public key must be cryptographically bound to the claimed principal.
        """
        spoofed_principal = second_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        signature = create_signature(spoofed_principal, timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=spoofed_principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False
        assert error is not None
        assert "principal" in error.lower()

    @pytest.mark.p0
    @pytest.mark.security
    def test_tampered_message_rejected(self, test_keypair, create_signature):
        """
        P0: A signature verified against a different endpoint MUST fail.

        This prevents an attacker from using a signature for /chat/list
        to authenticate a request to /chat/delete.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        original_endpoint = "/chat/list"
        tampered_endpoint = "/chat/delete"
        nonce = str(uuid.uuid4())

        # Sign for /chat/list
        signature = create_signature(principal, timestamp, original_endpoint, nonce)

        # Try to verify for /chat/delete
        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=tampered_endpoint,  # Different endpoint!
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False, "Tampered endpoint should be rejected"
        assert error is not None

    # =========================================================================
    # P1 TESTS - Important Edge Cases
    # =========================================================================

    @pytest.mark.p1
    @pytest.mark.security
    def test_future_timestamp_rejected(self, test_keypair, create_signature):
        """
        P1: Signatures with timestamps too far in the future should be rejected.

        Prevents attackers from pre-computing signatures for future use.
        """
        principal = test_keypair["principal"]
        # 120 seconds in the future
        future_timestamp = str(int((time.time() + 120) * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        signature = create_signature(principal, future_timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=future_timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False, "Future timestamp should be rejected"
        assert error is not None

    @pytest.mark.p1
    def test_invalid_timestamp_format(self, test_keypair, create_signature):
        """
        P1: Non-numeric timestamp should be rejected gracefully.
        """
        principal = test_keypair["principal"]
        invalid_timestamp = "not-a-number"
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex="a" * 128,  # Valid length but won't verify
            timestamp=invalid_timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False, "Invalid timestamp format should be rejected"
        assert error is not None
        assert "timestamp" in error.lower() or "invalid" in error.lower()

    @pytest.mark.p1
    def test_invalid_public_key_format(self, test_keypair, create_signature):
        """
        P1: Invalid public key hex should be rejected gracefully.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())
        signature = create_signature(principal, timestamp, endpoint, nonce)

        # Invalid hex (odd number of characters)
        invalid_public_key = "abc"

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=invalid_public_key,
            nonce=nonce,
        )

        assert success is False
        assert error is not None

    @pytest.mark.p1
    def test_wrong_length_public_key(self, test_keypair, create_signature):
        """
        P1: Public key with wrong length (not 32 bytes) should be rejected.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())
        signature = create_signature(principal, timestamp, endpoint, nonce)

        # 16 bytes instead of 32
        short_public_key = "ab" * 16

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=short_public_key,
            nonce=nonce,
        )

        assert success is False
        assert error is not None
        assert "length" in error.lower() or "invalid" in error.lower()

    @pytest.mark.p1
    def test_missing_public_key(self, test_keypair, create_signature):
        """
        P1: Missing public key should return appropriate error.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())
        signature = create_signature(principal, timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=None,  # No public key
            nonce=nonce,
        )

        assert success is False
        assert error is not None
        assert "public key" in error.lower()

    # =========================================================================
    # P2 TESTS - Edge Cases & Coverage
    # =========================================================================

    @pytest.mark.p2
    def test_boundary_timestamp_just_within_window(self, test_keypair, create_signature):
        """
        P2: Timestamp at exactly 59 seconds should still be valid.
        """
        principal = test_keypair["principal"]
        # 59 seconds ago - just within the 60s window
        boundary_timestamp = str(int((time.time() - 59) * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        signature = create_signature(principal, boundary_timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=boundary_timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is True, f"59s old timestamp should be valid. Error: {error}"

    @pytest.mark.p2
    def test_boundary_timestamp_just_outside_window(self, test_keypair, create_signature):
        """
        P2: Timestamp at exactly 61 seconds should be rejected.
        """
        principal = test_keypair["principal"]
        # 61 seconds ago - just outside the 60s window
        boundary_timestamp = str(int((time.time() - 61) * 1000))
        endpoint = "/chat/autosave"
        nonce = str(uuid.uuid4())

        signature = create_signature(principal, boundary_timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=boundary_timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is False, "61s old timestamp should be rejected"

    @pytest.mark.p2
    def test_special_characters_in_endpoint(self, test_keypair, create_signature):
        """
        P2: Endpoints with special characters should work.
        """
        principal = test_keypair["principal"]
        timestamp = str(int(time.time() * 1000))
        endpoint = "/chat/test-chat-123/delete?confirm=true"
        nonce = str(uuid.uuid4())

        signature = create_signature(principal, timestamp, endpoint, nonce)

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signature,
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=test_keypair["public_key_hex"],
            nonce=nonce,
        )

        assert success is True, f"Special char endpoint should work. Error: {error}"


class TestRequireAuthDecorator:
    """
    Tests for the @require_auth decorator.

    These are integration tests that require a Flask app context.
    """

    @pytest.mark.p0
    @pytest.mark.security
    def test_missing_headers_returns_401(self, app, client):
        """
        P0: Requests without auth headers MUST return 401.
        """
        # Access a protected endpoint without headers
        response = client.get("/chat/list")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    @pytest.mark.p0
    @pytest.mark.security
    def test_valid_auth_allows_request(self, app, client, auth_headers):
        """
        P0: Requests with valid auth headers should be allowed.
        """
        headers = auth_headers("/chat/list")

        response = client.get("/chat/list", headers=headers)

        # Should not be 401 (auth passed)
        # Might be 200 or other status depending on handler logic
        assert (
            response.status_code != 401
        ), f"Valid auth should not return 401. Got: {response.status_code}"

    @pytest.mark.p0
    @pytest.mark.security
    def test_expired_auth_returns_401(self, app, client, expired_auth_headers):
        """
        P0: Requests with expired timestamps MUST return 401.
        """
        headers = expired_auth_headers("/chat/list")

        response = client.get("/chat/list", headers=headers)

        assert (
            response.status_code == 401
        ), f"Expired auth should return 401. Got: {response.status_code}"


class TestVerifyRequestAuth:
    """
    Tests for verify_request_auth helper function.
    """

    @pytest.mark.p1
    def test_missing_principal_header(self, app):
        """
        P1: Missing ICP-Principal header should fail with specific error.
        """
        with app.test_request_context(headers={"ICP-Signature": "abc", "ICP-Timestamp": "123"}):
            success, principal, error = verify_request_auth()

            assert success is False
            assert principal is None
            assert "principal" in error.lower()

    @pytest.mark.p1
    def test_missing_signature_header(self, app, test_keypair):
        """
        P1: Missing ICP-Signature header should fail with specific error.
        """
        with app.test_request_context(
            headers={"ICP-Principal": test_keypair["principal"], "ICP-Timestamp": "123"}
        ):
            success, principal, error = verify_request_auth()

            assert success is False
            assert principal is None
            assert "signature" in error.lower()

    @pytest.mark.p1
    def test_missing_timestamp_header(self, app, test_keypair):
        """
        P1: Missing ICP-Timestamp header should fail with specific error.
        """
        with app.test_request_context(
            headers={"ICP-Principal": test_keypair["principal"], "ICP-Signature": "abc"}
        ):
            success, principal, error = verify_request_auth()

            assert success is False
            assert principal is None
            assert "timestamp" in error.lower()

    @pytest.mark.p1
    def test_missing_nonce_header(self, app, test_keypair):
        """
        P1: Missing ICP-Nonce header should fail with specific error.
        """
        with app.test_request_context(
            headers={
                "ICP-Principal": test_keypair["principal"],
                "ICP-Signature": "abc",
                "ICP-Timestamp": str(int(time.time() * 1000)),
                "ICP-PublicKey": test_keypair["public_key_hex"],
            }
        ):
            success, principal, error = verify_request_auth()

            assert success is False
            assert principal is None
            assert "nonce" in error.lower()


# =============================================================================
# TEST CRYPTO AVAILABILITY
# =============================================================================


class TestCryptoAvailability:
    """
    Tests to verify cryptography module is available.
    """

    @pytest.mark.p0
    def test_crypto_module_available(self):
        """
        P0: Cryptography module must be available for tests to be valid.
        """
        assert (
            CRYPTO_AVAILABLE is True
        ), "Cryptography module not available - install with: pip install cryptography"
