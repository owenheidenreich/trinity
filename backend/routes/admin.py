"""
Admin endpoints — caching, token & quota usage.
Routes: /admin/*
All require @require_admin decorator.
"""

from flask import Blueprint, jsonify

from icp_auth import require_admin

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/cache/stats")
@require_admin
def get_cache_stats():
    """Get statistics for all caches."""
    try:
        from services.caching import get_all_cache_stats

        stats = get_all_cache_stats()
        return jsonify(stats)
    except ImportError:
        return jsonify({"error": "Caching module not available"}), 503


@admin_bp.route("/admin/cache/clear", methods=["POST"])
@require_admin
def clear_caches():
    """Clear all caches (admin action)."""
    try:
        from services.caching import clear_all_caches

        clear_all_caches()
        return jsonify({"status": "cleared", "message": "All caches cleared"})
    except ImportError:
        return jsonify({"error": "Caching module not available"}), 503


@admin_bp.route("/admin/tokens/usage")
@require_admin
def get_token_usage():
    """Get token usage statistics."""
    try:
        from services.caching import get_token_tracker

        tracker = get_token_tracker()
        return jsonify({
            "totals": tracker.get_totals(),
            "top_users": tracker.get_top_users(limit=20),
        })
    except ImportError:
        return jsonify({"error": "Caching module not available"}), 503


@admin_bp.route("/admin/quota/usage")
@require_admin
def get_quota_usage():
    """Get per-user token quota usage."""
    try:
        from middleware.rate_limit import get_all_user_usage

        usage = get_all_user_usage()
        return jsonify({"users": usage, "user_count": len(usage)})
    except ImportError:
        return jsonify({"error": "Rate limit module not available"}), 503
