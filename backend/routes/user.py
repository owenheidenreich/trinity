"""
User status, stats, and export routes.
"""

import time

from flask import Blueprint, jsonify, request

from icp_auth import require_auth
from routes.memory import _memory_response
from services.state_store import get_state_store

user_bp = Blueprint("user", __name__)


@user_bp.route("/user/status", methods=["GET"])
@require_auth
def get_user_status():
    principal = request.principal
    store = get_state_store(principal)
    chats = store.list_chats(include_archived=True)
    pinned_count = sum(1 for c in chats if c.get("pinned"))
    archived_count = sum(1 for c in chats if c.get("archived"))

    return jsonify(
        {
            "storage": {
                "chats_used": len(chats),
                "pinned_count": pinned_count,
                "archived_count": archived_count,
            },
            "tokens": {
                "used_today": 0,
                "limit_today": None,
                "remaining_today": None,
            },
        }
    )


@user_bp.route("/user/export", methods=["GET"])
@require_auth
def export_user_data():
    principal = request.principal
    store = get_state_store(principal)
    chats = store.list_chats(include_archived=True)
    memory = _memory_response(principal, include_embeddings=False)

    return jsonify(
        {
            "principalId": principal,
            "generatedAt": int(time.time() * 1000),
            "chats": chats,
            "memory": memory,
            "note": "Use paginated /chat/{chat_id} to download full message bodies.",
        }
    )


@user_bp.route("/user/stats", methods=["GET"])
@require_auth
def get_user_stats():
    principal = request.principal
    store = get_state_store(principal)

    chats = store.list_chats(include_archived=True)
    memory = _memory_response(principal, include_embeddings=False)
    active_facts = [f for f in memory.get("facts", []) if not f.get("deleted") and not f.get("invalid_at")]

    return jsonify(
        {
            "profile": {
                "version": memory.get("version", "3.0"),
                "activeFacts": len(active_facts),
                "deletedFacts": len([f for f in memory.get("facts", []) if f.get("deleted")]),
                "lastUpdated": memory.get("lastUpdated"),
            },
            "chats": {
                "count": len(chats),
                "totalMessages": sum(int(c.get("messageCount", 0)) for c in chats),
            },
            "ipfs": {
                "mode": "checkpoint",
            },
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": "Argon2id|PBKDF2",
                "encryptedAtRest": True,
            },
        }
    )
