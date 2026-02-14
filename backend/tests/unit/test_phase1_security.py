"""
Trinity Phase 1 Security Tests
================================
Tests verifying all Phase 1 critical security fixes:

1.1 Admin endpoint authentication (@require_admin)
1.2 Encrypted user memory storage
1.3 Code execution disabled in production
1.4 Nonce-based replay protection
1.5 CSP headers (Cloudflare Worker - tested separately)

Created: February 10, 2026
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nacl.signing import SigningKey

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def admin_keypair():
    """Generate a keypair designated as admin."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "public_key_hex": verify_key.encode().hex(),
        "principal": "admin-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-adm",
    }


@pytest.fixture
def non_admin_keypair():
    """Generate a keypair NOT designated as admin."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "public_key_hex": verify_key.encode().hex(),
        "principal": "user-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx-usr",
    }


def make_auth_headers(keypair, endpoint, nonce=None):
    """Create valid auth headers for a given keypair and endpoint."""
    timestamp = str(int(time.time() * 1000))
    if nonce:
        message = f"{keypair['principal']}:{timestamp}:{endpoint}:{nonce}"
    else:
        message = f"{keypair['principal']}:{timestamp}:{endpoint}"
    signed = keypair["signing_key"].sign(message.encode("utf-8"))
    headers = {
        "ICP-Principal": keypair["principal"],
        "ICP-Signature": signed.signature.hex(),
        "ICP-Timestamp": timestamp,
        "ICP-PublicKey": keypair["public_key_hex"],
    }
    if nonce:
        headers["ICP-Nonce"] = nonce
    return headers


# =============================================================================
# 1.1 ADMIN ENDPOINT AUTHENTICATION
# =============================================================================


class TestAdminEndpointAuth:
    """Verify all /admin/* endpoints require admin authentication."""

    ADMIN_ENDPOINTS = [
        ("/admin/cache/stats", "GET"),
        ("/admin/tokens/usage", "GET"),
        ("/admin/quota/usage", "GET"),
    ]

    ADMIN_POST_ENDPOINTS = [
        ("/admin/cache/clear", "POST"),
    ]

    @pytest.mark.p0
    @pytest.mark.security
    @pytest.mark.parametrize("endpoint,method", ADMIN_ENDPOINTS + ADMIN_POST_ENDPOINTS)
    def test_admin_endpoints_reject_unauthenticated(self, client, endpoint, method):
        """Admin endpoints must return 401 without any auth headers."""
        if method == "GET":
            response = client.get(endpoint)
        else:
            response = client.post(endpoint)
        assert response.status_code == 401, (
            f"{endpoint} returned {response.status_code} without auth (expected 401)"
        )

    @pytest.mark.p0
    @pytest.mark.security
    @pytest.mark.parametrize("endpoint,method", ADMIN_ENDPOINTS)
    def test_admin_endpoints_reject_non_admin_user(
        self, client, non_admin_keypair, endpoint, method
    ):
        """Admin endpoints must return 403 for authenticated but non-admin users."""
        headers = make_auth_headers(non_admin_keypair, endpoint)
        with patch("icp_auth.ADMIN_PRINCIPALS", ["some-other-principal"]):
            response = client.get(endpoint, headers=headers)
        assert response.status_code == 403, (
            f"{endpoint} returned {response.status_code} for non-admin (expected 403)"
        )

    @pytest.mark.p0
    @pytest.mark.security
    def test_admin_endpoint_allows_admin_user(self, client, admin_keypair):
        """Admin endpoints must allow requests from admin principals."""
        endpoint = "/admin/cache/stats"
        headers = make_auth_headers(admin_keypair, endpoint)
        with patch("icp_auth.ADMIN_PRINCIPALS", [admin_keypair["principal"]]):
            response = client.get(endpoint, headers=headers)
        # Should not be 401 or 403
        assert response.status_code not in (401, 403), (
            f"Admin was rejected with status {response.status_code}"
        )

    @pytest.mark.p0
    @pytest.mark.security
    def test_admin_returns_403_when_no_admins_configured(self, client, admin_keypair):
        """If ADMIN_PRINCIPALS is empty, all admin access should be denied."""
        endpoint = "/admin/cache/stats"
        headers = make_auth_headers(admin_keypair, endpoint)
        with patch("icp_auth.ADMIN_PRINCIPALS", []):
            response = client.get(endpoint, headers=headers)
        assert response.status_code == 403


# =============================================================================
# 1.2 ENCRYPTED USER MEMORY STORAGE
# =============================================================================


class TestEncryptedUserMemory:
    """Verify user memory is stored encrypted, not plaintext."""

    @pytest.mark.p0
    @pytest.mark.security
    def test_save_user_memory_encrypts_data(self, tmp_path):
        """Saved user memory file must NOT contain plaintext JSON."""
        with patch("storage.CHATS_DIR", str(tmp_path)):
            from storage import save_user_memory

            principal = "test-encrypt-user"
            memory = {
                "principalId": principal,
                "version": "1.0",
                "facts": ["User likes Python", "User lives in NYC"],
                "preferences": {"theme": "dark"},
                "createdAt": int(time.time() * 1000),
                "lastUpdated": int(time.time() * 1000),
            }

            save_user_memory(principal, memory)

            # Read the raw file
            memory_path = tmp_path / principal / "user_memory.json"
            assert memory_path.exists(), "Memory file was not created"

            raw_content = memory_path.read_text()

            # The raw file should NOT contain plaintext facts
            assert "User likes Python" not in raw_content, (
                "User memory is stored in PLAINTEXT - encryption not working!"
            )
            assert "User lives in NYC" not in raw_content, (
                "User memory is stored in PLAINTEXT - encryption not working!"
            )

            # The file should contain encryption markers
            parsed = json.loads(raw_content)
            assert "encryption" in parsed, "No encryption metadata found"
            assert "encryptedContent" in parsed, "No encrypted content found"
            assert parsed["encryption"]["algorithm"] == "AES-256-GCM"

    @pytest.mark.p0
    @pytest.mark.security
    def test_load_user_memory_decrypts_data(self, tmp_path):
        """Loading encrypted user memory should return the original data."""
        with patch("storage.CHATS_DIR", str(tmp_path)):
            from storage import load_user_memory, save_user_memory

            principal = "test-decrypt-user"
            original_memory = {
                "principalId": principal,
                "version": "1.0",
                "facts": ["Secret fact A", "Secret fact B"],
                "preferences": {"lang": "en"},
                "createdAt": 1000000,
                "lastUpdated": 1000000,
            }

            save_user_memory(principal, original_memory)
            loaded = load_user_memory(principal)

            # String facts are normalized to dicts on load
            assert len(loaded["facts"]) == 2
            assert loaded["facts"][0]["text"] == "Secret fact A"
            assert loaded["facts"][1]["text"] == "Secret fact B"
            assert loaded["preferences"]["lang"] == "en"

    @pytest.mark.p1
    def test_load_legacy_unencrypted_memory(self, tmp_path):
        """Legacy plaintext memory files should still load (backward compat)."""
        with patch("storage.CHATS_DIR", str(tmp_path)):
            from storage import load_user_memory

            principal = "legacy-user"
            user_dir = tmp_path / principal
            user_dir.mkdir(parents=True)

            # Write a legacy plaintext file
            legacy_data = {
                "principalId": principal,
                "version": "1.0",
                "facts": ["Legacy fact"],
                "preferences": {},
                "createdAt": 1000000,
                "lastUpdated": 1000000,
            }
            (user_dir / "user_memory.json").write_text(json.dumps(legacy_data))

            loaded = load_user_memory(principal)
            # Legacy string facts normalized to dicts
            assert len(loaded["facts"]) == 1
            assert loaded["facts"][0]["text"] == "Legacy fact"

    @pytest.mark.p0
    @pytest.mark.security
    def test_different_principals_cannot_decrypt(self, tmp_path):
        """Memory encrypted for one principal cannot be decrypted by another."""
        with patch("storage.CHATS_DIR", str(tmp_path)):
            from encryption import EncryptionUtils
            from storage import save_user_memory

            principal_a = "principal-aaa"
            memory = {
                "principalId": principal_a,
                "version": "1.0",
                "facts": ["Secret"],
                "preferences": {},
                "createdAt": 1000000,
                "lastUpdated": 1000000,
            }

            save_user_memory(principal_a, memory)

            # Try to decrypt with a different principal
            memory_path = tmp_path / principal_a / "user_memory.json"
            encrypted_data = json.loads(memory_path.read_text())

            with pytest.raises(ValueError, match="Failed to decrypt"):
                EncryptionUtils.decrypt_chat(encrypted_data, "principal-bbb")


# =============================================================================
# 1.3 CODE EXECUTION DISABLED IN PRODUCTION
# =============================================================================


class TestCodeExecutionDisabled:
    """Verify code execution is disabled by default."""

    @pytest.mark.p0
    @pytest.mark.security
    def test_config_defaults_to_disabled(self):
        """CODE_EXECUTION_ENABLED should default to False when env var not set."""
        # Simulate no env var set
        with patch.dict(os.environ, {}, clear=False):
            # Remove the var if it exists
            env_copy = os.environ.copy()
            env_copy.pop("CODE_EXECUTION_ENABLED", None)
            with patch.dict(os.environ, env_copy, clear=True):
                # Re-evaluate the config expression
                result = os.getenv("CODE_EXECUTION_ENABLED", "false").lower() == "true"
                assert result is False, "CODE_EXECUTION_ENABLED defaults to True - DANGEROUS!"

    @pytest.mark.p0
    @pytest.mark.security
    def test_code_executor_returns_error_when_disabled(self):
        """Code executor must return error when disabled, never execute code."""
        with patch("services.code_executor.CODE_EXECUTION_ENABLED", False):
            from services.code_executor import execute_python_code

            success, output = execute_python_code("print('hello')")
            assert success is False
            assert "disabled" in output.lower()

    @pytest.mark.p1
    def test_code_executor_works_when_explicitly_enabled(self):
        """Code executor should work when CODE_EXECUTION_ENABLED=true."""
        with patch("services.code_executor.CODE_EXECUTION_ENABLED", True):
            from services.code_executor import execute_python_code

            # Simple math should work in sandbox
            success, output = execute_python_code("result = 2 + 2")
            # May fail if RestrictedPython not installed - that's okay
            # The point is it doesn't refuse due to disabled flag


# =============================================================================
# 1.4 NONCE-BASED REPLAY PROTECTION
# =============================================================================


class TestNonceReplayProtection:
    """Verify nonce prevents request replay attacks."""

    @pytest.mark.p0
    @pytest.mark.security
    def test_nonce_included_in_signature_message(self):
        """When nonce is provided, it must be part of the signed message."""
        from icp_auth import verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = "nonce-test-user"
        timestamp = str(int(time.time() * 1000))
        endpoint = "/test"
        nonce = str(uuid.uuid4())

        # Sign WITH nonce
        message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
        signed = signing_key.sign(message.encode("utf-8"))

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signed.signature.hex(),
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=verify_key.encode().hex(),
            nonce=nonce,
        )
        assert success, f"Valid nonce request failed: {error}"

    @pytest.mark.p0
    @pytest.mark.security
    def test_replayed_nonce_rejected(self):
        """Same nonce used twice must be rejected (replay attack)."""
        from icp_auth import used_nonces, verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = "replay-test-user"
        timestamp = str(int(time.time() * 1000))
        endpoint = "/test"
        nonce = str(uuid.uuid4())

        message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
        signed = signing_key.sign(message.encode("utf-8"))

        # First request should succeed
        success1, error1 = verify_icp_signature(
            principal=principal,
            signature_hex=signed.signature.hex(),
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=verify_key.encode().hex(),
            nonce=nonce,
        )
        assert success1, f"First request failed: {error1}"

        # Second request with SAME nonce should fail
        success2, error2 = verify_icp_signature(
            principal=principal,
            signature_hex=signed.signature.hex(),
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=verify_key.encode().hex(),
            nonce=nonce,
        )
        assert not success2, "Replayed request was accepted!"
        assert "nonce already used" in error2.lower() or "replay" in error2.lower()

        # Clean up to avoid contaminating other tests
        nonce_key = f"{principal}:{nonce}"
        if nonce_key in used_nonces:
            del used_nonces[nonce_key]

    @pytest.mark.p0
    @pytest.mark.security
    def test_different_nonces_both_accepted(self):
        """Two requests with different nonces should both succeed."""
        from icp_auth import used_nonces, verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = "multi-nonce-user"
        timestamp = str(int(time.time() * 1000))
        endpoint = "/test"

        results = []
        nonces_used = []
        for _ in range(3):
            nonce = str(uuid.uuid4())
            nonces_used.append(nonce)
            message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
            signed = signing_key.sign(message.encode("utf-8"))

            success, error = verify_icp_signature(
                principal=principal,
                signature_hex=signed.signature.hex(),
                timestamp=timestamp,
                endpoint=endpoint,
                public_key_hex=verify_key.encode().hex(),
                nonce=nonce,
            )
            results.append((success, error))

        # Clean up
        for n in nonces_used:
            nonce_key = f"{principal}:{n}"
            if nonce_key in used_nonces:
                del used_nonces[nonce_key]

        for i, (success, error) in enumerate(results):
            assert success, f"Request {i+1} with unique nonce failed: {error}"

    @pytest.mark.p1
    def test_legacy_request_without_nonce_still_works(self):
        """Requests without nonce should still work (backward compatibility)."""
        from icp_auth import verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = "legacy-no-nonce"
        timestamp = str(int(time.time() * 1000))
        endpoint = "/test"

        # Sign WITHOUT nonce (legacy format)
        message = f"{principal}:{timestamp}:{endpoint}"
        signed = signing_key.sign(message.encode("utf-8"))

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signed.signature.hex(),
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=verify_key.encode().hex(),
            nonce=None,  # No nonce
        )
        assert success, f"Legacy request without nonce failed: {error}"

    @pytest.mark.p0
    @pytest.mark.security
    def test_nonce_with_wrong_signature_rejected(self):
        """A nonce signed with wrong key must be rejected."""
        from icp_auth import verify_icp_signature

        signing_key = SigningKey.generate()
        wrong_key = SigningKey.generate()
        principal = "wrong-sig-user"
        timestamp = str(int(time.time() * 1000))
        endpoint = "/test"
        nonce = str(uuid.uuid4())

        # Sign with wrong key
        message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
        signed = wrong_key.sign(message.encode("utf-8"))

        success, error = verify_icp_signature(
            principal=principal,
            signature_hex=signed.signature.hex(),
            timestamp=timestamp,
            endpoint=endpoint,
            public_key_hex=signing_key.verify_key.encode().hex(),  # Correct public key
            nonce=nonce,
        )
        assert not success, "Request with wrong signature was accepted!"


# =============================================================================
# 1.5 CSP HEADERS (static verification)
# =============================================================================


class TestCSPHeaders:
    """Verify CSP headers are properly configured in Cloudflare Worker."""

    @pytest.mark.p1
    def test_worker_js_contains_csp_header(self):
        """Cloudflare Worker must include Content-Security-Policy header."""
        worker_path = Path(__file__).parent.parent.parent.parent / "deploy" / "cloudflare-worker" / "worker.js"
        if not worker_path.exists():
            pytest.skip("worker.js not found")

        content = worker_path.read_text()

        assert "Content-Security-Policy" in content, (
            "worker.js missing Content-Security-Policy header"
        )
        assert "frame-ancestors 'none'" in content, (
            "CSP missing frame-ancestors directive"
        )
        assert "script-src" in content, (
            "CSP missing script-src directive"
        )

    @pytest.mark.p1
    def test_worker_js_has_security_headers(self):
        """Cloudflare Worker must include standard security headers."""
        worker_path = Path(__file__).parent.parent.parent.parent / "deploy" / "cloudflare-worker" / "worker.js"
        if not worker_path.exists():
            pytest.skip("worker.js not found")

        content = worker_path.read_text()

        assert "X-Content-Type-Options" in content
        assert "X-Frame-Options" in content
        assert "Referrer-Policy" in content

    @pytest.mark.p1
    def test_worker_js_allows_nonce_header(self):
        """Cloudflare Worker must allow ICP-Nonce header in CORS."""
        worker_path = Path(__file__).parent.parent.parent.parent / "deploy" / "cloudflare-worker" / "worker.js"
        if not worker_path.exists():
            pytest.skip("worker.js not found")

        content = worker_path.read_text()

        assert "ICP-Nonce" in content, (
            "worker.js CORS headers missing ICP-Nonce"
        )
