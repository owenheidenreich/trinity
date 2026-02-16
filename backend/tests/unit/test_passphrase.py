"""
Tests for passphrase-based encryption (Milestone 1).

Tests:
  1. Passphrase KDF and encrypt/decrypt
  2. Canary creation and verification
  3. decrypt_auto routing (passphrase vs principal)
  4. Session manager lifecycle
  5. Security: principal cannot decrypt passphrase data
"""
import pytest
from encryption import EncryptionUtils
from services.session_manager import (
    set_session_passphrase,
    get_session_passphrase,
    has_passphrase,
    clear_session,
    clear_all_sessions,
)


# =============================================================================
# PASSPHRASE ENCRYPTION
# =============================================================================

class TestPassphraseEncryption:
    """Tests for passphrase-based encrypt/decrypt."""

    def test_encrypt_decrypt_roundtrip(self):
        data = {"message": "hello world", "count": 42}
        passphrase = "my-secure-passphrase"

        encrypted = EncryptionUtils.encrypt_with_passphrase(data, passphrase)
        decrypted = EncryptionUtils.decrypt_with_passphrase(encrypted, passphrase)

        assert decrypted == data

    def test_encrypted_envelope_has_passphrase_marker(self):
        data = {"test": True}
        encrypted = EncryptionUtils.encrypt_with_passphrase(data, "testpass123")

        assert encrypted["version"] == "2.0"
        assert encrypted["encryption"]["kdf_source"] == "passphrase"
        assert encrypted["encryption"]["algorithm"] == "AES-256-GCM"

    def test_different_passphrase_cannot_decrypt(self):
        data = {"secret": "value"}
        encrypted = EncryptionUtils.encrypt_with_passphrase(data, "correct-passphrase")

        with pytest.raises(ValueError):
            EncryptionUtils.decrypt_with_passphrase(encrypted, "wrong-passphrase")

    def test_principal_cannot_decrypt_passphrase_data(self):
        """The critical security test: principal-based decryption must fail
        on passphrase-encrypted data."""
        data = {"secret": "value"}
        passphrase = "user-secret-passphrase"
        principal = "aaaaa-bbbbb-ccccc-ddddd-eeeee"

        encrypted = EncryptionUtils.encrypt_with_passphrase(data, passphrase)

        with pytest.raises(ValueError):
            EncryptionUtils.decrypt_chat(encrypted, principal)

    def test_each_encryption_uses_unique_salt(self):
        data = {"test": True}
        enc1 = EncryptionUtils.encrypt_with_passphrase(data, "same-passphrase")
        enc2 = EncryptionUtils.encrypt_with_passphrase(data, "same-passphrase")

        assert enc1["encryption"]["salt"] != enc2["encryption"]["salt"]
        assert enc1["encryptedContent"] != enc2["encryptedContent"]

    def test_unicode_passphrase(self):
        data = {"emoji": True}
        passphrase = "p@$$w0rd-with-unicode"

        encrypted = EncryptionUtils.encrypt_with_passphrase(data, passphrase)
        decrypted = EncryptionUtils.decrypt_with_passphrase(encrypted, passphrase)

        assert decrypted == data

    def test_empty_data_encrypts(self):
        encrypted = EncryptionUtils.encrypt_with_passphrase({}, "passphrase")
        decrypted = EncryptionUtils.decrypt_with_passphrase(encrypted, "passphrase")
        assert decrypted == {}

    def test_large_data_encrypts(self):
        data = {"facts": [{"text": f"fact {i}", "importance": 3} for i in range(1000)]}
        encrypted = EncryptionUtils.encrypt_with_passphrase(data, "passphrase")
        decrypted = EncryptionUtils.decrypt_with_passphrase(encrypted, "passphrase")
        assert len(decrypted["facts"]) == 1000


# =============================================================================
# CANARY
# =============================================================================

class TestPassphraseCanary:
    """Tests for canary blob creation and verification."""

    def test_create_and_verify_canary(self):
        passphrase = "my-passphrase"
        canary = EncryptionUtils.create_passphrase_canary(passphrase)

        assert EncryptionUtils.verify_passphrase_canary(canary, passphrase) is True

    def test_wrong_passphrase_fails_canary(self):
        canary = EncryptionUtils.create_passphrase_canary("correct")

        assert EncryptionUtils.verify_passphrase_canary(canary, "wrong") is False

    def test_canary_is_encrypted_envelope(self):
        canary = EncryptionUtils.create_passphrase_canary("test")

        assert "encryption" in canary
        assert "encryptedContent" in canary
        assert canary["encryption"]["kdf_source"] == "passphrase"


# =============================================================================
# DECRYPT_AUTO
# =============================================================================

class TestDecryptAuto:
    """Tests for automatic decryption routing."""

    def test_routes_passphrase_data_to_passphrase_decrypt(self):
        data = {"test": "passphrase-encrypted"}
        passphrase = "my-pass"
        encrypted = EncryptionUtils.encrypt_with_passphrase(data, passphrase)

        result = EncryptionUtils.decrypt_auto(encrypted, passphrase=passphrase, principal_id="ignored")
        assert result == data

    def test_routes_legacy_data_to_principal_decrypt(self):
        data = {"test": "principal-encrypted"}
        principal = "test-principal-id"
        encrypted = EncryptionUtils.encrypt_chat(data, principal)

        result = EncryptionUtils.decrypt_auto(encrypted, passphrase=None, principal_id=principal)
        assert result == data

    def test_passphrase_data_without_passphrase_raises(self):
        data = {"test": True}
        encrypted = EncryptionUtils.encrypt_with_passphrase(data, "pass")

        with pytest.raises(ValueError, match="Passphrase required"):
            EncryptionUtils.decrypt_auto(encrypted, passphrase=None, principal_id="anything")

    def test_legacy_data_without_principal_raises(self):
        data = {"test": True}
        encrypted = EncryptionUtils.encrypt_chat(data, "principal")

        with pytest.raises(ValueError, match="Principal ID required"):
            EncryptionUtils.decrypt_auto(encrypted, passphrase=None, principal_id=None)


# =============================================================================
# SESSION MANAGER
# =============================================================================

class TestSessionManager:
    """Tests for in-memory passphrase session management."""

    def setup_method(self):
        clear_all_sessions()

    def test_set_and_get_passphrase(self):
        set_session_passphrase("user-1", "my-passphrase")
        assert get_session_passphrase("user-1") == "my-passphrase"

    def test_get_nonexistent_returns_none(self):
        assert get_session_passphrase("no-such-user") is None

    def test_has_passphrase(self):
        assert has_passphrase("user-1") is False
        set_session_passphrase("user-1", "pass")
        assert has_passphrase("user-1") is True

    def test_clear_session(self):
        set_session_passphrase("user-1", "pass")
        clear_session("user-1")
        assert has_passphrase("user-1") is False
        assert get_session_passphrase("user-1") is None

    def test_clear_all_sessions(self):
        set_session_passphrase("user-1", "pass1")
        set_session_passphrase("user-2", "pass2")
        clear_all_sessions()
        assert has_passphrase("user-1") is False
        assert has_passphrase("user-2") is False

    def test_multiple_users_isolated(self):
        set_session_passphrase("user-1", "pass1")
        set_session_passphrase("user-2", "pass2")
        assert get_session_passphrase("user-1") == "pass1"
        assert get_session_passphrase("user-2") == "pass2"

    def test_overwrite_passphrase(self):
        set_session_passphrase("user-1", "old-pass")
        set_session_passphrase("user-1", "new-pass")
        assert get_session_passphrase("user-1") == "new-pass"

    def test_clear_nonexistent_is_safe(self):
        clear_session("no-such-user")  # Should not raise
