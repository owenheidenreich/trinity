"""
Trinity Backend - Encryption Module
AES-256-GCM encryption for chat content
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


class EncryptionUtils:
    """Handle AES-256-GCM encryption for chat content"""
    
    @staticmethod
    def derive_key(principal_id: str, salt: bytes) -> bytes:
        """Derive encryption key from principal ID using PBKDF2"""
        return PBKDF2(
            principal_id, 
            salt, 
            dkLen=ENCRYPTION_KEY_LENGTH, 
            count=PBKDF2_ITERATIONS, 
            hmac_hash_module=SHA256
        )
    
    @staticmethod
    def encrypt_chat(chat_data: Dict, principal_id: str) -> Dict:
        """Encrypt chat content with AES-256-GCM"""
        salt = get_random_bytes(16)
        key = EncryptionUtils.derive_key(principal_id, salt)
        
        # Serialize chat data
        plaintext = json.dumps(chat_data).encode('utf-8')
        
        # Generate nonce and encrypt
        cipher = AES.new(key, AES.MODE_GCM)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        
        return {
            'version': '1.0',
            'encryption': {
                'algorithm': 'AES-256-GCM',
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
            
            key = EncryptionUtils.derive_key(principal_id, salt)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
            return json.loads(plaintext.decode('utf-8'))
        except Exception as e:
            logger.error(f'Decryption failed: {e}')
            raise ValueError('Failed to decrypt chat - wrong principal or corrupted data')
