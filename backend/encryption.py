"""
Trinity Backend - Encryption Module
AES-256-GCM encryption for chat content
Supports Argon2id (preferred) or PBKDF2 (fallback) for key derivation
"""

import base64
import json
import logging
import time
from typing import Dict

from config import ENCRYPTION_KEY_LENGTH, PBKDF2_ITERATIONS
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes

logger = logging.getLogger(__name__)

# Try to use Argon2id (more secure, resistant to GPU attacks)
try:
    from argon2.low_level import Type, hash_secret_raw

    ARGON2_AVAILABLE = True
    logger.info("✅ Argon2id available for key derivation")
except ImportError:
    ARGON2_AVAILABLE = False
    logger.warning("⚠️ Argon2 not available, using PBKDF2 fallback")


class EncryptionUtils:
    """Handle AES-256-GCM encryption for chat content"""

    @staticmethod
    def derive_key_argon2(principal_id: str, salt: bytes) -> bytes:
        """Derive encryption key using Argon2id (recommended)"""
        if not ARGON2_AVAILABLE:
            raise RuntimeError("Argon2 not available")

        return hash_secret_raw(
            secret=principal_id.encode("utf-8"),
            salt=salt,
            time_cost=3,  # Number of iterations
            memory_cost=65536,  # 64 MB memory
            parallelism=4,  # 4 threads
            hash_len=ENCRYPTION_KEY_LENGTH,
            type=Type.ID,  # Argon2id (hybrid)
        )

    @staticmethod
    def derive_key_pbkdf2(principal_id: str, salt: bytes) -> bytes:
        """Derive encryption key from principal ID using PBKDF2 (fallback)"""
        return PBKDF2(
            principal_id,
            salt,
            dkLen=ENCRYPTION_KEY_LENGTH,
            count=PBKDF2_ITERATIONS,
            hmac_hash_module=SHA256,
        )

    @staticmethod
    def derive_key(principal_id: str, salt: bytes, algorithm: str = None) -> tuple[bytes, str]:
        """
        Derive encryption key using best available algorithm.
        Returns (key, algorithm_used) for storage.
        """
        if algorithm == "pbkdf2" or (algorithm is None and not ARGON2_AVAILABLE):
            return EncryptionUtils.derive_key_pbkdf2(principal_id, salt), "pbkdf2"
        else:
            try:
                return EncryptionUtils.derive_key_argon2(principal_id, salt), "argon2id"
            except Exception:
                return EncryptionUtils.derive_key_pbkdf2(principal_id, salt), "pbkdf2"

    @staticmethod
    def encrypt_chat(chat_data: Dict, principal_id: str) -> Dict:
        """Encrypt chat content with AES-256-GCM"""
        salt = get_random_bytes(16)
        key, kdf_algorithm = EncryptionUtils.derive_key(principal_id, salt)

        # Serialize chat data
        plaintext = json.dumps(chat_data).encode("utf-8")

        # Generate nonce and encrypt
        cipher = AES.new(key, AES.MODE_GCM)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        return {
            "version": "1.1",  # Updated version for Argon2id support
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": kdf_algorithm,  # 'argon2id' or 'pbkdf2'
                "salt": base64.b64encode(salt).decode("utf-8"),
                "nonce": base64.b64encode(nonce).decode("utf-8"),
                "tag": base64.b64encode(tag).decode("utf-8"),
            },
            "encryptedContent": base64.b64encode(ciphertext).decode("utf-8"),
            "fileMetadata": {
                "principalId": principal_id,
                "createdAt": chat_data.get("metadata", {}).get(
                    "createdAt", int(time.time() * 1000)
                ),
                "contentType": "application/json",
            },
        }

    @staticmethod
    def decrypt_chat(encrypted_data: Dict, principal_id: str) -> Dict:
        """Decrypt chat content"""
        try:
            salt = base64.b64decode(encrypted_data["encryption"]["salt"])
            nonce = base64.b64decode(encrypted_data["encryption"]["nonce"])
            tag = base64.b64decode(encrypted_data["encryption"]["tag"])
            ciphertext = base64.b64decode(encrypted_data["encryptedContent"])

            # Detect which KDF was used (for backward compatibility)
            kdf_algorithm = encrypted_data["encryption"].get("kdf", "pbkdf2")
            key, _ = EncryptionUtils.derive_key(principal_id, salt, algorithm=kdf_algorithm)

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)

            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Failed to decrypt chat - wrong principal or corrupted data")

    # --- Passphrase-based encryption (Milestone 1) ---

    @staticmethod
    def derive_key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
        """Derive encryption key from user passphrase using Argon2id with hardened params.

        Unlike principal-based derivation, passphrase is a secret known only to the user.
        Uses stronger cost parameters since passphrase entropy is typically lower than
        a cryptographic key.
        """
        if not ARGON2_AVAILABLE:
            return PBKDF2(
                passphrase,
                salt,
                dkLen=ENCRYPTION_KEY_LENGTH,
                count=PBKDF2_ITERATIONS * 2,
                hmac_hash_module=SHA256,
            )

        return hash_secret_raw(
            secret=passphrase.encode("utf-8"),
            salt=salt,
            time_cost=6,
            memory_cost=131072,  # 128 MB
            parallelism=4,
            hash_len=ENCRYPTION_KEY_LENGTH,
            type=Type.ID,
        )

    @staticmethod
    def encrypt_with_passphrase(data: Dict, passphrase: str) -> Dict:
        """Encrypt data using a user-supplied passphrase.

        The passphrase is never stored — only the user knows it.
        The encrypted envelope includes kdf_source: 'passphrase' so decrypt
        logic can distinguish from legacy principal-based encryption.
        """
        salt = get_random_bytes(16)
        key = EncryptionUtils.derive_key_from_passphrase(passphrase, salt)

        plaintext = json.dumps(data).encode("utf-8")
        cipher = AES.new(key, AES.MODE_GCM)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        kdf_name = "argon2id" if ARGON2_AVAILABLE else "pbkdf2"

        return {
            "version": "2.0",
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": kdf_name,
                "kdf_source": "passphrase",
                "salt": base64.b64encode(salt).decode("utf-8"),
                "nonce": base64.b64encode(nonce).decode("utf-8"),
                "tag": base64.b64encode(tag).decode("utf-8"),
            },
            "encryptedContent": base64.b64encode(ciphertext).decode("utf-8"),
            "fileMetadata": {
                "createdAt": int(time.time() * 1000),
                "contentType": "application/json",
            },
        }

    @staticmethod
    def decrypt_with_passphrase(encrypted_data: Dict, passphrase: str) -> Dict:
        """Decrypt data that was encrypted with a passphrase."""
        try:
            salt = base64.b64decode(encrypted_data["encryption"]["salt"])
            nonce = base64.b64decode(encrypted_data["encryption"]["nonce"])
            tag = base64.b64decode(encrypted_data["encryption"]["tag"])
            ciphertext = base64.b64decode(encrypted_data["encryptedContent"])

            key = EncryptionUtils.derive_key_from_passphrase(passphrase, salt)

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)

            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error(f"Passphrase decryption failed: {e}")
            raise ValueError("Failed to decrypt - wrong passphrase or corrupted data")

    @staticmethod
    def decrypt_auto(encrypted_data: Dict, passphrase: str = None, principal_id: str = None) -> Dict:
        """Decrypt data, automatically choosing passphrase or principal-based decryption.

        Tries passphrase first if the envelope indicates kdf_source='passphrase'.
        Falls back to principal-based for legacy data.
        """
        kdf_source = encrypted_data.get("encryption", {}).get("kdf_source")

        if kdf_source == "passphrase":
            if not passphrase:
                raise ValueError("Passphrase required to decrypt this data")
            return EncryptionUtils.decrypt_with_passphrase(encrypted_data, passphrase)

        # Legacy: principal-based encryption
        if not principal_id:
            raise ValueError("Principal ID required to decrypt legacy data")
        return EncryptionUtils.decrypt_chat(encrypted_data, principal_id)

    @staticmethod
    def create_passphrase_canary(passphrase: str) -> Dict:
        """Create a small encrypted blob to verify passphrase correctness on login.

        Contains a known plaintext marker. If decryption succeeds and the marker
        matches, the passphrase is correct.
        """
        canary_data = {
            "marker": "trinity-passphrase-canary-v1",
            "created_at": int(time.time() * 1000),
        }
        return EncryptionUtils.encrypt_with_passphrase(canary_data, passphrase)

    @staticmethod
    def verify_passphrase_canary(canary: Dict, passphrase: str) -> bool:
        """Verify a passphrase by decrypting the canary blob."""
        try:
            result = EncryptionUtils.decrypt_with_passphrase(canary, passphrase)
            return result.get("marker") == "trinity-passphrase-canary-v1"
        except (ValueError, Exception):
            return False
