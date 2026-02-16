"""
Trinity ICP Authentication Verification Module
Verifies Ed25519 signatures from ICP Principal IDs
"""

import base64
import hashlib
import logging
import time
import zlib
from functools import wraps
from typing import Optional, Tuple

from cachetools import TTLCache
from flask import jsonify, request

from config import ADMIN_PRINCIPALS, AUTH_TIMESTAMP_WINDOW_MS

logger = logging.getLogger(__name__)

# Track used nonces slightly longer than auth window
# This prevents replay attacks even within the valid timestamp window
NONCE_TTL_SECONDS = max(65, int(AUTH_TIMESTAMP_WINDOW_MS / 1000) + 5)
used_nonces = TTLCache(maxsize=10000, ttl=NONCE_TTL_SECONDS)

# Ed25519 SubjectPublicKeyInfo DER prefix:
# 30 2a 30 05 06 03 2b 65 70 03 21 00 || <32-byte raw key>
_ED25519_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")

# Will need to install: pip install cryptography
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ cryptography module not installed - signature verification disabled")
    CRYPTO_AVAILABLE = False


def principal_from_public_key(public_key_bytes: bytes) -> str:
    """
    Derive ICP self-authenticating principal text from a raw Ed25519 public key.
    """
    if len(public_key_bytes) != 32:
        raise ValueError(f"Invalid public key length: {len(public_key_bytes)} (expected 32)")

    der_key = _ED25519_DER_PREFIX + public_key_bytes
    principal_bytes = hashlib.sha224(der_key).digest() + b"\x02"
    checksum = (zlib.crc32(principal_bytes) & 0xFFFFFFFF).to_bytes(4, "big")

    encoded = (
        base64.b32encode(checksum + principal_bytes)
        .decode("ascii")
        .lower()
        .rstrip("=")
    )
    return "-".join(encoded[i : i + 5] for i in range(0, len(encoded), 5))


def _normalize_principal(principal: str) -> str:
    """Normalize principal text for safe equality comparison."""
    return (principal or "").strip().lower()


def verify_icp_signature(
    principal: str,
    signature_hex: str,
    timestamp: str,
    endpoint: str,
    public_key_hex: Optional[str] = None,
    nonce: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Verify Ed25519 signature from ICP identity

    Args:
        principal: ICP Principal ID (e.g., "xxn7o-7cigj-...")
        signature_hex: Hex-encoded signature
        timestamp: Unix timestamp in milliseconds (as string)
        endpoint: Request endpoint (e.g., "/chat/autosave")
        public_key_hex: Hex-encoded public key (32 bytes)
        nonce: Random unique identifier to prevent replay attacks (required)

    Returns:
        (success: bool, error_message: Optional[str])
    """
    if not CRYPTO_AVAILABLE:
        logger.error("❌ Crypto library not available")
        return False, "Signature verification not available"

    # 1. Check timestamp freshness (prevent replay attacks)
    try:
        timestamp_ms = int(timestamp)
        current_ms = int(time.time() * 1000)
        time_diff = abs(current_ms - timestamp_ms)

        if time_diff > AUTH_TIMESTAMP_WINDOW_MS:
            logger.warning(f"⚠️ Timestamp expired: {time_diff}ms difference")
            return False, "Request timestamp expired"
    except ValueError:
        return False, "Invalid timestamp format"

    if not nonce:
        return False, "Missing nonce"

    # 2. Check nonce hasn't been used (prevents replay within valid timestamp window)
    nonce_key = f"{principal}:{nonce}"
    if nonce_key in used_nonces:
        logger.warning(f"⚠️ Nonce already used: {nonce[:16]}... (replay attack detected)")
        return False, "Nonce already used (replay attack detected)"

    # 3. Reconstruct the signed message
    message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
    message_bytes = message.encode("utf-8")

    logger.info(f"🔍 Verifying signature for message: {message[:80]}...")

    # 4. Get public key
    if not public_key_hex:
        return False, "Public key required - send 'ICP-PublicKey' header"
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
        if len(public_key_bytes) != 32:
            return False, f"Invalid public key length: {len(public_key_bytes)} (expected 32)"
    except ValueError:
        return False, "Invalid public key hex format"

    # 5. Bind principal to public key (prevents principal spoofing).
    try:
        expected_principal = principal_from_public_key(public_key_bytes)
    except ValueError as e:
        return False, str(e)

    if _normalize_principal(principal) != _normalize_principal(expected_principal):
        logger.warning(
            "❌ Principal/public key mismatch: got %s expected %s",
            principal[:20],
            expected_principal[:20],
        )
        return False, "Principal does not match public key"

    # 6. Convert signature from hex to bytes
    try:
        signature_bytes = bytes.fromhex(signature_hex)
        if len(signature_bytes) != 64:
            return False, f"Invalid signature length: {len(signature_bytes)} (expected 64)"
    except ValueError:
        return False, "Invalid signature hex format"

    # 7. Verify signature
    # NOTE: Ed25519PublicKey.verify() uses constant-time comparison internally
    # to prevent timing attacks. The cryptography library handles this correctly.
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature_bytes, message_bytes)

        # Mark nonce as used AFTER successful verification
        used_nonces[nonce_key] = True

        logger.info(f"✅ Signature verified for principal: {principal[:20]}...")
        return True, None

    except InvalidSignature:
        logger.warning(f"❌ Invalid signature for principal: {principal[:20]}...")
        return False, "Invalid signature"
    except Exception as e:
        logger.error(f"❌ Signature verification error: {str(e)}")
        return False, f"Verification error: {str(e)}"


def verify_request_auth() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Extract and verify authentication from current Flask request

    Returns:
        (success: bool, principal: Optional[str], error_message: Optional[str])
    """
    def _header(name: str) -> Optional[str]:
        # Prefer canonical header names, keep X-ICP-* for compatibility.
        return request.headers.get(name) or request.headers.get(f"X-{name}")

    # Extract headers
    principal = _header("ICP-Principal")
    signature = _header("ICP-Signature")
    timestamp = _header("ICP-Timestamp")
    public_key = _header("ICP-PublicKey")
    nonce = _header("ICP-Nonce")

    # Check required headers
    if not principal:
        return False, None, "Missing ICP-Principal header"
    if not signature:
        return False, None, "Missing ICP-Signature header"
    if not timestamp:
        return False, None, "Missing ICP-Timestamp header"
    if not public_key:
        return False, None, "Missing ICP-PublicKey header"
    if not nonce:
        return False, None, "Missing ICP-Nonce header"

    # Verify signature
    success, error = verify_icp_signature(
        principal=principal,
        signature_hex=signature,
        timestamp=timestamp,
        endpoint=request.path,
        public_key_hex=public_key,
        nonce=nonce,
    )

    if success:
        return True, principal, None
    else:
        return False, None, error


def require_auth(f):
    """
    Decorator to require ICP authentication on Flask routes

    Usage:
        @app.route('/chat/autosave', methods=['POST'])
        @require_auth
        def autosave():
            principal = request.principal  # Available after verification
            ...
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        success, principal, error = verify_request_auth()

        if not success:
            logger.warning(f"❌ Auth failed: {error}")
            return (
                jsonify({"success": False, "error": "Authentication required", "details": error}),
                401,
            )

        # Attach principal to request object
        request.principal = principal
        logger.info(f"✅ Authenticated request from: {principal[:20]}...")

        return f(*args, **kwargs)

    return decorated_function


def require_admin(f):
    """
    Decorator to require admin-level ICP authentication.
    The request must be signed by a principal listed in ADMIN_PRINCIPALS env var.

    Usage:
        @app.route('/admin/cache/clear', methods=['POST'])
        @require_admin
        def clear_cache():
            ...
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        success, principal, error = verify_request_auth()

        if not success:
            logger.warning(f"❌ Admin auth failed: {error}")
            return (
                jsonify({"success": False, "error": "Authentication required", "details": error}),
                401,
            )

        if not ADMIN_PRINCIPALS:
            logger.error("❌ No ADMIN_PRINCIPALS configured")
            return (
                jsonify({"success": False, "error": "Admin access not configured"}),
                403,
            )

        if principal not in ADMIN_PRINCIPALS:
            logger.warning(f"❌ Non-admin principal attempted admin access: {principal[:20]}...")
            return (
                jsonify({"success": False, "error": "Admin access required"}),
                403,
            )

        request.principal = principal
        logger.info(f"✅ Admin request from: {principal[:20]}...")

        return f(*args, **kwargs)

    return decorated_function


# Example usage test
if __name__ == "__main__":
    # Test with known values
    print("🧪 Testing ICP signature verification...")

    test_principal = "xxn7o-7cigj-hygmy-s7abc-def34-ghi56-jkl78-mno90-pqr12-stu34-wxy"
    test_timestamp = str(int(time.time() * 1000))
    test_endpoint = "/test/verify"
    test_message = f"{test_principal}:{test_timestamp}:{test_endpoint}"

    print(f"Message to sign: {test_message}")
    print("\nNote: Requires public key and signature from frontend test")
    print("Run test-signing.html and export test vectors")
