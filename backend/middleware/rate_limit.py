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

# Request tracking per IP
request_counts = defaultdict(list)


def rate_limit(f):
    """Rate limit decorator - limits requests per IP address."""
    @wraps(f)
    def decorated(*args, **kwargs):
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
