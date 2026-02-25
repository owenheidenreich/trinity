"""
Canonical chat + memory routes backed by state_store.
"""

import time
from typing import Dict

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


@chat_bp.route("/user/status", methods=["GET"])
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


# ---------------------------------------------------------------------------
# Memory APIs
# ---------------------------------------------------------------------------


def _memory_response(principal: str, include_embeddings: bool = False, raw: bool = False) -> Dict:
    store = get_state_store(principal)
    facts = store.list_facts(
        include_deleted=True,
        include_invalid=True,
        with_embeddings=include_embeddings,
    )
    summaries = store.list_conversation_summaries()
    payload = {
        "principalId": principal,
        "version": "3.0",
        "facts": facts,
        "conversation_summaries": summaries,
        "ingestion_jobs_recent": store.list_recent_ingestion_jobs(limit=30),
        "createdAt": None,
        "lastUpdated": int(time.time() * 1000),
    }
    if raw:
        payload["graph_triples"] = store.list_graph_triples(limit=200, include_invalid=True)
        payload["sync_checkpoint"] = store.get_sync_checkpoint()
    return payload


@chat_bp.route("/user/memory", methods=["GET"])
@require_auth
@storage_rate_limit
def get_user_memory():
    principal = request.principal
    include_embeddings = str(request.args.get("include_embeddings", "")).lower() in {
        "1",
        "true",
        "yes",
    }
    raw = str(request.args.get("raw", "")).lower() in {"1", "true", "yes"}
    return jsonify(_memory_response(principal, include_embeddings=include_embeddings, raw=raw))


@chat_bp.route("/user/memory", methods=["POST"])
@require_auth
@storage_rate_limit
def update_user_memory():
    return (
        jsonify(
            {
                "error": "Route retired",
                "message": "Use /user/memory/fact and /user/memory/fact/{fact_id} for memory writes.",
            }
        ),
        410,
    )


@chat_bp.route("/user/memory/fact", methods=["POST"])
@require_auth
@storage_rate_limit
def add_memory_fact():
    principal = request.principal
    data = request.json or {}
    text = (data.get("fact") or data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Fact text is required"}), 400

    category = str(data.get("category", "general")).strip().lower() or "general"
    try:
        importance = int(data.get("importance", 3))
    except (TypeError, ValueError):
        importance = 3
    importance = max(1, min(5, importance))

    embedding = None
    try:
        from services.embeddings import embed_text

        vec = embed_text(text)
        if vec is not None:
            embedding = vec.tolist()
    except Exception:
        embedding = None

    store = get_state_store(principal)
    fact_id = store.create_fact(
        text=text,
        category=category,
        importance=importance,
        source_message_id=data.get("source_message_id"),
        embedding=embedding,
    )

    fact = store.get_fact(fact_id, with_embedding=False)
    return jsonify({"success": True, "fact": fact, "fact_id": fact_id})


@chat_bp.route("/user/memory/fact/<int:fact_id>", methods=["PATCH", "PUT"])
@require_auth
@storage_rate_limit
def edit_memory_fact(fact_id):
    principal = request.principal
    data = request.json or {}

    updates: Dict = {}
    if "text" in data:
        text = str(data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text cannot be empty"}), 400
        updates["text"] = text
        try:
            from services.embeddings import embed_text

            vec = embed_text(text)
            if vec is not None:
                updates["embedding"] = vec.tolist()
        except Exception:
            pass

    if "category" in data:
        updates["category"] = str(data.get("category") or "general").strip().lower() or "general"

    if "importance" in data:
        try:
            updates["importance"] = max(1, min(5, int(data.get("importance", 3))))
        except (TypeError, ValueError):
            updates["importance"] = 3

    if not updates:
        return jsonify({"error": "No updates provided"}), 400

    store = get_state_store(principal)
    if not store.update_fact(fact_id, updates):
        return jsonify({"error": "Fact not found"}), 404

    return jsonify({"success": True, "fact": store.get_fact(fact_id, with_embedding=False)})


@chat_bp.route("/user/memory/fact/<int:fact_id>", methods=["DELETE"])
@require_auth
@storage_rate_limit
def delete_memory_fact(fact_id):
    principal = request.principal
    store = get_state_store(principal)

    if not store.soft_delete_fact(fact_id):
        return jsonify({"error": "Fact not found"}), 404

    return jsonify({"success": True, "fact_id": fact_id, "deletedAt": int(time.time() * 1000)})


# ---------------------------------------------------------------------------
# Optional export/stats compatibility
# ---------------------------------------------------------------------------


@chat_bp.route("/user/export", methods=["GET"])
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


@chat_bp.route("/user/stats", methods=["GET"])
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
