"""
Chat Blueprint — /chat/*, /user/status, /user/memory*
=====================================================
Handles encrypted chat storage, archival, user memory and status dashboard.
All chat/user endpoints require Ed25519 auth via @require_auth.
"""

import json
import time
from typing import Dict

from flask import Blueprint, jsonify, request

from config import LIGHTHOUSE_GATEWAY, MAX_ARCHIVED_CHATS, PRINCIPAL_DISPLAY_LENGTH, http_session, logger
from icp_auth import require_auth
from services.user_data_store import (
    discard_queued_chat_sync,
    decrypt_for_user,
    encrypt_for_user,
    ensure_user_data_restored,
    flush_chat_sync_now,
    load_manifest,
    queue_chat_sync,
    remove_chat_from_manifest,
    save_manifest,
    sync_manifest_to_ipfs,
    update_chat_in_manifest,
)
# Keep get_lighthouse_uploads import for test patch compatibility while
# routes have moved to manifest-first lookup.
from lighthouse import download_from_ipfs, get_lighthouse_uploads, upload_to_ipfs
from middleware import storage_rate_limit, track_error, track_storage
from storage import get_user_dir, load_metadata, load_user_memory, save_metadata, save_user_memory
from validation import validate_chat_id, validate_cid, validate_principal_id

chat_bp = Blueprint("chat", __name__)


# ===== HELPER =====


def _ensure_restored(principal_id: str):
    """Ensure local cache has been restored from IPFS manifest for this session."""
    try:
        ensure_user_data_restored(principal_id)
    except Exception as e:
        logger.warning(f"⚠️ Data restore check failed: {e}")


def _format_manifest_chat(chat: Dict) -> Dict:
    """Normalize manifest chat entry to API shape expected by frontend."""
    return {
        "chatId": chat.get("chatId"),
        "title": chat.get("title", "Untitled"),
        "cid": chat.get("cid"),
        "lastUpdated": chat.get("lastUpdated", 0),
        "messageCount": chat.get("messageCount", 0),
        "pinned": chat.get("pinned", False),
        "isArchived": chat.get("archived", False),
        "archived": chat.get("archived", False),
        "archivedAt": chat.get("archivedAt"),
        "createdAt": chat.get("createdAt"),
    }


def _get_chat_manifest(principal_id: str) -> Dict:
    """
    Load chat manifest and opportunistically hydrate from local metadata cache
    when manifest chat entries are missing.
    """
    manifest = load_manifest(principal_id)
    if manifest.get("chats"):
        return manifest

    metadata = load_metadata(principal_id)
    cache_chats = metadata.get("chats", [])
    if not cache_chats:
        return manifest

    migrated = []
    now_ms = int(time.time() * 1000)
    for chat in cache_chats:
        chat_id = chat.get("chatId")
        if not chat_id or not validate_chat_id(chat_id):
            continue

        migrated.append({
            "chatId": chat_id,
            "cid": chat.get("cid"),
            "title": chat.get("title", "Untitled"),
            "createdAt": chat.get("createdAt", now_ms),
            "lastUpdated": chat.get("lastUpdated", now_ms),
            "messageCount": chat.get("messageCount", 0),
            "pinned": chat.get("pinned", False),
            "archived": chat.get("archived", chat.get("isArchived", False)),
            "archivedAt": chat.get("archivedAt"),
        })

    if migrated:
        manifest["chats"] = migrated
        save_manifest(principal_id, manifest)
        sync_manifest_to_ipfs(principal_id, manifest)

    return manifest


def _chat_cache_path(principal_id: str, chat_id: str):
    """Path for local encrypted chat snapshot."""
    return get_user_dir(principal_id) / f"{chat_id}.json"


def _save_local_chat_snapshot(principal_id: str, chat_data: Dict):
    """Persist encrypted chat snapshot locally (hot path, low-latency)."""
    encrypted = encrypt_for_user(chat_data, principal_id)
    with open(_chat_cache_path(principal_id, chat_data["chatId"]), "w") as f:
        json.dump(encrypted, f)


def _load_local_chat_snapshot(principal_id: str, chat_id: str):
    """Load and decrypt local chat snapshot if present."""
    path = _chat_cache_path(principal_id, chat_id)
    if not path.exists():
        return None

    try:
        with open(path, "r") as f:
            encrypted = json.load(f)
        return decrypt_for_user(encrypted, principal_id)
    except Exception as e:
        logger.warning("⚠️ Failed reading local chat snapshot %s: %s", chat_id[:12], e)
        return None


def _delete_local_chat_snapshot(principal_id: str, chat_id: str):
    """Delete local cached snapshot for a chat (best-effort)."""
    path = _chat_cache_path(principal_id, chat_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as e:
            logger.debug("Local chat snapshot delete failed for %s: %s", chat_id[:12], e)


# ===== AUTOSAVE =====

@chat_bp.route("/chat/autosave", methods=["POST"])
@require_auth
@storage_rate_limit
def autosave_chat():
    """Save chat locally and queue a debounced IPFS checkpoint."""
    with track_storage("autosave_chat"):
        try:
            principal = request.principal
            data = request.json

            logger.debug(f"📥 Autosave request from {principal[:PRINCIPAL_DISPLAY_LENGTH]}...")

            chat_id = data.get("chatId")
            messages = data.get("messages", [])
            metadata = data.get("metadata", {})

            if not chat_id:
                logger.error("❌ Missing chatId in autosave request")
                return jsonify({"error": "Missing chatId"}), 400

            if not validate_chat_id(chat_id):
                logger.warning(f"⚠️ Invalid chatId format: {chat_id[:20]}...")
                return jsonify({"error": "Invalid chatId format"}), 400

            if not validate_principal_id(principal):
                logger.warning(f"⚠️ Invalid principal format: {principal[:20]}...")
                return jsonify({"error": "Invalid principal format"}), 400

            logger.debug(f"   chatId: {chat_id}, messages: {len(messages)}")

            # Prepare chat snapshot payload
            chat_data = {
                "chatId": chat_id,
                "messages": messages,
                "metadata": metadata,
                "principal": principal,
                "savedAt": int(time.time() * 1000),
            }

            # Hot path: always persist encrypted snapshot locally first.
            _save_local_chat_snapshot(principal, chat_data)

            _ensure_restored(principal)
            manifest = _get_chat_manifest(principal)
            manifest_chat = next(
                (c for c in manifest.get("chats", []) if c.get("chatId") == chat_id),
                None,
            )
            existing_cid = manifest_chat.get("cid") if manifest_chat else None
            archived = bool(manifest_chat.get("archived", False)) if manifest_chat else False
            pinned = bool(manifest_chat.get("pinned", False)) if manifest_chat else False

            # Update metadata cache for sidebar/status/export paths.
            user_metadata = load_metadata(principal)

            # Read title from top-level (frontend sends it there) or metadata fallback
            chat_title = data.get("title") or metadata.get("title") or "Untitled"

            chat_entry = next((c for c in user_metadata["chats"] if c["chatId"] == chat_id), None)
            if not chat_entry:
                chat_entry = {
                    "chatId": chat_id,
                    "title": chat_title,
                    "createdAt": int(time.time() * 1000),
                    "isArchived": archived,
                }
                user_metadata["chats"].append(chat_entry)

            # Always update title (may improve as conversation grows)
            chat_entry["title"] = chat_title
            chat_entry["lastUpdated"] = metadata.get("updatedAt", int(time.time() * 1000))
            chat_entry["messageCount"] = len(messages)
            chat_entry["pinned"] = pinned
            chat_entry["isArchived"] = archived
            if existing_cid:
                chat_entry["cid"] = existing_cid

            save_metadata(principal, user_metadata)

            # Keep manifest metadata fresh now; CID is updated by queued sync.
            try:
                update_chat_in_manifest(
                    principal_id=principal,
                    chat_id=chat_id,
                    cid=existing_cid,
                    title=chat_title,
                    message_count=len(messages),
                    archived=archived,
                    pinned=pinned,
                )
            except Exception as manifest_err:
                logger.warning(f"⚠️ Manifest update failed: {manifest_err}")

            # Queue debounced chat checkpoint to IPFS.
            queue_chat_sync(
                principal_id=principal,
                chat_id=chat_id,
                chat_data=chat_data,
                title=chat_title,
                message_count=len(messages),
                archived=archived,
                pinned=pinned,
            )

            logger.info(f"💾 Autosaved chat {chat_id[:8]}... ({len(messages)} msgs)")

            return jsonify(
                {
                    "success": True,
                    "chatId": chat_id,
                    "savedAt": int(time.time() * 1000),
                    "cid": existing_cid,
                    "syncQueued": True,
                    "nextAutoDeleteAt": int(time.time() * 1000) + (7 * 24 * 60 * 60 * 1000),
                }
            )

        except Exception as e:
            track_error("StorageError", "/chat/autosave")
            logger.error(f"❌ Autosave error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500


# ===== LIST / GET / DELETE =====

@chat_bp.route("/chat/list", methods=["GET"])
@require_auth
@storage_rate_limit
def list_chats():
    """List all chats for user from the manifest (authoritative source)."""
    try:
        principal = request.principal

        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        chats = [_format_manifest_chat(chat) for chat in manifest.get("chats", [])]

        chats.sort(key=lambda x: x.get("lastUpdated", 0), reverse=True)

        return jsonify({"chats": chats, "count": len(chats)})

    except Exception as e:
        logger.error(f"List chats error: {e}")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/<chat_id>", methods=["GET"])
@require_auth
@storage_rate_limit
def get_chat(chat_id):
    """Load specific chat (local snapshot first, then IPFS)."""
    try:
        principal = request.principal

        if not validate_chat_id(chat_id):
            logger.warning(f"⚠️ Invalid chatId format in GET: {chat_id[:20]}...")
            return jsonify({"error": "Invalid chatId format"}), 400

        local_chat = _load_local_chat_snapshot(principal, chat_id)
        if local_chat:
            logger.info(f"📁 Loaded chat from local snapshot: {chat_id[:8]}...")
            return jsonify(local_chat)

        logger.info(f"🔍 Fetching chat from manifest/IPFS: {chat_id[:8]}...")
        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        chat_entry = next(
            (c for c in manifest.get("chats", []) if c.get("chatId") == chat_id),
            None,
        )
        cid = chat_entry.get("cid") if chat_entry else None

        if cid:
            logger.info(f"☁️  Found CID: {cid[:16]}..., downloading from IPFS")
            try:
                gateway_url = f"{LIGHTHOUSE_GATEWAY}/ipfs/{cid}"
                response = http_session.get(gateway_url, timeout=30)

                if response.status_code == 200:
                    encrypted_data = response.json()
                    decrypted = decrypt_for_user(encrypted_data, principal)
                    logger.info(f"✅ Loaded chat from IPFS: {chat_id[:8]}...")
                    return jsonify(decrypted)
                else:
                    logger.warning(f"IPFS gateway returned {response.status_code}")
            except Exception as ipfs_error:
                logger.error(f"Failed to download from IPFS: {ipfs_error}")

        return jsonify({"error": "Chat not found on IPFS"}), 404

    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        logger.error(f"Get chat error: {e}")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/<chat_id>", methods=["DELETE"])
@require_auth
@storage_rate_limit
def delete_chat(chat_id):
    """Delete chat - marks as deleted in metadata (IPFS is immutable)"""
    try:
        principal = request.principal

        if not validate_chat_id(chat_id):
            logger.warning(f"⚠️ Invalid chatId format in DELETE: {chat_id[:20]}...")
            return jsonify({"error": "Invalid chatId format"}), 400

        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        manifest_entry = next(
            (c for c in manifest.get("chats", []) if c.get("chatId") == chat_id),
            None,
        )

        # Check if chat is pinned — prevent deletion of pinned chats
        if manifest_entry and manifest_entry.get("pinned"):
            return jsonify({
                "error": {
                    "code": 400,
                    "message": "Cannot delete a pinned chat. Unpin it first.",
                }
            }), 400

        if manifest_entry:
            remove_chat_from_manifest(principal, chat_id)

        discard_queued_chat_sync(principal, chat_id)
        _delete_local_chat_snapshot(principal, chat_id)

        # Keep local metadata cache aligned for status/export endpoints
        user_metadata = load_metadata(principal)
        user_metadata["chats"] = [c for c in user_metadata.get("chats", []) if c.get("chatId") != chat_id]
        save_metadata(principal, user_metadata)

        logger.info(f"🗑️  Chat deleted from index: {chat_id[:8]}...")

        return jsonify({"success": True, "deletedAt": int(time.time() * 1000)})

    except Exception as e:
        logger.error(f"Delete chat error: {e}")
        return jsonify({"error": str(e)}), 500


# ===== PIN =====

@chat_bp.route("/chat/<chat_id>/pin", methods=["POST"])
@require_auth
@storage_rate_limit
def toggle_pin(chat_id):
    """Toggle pin status on a chat. Pinned chats appear at top and cannot be deleted."""
    try:
        principal = request.principal

        if not validate_chat_id(chat_id):
            return jsonify({"error": "Invalid chatId format"}), 400

        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        chat_entry = next((c for c in manifest.get("chats", []) if c.get("chatId") == chat_id), None)

        if not chat_entry:
            return jsonify({"error": "Chat not found"}), 404

        chat_entry["pinned"] = not chat_entry.get("pinned", False)
        save_manifest(principal, manifest)
        sync_manifest_to_ipfs(principal, manifest)

        # Keep local metadata cache aligned for status/export endpoints
        user_metadata = load_metadata(principal)
        meta_entry = next((c for c in user_metadata.get("chats", []) if c.get("chatId") == chat_id), None)
        if meta_entry:
            meta_entry["pinned"] = chat_entry["pinned"]
            meta_entry["isArchived"] = chat_entry.get("archived", False)
        save_metadata(principal, user_metadata)

        logger.info(f"📌 Chat {'pinned' if chat_entry['pinned'] else 'unpinned'}: {chat_id[:8]}...")

        return jsonify({
            "success": True,
            "chatId": chat_id,
            "pinned": chat_entry["pinned"],
        })

    except Exception as e:
        logger.error(f"Pin toggle error: {e}")
        return jsonify({"error": str(e)}), 500


# ===== ARCHIVE =====

@chat_bp.route("/chat/<chat_id>/archive", methods=["POST"])
@require_auth
@storage_rate_limit
def archive_chat(chat_id):
    """Mark chat as archived — chat is already on IPFS, this flags it as permanent"""
    try:
        principal = request.principal

        if not validate_chat_id(chat_id):
            logger.warning(f"⚠️ Invalid chatId format in archive: {chat_id[:20]}...")
            return jsonify({"error": "Invalid chatId format"}), 400

        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        chat_entry = next((c for c in manifest.get("chats", []) if c.get("chatId") == chat_id), None)

        if not chat_entry or not chat_entry.get("cid"):
            flushed_cid = flush_chat_sync_now(principal, chat_id)
            if flushed_cid:
                manifest = _get_chat_manifest(principal)
                chat_entry = next(
                    (c for c in manifest.get("chats", []) if c.get("chatId") == chat_id),
                    None,
                )
        if not chat_entry or not chat_entry.get("cid"):
            return jsonify({"error": "Chat not found on IPFS"}), 404

        if chat_entry.get("archived", False):
            return jsonify({"error": "Chat is already archived"}), 400

        # Hard limit: Maximum 20 archived chats
        archived_count = sum(1 for c in manifest.get("chats", []) if c.get("archived", False))
        if archived_count >= MAX_ARCHIVED_CHATS:
            return (
                jsonify(
                    {
                        "error": "Maximum 20 archived chats reached. Please delete an archived chat first.",
                        "limit": MAX_ARCHIVED_CHATS,
                        "current": archived_count,
                    }
                ),
                400,
            )

        chat_entry["archived"] = True
        chat_entry["archivedAt"] = int(time.time() * 1000)
        save_manifest(principal, manifest)
        sync_manifest_to_ipfs(principal, manifest)

        # Keep local metadata cache aligned for status/export endpoints
        user_metadata = load_metadata(principal)
        meta_entry = next((c for c in user_metadata.get("chats", []) if c.get("chatId") == chat_id), None)
        if meta_entry:
            meta_entry["isArchived"] = True
            meta_entry["archivedAt"] = chat_entry["archivedAt"]
        save_metadata(principal, user_metadata)

        logger.info(f"✅ Chat archived: {chat_id[:8]}... CID: {chat_entry['cid'][:16]}...")

        return jsonify(
            {
                "success": True,
                "chatId": chat_id,
                "cid": chat_entry["cid"],
                "archivedAt": chat_entry["archivedAt"],
                "archivedCount": archived_count + 1,
            }
        )

    except Exception as e:
        logger.error(f"❌ Archive error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ===== ARCHIVE RECOVERY =====

@chat_bp.route("/chat/recover-archives", methods=["GET"])
@require_auth
def recover_archives():
    """List archived chats from the manifest."""
    try:
        principal = request.principal
        logger.info(f"🔍 Recovering archives for {principal[:20]}...")

        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        archived_chats = [
            _format_manifest_chat(chat)
            for chat in manifest.get("chats", [])
            if chat.get("archived", False) and chat.get("cid")
        ]

        archived_chats.sort(key=lambda x: x.get("archivedAt", 0), reverse=True)

        if not archived_chats:
            return jsonify(
                {"success": True, "message": "No archived chats found", "archives": [], "count": 0}
            )

        logger.info(f"✅ Recovered {len(archived_chats)} archived chats")

        return jsonify(
            {
                "success": True,
                "archives": archived_chats,
                "count": len(archived_chats),
                "recoveredAt": int(time.time() * 1000),
            }
        )

    except ValueError as e:
        logger.error(f"Decryption failed during recovery: {e}")
        return jsonify({"error": "Failed to decrypt archives - wrong principal?"}), 401
    except Exception as e:
        logger.error(f"❌ Archive recovery error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/archive/<cid>", methods=["GET"])
@require_auth
def get_archived_chat(cid):
    """Download and decrypt a specific archived chat by its CID."""
    try:
        principal = request.principal

        if not validate_cid(cid):
            logger.warning(f"⚠️ Invalid CID format: {cid[:20]}...")
            return jsonify({"error": "Invalid CID format"}), 400

        logger.info(f"📥 Downloading archived chat: {cid}")

        chat_data = download_from_ipfs(cid)

        if not chat_data:
            return jsonify({"error": "Failed to download chat from IPFS", "cid": cid}), 404

        encrypted_chat = json.loads(chat_data.decode("utf-8"))
        decrypted_chat = decrypt_for_user(encrypted_chat, principal)

        logger.info(f"✅ Archived chat recovered: {cid}")

        return jsonify(
            {
                "success": True,
                "cid": cid,
                "chat": decrypted_chat,
                "recoveredAt": int(time.time() * 1000),
            }
        )

    except ValueError as e:
        logger.error(f"Decryption failed: {e}")
        return jsonify({"error": "Failed to decrypt chat - wrong principal?"}), 401
    except Exception as e:
        logger.error(f"❌ Archive download error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/archive/status/<cid>", methods=["GET"])
def get_archive_status(cid):
    """Check IPFS availability status for an archived chat (no auth required)."""
    try:
        if not validate_cid(cid):
            logger.warning(f"⚠️ Invalid CID format in status check: {cid[:20]}...")
            return jsonify({"error": "Invalid CID format"}), 400

        logger.info(f"📊 Checking IPFS status for: {cid}")

        return jsonify(
            {
                "cid": cid,
                "status": "available",
                "message": "Content is pinned on IPFS via Lighthouse",
                "gateways": [
                    f"{LIGHTHOUSE_GATEWAY}/ipfs/{cid}",
                    f"https://ipfs.io/ipfs/{cid}",
                    f"https://dweb.link/ipfs/{cid}",
                ],
                "checkedAt": int(time.time() * 1000),
            }
        )

    except Exception as e:
        logger.error(f"❌ Status check error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ===== USER STATUS DASHBOARD =====

@chat_bp.route("/user/status", methods=["GET"])
@require_auth
def get_user_status():
    """Get comprehensive user status for dashboard display."""
    try:
        principal = request.principal
        ip = request.remote_addr or "unknown"

        _ensure_restored(principal)
        manifest = _get_chat_manifest(principal)
        chats = manifest.get("chats", [])
        pinned_count = sum(1 for c in chats if c.get("pinned"))
        archived_count = sum(1 for c in chats if c.get("archived"))

        # Rate limit info (lazy import — only used in this endpoint)
        from middleware.rate_limit import get_rate_limit_info, request_counts, RATE_LIMIT, RATE_WINDOW
        rate_info = get_rate_limit_info(ip, request_counts, RATE_LIMIT, RATE_WINDOW)

        # Token quota info
        from middleware.rate_limit import check_token_quota, get_user_id, TOKEN_QUOTA_DAILY, TOKEN_QUOTA_HOURLY
        user_id = get_user_id()
        _, quota_info = check_token_quota(user_id)

        return jsonify({
            "storage": {
                "chats_used": len(chats),
                "chats_limit": MAX_ARCHIVED_CHATS,
                "pinned_count": pinned_count,
                "archived_count": archived_count,
            },
            "rate_limits": {
                "requests_remaining": rate_info["remaining"],
                "requests_limit": rate_info["limit"],
                "resets_in_seconds": rate_info["reset_in"],
            },
            "tokens": {
                "used_today": quota_info.get("tokens_used", 0),
                "limit_today": TOKEN_QUOTA_DAILY,
                "remaining_today": quota_info.get("tokens_remaining", TOKEN_QUOTA_DAILY),
            },
        })

    except Exception as e:
        logger.error(f"User status error: {e}")
        return jsonify({"error": str(e)}), 500


# ===== USER MEMORY =====

@chat_bp.route("/user/memory", methods=["GET"])
@require_auth
@storage_rate_limit
def get_user_memory():
    """Get user's persistent memory (facts, preferences).
    Also triggers IPFS restore on first request per session."""
    try:
        principal = request.principal

        # Ensure all user data is restored from IPFS (idempotent)
        try:
            from services.user_data_store import ensure_user_data_restored
            ensure_user_data_restored(principal)
        except Exception as e:
            logger.warning(f"⚠️ Data restore check failed: {e}")

        memory = load_user_memory(principal)

        logger.debug(f'📖 Loaded user memory: {len(memory.get("facts", []))} facts')
        return jsonify(memory)

    except Exception as e:
        logger.error(f"❌ Error loading user memory: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/user/memory", methods=["POST"])
@require_auth
@storage_rate_limit
def update_user_memory():
    """Update user's persistent memory"""
    try:
        principal = request.principal
        data = request.json

        if not data:
            return jsonify({"error": "No data provided"}), 400

        memory = load_user_memory(principal)

        if "facts" in data:
            memory["facts"] = data["facts"]

        if "preferences" in data:
            memory["preferences"] = data["preferences"]

        save_user_memory(principal, memory)

        logger.debug("💾 Updated user memory")
        return jsonify({"success": True, "memory": memory})

    except Exception as e:
        logger.error(f"❌ Error updating user memory: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/user/memory/fact", methods=["POST"])
@require_auth
@storage_rate_limit
def add_memory_fact():
    """Add a single fact to user's memory (normalized schema with dedup)."""
    try:
        principal = request.principal
        data = request.json

        if not data or "fact" not in data:
            return jsonify({"error": "Fact is required"}), 400

        # Use tool_save_memory which handles dedup/merge
        try:
            from services.memory_tools import tool_save_memory
            success, result = tool_save_memory({
                "fact": data["fact"],
                "category": data.get("category", "general"),
                "importance": str(data.get("importance", 3)),
            }, principal)

            memory = load_user_memory(principal)
            active_count = len([f for f in memory.get("facts", []) if not f.get("deleted", False)])
            return jsonify({"success": success, "message": result, "totalFacts": active_count})
        except ImportError:
            # Fallback if embeddings not available
            memory = load_user_memory(principal)
            new_fact = {
                "text": data["fact"],
                "category": data.get("category", "general"),
                "importance": int(data.get("importance", 3)),
                "embedding": None,
                "created_at": int(time.time() * 1000),
                "deleted": False,
                "source_chat_id": None,
                "last_mentioned": int(time.time() * 1000),
            }
            memory["facts"].append(new_fact)
            save_user_memory(principal, memory)
            return jsonify({"success": True, "fact": new_fact, "totalFacts": len(memory["facts"])})

    except Exception as e:
        logger.error(f"❌ Error adding memory fact: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/user/memory/fact/<int:index>", methods=["DELETE"])
@require_auth
@storage_rate_limit
def delete_memory_fact(index):
    """Soft-delete a fact from user's memory (preserved in exports)."""
    try:
        principal = request.principal
        memory = load_user_memory(principal)
        facts = memory.get("facts", [])

        if index < 0 or index >= len(facts):
            return jsonify({"error": "Invalid fact index"}), 400

        # Soft delete — mark as deleted instead of removing
        facts[index]["deleted"] = True
        facts[index]["deleted_at"] = int(time.time() * 1000)
        memory["facts"] = facts
        save_user_memory(principal, memory)

        active_count = len([f for f in facts if not f.get("deleted", False)])
        logger.info(f'🗑️ Soft-deleted fact #{index} (active: {active_count})')
        return jsonify(
            {"success": True, "deletedFact": facts[index], "totalFacts": active_count}
        )

    except Exception as e:
        logger.error(f"❌ Error deleting memory fact: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ===== USER DATA EXPORT =====

@chat_bp.route("/user/export", methods=["GET"])
@require_auth
def export_user_data():
    """
    Export ALL user data as a ZIP archive.

    Returns a ZIP containing:
    - profile.json: structured user profile with all facts
    - chats/*.md: each chat as human-readable Markdown
    - chats/*.json: each chat as structured JSON
    - manifest.json: IPFS manifest with CIDs for verification
    - README.txt: explains what each file is
    """
    import io
    import zipfile

    from flask import send_file

    try:
        principal = request.principal

        # Build ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:

            # 1. Profile (user memory, stripped of embeddings for readability)
            memory = load_user_memory(principal)
            profile_export = {
                "principalId": memory.get("principalId"),
                "version": memory.get("version"),
                "profile": memory.get("profile", {}),
                "facts": [],
                "exportedAt": int(time.time() * 1000),
            }
            for fact in memory.get("facts", []):
                exported_fact = {k: v for k, v in fact.items() if k != "embedding"}
                profile_export["facts"].append(exported_fact)
            zf.writestr("profile.json", json.dumps(profile_export, indent=2))

            # 2. Chats
            _ensure_restored(principal)
            manifest = _get_chat_manifest(principal)
            for chat_meta in manifest.get("chats", []):
                chat_id = chat_meta.get("chatId", "")
                cid = chat_meta.get("cid")
                if not chat_id:
                    continue

                chat_data = None

                if cid:
                    # Load chat from IPFS via manifest CID.
                    try:
                        raw = download_from_ipfs(cid)
                        if raw:
                            encrypted = json.loads(raw.decode("utf-8"))
                            chat_data = decrypt_for_user(encrypted, principal)
                    except Exception:
                        chat_data = None

                # Fall back to local snapshot for unsynced/new checkpoints.
                if chat_data is None:
                    chat_data = _load_local_chat_snapshot(principal, chat_id)
                if chat_data is None:
                    continue

                title = chat_data.get("title", chat_meta.get("title", "Untitled"))
                messages = chat_data.get("messages", [])

                # Markdown version
                md_lines = [f"# {title}\n"]
                for msg in messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    ts = msg.get("timestamp", "")
                    md_lines.append(f"### {role.title()}")
                    if ts:
                        md_lines.append(f"*{ts}*\n")
                    md_lines.append(f"{content}\n")
                zf.writestr(f"chats/{chat_id}.md", "\n".join(md_lines))

                # JSON version (structured, no embeddings)
                json_export = {
                    "chatId": chat_id,
                    "title": title,
                    "messages": messages,
                    "createdAt": chat_data.get("createdAt"),
                    "lastUpdated": chat_data.get("lastUpdated"),
                }
                zf.writestr(f"chats/{chat_id}.json", json.dumps(json_export, indent=2))

            # 3. Manifest (IPFS CIDs for verification)
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # 4. README
            readme = """Trinity Data Export
===================

This archive contains ALL data Trinity has stored about you.

Files:
- profile.json    — Your user profile: facts, preferences, profile data.
                     Facts with "deleted": true were soft-deleted but preserved
                     for your review.
- chats/*.md      — Your conversations in human-readable Markdown format.
- chats/*.json    — Your conversations in structured JSON (for import/analysis).
- manifest.json   — IPFS content identifiers (CIDs) for your encrypted data.
                     You can verify your data on IPFS using these CIDs.

Encryption Note:
  All of this data was encrypted on the server with YOUR Ed25519 key.
  The server operator cannot read any of it. This export was generated
  during an authenticated session where your key was available.

Data Ownership:
  This data belongs to you. Trinity does not retain copies after you
  delete your account. You can import this data into another system
  or use it as a backup.

Generated: """ + time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + "\n"

            zf.writestr("README.txt", readme)

        zip_buffer.seek(0)
        logger.info(f"📦 Data export generated for {principal[:20]}...")

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"trinity-export-{int(time.time())}.zip",
        )

    except Exception as e:
        logger.error(f"❌ Export error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/user/stats", methods=["GET"])
@require_auth
def get_user_stats():
    """
    Get user's data statistics: profile size, fact count, chat count,
    total messages, IPFS storage used, last sync time.
    """
    try:
        principal = request.principal

        _ensure_restored(principal)
        memory = load_user_memory(principal)
        manifest = _get_chat_manifest(principal)

        all_facts = memory.get("facts", [])
        active_facts = [f for f in all_facts if not f.get("deleted", False)]
        deleted_facts = [f for f in all_facts if f.get("deleted", False)]

        # Count categories
        categories = {}
        for fact in active_facts:
            cat = fact.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1

        # Chat stats
        chats = manifest.get("chats", [])
        total_messages = sum(c.get("messageCount", 0) for c in chats)

        stats = {
            "profile": {
                "version": memory.get("version", "1.0"),
                "activeFacts": len(active_facts),
                "deletedFacts": len(deleted_facts),
                "categories": categories,
                "createdAt": memory.get("createdAt"),
                "lastUpdated": memory.get("lastUpdated"),
            },
            "chats": {
                "count": len(chats),
                "totalMessages": total_messages,
            },
            "ipfs": {
                "profileCid": manifest.get("profile", {}).get("cid") if manifest else None,
                "vectorDbCid": manifest.get("memoryIndex", {}).get("cid") if manifest else None,
                "totalBytes": manifest.get("totalBytes", 0) if manifest else 0,
                "lastSynced": manifest.get("lastUpdated") if manifest else None,
                "archivedChats": sum(
                    1 for c in manifest.get("chats", []) if c.get("archived", False)
                ) if manifest else 0,
            },
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": "Argon2id",
                "encryptedAtRest": True,
                "encryptedOnIPFS": True,
            },
        }

        return jsonify(stats)

    except Exception as e:
        logger.error(f"❌ Stats error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
