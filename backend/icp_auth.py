"""
Trinity ICP Authentication Verification Module
Verifies Ed25519 signatures from ICP Principal IDs
"""

import logging
import time
from functools import wraps
from typing import Optional, Tuple

from cachetools import TTLCache
from flask import g, jsonify, request

from config import ADMIN_PRINCIPALS

logger = logging.getLogger(__name__)

# Track used nonces for 65 seconds (slightly longer than auth window)
# This prevents replay attacks even within the valid timestamp window
used_nonces = TTLCache(maxsize=10000, ttl=65)

# Will need to install: pip install cryptography
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ cryptography module not installed - signature verification disabled")
    CRYPTO_AVAILABLE = False


def principal_to_public_key(principal: str) -> bytes:
    """
    Extract Ed25519 public key from ICP Principal ID

    ICP Principal format: base32-encoded DER public key with checksum
    This is a simplified extraction - may need adjustment for production
    """
    # Remove dashes from principal
    principal.replace("-", "")

    # ICP uses custom base32 encoding - for now, we'll need the public key
    # sent separately or extracted from the identity during login
    # TODO: Implement proper Principal -> PublicKey extraction

    # For Phase 2 testing, we'll require the public key to be sent in headers
    raise NotImplementedError(
        "Principal to public key extraction not yet implemented. "
        "For Phase 2, send 'ICP-PublicKey' header with DER-encoded public key."
    )


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
        public_key_hex: Optional hex-encoded public key (32 bytes)
        nonce: Random unique identifier to prevent replay attacks

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

        # SECURITY: 60-second window to prevent replay attacks
        # Balance between security and network latency tolerance
        # (30s was too tight - users hitting 31s due to network delays)
        if time_diff > 60000:  # 60 seconds in milliseconds
            logger.warning(f"⚠️ Timestamp expired: {time_diff}ms difference")
            return False, "Request timestamp expired"
    except ValueError:
        return False, "Invalid timestamp format"

    # 2. Check nonce hasn't been used (prevents replay within valid timestamp window)
    if nonce:
        nonce_key = f"{principal}:{nonce}"
        if nonce_key in used_nonces:
            logger.warning(f"⚠️ Nonce already used: {nonce[:16]}... (replay attack detected)")
            return False, "Nonce already used (replay attack detected)"

    # 3. Reconstruct the signed message
    # If nonce is provided, it's included in the message
    if nonce:
        message = f"{principal}:{timestamp}:{endpoint}:{nonce}"
    else:
        # Legacy format without nonce (for backward compatibility during migration)
        message = f"{principal}:{timestamp}:{endpoint}"
    message_bytes = message.encode("utf-8")

    logger.info(f"🔍 Verifying signature for message: {message[:80]}...")

    # 4. Get public key
    if not public_key_hex:
        # Try to extract from Principal (not yet implemented)
        try:
            public_key_bytes = principal_to_public_key(principal)
        except NotImplementedError:
            return False, "Public key required - send 'ICP-PublicKey' header"
    else:
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            if len(public_key_bytes) != 32:
                return False, f"Invalid public key length: {len(public_key_bytes)} (expected 32)"
        except ValueError:
            return False, "Invalid public key hex format"

    # 5. Convert signature from hex to bytes
    try:
        signature_bytes = bytes.fromhex(signature_hex)
        if len(signature_bytes) != 64:
            return False, f"Invalid signature length: {len(signature_bytes)} (expected 64)"
    except ValueError:
        return False, "Invalid signature hex format"

    # 6. Verify signature
    # NOTE: Ed25519PublicKey.verify() uses constant-time comparison internally
    # to prevent timing attacks. The cryptography library handles this correctly.
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature_bytes, message_bytes)

        # Mark nonce as used AFTER successful verification
        if nonce:
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
    # Extract headers
    principal = request.headers.get("ICP-Principal")
    signature = request.headers.get("ICP-Signature")
    timestamp = request.headers.get("ICP-Timestamp")
    public_key = request.headers.get("ICP-PublicKey")
    nonce = request.headers.get("ICP-Nonce")  # Replay protection

    # Check required headers
    if not principal:
        return False, None, "Missing ICP-Principal header"
    if not signature:
        return False, None, "Missing ICP-Signature header"
    if not timestamp:
        return False, None, "Missing ICP-Timestamp header"

    # Verify signature (nonce is optional for backward compatibility)
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
