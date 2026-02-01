"""
Trinity Backend - Rate Limiting Middleware
IP-based rate limiting to prevent abuse
"""

from functools import wraps
from collections import defaultdict
import time
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT = 30  # requests per window (generous for legitimate users)
RATE_WINDOW = 60  # seconds

# Stricter limits for storage endpoints (prevent abuse)
STORAGE_RATE_LIMIT = 10  # requests per window
STORAGE_RATE_WINDOW = 60  # seconds

# Memory leak prevention - max IPs to track
MAX_TRACKED_IPS = 10000
CLEANUP_THRESHOLD = 8000  # Cleanup when we hit this many

# Request tracking per IP
request_counts = defaultdict(list)
storage_request_counts = defaultdict(list)


def cleanup_stale_ips():
    """
    Remove stale IP entries to prevent memory leaks.
    Called periodically when tracking too many IPs.
    """
    now = time.time()
    
    # Cleanup general rate limit tracking
    stale_ips = [
        ip for ip, timestamps in request_counts.items()
        if not timestamps or (now - max(timestamps)) > RATE_WINDOW * 10
    ]
    for ip in stale_ips:
        del request_counts[ip]
    
    # Cleanup storage rate limit tracking
    stale_storage_ips = [
        ip for ip, timestamps in storage_request_counts.items()
        if not timestamps or (now - max(timestamps)) > STORAGE_RATE_WINDOW * 10
    ]
    for ip in stale_storage_ips:
        del storage_request_counts[ip]
    
    if stale_ips or stale_storage_ips:
        logger.info(f'🗑️ Rate limit cleanup: removed {len(stale_ips)} + {len(stale_storage_ips)} stale IPs')


def rate_limit(f):
    """Rate limit decorator - limits requests per IP address."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Periodic cleanup to prevent memory leaks
        if len(request_counts) > CLEANUP_THRESHOLD:
            cleanup_stale_ips()
        
        ip = request.remote_addr or 'unknown'
        now = time.time()
        
        # Clean old requests
        request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_WINDOW]
        
        if len(request_counts[ip]) >= RATE_LIMIT:
            logger.warning(f'⚠️ Rate limit exceeded for IP: {ip}')
            return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429
        
        request_counts[ip].append(now)
        return f(*args, **kwargs)
    return decorated


def storage_rate_limit(f):
    """
    Stricter rate limit for storage endpoints.
    Prevents abuse of autosave, list, and memory endpoints.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or 'unknown'
        now = time.time()
        
        # Clean old requests
        storage_request_counts[ip] = [
            t for t in storage_request_counts[ip] 
            if now - t < STORAGE_RATE_WINDOW
        ]
        
        if len(storage_request_counts[ip]) >= STORAGE_RATE_LIMIT:
            logger.warning(f'⚠️ Storage rate limit exceeded for IP: {ip}')
            return jsonify({
                'error': 'Storage rate limit exceeded. Try again later.',
                'retry_after': STORAGE_RATE_WINDOW
            }), 429
        
        storage_request_counts[ip].append(now)
        return f(*args, **kwargs)
    return decorated
