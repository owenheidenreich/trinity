"""
Trinity ICP Authentication Verification Module
Verifies Ed25519 signatures from ICP Principal IDs
"""

import time
import base64
from typing import Tuple, Optional
from flask import request
import logging

logger = logging.getLogger(__name__)

# Will need to install: pip install cryptography
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.exceptions import InvalidSignature
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
    principal_clean = principal.replace('-', '')
    
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
    public_key_hex: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Verify Ed25519 signature from ICP identity
    
    Args:
        principal: ICP Principal ID (e.g., "xxn7o-7cigj-...")
        signature_hex: Hex-encoded signature
        timestamp: Unix timestamp in milliseconds (as string)
        endpoint: Request endpoint (e.g., "/chat/autosave")
        public_key_hex: Optional hex-encoded public key (32 bytes)
    
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
        
        # Allow 5 minutes tolerance
        if time_diff > 300000:  # 5 minutes in milliseconds
            logger.warning(f"⚠️ Timestamp expired: {time_diff}ms difference")
            return False, f"Timestamp expired (diff: {time_diff}ms)"
    except ValueError:
        return False, "Invalid timestamp format"
    
    # 2. Reconstruct the signed message
    message = f"{principal}:{timestamp}:{endpoint}"
    message_bytes = message.encode('utf-8')
    
    logger.info(f"🔍 Verifying signature for message: {message[:80]}...")
    
    # 3. Get public key
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
    
    # 4. Convert signature from hex to bytes
    try:
        signature_bytes = bytes.fromhex(signature_hex)
        if len(signature_bytes) != 64:
            return False, f"Invalid signature length: {len(signature_bytes)} (expected 64)"
    except ValueError:
        return False, "Invalid signature hex format"
    
    # 5. Verify signature
    # NOTE: Ed25519PublicKey.verify() uses constant-time comparison internally
    # to prevent timing attacks. The cryptography library handles this correctly.
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature_bytes, message_bytes)
        
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
    principal = request.headers.get('ICP-Principal')
    signature = request.headers.get('ICP-Signature')
    timestamp = request.headers.get('ICP-Timestamp')
    public_key = request.headers.get('ICP-PublicKey')  # Optional, for Phase 2 testing
    
    # Check required headers
    if not principal:
        return False, None, "Missing ICP-Principal header"
    if not signature:
        return False, None, "Missing ICP-Signature header"
    if not timestamp:
        return False, None, "Missing ICP-Timestamp header"
    
    # Verify signature
    success, error = verify_icp_signature(
        principal=principal,
        signature_hex=signature,
        timestamp=timestamp,
        endpoint=request.path,
        public_key_hex=public_key
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
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        success, principal, error = verify_request_auth()
        
        if not success:
            logger.warning(f"❌ Auth failed: {error}")
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'details': error
            }), 401
        
        # Attach principal to request object
        request.principal = principal
        logger.info(f"✅ Authenticated request from: {principal[:20]}...")
        
        return f(*args, **kwargs)
    
    return decorated_function


# Example usage test
if __name__ == '__main__':
    # Test with known values
    print("🧪 Testing ICP signature verification...")
    
    test_principal = "xxn7o-7cigj-hygmy-s7abc-def34-ghi56-jkl78-mno90-pqr12-stu34-wxy"
    test_timestamp = str(int(time.time() * 1000))
    test_endpoint = "/test/verify"
    test_message = f"{test_principal}:{test_timestamp}:{test_endpoint}"
    
    print(f"Message to sign: {test_message}")
    print("\nNote: Requires public key and signature from frontend test")
    print("Run test-signing.html and export test vectors")
