"""
Admin endpoints — caching, token & quota usage, storage status.
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


@admin_bp.route("/admin/storage/status")
@require_admin
def get_storage_status():
    """Get IPFS sync status across all users — pending syncs, last sync times, errors."""
    try:
        from services.user_data_store import get_all_sync_status, get_pending_sync_count

        sync_status = get_all_sync_status()
        pending_count = get_pending_sync_count()

        return jsonify({
            "pendingSyncs": pending_count,
            "userSyncStatus": sync_status,
            "userCount": len(sync_status),
        })
    except ImportError:
        return jsonify({"error": "User data store module not available"}), 503


@admin_bp.route("/admin/storage/rollback/<principal_id>", methods=["POST"])
@require_admin
def rollback_storage_manifest(principal_id):
    """Rollback a principal's manifest to the previous (or requested) version."""
    try:
        from flask import request
        from services.user_data_store import rollback_manifest

        payload = request.get_json(silent=True) or {}
        target_version = payload.get("targetVersion")
        ok = rollback_manifest(principal_id, target_version=target_version)
        if not ok:
            return jsonify({"success": False, "error": "Rollback target not found or restore failed"}), 404
        return jsonify({"success": True, "principal": principal_id, "targetVersion": target_version})
    except ImportError:
        return jsonify({"error": "User data store module not available"}), 503


@admin_bp.route("/admin/slo/status")
@require_admin
def get_slo_status():
    """Get current SLO snapshot + ingestion queue state."""
    try:
        from services.memory_ingestion import get_ingestion_stats
        from services.slo_metrics import get_slo_snapshot

        return jsonify({
            "slo": get_slo_snapshot(),
            "ingestion": get_ingestion_stats(),
        })
    except ImportError:
        return jsonify({"error": "SLO or ingestion modules not available"}), 503
