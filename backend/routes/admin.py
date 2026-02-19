"""
Admin endpoints — caching, token & quota usage, storage status.
Routes: /admin/*
All require @require_admin decorator.
"""

from pathlib import Path

from flask import Blueprint, jsonify

from config import CHATS_DIR
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
    """Get canonical checkpoint status across principals."""
    try:
        from services.state_store import get_state_store

        root = Path(CHATS_DIR)
        statuses = []
        pending = 0
        if root.exists():
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                principal_id = child.name
                try:
                    store = get_state_store(principal_id)
                    checkpoint = store.get_sync_checkpoint()
                    pending_jobs = store.count_pending_jobs()
                    pending += int(pending_jobs)
                    statuses.append(
                        {
                            "principalId": principal_id,
                            "lastIpfsCid": checkpoint.get("last_ipfs_cid"),
                            "lastSyncAt": checkpoint.get("last_sync_at"),
                            "lastSyncedMessageId": checkpoint.get("last_synced_message_id"),
                            "pendingJobs": int(pending_jobs),
                        }
                    )
                except Exception:
                    continue

        return jsonify(
            {
                "pendingSyncs": pending,
                "userSyncStatus": statuses,
                "userCount": len(statuses),
            }
        )
    except ImportError:
        return jsonify({"error": "State store module not available"}), 503


@admin_bp.route("/admin/storage/rollback/<principal_id>", methods=["POST"])
@require_admin
def rollback_storage_manifest(principal_id):
    """Restore principal canonical state from latest valid IPFS checkpoint."""
    try:
        from services.state_checkpoint import restore_state_checkpoint_from_ipfs

        ok = restore_state_checkpoint_from_ipfs(principal_id)
        if not ok:
            return jsonify({"success": False, "error": "No valid checkpoint available for restore"}), 404
        return jsonify({"success": True, "principal": principal_id})
    except ImportError:
        return jsonify({"error": "Checkpoint restore module not available"}), 503


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
