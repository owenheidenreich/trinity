"""
Canonical chat routes backed by state_store.
"""

import time

from flask import Blueprint, jsonify, request

from icp_auth import require_auth, require_auth_or_anonymous
from middleware import storage_rate_limit
from services.state_store import get_state_store

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat/start", methods=["POST"])
@require_auth_or_anonymous
@storage_rate_limit
def start_chat():
    principal = request.principal
    data = request.json or {}
    requested_chat_id = data.get("chat_id")
    title = (data.get("title") or "New Chat").strip() or "New Chat"

    store = get_state_store(principal)
    chat_id = store.create_chat(chat_id=requested_chat_id, title=title)
    chat = store.get_chat(chat_id)

    return jsonify(
        {
            "success": True,
            "chat_id": chat_id,
            "chatId": chat_id,
            "chat": chat,
        }
    )


@chat_bp.route("/chat/list", methods=["GET"])
@require_auth
@storage_rate_limit
def list_chats():
    principal = request.principal
    store = get_state_store(principal)
    chats = store.list_chats(include_archived=True)
    return jsonify({"chats": chats, "count": len(chats)})


@chat_bp.route("/chat/<chat_id>", methods=["GET"])
@require_auth_or_anonymous
@storage_rate_limit
def get_chat(chat_id):
    principal = request.principal
    store = get_state_store(principal)

    chat = store.get_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    before_message_id = request.args.get("before_message_id", default=None, type=int)
    limit = request.args.get("limit", default=50, type=int)
    if not limit:
        limit = 50
    limit = max(1, min(int(limit), 200))

    messages = store.get_messages(chat_id=chat_id, before_message_id=before_message_id, limit=limit)

    # Frontend compatibility shape.
    compat_messages = [
        {
            "id": m["message_id"],
            "chatId": m["chat_id"],
            "role": m["role"],
            "content": m["content"],
            "timestamp": m["created_at"],
            "createdAt": m["created_at"],
            "status": "persisted",
        }
        for m in messages
    ]

    return jsonify(
        {
            "chat_id": chat_id,
            "chatId": chat_id,
            "title": chat.get("title", "Untitled"),
            "pinned": bool(chat.get("pinned", False)),
            "archived": bool(chat.get("archived", False)),
            "createdAt": chat.get("createdAt"),
            "updatedAt": chat.get("lastUpdated"),
            "messageCount": chat.get("messageCount", 0),
            "messages": compat_messages,
            "pagination": {
                "before_message_id": before_message_id,
                "limit": limit,
                "returned": len(compat_messages),
                "has_more": len(compat_messages) >= limit,
            },
        }
    )


@chat_bp.route("/chat/<chat_id>", methods=["PATCH"])
@require_auth
@storage_rate_limit
def patch_chat(chat_id):
    principal = request.principal
    data = request.json or {}

    title = data.get("title")
    pinned = data.get("pinned")
    archived = data.get("archived")

    if title is not None and not isinstance(title, str):
        return jsonify({"error": "title must be a string"}), 400
    if pinned is not None and not isinstance(pinned, bool):
        return jsonify({"error": "pinned must be a boolean"}), 400
    if archived is not None and not isinstance(archived, bool):
        return jsonify({"error": "archived must be a boolean"}), 400

    store = get_state_store(principal)
    ok = store.update_chat(chat_id, title=title, pinned=pinned, archived=archived)
    if not ok:
        return jsonify({"error": "Chat not found"}), 404

    return jsonify({"success": True, "chat": store.get_chat(chat_id)})


@chat_bp.route("/chat/<chat_id>", methods=["DELETE"])
@require_auth
@storage_rate_limit
def delete_chat(chat_id):
    principal = request.principal
    store = get_state_store(principal)
    ok = store.delete_chat(chat_id)
    if not ok:
        return jsonify({"error": "Chat not found"}), 404
    return jsonify({"success": True, "deletedAt": int(time.time() * 1000)})


# Compatibility wrappers
@chat_bp.route("/chat/<chat_id>/pin", methods=["POST"])
@require_auth
@storage_rate_limit
def toggle_pin(chat_id):
    principal = request.principal
    store = get_state_store(principal)
    chat = store.get_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    pinned = not bool(chat.get("pinned", False))
    store.update_chat(chat_id, pinned=pinned)
    return jsonify({"success": True, "chatId": chat_id, "pinned": pinned})


@chat_bp.route("/chat/<chat_id>/archive", methods=["POST"])
@require_auth
@storage_rate_limit
def archive_chat(chat_id):
    principal = request.principal
    store = get_state_store(principal)
    chat = store.get_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    if chat.get("archived"):
        return jsonify({"error": "Chat is already archived"}), 400
    store.update_chat(chat_id, archived=True)
    return jsonify({"success": True, "chatId": chat_id, "archivedAt": int(time.time() * 1000)})


@chat_bp.route("/chat/recover-archives", methods=["GET"])
@require_auth
@storage_rate_limit
def recover_archives():
    principal = request.principal
    store = get_state_store(principal)
    archives = [chat for chat in store.list_chats(include_archived=True) if chat.get("archived")]
    return jsonify({"success": True, "archives": archives, "count": len(archives)})


@chat_bp.route("/chat/archive/<cid>", methods=["GET"])
def get_archived_chat(_cid):
    return jsonify({"error": "Archived CID retrieval is retired in canonical-db mode"}), 410


@chat_bp.route("/chat/archive/status/<cid>", methods=["GET"])
def get_archive_status(cid):
    return jsonify(
        {
            "cid": cid,
            "status": "checkpoint-mode",
            "message": "Chat runtime source is canonical DB; IPFS is checkpoint/archive layer.",
            "checkedAt": int(time.time() * 1000),
        }
    )
