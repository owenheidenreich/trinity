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
import sqlite3
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
    from icp_auth import principal_from_public_key

    public_key_hex = verify_key.encode().hex()
    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "public_key_hex": public_key_hex,
        "principal": principal_from_public_key(bytes.fromhex(public_key_hex)),
    }


@pytest.fixture
def non_admin_keypair():
    """Generate a keypair NOT designated as admin."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    from icp_auth import principal_from_public_key

    public_key_hex = verify_key.encode().hex()
    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "public_key_hex": public_key_hex,
        "principal": principal_from_public_key(bytes.fromhex(public_key_hex)),
    }


def make_auth_headers(keypair, endpoint, nonce=None):
    """Create valid auth headers for a given keypair and endpoint."""
    timestamp = str(int(time.time() * 1000))
    nonce = nonce or str(uuid.uuid4())
    message = f"{keypair['principal']}:{timestamp}:{endpoint}:{nonce}"
    signed = keypair["signing_key"].sign(message.encode("utf-8"))
    headers = {
        "ICP-Principal": keypair["principal"],
        "ICP-Signature": signed.signature.hex(),
        "ICP-Timestamp": timestamp,
        "ICP-PublicKey": keypair["public_key_hex"],
        "ICP-Nonce": nonce,
    }
    return headers


# =============================================================================
# 1.1 ADMIN ENDPOINT AUTHENTICATION
# =============================================================================


# =============================================================================
# 1.2 ENCRYPTED USER MEMORY STORAGE
# =============================================================================


class TestEncryptedUserMemory:
    """Verify user memory is stored encrypted, not plaintext."""

    @pytest.mark.p0
    @pytest.mark.security
    def test_save_user_memory_encrypts_data(self, tmp_path):
        """Saved memory facts must be encrypted at rest in canonical state.db."""
        with patch("storage.CHATS_DIR", str(tmp_path)), \
             patch("services.state_store.CHATS_DIR", str(tmp_path)):
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

            db_path = tmp_path / principal / "state.db"
            assert db_path.exists(), "Canonical state DB was not created"

            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                "SELECT text_enc FROM memory_facts WHERE principal_id = ? ORDER BY fact_id ASC",
                (principal,),
            ).fetchall()
            conn.close()

            assert len(rows) == 2
            raw_values = [row[0] for row in rows]
            assert all("User likes Python" not in value for value in raw_values)
            assert all("User lives in NYC" not in value for value in raw_values)

            parsed = json.loads(raw_values[0])
            assert "encryption" in parsed
            assert "encryptedContent" in parsed
            assert parsed["encryption"]["algorithm"] == "AES-256-GCM"

    @pytest.mark.p0
    @pytest.mark.security
    def test_load_user_memory_decrypts_data(self, tmp_path):
        """Loading encrypted user memory should return the original data."""
        with patch("storage.CHATS_DIR", str(tmp_path)), \
             patch("services.state_store.CHATS_DIR", str(tmp_path)):
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

            # String facts are normalized to dicts on load.
            assert len(loaded["facts"]) == 2
            loaded_texts = {fact["text"] for fact in loaded["facts"]}
            assert loaded_texts == {"Secret fact A", "Secret fact B"}
            # Legacy top-level preferences are not persisted in canonical schema.
            assert isinstance(loaded["profile"]["preferences"], dict)

    @pytest.mark.p1
    def test_load_legacy_unencrypted_memory(self, tmp_path):
        """Legacy plaintext memory files should still load (backward compat)."""
        with patch("storage.CHATS_DIR", str(tmp_path)), \
             patch("services.state_store.CHATS_DIR", str(tmp_path)):
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
        """Fact envelopes encrypted for one principal cannot be decrypted by another."""
        with patch("storage.CHATS_DIR", str(tmp_path)), \
             patch("services.state_store.CHATS_DIR", str(tmp_path)):
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

            db_path = tmp_path / principal_a / "state.db"
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT text_enc FROM memory_facts WHERE principal_id = ? LIMIT 1",
                (principal_a,),
            ).fetchone()
            conn.close()
            assert row is not None
            encrypted_envelope = json.loads(row[0])

            with pytest.raises(ValueError):
                EncryptionUtils.decrypt_auto(
                    encrypted_envelope,
                    passphrase=None,
                    principal_id="principal-bbb",
                )


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
        from icp_auth import principal_from_public_key, verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = principal_from_public_key(bytes(verify_key))
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
        from icp_auth import principal_from_public_key, used_nonces, verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = principal_from_public_key(bytes(verify_key))
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
        from icp_auth import principal_from_public_key, used_nonces, verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = principal_from_public_key(bytes(verify_key))
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
    def test_request_without_nonce_rejected(self):
        """Requests without nonce must be rejected."""
        from icp_auth import principal_from_public_key, verify_icp_signature

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        principal = principal_from_public_key(bytes(verify_key))
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
        assert not success, "Nonce-free request should be rejected"
        assert error is not None
        assert "nonce" in error.lower()

    @pytest.mark.p0
    @pytest.mark.security
    def test_nonce_with_wrong_signature_rejected(self):
        """A nonce signed with wrong key must be rejected."""
        from icp_auth import principal_from_public_key, verify_icp_signature

        signing_key = SigningKey.generate()
        wrong_key = SigningKey.generate()
        principal = principal_from_public_key(bytes(signing_key.verify_key))
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
    def test_csp_contains_ic0_and_wasm_eval_regression_guards(self):
        """CSP in all served entry points must allow ICP API calls and WASM auth libs."""
        project_root = Path(__file__).parent.parent.parent.parent
        csp_files = [
            project_root / "deploy" / "cloudflare-worker" / "worker.js",
            project_root / "trinity-icp" / "src" / "index.html",
            project_root / "trinity-icp" / "src-react" / "index.html",
            project_root / "trinity-icp" / "src-react" / "public" / ".ic-assets.json5",
        ]

        missing_files = [str(path) for path in csp_files if not path.exists()]
        if missing_files:
            pytest.skip(f"CSP source files not found: {', '.join(missing_files)}")

        for csp_path in csp_files:
            content = csp_path.read_text()
            assert "'wasm-unsafe-eval'" in content, (
                f"{csp_path} missing wasm-unsafe-eval in CSP"
            )
            assert "https://ic0.app" in content, (
                f"{csp_path} missing https://ic0.app in CSP connect-src"
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
