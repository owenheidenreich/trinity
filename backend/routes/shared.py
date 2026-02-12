"""
Shared utilities used across multiple route blueprints.
Extracted from inference_server.py to avoid circular imports.
"""

import threading
import time
from datetime import datetime

from flask import jsonify

from config import logger


# ===== STANDARDIZED ERROR RESPONSES =====

def error_response(code, message, details=None, retry_after=None):
    """Build a standardized error response with structured error object."""
    error_body = {
        "code": code,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if details:
        error_body["details"] = details
    if retry_after:
        error_body["retry_after_seconds"] = retry_after

    resp = jsonify({"error": error_body})
    resp.status_code = code
    if retry_after:
        resp.headers["Retry-After"] = str(retry_after)
    return resp


# ===== DOCUMENT STORE (shared by tools_bp) =====

_document_store_lock = threading.Lock()
document_store = {}
DOCUMENT_STORE_MAX_AGE = 3600  # 1 hour max lifetime per document
DOCUMENT_STORE_MAX_SIZE = 100  # Max documents to store
MAX_DOCUMENT_SIZE = 5_000_000  # 5MB max per document upload


def cleanup_document_store():
    """Remove expired documents to prevent memory leaks. Thread-safe."""
    now = time.time()
    with _document_store_lock:
        expired = [
            session_id
            for session_id, doc in document_store.items()
            if now - doc.get("uploaded_at_ts", now) > DOCUMENT_STORE_MAX_AGE
        ]
        for session_id in expired:
            del document_store[session_id]
            logger.info(f"🗑️ Cleaned up expired document session: {session_id}")

        while len(document_store) > DOCUMENT_STORE_MAX_SIZE:
            oldest = min(
                document_store.keys(), key=lambda k: document_store[k].get("uploaded_at_ts", 0)
            )
            del document_store[oldest]
            logger.info(f"🗑️ Cleaned up document store overflow: {oldest}")


# ===== IO EXECUTOR (shared by tools browse) =====

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

_io_executor = ThreadPoolExecutor(max_workers=10)


# ===== FUNDING CACHE (used by session_bp) =====

_funding_cache_lock = threading.Lock()
_funding_cache = {"data": None, "timestamp": 0, "ttl": 300}  # 5 minute cache
