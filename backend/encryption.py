"""
Trinity Backend - Encryption Module
AES-256-GCM encryption for chat content
Supports Argon2id (preferred) or PBKDF2 (fallback) for key derivation
"""

import json
import base64
import time
import logging
from typing import Dict

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256

from config import PBKDF2_ITERATIONS, ENCRYPTION_KEY_LENGTH

logger = logging.getLogger(__name__)

# Try to use Argon2id (more secure, resistant to GPU attacks)
try:
    from argon2.low_level import hash_secret_raw, Type
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
            secret=principal_id.encode('utf-8'),
            salt=salt,
            time_cost=3,        # Number of iterations
            memory_cost=65536,  # 64 MB memory
            parallelism=4,      # 4 threads
            hash_len=ENCRYPTION_KEY_LENGTH,
            type=Type.ID        # Argon2id (hybrid)
        )
    
    @staticmethod
    def derive_key_pbkdf2(principal_id: str, salt: bytes) -> bytes:
        """Derive encryption key from principal ID using PBKDF2 (fallback)"""
        return PBKDF2(
            principal_id, 
            salt, 
            dkLen=ENCRYPTION_KEY_LENGTH, 
            count=PBKDF2_ITERATIONS, 
            hmac_hash_module=SHA256
        )
    
    @staticmethod
    def derive_key(principal_id: str, salt: bytes, algorithm: str = None) -> tuple[bytes, str]:
        """
        Derive encryption key using best available algorithm.
        Returns (key, algorithm_used) for storage.
        """
        if algorithm == 'pbkdf2' or (algorithm is None and not ARGON2_AVAILABLE):
            return EncryptionUtils.derive_key_pbkdf2(principal_id, salt), 'pbkdf2'
        else:
            try:
                return EncryptionUtils.derive_key_argon2(principal_id, salt), 'argon2id'
            except Exception:
                return EncryptionUtils.derive_key_pbkdf2(principal_id, salt), 'pbkdf2'
    
    @staticmethod
    def encrypt_chat(chat_data: Dict, principal_id: str) -> Dict:
        """Encrypt chat content with AES-256-GCM"""
        salt = get_random_bytes(16)
        key, kdf_algorithm = EncryptionUtils.derive_key(principal_id, salt)
        
        # Serialize chat data
        plaintext = json.dumps(chat_data).encode('utf-8')
        
        # Generate nonce and encrypt
        cipher = AES.new(key, AES.MODE_GCM)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        
        return {
            'version': '1.1',  # Updated version for Argon2id support
            'encryption': {
                'algorithm': 'AES-256-GCM',
                'kdf': kdf_algorithm,  # 'argon2id' or 'pbkdf2'
                'salt': base64.b64encode(salt).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'tag': base64.b64encode(tag).decode('utf-8')
            },
            'encryptedContent': base64.b64encode(ciphertext).decode('utf-8'),
            'fileMetadata': {
                'principalId': principal_id,
                'createdAt': chat_data.get('metadata', {}).get('createdAt', int(time.time() * 1000)),
                'contentType': 'application/json'
            }
        }
    
    @staticmethod
    def decrypt_chat(encrypted_data: Dict, principal_id: str) -> Dict:
        """Decrypt chat content"""
        try:
            salt = base64.b64decode(encrypted_data['encryption']['salt'])
            nonce = base64.b64decode(encrypted_data['encryption']['nonce'])
            tag = base64.b64decode(encrypted_data['encryption']['tag'])
            ciphertext = base64.b64decode(encrypted_data['encryptedContent'])
            
            # Detect which KDF was used (for backward compatibility)
            kdf_algorithm = encrypted_data['encryption'].get('kdf', 'pbkdf2')
            key, _ = EncryptionUtils.derive_key(principal_id, salt, algorithm=kdf_algorithm)
            
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
            return json.loads(plaintext.decode('utf-8'))
        except Exception as e:
            logger.error(f'Decryption failed: {e}')
            raise ValueError('Failed to decrypt chat - wrong principal or corrupted data')
