"""
Trinity Backend - ICP Idempotency Cache Middleware
Ensures all 13 ICP subnet replicas receive identical responses

ICP HTTP Outcalls require deterministic responses across replicas.
This middleware caches responses by X-Request-ID to ensure consensus.
"""

from functools import wraps
from typing import Dict, Tuple, Optional
import threading
import time
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)


class ICPIdempotencyCache:
    """Cache for ICP HTTP Outcalls - ensures all 13 replicas get identical responses"""
    
    def __init__(self, ttl_seconds: int = 30):
        self._cache: Dict[str, Tuple[Dict, int, float]] = {}  # request_id -> (response, status_code, timestamp)
        self._lock = threading.Lock()
        self._request_locks: Dict[str, threading.Lock] = {}  # Per-request locks to serialize LLM calls
        self._ttl = ttl_seconds
    
    def get(self, request_id: str) -> Optional[Tuple[Dict, int]]:
        """Get cached response if it exists and is not expired"""
        with self._lock:
            if request_id in self._cache:
                response, status_code, timestamp = self._cache[request_id]
                if time.time() - timestamp < self._ttl:
                    # DEBUG level to reduce log spam from 13 ICP replicas
                    logger.debug(f'🎯 ICP cache hit for request_id: {request_id}')
                    return response, status_code
                else:
                    del self._cache[request_id]
            return None
    
    def set(self, request_id: str, response: Dict, status_code: int):
        """Cache a response for the given request_id"""
        with self._lock:
            self._cache[request_id] = (response, status_code, time.time())
            # DEBUG level to reduce log spam from frequent ICP health checks
            logger.debug(f'💾 ICP cached response for request_id: {request_id}')
            self._cleanup()
    
    def _cleanup(self):
        """Remove expired entries"""
        now = time.time()
        expired = [rid for rid, (_, _, ts) in self._cache.items() if now - ts > self._ttl]
        for rid in expired:
            del self._cache[rid]
        # Also cleanup old request locks
        expired_locks = [rid for rid in self._request_locks if rid not in self._cache]
        for rid in expired_locks[:100]:  # Limit cleanup to prevent long locks
            del self._request_locks[rid]
    
    def get_request_lock(self, request_id: str) -> threading.Lock:
        """Get or create a lock for a specific request_id"""
        with self._lock:
            if request_id not in self._request_locks:
                self._request_locks[request_id] = threading.Lock()
            return self._request_locks[request_id]


# Global idempotency cache for ICP outcalls
icp_cache = ICPIdempotencyCache(ttl_seconds=30)


def icp_idempotent(f):
    """
    Decorator for ICP-compatible idempotent endpoints.
    Uses X-Request-ID header to return cached responses for the same request.
    This ensures all 13 ICP replicas receive identical responses.
    
    CRITICAL: Uses per-request locking to prevent race conditions.
    When 13 replicas hit this endpoint simultaneously:
    1. First replica acquires lock, others wait
    2. First replica executes LLM, caches result, releases lock
    3. Other 12 replicas get cached result
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        request_id = request.headers.get('X-Request-ID')
        
        if request_id:
            # Fast path: Check cache first (no locking needed for reads)
            cached = icp_cache.get(request_id)
            if cached:
                response, status_code = cached
                return jsonify(response), status_code
            
            # Acquire per-request lock - serializes LLM calls for same request_id
            request_lock = icp_cache.get_request_lock(request_id)
            with request_lock:
                # Double-check cache after acquiring lock (another thread may have cached it)
                cached = icp_cache.get(request_id)
                if cached:
                    response, status_code = cached
                    logger.debug(f'🔄 ICP cache hit after lock for request_id: {request_id}')
                    return jsonify(response), status_code
                
                # Execute the actual function (only one thread per request_id does this)
                result = f(*args, **kwargs)
                
                # Cache the result
                if result:
                    if isinstance(result, tuple):
                        response_data = result[0].get_json()
                        status_code = result[1] if len(result) > 1 else 200
                    else:
                        response_data = result.get_json()
                        status_code = 200
                    
                    icp_cache.set(request_id, response_data, status_code)
                
                return result
        else:
            # No request_id - just execute without caching (direct browser request)
            return f(*args, **kwargs)
    
    return decorated
