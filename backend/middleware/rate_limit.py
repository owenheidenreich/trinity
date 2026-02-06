"""
Trinity Backend - Rate Limiting Middleware
IP-based rate limiting and token quota tracking to prevent abuse

Phase 5: Added per-user token quotas and usage tracking.
"""

from functools import wraps
from collections import defaultdict
import time
from flask import request, jsonify, g
import logging

logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT = 30  # requests per window (generous for legitimate users)
RATE_WINDOW = 60  # seconds

# Stricter limits for storage endpoints (prevent abuse)
STORAGE_RATE_LIMIT = 10  # requests per window
STORAGE_RATE_WINDOW = 60  # seconds

# Token quota configuration (Phase 5)
TOKEN_QUOTA_DAILY = 100000  # tokens per user per day (default)
TOKEN_QUOTA_HOURLY = 20000  # tokens per user per hour
TOKEN_QUOTA_WINDOW = 86400  # 24 hours in seconds

# Memory leak prevention - max IPs to track
MAX_TRACKED_IPS = 10000
CLEANUP_THRESHOLD = 8000  # Cleanup when we hit this many

# Request tracking per IP
request_counts = defaultdict(list)
storage_request_counts = defaultdict(list)

# Token usage tracking per user (Phase 5)
# user_id -> {'tokens': int, 'requests': int, 'window_start': float}
token_usage_tracking = defaultdict(lambda: {
    'tokens': 0,
    'requests': 0,
    'window_start': time.time()
})


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


# =============================================================================
# TOKEN QUOTA TRACKING (Phase 5)
# =============================================================================

def get_user_id() -> str:
    """
    Extract user identifier from request.
    Priority: principal > session header > IP address
    """
    # Try to get principal from various sources
    principal = request.headers.get('X-ICP-Principal')
    if principal:
        return f'principal:{principal}'
    
    session_id = request.headers.get('X-Session-ID')
    if session_id:
        return f'session:{session_id}'
    
    # Check request body for principal
    if request.is_json:
        try:
            data = request.get_json(silent=True) or {}
            if data.get('principal'):
                return f'principal:{data["principal"]}'
        except Exception:
            pass
    
    # Fallback to IP
    return f'ip:{request.remote_addr or "unknown"}'


def check_token_quota(user_id: str, estimated_tokens: int = 0) -> tuple[bool, dict]:
    """
    Check if user is within their token quota.
    
    Args:
        user_id: User identifier
        estimated_tokens: Estimated tokens for this request
        
    Returns:
        Tuple of (is_allowed, quota_info)
    """
    now = time.time()
    usage = token_usage_tracking[user_id]
    
    # Reset window if expired
    if now - usage['window_start'] > TOKEN_QUOTA_WINDOW:
        usage['tokens'] = 0
        usage['requests'] = 0
        usage['window_start'] = now
    
    # Check quota
    remaining = TOKEN_QUOTA_DAILY - usage['tokens']
    is_allowed = remaining >= estimated_tokens
    
    quota_info = {
        'user_id': user_id,
        'tokens_used': usage['tokens'],
        'tokens_remaining': max(0, remaining),
        'quota_daily': TOKEN_QUOTA_DAILY,
        'requests_in_window': usage['requests'],
        'window_resets_in': int(TOKEN_QUOTA_WINDOW - (now - usage['window_start']))
    }
    
    return is_allowed, quota_info


def record_token_usage(user_id: str, tokens: int) -> dict:
    """
    Record token usage for a user.
    
    Args:
        user_id: User identifier
        tokens: Number of tokens used
        
    Returns:
        Updated quota info
    """
    now = time.time()
    usage = token_usage_tracking[user_id]
    
    # Reset window if expired
    if now - usage['window_start'] > TOKEN_QUOTA_WINDOW:
        usage['tokens'] = 0
        usage['requests'] = 0
        usage['window_start'] = now
    
    usage['tokens'] += tokens
    usage['requests'] += 1
    
    remaining = TOKEN_QUOTA_DAILY - usage['tokens']
    
    return {
        'user_id': user_id,
        'tokens_used': usage['tokens'],
        'tokens_remaining': max(0, remaining),
        'quota_daily': TOKEN_QUOTA_DAILY
    }


def token_quota(estimated_tokens: int = 1000):
    """
    Decorator to enforce token quota before processing request.
    
    Args:
        estimated_tokens: Estimated tokens for the request type
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = get_user_id()
            is_allowed, quota_info = check_token_quota(user_id, estimated_tokens)
            
            if not is_allowed:
                logger.warning(f'⚠️ Token quota exceeded for user: {user_id}')
                return jsonify({
                    'error': 'Token quota exceeded. Try again later.',
                    'quota': quota_info
                }), 429
            
            # Store user_id in g for later use
            g.rate_limit_user_id = user_id
            
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_all_user_usage() -> dict:
    """Get usage stats for all tracked users (admin endpoint)."""
    now = time.time()
    result = {}
    
    for user_id, usage in token_usage_tracking.items():
        # Skip expired windows
        if now - usage['window_start'] > TOKEN_QUOTA_WINDOW * 2:
            continue
        
        result[user_id] = {
            'tokens_used': usage['tokens'],
            'requests': usage['requests'],
            'window_active': now - usage['window_start'] < TOKEN_QUOTA_WINDOW
        }
    
    return result


def cleanup_token_tracking():
    """Clean up expired token tracking entries."""
    now = time.time()
    expired = [
        user_id for user_id, usage in token_usage_tracking.items()
        if now - usage['window_start'] > TOKEN_QUOTA_WINDOW * 2
    ]
    
    for user_id in expired:
        del token_usage_tracking[user_id]
    
    if expired:
        logger.info(f'🗑️ Token tracking cleanup: removed {len(expired)} expired entries')
