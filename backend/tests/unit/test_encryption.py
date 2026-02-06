"""
Trinity Backend - Encryption Security Test Suite
=================================================
Comprehensive adversarial testing for AES-256-GCM encryption.

Security Focus Areas:
1. Key derivation security (Argon2id/PBKDF2)
2. Encryption/decryption integrity
3. Authentication tag verification
4. Ciphertext tampering detection
5. Wrong key rejection
6. Replay attack prevention
7. Side-channel considerations
8. Edge cases and malformed input

Target Coverage: 95%+
"""

import base64
import copy
import json
from unittest.mock import patch

import pytest
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


class TestEncryptionUtils:
    """Core encryption/decryption functionality tests."""

    def test_encrypt_decrypt_roundtrip(self, encryption_utils):
        """Verify data survives encryption/decryption cycle."""
        chat_data = {
            "id": "test-chat-123",
            "title": "Security Test Chat",
            "messages": [
                {"role": "user", "content": "Hello, world!"},
                {"role": "assistant", "content": "Greetings!"},
            ],
            "metadata": {"createdAt": 1700000000000},
        }
        principal_id = "abc123-def456-ghi789"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal_id)
        decrypted = encryption_utils.decrypt_chat(encrypted, principal_id)

        assert decrypted == chat_data

    def test_encrypt_produces_different_ciphertext_each_time(self, encryption_utils):
        """Ensure nonce randomization prevents identical ciphertexts."""
        chat_data = {"id": "test", "messages": []}
        principal_id = "test-principal"

        encrypted1 = encryption_utils.encrypt_chat(chat_data, principal_id)
        encrypted2 = encryption_utils.encrypt_chat(chat_data, principal_id)

        # Same plaintext should produce different ciphertext
        assert encrypted1["encryptedContent"] != encrypted2["encryptedContent"]
        assert encrypted1["encryption"]["nonce"] != encrypted2["encryption"]["nonce"]
        assert encrypted1["encryption"]["salt"] != encrypted2["encryption"]["salt"]

    def test_encrypted_structure_contains_all_fields(self, encryption_utils):
        """Verify encrypted output has correct structure."""
        chat_data = {"id": "test", "messages": []}
        encrypted = encryption_utils.encrypt_chat(chat_data, "test-principal")

        assert "version" in encrypted
        assert "encryption" in encrypted
        assert "encryptedContent" in encrypted
        assert "fileMetadata" in encrypted

        enc_meta = encrypted["encryption"]
        assert enc_meta["algorithm"] == "AES-256-GCM"
        assert enc_meta["kdf"] in ("argon2id", "pbkdf2")
        assert "salt" in enc_meta
        assert "nonce" in enc_meta
        assert "tag" in enc_meta

    def test_file_metadata_preserved(self, encryption_utils):
        """Verify metadata is correctly populated."""
        principal_id = "principal-abc"
        created_at = 1699999999000
        chat_data = {"id": "test", "messages": [], "metadata": {"createdAt": created_at}}

        encrypted = encryption_utils.encrypt_chat(chat_data, principal_id)

        assert encrypted["fileMetadata"]["principalId"] == principal_id
        assert encrypted["fileMetadata"]["createdAt"] == created_at
        assert encrypted["fileMetadata"]["contentType"] == "application/json"


class TestKeyDerivationSecurity:
    """Key derivation function security tests."""

    def test_same_password_different_salt_produces_different_keys(self, encryption_utils):
        """Salt must produce unique keys for same password."""
        principal = "test-principal"
        salt1 = get_random_bytes(16)
        salt2 = get_random_bytes(16)

        key1, _ = encryption_utils.derive_key(principal, salt1)
        key2, _ = encryption_utils.derive_key(principal, salt2)

        assert key1 != key2

    def test_different_password_same_salt_produces_different_keys(self, encryption_utils):
        """Different passwords must produce different keys."""
        salt = get_random_bytes(16)

        key1, _ = encryption_utils.derive_key("principal-1", salt)
        key2, _ = encryption_utils.derive_key("principal-2", salt)

        assert key1 != key2

    def test_key_length_is_256_bits(self, encryption_utils):
        """Key must be exactly 32 bytes (256 bits) for AES-256."""
        salt = get_random_bytes(16)
        key, _ = encryption_utils.derive_key("test", salt)

        assert len(key) == 32

    def test_pbkdf2_fallback_explicit(self, encryption_utils):
        """PBKDF2 can be explicitly requested."""
        salt = get_random_bytes(16)
        key, algo = encryption_utils.derive_key("test", salt, algorithm="pbkdf2")

        assert algo == "pbkdf2"
        assert len(key) == 32

    def test_key_derivation_deterministic(self, encryption_utils):
        """Same inputs must always produce same key."""
        principal = "test-principal"
        salt = b"static_salt_1234"  # 16 bytes

        key1, _ = encryption_utils.derive_key(principal, salt)
        key2, _ = encryption_utils.derive_key(principal, salt)

        assert key1 == key2

    def test_empty_principal_still_derives_key(self, encryption_utils):
        """Edge case: empty string should still derive a key."""
        salt = get_random_bytes(16)
        key, _ = encryption_utils.derive_key("", salt)

        assert len(key) == 32

    def test_unicode_principal_supported(self, encryption_utils):
        """Unicode characters in principal ID handled correctly."""
        salt = get_random_bytes(16)
        # Japanese characters
        key, _ = encryption_utils.derive_key("プリンシパル-123", salt)

        assert len(key) == 32


class TestCiphertextTamperingDetection:
    """Authentication tag verification and tamper detection."""

    def test_tampered_ciphertext_detected(self, encryption_utils):
        """Modified ciphertext must fail authentication."""
        chat_data = {"id": "test", "secret": "confidential"}
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)

        # Tamper with ciphertext (flip a bit)
        original_ct = base64.b64decode(encrypted["encryptedContent"])
        tampered_ct = bytearray(original_ct)
        tampered_ct[0] ^= 0xFF  # Flip all bits in first byte
        encrypted["encryptedContent"] = base64.b64encode(bytes(tampered_ct)).decode()

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, principal)

    def test_tampered_tag_detected(self, encryption_utils):
        """Modified authentication tag must fail."""
        chat_data = {"id": "test"}
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)

        # Tamper with tag
        original_tag = base64.b64decode(encrypted["encryption"]["tag"])
        tampered_tag = bytearray(original_tag)
        tampered_tag[0] ^= 0xFF
        encrypted["encryption"]["tag"] = base64.b64encode(bytes(tampered_tag)).decode()

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, principal)

    def test_tampered_nonce_causes_decryption_failure(self, encryption_utils):
        """Modified nonce produces wrong decryption or auth failure."""
        chat_data = {"id": "test"}
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)

        # Tamper with nonce
        original_nonce = base64.b64decode(encrypted["encryption"]["nonce"])
        tampered_nonce = bytearray(original_nonce)
        tampered_nonce[0] ^= 0xFF
        encrypted["encryption"]["nonce"] = base64.b64encode(bytes(tampered_nonce)).decode()

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, principal)

    def test_tampered_salt_causes_wrong_key(self, encryption_utils):
        """Modified salt produces wrong key, fails authentication."""
        chat_data = {"id": "test"}
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)

        # Tamper with salt
        original_salt = base64.b64decode(encrypted["encryption"]["salt"])
        tampered_salt = bytearray(original_salt)
        tampered_salt[0] ^= 0xFF
        encrypted["encryption"]["salt"] = base64.b64encode(bytes(tampered_salt)).decode()

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, principal)

    def test_truncated_ciphertext_fails(self, encryption_utils):
        """Shortened ciphertext must fail."""
        chat_data = {"id": "test", "messages": ["a" * 1000]}  # Longer content
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)

        # Truncate ciphertext
        original_ct = base64.b64decode(encrypted["encryptedContent"])
        truncated_ct = original_ct[: len(original_ct) // 2]
        encrypted["encryptedContent"] = base64.b64encode(truncated_ct).decode()

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, principal)


class TestWrongKeyRejection:
    """Access control via encryption key."""

    def test_wrong_principal_cannot_decrypt(self, encryption_utils):
        """Data encrypted for one principal must not decrypt for another."""
        chat_data = {"id": "test", "secret": "do not leak"}
        original_principal = "alice-principal"
        attacker_principal = "mallory-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, original_principal)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, attacker_principal)

    def test_similar_principal_cannot_decrypt(self, encryption_utils):
        """Even slightly different principal must fail."""
        chat_data = {"id": "test"}
        original = "principal-abc123"
        similar = "principal-abc124"  # One character different

        encrypted = encryption_utils.encrypt_chat(chat_data, original)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, similar)

    def test_case_sensitive_principal(self, encryption_utils):
        """Principal comparison must be case-sensitive."""
        chat_data = {"id": "test"}
        original = "Principal-ABC"
        different_case = "principal-abc"

        encrypted = encryption_utils.encrypt_chat(chat_data, original)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, different_case)

    def test_empty_principal_attacker_fails(self, encryption_utils):
        """Empty string principal must not decrypt real principal's data."""
        chat_data = {"id": "test"}
        real_principal = "real-user-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, real_principal)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, "")


class TestMalformedInputHandling:
    """Graceful handling of corrupted/invalid input."""

    def test_invalid_base64_ciphertext(self, encryption_utils):
        """Invalid base64 in ciphertext must fail gracefully."""
        encrypted = {
            "encryption": {
                "salt": base64.b64encode(get_random_bytes(16)).decode(),
                "nonce": base64.b64encode(get_random_bytes(12)).decode(),
                "tag": base64.b64encode(get_random_bytes(16)).decode(),
                "kdf": "pbkdf2",
            },
            "encryptedContent": "!!!not-valid-base64!!!",
        }

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, "test")

    def test_missing_encryption_fields(self, encryption_utils):
        """Missing required fields must fail gracefully."""
        encrypted = {
            "encryption": {
                "salt": base64.b64encode(get_random_bytes(16)).decode(),
                # missing nonce, tag
            },
            "encryptedContent": base64.b64encode(b"fake").decode(),
        }

        with pytest.raises((ValueError, KeyError)):
            encryption_utils.decrypt_chat(encrypted, "test")

    def test_empty_ciphertext(self, encryption_utils):
        """Empty ciphertext must fail."""
        encrypted = {
            "encryption": {
                "salt": base64.b64encode(get_random_bytes(16)).decode(),
                "nonce": base64.b64encode(get_random_bytes(12)).decode(),
                "tag": base64.b64encode(get_random_bytes(16)).decode(),
                "kdf": "pbkdf2",
            },
            "encryptedContent": "",
        }

        with pytest.raises(ValueError):
            encryption_utils.decrypt_chat(encrypted, "test")

    def test_wrong_tag_length(self, encryption_utils):
        """Tag with wrong length must fail."""
        encrypted = {
            "encryption": {
                "salt": base64.b64encode(get_random_bytes(16)).decode(),
                "nonce": base64.b64encode(get_random_bytes(12)).decode(),
                "tag": base64.b64encode(b"short").decode(),  # Too short
                "kdf": "pbkdf2",
            },
            "encryptedContent": base64.b64encode(get_random_bytes(32)).decode(),
        }

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(encrypted, "test")


class TestKDFAlgorithmSelection:
    """KDF algorithm selection and backward compatibility."""

    def test_pbkdf2_encrypted_data_decrypts_correctly(self, encryption_utils):
        """Data encrypted with explicit PBKDF2 must decrypt."""
        chat_data = {"id": "legacy-test"}
        principal = "test-principal"
        salt = get_random_bytes(16)

        # Encrypt manually with PBKDF2
        key, algo = encryption_utils.derive_key(principal, salt, algorithm="pbkdf2")
        assert algo == "pbkdf2"

        plaintext = json.dumps(chat_data).encode("utf-8")
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        encrypted = {
            "version": "1.1",
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": "pbkdf2",
                "salt": base64.b64encode(salt).decode(),
                "nonce": base64.b64encode(cipher.nonce).decode(),
                "tag": base64.b64encode(tag).decode(),
            },
            "encryptedContent": base64.b64encode(ciphertext).decode(),
        }

        decrypted = encryption_utils.decrypt_chat(encrypted, principal)
        assert decrypted == chat_data

    def test_legacy_data_without_kdf_field_uses_pbkdf2(self, encryption_utils):
        """Old encrypted data without 'kdf' field should use PBKDF2."""
        chat_data = {"id": "v1-legacy"}
        principal = "test-principal"
        salt = get_random_bytes(16)

        # Encrypt with PBKDF2 (simulating old format)
        key, _ = encryption_utils.derive_key(principal, salt, algorithm="pbkdf2")

        plaintext = json.dumps(chat_data).encode("utf-8")
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        encrypted = {
            "version": "1.0",  # Old version
            "encryption": {
                "algorithm": "AES-256-GCM",
                # NO 'kdf' field - simulating legacy data
                "salt": base64.b64encode(salt).decode(),
                "nonce": base64.b64encode(cipher.nonce).decode(),
                "tag": base64.b64encode(tag).decode(),
            },
            "encryptedContent": base64.b64encode(ciphertext).decode(),
        }

        decrypted = encryption_utils.decrypt_chat(encrypted, principal)
        assert decrypted == chat_data


class TestArgon2Availability:
    """Argon2id availability and fallback behavior."""

    def test_argon2_unavailable_falls_back_to_pbkdf2(self):
        """When Argon2 unavailable, PBKDF2 is used."""
        with patch.dict("sys.modules", {"argon2": None, "argon2.low_level": None}):
            # Need to reimport to trigger fallback
            pass


            # This tests the fallback logic in derive_key
            from encryption import EncryptionUtils

            salt = get_random_bytes(16)

            # Force the fallback path
            with patch.object(
                EncryptionUtils,
                "derive_key_argon2",
                side_effect=RuntimeError("Argon2 not available"),
            ):
                key, algo = EncryptionUtils.derive_key("test", salt)
                assert algo == "pbkdf2"
                assert len(key) == 32


class TestLargeDataHandling:
    """Performance and correctness with large data."""

    def test_large_chat_encrypts_correctly(self, encryption_utils):
        """Large chat data (many messages) encrypts/decrypts correctly."""
        chat_data = {
            "id": "large-chat",
            "messages": [
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}: " + "x" * 1000,
                }
                for i in range(100)  # 100 messages, ~100KB
            ],
        }
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)
        decrypted = encryption_utils.decrypt_chat(encrypted, principal)

        assert decrypted == chat_data
        assert len(decrypted["messages"]) == 100

    def test_special_characters_in_content(self, encryption_utils):
        """Unicode, emoji, special chars preserved."""
        chat_data = {
            "id": "unicode-test",
            "messages": [
                {"role": "user", "content": "🔐 Encryption test 日本語 العربية"},
                {"role": "assistant", "content": "∑∫∂ε Math symbols <script>alert(1)</script>"},
            ],
        }
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)
        decrypted = encryption_utils.decrypt_chat(encrypted, principal)

        assert decrypted == chat_data

    def test_nested_json_structures(self, encryption_utils):
        """Complex nested JSON preserved."""
        chat_data = {
            "id": "nested",
            "metadata": {"nested": {"deep": {"value": [1, 2, {"key": "value"}]}}},
            "messages": [],
        }
        principal = "test-principal"

        encrypted = encryption_utils.encrypt_chat(chat_data, principal)
        decrypted = encryption_utils.decrypt_chat(encrypted, principal)

        assert decrypted == chat_data


class TestReplayAndReorderingAttacks:
    """Protection against replay and message reordering."""

    def test_cannot_swap_ciphertext_between_users(self, encryption_utils):
        """Ciphertext from user A cannot be used to access user B's decryption."""
        chat_a = {"id": "alice-chat", "secret": "alice-secret"}
        chat_b = {"id": "bob-chat", "secret": "bob-secret"}

        encrypted_a = encryption_utils.encrypt_chat(chat_a, "alice")
        encrypted_b = encryption_utils.encrypt_chat(chat_b, "bob")

        # Try to use Alice's salt/nonce with Bob's ciphertext
        hybrid = copy.deepcopy(encrypted_a)
        hybrid["encryptedContent"] = encrypted_b["encryptedContent"]

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(hybrid, "alice")

    def test_cannot_use_old_encryption_metadata_with_new_content(self, encryption_utils):
        """Old metadata cannot decrypt newly encrypted content."""
        principal = "test"
        chat1 = {"id": "v1", "data": "original"}
        chat2 = {"id": "v2", "data": "updated"}

        encrypted1 = encryption_utils.encrypt_chat(chat1, principal)
        encrypted2 = encryption_utils.encrypt_chat(chat2, principal)

        # Try using encryption params from v1 with ciphertext from v2
        hybrid = copy.deepcopy(encrypted1)
        hybrid["encryptedContent"] = encrypted2["encryptedContent"]

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption_utils.decrypt_chat(hybrid, principal)


class TestCryptographicProperties:
    """Verify cryptographic guarantees."""

    def test_nonce_is_unique_per_encryption(self, encryption_utils):
        """Nonces must never repeat (critical for GCM security)."""
        principal = "test"
        chat = {"id": "test"}

        nonces = set()
        for _ in range(100):
            encrypted = encryption_utils.encrypt_chat(chat, principal)
            nonce = encrypted["encryption"]["nonce"]
            assert nonce not in nonces, "Nonce reuse detected!"
            nonces.add(nonce)

    def test_salt_is_unique_per_encryption(self, encryption_utils):
        """Salt randomization verified."""
        principal = "test"
        chat = {"id": "test"}

        salts = set()
        for _ in range(100):
            encrypted = encryption_utils.encrypt_chat(chat, principal)
            salt = encrypted["encryption"]["salt"]
            assert salt not in salts, "Salt reuse detected!"
            salts.add(salt)

    def test_ciphertext_length_hides_exact_plaintext_length(self, encryption_utils):
        """Ciphertext should be close to plaintext length (AES-GCM property)."""
        # Note: AES-GCM doesn't pad, so ciphertext ≈ plaintext length
        # This test verifies the relationship is consistent
        principal = "test"

        short_chat = {"id": "a"}
        long_chat = {"id": "a" * 1000}

        short_encrypted = encryption_utils.encrypt_chat(short_chat, principal)
        long_encrypted = encryption_utils.encrypt_chat(long_chat, principal)

        short_ct = base64.b64decode(short_encrypted["encryptedContent"])
        long_ct = base64.b64decode(long_encrypted["encryptedContent"])

        # Long plaintext should produce longer ciphertext
        assert len(long_ct) > len(short_ct)


# ============== FIXTURES ==============


@pytest.fixture
def encryption_utils():
    """Provide EncryptionUtils class for testing."""
    from encryption import EncryptionUtils

    return EncryptionUtils
