"""
Trinity Backend - Input Validation
Validation functions for request parameters
"""

import re


def validate_chat_id(chat_id: str) -> bool:
    """Validate chat_id format - alphanumeric, dash, underscore only."""
    if not chat_id or len(chat_id) > 64:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', chat_id))


def validate_principal_id(principal_id: str) -> bool:
    """Validate ICP principal format."""
    if not principal_id or len(principal_id) > 64:
        return False
    # ICP principals are base32-ish with dashes
    return bool(re.match(r'^[a-z0-9-]+$', principal_id.lower()))


def validate_cid(cid: str) -> bool:
    """Validate IPFS CID format - base32/base58 alphanumeric."""
    if not cid or len(cid) > 100:
        return False
    return bool(re.match(r'^[a-zA-Z0-9]+$', cid))
