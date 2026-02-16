"""
Trinity Backend - Rate Limiting Middleware
IP-based rate limiting and token quota tracking to prevent abuse

Phase 5: Added per-user token quotas and usage tracking.
Phase 2.1: File-based persistence for rate limits (survives restarts).
Phase 2.7: Rate limit response headers (X-RateLimit-*).
"""

import json
import logging
import time
from collections import defaultdict
from functools import wraps
from pathlib import Path

from flask import g, jsonify, request

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

# Persistence file for rate limits (survives container restarts)
RATE_LIMIT_FILE = Path("/app/data/rate_limits.json")

# Request tracking per IP
request_counts = defaultdict(list)
storage_request_counts = defaultdict(list)

# Token usage tracking per user (Phase 5)
# user_id -> {'tokens': int, 'requests': int, 'window_start': float}
token_usage_tracking = defaultdict(
    lambda: {"tokens": 0, "requests": 0, "window_start": time.time()}
)


# =============================================================================
# PERSISTENCE (Phase 2.1)
# =============================================================================

def _load_persisted_rate_limits():
    """Load rate limit state from disk on startup."""
    try:
        if RATE_LIMIT_FILE.exists():
            with open(RATE_LIMIT_FILE, "r") as f:
                data = json.load(f)
            now = time.time()

            # Restore request counts (discard expired entries)
            for ip, timestamps in data.get("request_counts", {}).items():
                valid = [t for t in timestamps if now - t < RATE_WINDOW]
                if valid:
                    request_counts[ip] = valid

            for ip, timestamps in data.get("storage_request_counts", {}).items():
                valid = [t for t in timestamps if now - t < STORAGE_RATE_WINDOW]
                if valid:
                    storage_request_counts[ip] = valid

            # Restore token usage (discard expired windows)
            for user_id, usage in data.get("token_usage", {}).items():
                if now - usage.get("window_start", 0) < TOKEN_QUOTA_WINDOW:
                    token_usage_tracking[user_id] = usage

            logger.info(
                f"📂 Rate limits restored: {len(request_counts)} IPs, "
                f"{len(token_usage_tracking)} token users"
            )
    except Exception as e:
        logger.warning(f"⚠️ Could not load rate limits from disk: {e}")


def _save_rate_limits():
    """Persist rate limit state to disk."""
    try:
        RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "request_counts": dict(request_counts),
            "storage_request_counts": dict(storage_request_counts),
            "token_usage": dict(token_usage_tracking),
            "saved_at": time.time(),
        }
        with open(RATE_LIMIT_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"⚠️ Could not persist rate limits: {e}")


# Save counter — persist every N requests to avoid excessive I/O
_save_counter = 0
_SAVE_INTERVAL = 10  # persist every 10 requests


def _maybe_persist():
    """Persist rate limits periodically."""
    global _save_counter
    _save_counter += 1
    if _save_counter >= _SAVE_INTERVAL:
        _save_counter = 0
        _save_rate_limits()


# Load persisted data on module import
_load_persisted_rate_limits()


def cleanup_stale_ips():
    """
    Remove stale IP entries to prevent memory leaks.
    Called periodically when tracking too many IPs.
    """
    now = time.time()

    # Cleanup general rate limit tracking
    stale_ips = [
        ip
        for ip, timestamps in request_counts.items()
        if not timestamps or (now - max(timestamps)) > RATE_WINDOW * 10
    ]
    for ip in stale_ips:
        del request_counts[ip]

    # Cleanup storage rate limit tracking
    stale_storage_ips = [
        ip
        for ip, timestamps in storage_request_counts.items()
        if not timestamps or (now - max(timestamps)) > STORAGE_RATE_WINDOW * 10
    ]
    for ip in stale_storage_ips:
        del storage_request_counts[ip]

    if stale_ips or stale_storage_ips:
        logger.info(
            f"🗑️ Rate limit cleanup: removed {len(stale_ips)} + {len(stale_storage_ips)} stale IPs"
        )
    _save_rate_limits()


# =============================================================================
# RATE LIMIT HELPERS (Phase 2.7)
# =============================================================================

def get_rate_limit_info(ip, counts, limit, window):
    """Get rate limit status for an IP."""
    now = time.time()
    recent = [t for t in counts.get(ip, []) if now - t < window]
    remaining = max(0, limit - len(recent))
    # Reset time = when the oldest request in the window expires
    if recent:
        reset_time = min(recent) + window
        reset_in = max(0, int(reset_time - now))
    else:
        reset_in = 0
    return {
        "remaining": remaining,
        "limit": limit,
        "reset_in": reset_in,
        "used": len(recent),
    }


def add_rate_limit_headers(response, ip):
    """Add X-RateLimit-* headers to any response."""
    info = get_rate_limit_info(ip, request_counts, RATE_LIMIT, RATE_WINDOW)
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(info["reset_in"])
    return response


def rate_limit_exceeded_response(ip, counts, limit, window):
    """Build a 429 response with Retry-After and rate limit info."""
    info = get_rate_limit_info(ip, counts, limit, window)
    retry_after = info["reset_in"] or window
    response = jsonify({
        "error": {
            "code": 429,
            "message": f"Too many requests. Try again in {retry_after} seconds.",
            "retry_after_seconds": retry_after,
        }
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = "0"
    response.headers["X-RateLimit-Reset"] = str(info["reset_in"])
    return response


def rate_limit(f):
    """Rate limit decorator - limits requests per IP address."""

    @wraps(f)
    def decorated(*args, **kwargs):
        # Periodic cleanup to prevent memory leaks
        if len(request_counts) > CLEANUP_THRESHOLD:
            cleanup_stale_ips()

        ip = request.remote_addr or "unknown"
        now = time.time()

        # Clean old requests
        request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_WINDOW]

        if len(request_counts[ip]) >= RATE_LIMIT:
            logger.warning(f"⚠️ Rate limit exceeded for IP: {ip}")
            return rate_limit_exceeded_response(ip, request_counts, RATE_LIMIT, RATE_WINDOW)

        request_counts[ip].append(now)
        _maybe_persist()
        return f(*args, **kwargs)

    return decorated


def storage_rate_limit(f):
    """
    Stricter rate limit for storage endpoints.
    Prevents abuse of autosave, list, and memory endpoints.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        now = time.time()

        # Clean old requests
        storage_request_counts[ip] = [
            t for t in storage_request_counts[ip] if now - t < STORAGE_RATE_WINDOW
        ]

        if len(storage_request_counts[ip]) >= STORAGE_RATE_LIMIT:
            logger.warning(f"⚠️ Storage rate limit exceeded for IP: {ip}")
            return rate_limit_exceeded_response(
                ip, storage_request_counts, STORAGE_RATE_LIMIT, STORAGE_RATE_WINDOW
            )

        storage_request_counts[ip].append(now)
        _maybe_persist()
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
    principal = (
        getattr(request, "principal", None)
        or request.headers.get("ICP-Principal")
        or request.headers.get("X-ICP-Principal")
    )
    if principal:
        return f"principal:{principal}"

    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return f"session:{session_id}"

    # Check request body for principal
    if request.is_json:
        try:
            data = request.get_json(silent=True) or {}
            if data.get("principal"):
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
    if now - usage["window_start"] > TOKEN_QUOTA_WINDOW:
        usage["tokens"] = 0
        usage["requests"] = 0
        usage["window_start"] = now

    # Check quota
    remaining = TOKEN_QUOTA_DAILY - usage["tokens"]
    is_allowed = remaining >= estimated_tokens

    quota_info = {
        "user_id": user_id,
        "tokens_used": usage["tokens"],
        "tokens_remaining": max(0, remaining),
        "quota_daily": TOKEN_QUOTA_DAILY,
        "requests_in_window": usage["requests"],
        "window_resets_in": int(TOKEN_QUOTA_WINDOW - (now - usage["window_start"])),
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
    if now - usage["window_start"] > TOKEN_QUOTA_WINDOW:
        usage["tokens"] = 0
        usage["requests"] = 0
        usage["window_start"] = now

    usage["tokens"] += tokens
    usage["requests"] += 1

    remaining = TOKEN_QUOTA_DAILY - usage["tokens"]

    return {
        "user_id": user_id,
        "tokens_used": usage["tokens"],
        "tokens_remaining": max(0, remaining),
        "quota_daily": TOKEN_QUOTA_DAILY,
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
                logger.warning(f"⚠️ Token quota exceeded for user: {user_id}")
                return (
                    jsonify(
                        {"error": "Token quota exceeded. Try again later.", "quota": quota_info}
                    ),
                    429,
                )

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
        if now - usage["window_start"] > TOKEN_QUOTA_WINDOW * 2:
            continue

        result[user_id] = {
            "tokens_used": usage["tokens"],
            "requests": usage["requests"],
            "window_active": now - usage["window_start"] < TOKEN_QUOTA_WINDOW,
        }

    return result


def cleanup_token_tracking():
    """Clean up expired token tracking entries."""
    now = time.time()
    expired = [
        user_id
        for user_id, usage in token_usage_tracking.items()
        if now - usage["window_start"] > TOKEN_QUOTA_WINDOW * 2
    ]

    for user_id in expired:
        del token_usage_tracking[user_id]

    if expired:
        logger.info(f"🗑️ Token tracking cleanup: removed {len(expired)} expired entries")
