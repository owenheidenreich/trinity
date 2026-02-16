"""
Authentication fixtures for Trinity test suite.

Provides Ed25519 test keypairs, valid/invalid signatures, and auth header generators.
Created: February 5, 2026
"""

import time
import uuid
from typing import Callable, Dict

import pytest
from nacl.signing import SigningKey


@pytest.fixture
def test_keypair() -> Dict:
    """
    Generate a fresh Ed25519 keypair for auth testing.

    Returns:
        Dict with:
        - signing_key: NaCl SigningKey for signing
        - verify_key: NaCl VerifyKey for verification
        - private_key_hex: Hex-encoded 64-byte signing key
        - public_key_hex: Hex-encoded 32-byte public key
        - principal: Test principal ID string
    """
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    from icp_auth import principal_from_public_key

    public_key_hex = verify_key.encode().hex()
    principal = principal_from_public_key(bytes.fromhex(public_key_hex))

    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "private_key_hex": signing_key.encode().hex(),
        "public_key_hex": public_key_hex,
        "principal": principal,
    }


@pytest.fixture
def second_keypair() -> Dict:
    """
    Generate a second Ed25519 keypair (for testing wrong-key scenarios).
    """
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    from icp_auth import principal_from_public_key

    public_key_hex = verify_key.encode().hex()
    principal = principal_from_public_key(bytes.fromhex(public_key_hex))

    return {
        "signing_key": signing_key,
        "verify_key": verify_key,
        "private_key_hex": signing_key.encode().hex(),
        "public_key_hex": public_key_hex,
        "principal": principal,
    }


@pytest.fixture
def create_signature(test_keypair) -> Callable:
    """
    Factory fixture to create valid signatures for any message.

    Usage:
        signature = create_signature(principal, timestamp, endpoint)
    """

    def _create_signature(principal: str, timestamp: str, endpoint: str, nonce: str) -> str:
        message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
        signed = test_keypair["signing_key"].sign(message.encode("utf-8"))
        return signed.signature.hex()

    return _create_signature


@pytest.fixture
def auth_headers(test_keypair, create_signature) -> Callable:
    """
    Factory fixture to generate valid authentication headers.

    Usage:
        headers = auth_headers('/chat/autosave')  # Uses current timestamp
        headers = auth_headers('/chat/autosave', timestamp='1234567890000')
    """

    def _auth_headers(endpoint: str, timestamp: str = None) -> Dict[str, str]:
        if timestamp is None:
            timestamp = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4())

        signature = create_signature(test_keypair["principal"], timestamp, endpoint, nonce)

        return {
            "ICP-Principal": test_keypair["principal"],
            "ICP-Signature": signature,
            "ICP-Timestamp": timestamp,
            "ICP-PublicKey": test_keypair["public_key_hex"],
            "ICP-Nonce": nonce,
        }

    return _auth_headers


@pytest.fixture
def expired_auth_headers(test_keypair, create_signature) -> Callable:
    """
    Factory fixture to generate expired authentication headers (>60s old).
    """

    def _expired_headers(endpoint: str) -> Dict[str, str]:
        # 120 seconds ago (well past the 60s window)
        old_timestamp = str(int((time.time() - 120) * 1000))
        nonce = str(uuid.uuid4())

        signature = create_signature(test_keypair["principal"], old_timestamp, endpoint, nonce)

        return {
            "ICP-Principal": test_keypair["principal"],
            "ICP-Signature": signature,
            "ICP-Timestamp": old_timestamp,
            "ICP-PublicKey": test_keypair["public_key_hex"],
            "ICP-Nonce": nonce,
        }

    return _expired_headers


@pytest.fixture
def future_auth_headers(test_keypair, create_signature) -> Callable:
    """
    Factory fixture to generate future authentication headers (>60s in future).
    """

    def _future_headers(endpoint: str) -> Dict[str, str]:
        # 120 seconds in the future
        future_timestamp = str(int((time.time() + 120) * 1000))
        nonce = str(uuid.uuid4())

        signature = create_signature(test_keypair["principal"], future_timestamp, endpoint, nonce)

        return {
            "ICP-Principal": test_keypair["principal"],
            "ICP-Signature": signature,
            "ICP-Timestamp": future_timestamp,
            "ICP-PublicKey": test_keypair["public_key_hex"],
            "ICP-Nonce": nonce,
        }

    return _future_headers
