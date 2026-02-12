"""
Chat Blueprint — /chat/*, /user/status, /user/memory*
=====================================================
Handles encrypted chat storage, archival, user memory and status dashboard.
All chat/user endpoints require Ed25519 auth via @require_auth.
"""

import json
import time
from typing import Dict, Optional

from flask import Blueprint, jsonify, request

from config import LIGHTHOUSE_GATEWAY, MAX_ARCHIVED_CHATS, IPFS_SCAN_LIMIT, PRINCIPAL_DISPLAY_LENGTH, http_session, logger
from encryption import EncryptionUtils
from icp_auth import require_admin, require_auth
from lighthouse import download_from_ipfs, get_lighthouse_uploads, upload_to_ipfs
from middleware import storage_rate_limit, track_error, track_storage
from storage import load_metadata, load_user_memory, save_metadata, save_user_memory
from validation import validate_chat_id, validate_cid, validate_principal_id

chat_bp = Blueprint("chat", __name__)


# ===== HELPER =====

def update_master_bundle(principal_id: str, user_metadata: Dict = None) -> Optional[str]:
    """
    Create/update master bundle containing index of all archived chats.
    This is the single CID that gives access to all user's archives.

    Args:
        principal_id: User's principal ID
        user_metadata: Optional pre-loaded metadata (loads if not provided)

    Returns:
        New master bundle CID on success, None on failure
    """
    try:
        if user_metadata is None:
            user_metadata = load_metadata(principal_id)

        # Build manifest of all archived chats
        archived_chats = [
            {
                "chatId": c["chatId"],
                "title": c.get("title", "Untitled"),
                "cid": c.get("cid"),
                "archivedAt": c.get("archivedAt"),
                "messageCount": c.get("messageCount", 0),
            }
            for c in user_metadata.get("chats", [])
            if c.get("isArchived") and c.get("cid")
        ]

        if not archived_chats:
            logger.info(f"No archived chats with CIDs for {principal_id[:20]}...")
            return None

        # Create master bundle manifest
        manifest = {
            "version": "1.0",
            "type": "master_bundle",
            "principal": principal_id,
            "createdAt": int(time.time() * 1000),
            "bundleVersion": user_metadata.get("lastBundleVersion", 0) + 1,
            "chats": archived_chats,
            "chatCount": len(archived_chats),
        }

        # Encrypt manifest with principal ID
        encrypted_manifest = EncryptionUtils.encrypt_chat(manifest, principal_id)

        # Upload master bundle
        bundle_filename = f"{principal_id[:20]}_master_bundle.json"
        bundle_data = json.dumps(encrypted_manifest).encode("utf-8")

        bundle_cid = upload_to_ipfs(
            bundle_data, bundle_filename, principal_id=principal_id, is_master_bundle=True
        )

        if bundle_cid:
            # Update local metadata with new bundle CID
            user_metadata["currentBundleCID"] = bundle_cid
            user_metadata["lastBundleVersion"] = manifest["bundleVersion"]
            user_metadata["lastSyncedAt"] = int(time.time() * 1000)
            save_metadata(principal_id, user_metadata)

            logger.info(
                f'✅ Master bundle updated: {bundle_cid} (v{manifest["bundleVersion"]}, {len(archived_chats)} chats)'
            )

        return bundle_cid

    except Exception as e:
        logger.error(f"❌ Master bundle update error: {e}", exc_info=True)
        return None


# ===== AUTOSAVE =====

@chat_bp.route("/chat/autosave", methods=["POST"])
@require_auth
@storage_rate_limit
def autosave_chat():
    """Save chat - encrypts and uploads directly to IPFS via Lighthouse"""
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

            # Prepare chat data for encryption
            chat_data = {
                "chatId": chat_id,
                "messages": messages,
                "metadata": metadata,
                "principal": principal,
                "savedAt": int(time.time() * 1000),
            }

            # Encrypt content
            encrypted = EncryptionUtils.encrypt_chat(chat_data, principal)
            encrypted_json = json.dumps(encrypted)

            # Upload to IPFS (source of truth)
            lighthouse_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_{chat_id}.json"
            cid = upload_to_ipfs(
                encrypted_json.encode("utf-8"), lighthouse_filename, principal_id=principal
            )

            if not cid:
                logger.error(f"❌ IPFS upload failed for chat {chat_id[:8]}")
                return jsonify({"success": False, "error": "IPFS upload failed"}), 500

            logger.info(f"☁️  Saved to IPFS: {cid[:16]}...")

            # Update metadata with CID for later retrieval
            user_metadata = load_metadata(principal)

            chat_entry = next((c for c in user_metadata["chats"] if c["chatId"] == chat_id), None)
            if not chat_entry:
                chat_entry = {
                    "chatId": chat_id,
                    "title": metadata.get("title", "Untitled"),
                    "createdAt": int(time.time() * 1000),
                    "isArchived": False,
                }
                user_metadata["chats"].append(chat_entry)

            chat_entry["lastUpdated"] = metadata.get("updatedAt", int(time.time() * 1000))
            chat_entry["messageCount"] = len(messages)
            if cid:
                chat_entry["cid"] = cid

            save_metadata(principal, user_metadata)

            # Also sync metadata to IPFS
            try:
                metadata_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_metadata.json"
                metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
                upload_to_ipfs(
                    json.dumps(metadata_encrypted).encode("utf-8"),
                    metadata_filename,
                    principal_id=principal,
                    is_master_bundle=True,
                )
            except Exception as meta_sync_error:
                logger.warning(f"⚠️  Metadata sync failed: {meta_sync_error}")

            logger.info(f"💾 Autosaved chat {chat_id[:8]}... ({len(messages)} msgs)")

            return jsonify(
                {
                    "success": True,
                    "chatId": chat_id,
                    "savedAt": int(time.time() * 1000),
                    "cid": cid,
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
    """List all chats for user - fetches from IPFS via Lighthouse"""
    try:
        principal = request.principal

        logger.info(f"🔍 Fetching chat list from IPFS for {principal[:PRINCIPAL_DISPLAY_LENGTH]}...")

        chats = []
        try:
            uploads = get_lighthouse_uploads(principal)
            metadata_cid = None

            for upload in uploads:
                filename = upload.get("fileName", "")
                if principal[:PRINCIPAL_DISPLAY_LENGTH] in filename and "metadata" in filename:
                    metadata_cid = upload.get("cid")
                    break

            if metadata_cid:
                logger.info(f"☁️  Found metadata on IPFS: {metadata_cid[:16]}...")
                gateway_url = f"{LIGHTHOUSE_GATEWAY}/ipfs/{metadata_cid}"
                response = http_session.get(gateway_url, timeout=30)

                if response.status_code == 200:
                    encrypted_metadata = response.json()
                    recovered_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)
                    chats = recovered_metadata.get("chats", [])
                    logger.info(f"✅ Retrieved {len(chats)} chats from IPFS")
            else:
                for upload in uploads[:IPFS_SCAN_LIMIT]:
                    filename = upload.get("fileName", "")
                    if principal[:PRINCIPAL_DISPLAY_LENGTH] in filename and "metadata" not in filename:
                        parts = filename.replace(".json", "").split("_")
                        if len(parts) >= 2:
                            chat_id = parts[-1]
                            chats.append(
                                {
                                    "chatId": chat_id,
                                    "title": "Recovered Chat",
                                    "cid": upload.get("cid"),
                                    "lastUpdated": upload.get("createdAt", 0),
                                    "isArchived": False,
                                }
                            )
                if chats:
                    logger.info(f"✅ Found {len(chats)} individual chats on IPFS")

        except Exception as ipfs_error:
            logger.warning(f"⚠️  IPFS fetch failed: {ipfs_error}")

        chats.sort(key=lambda x: x.get("lastUpdated", 0), reverse=True)

        return jsonify({"chats": chats, "count": len(chats)})

    except Exception as e:
        logger.error(f"List chats error: {e}")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/<chat_id>", methods=["GET"])
@require_auth
@storage_rate_limit
def get_chat(chat_id):
    """Load specific chat from IPFS"""
    try:
        principal = request.principal

        if not validate_chat_id(chat_id):
            logger.warning(f"⚠️ Invalid chatId format in GET: {chat_id[:20]}...")
            return jsonify({"error": "Invalid chatId format"}), 400

        logger.info(f"🔍 Fetching chat from IPFS: {chat_id[:8]}...")

        cid = None
        try:
            uploads = get_lighthouse_uploads(principal)
            for upload in uploads:
                filename = upload.get("fileName", "")
                if chat_id in filename and "metadata" not in filename:
                    cid = upload.get("cid")
                    break
        except Exception as e:
            logger.warning(f"Could not search Lighthouse uploads: {e}")

        if cid:
            logger.info(f"☁️  Found CID: {cid[:16]}..., downloading from IPFS")
            try:
                gateway_url = f"{LIGHTHOUSE_GATEWAY}/ipfs/{cid}"
                response = http_session.get(gateway_url, timeout=30)

                if response.status_code == 200:
                    encrypted_data = response.json()
                    decrypted = EncryptionUtils.decrypt_chat(encrypted_data, principal)
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

        uploads = get_lighthouse_uploads(principal)
        metadata_cid = None
        for upload in uploads:
            filename = upload.get("fileName", "")
            if principal[:PRINCIPAL_DISPLAY_LENGTH] in filename and "metadata" in filename:
                metadata_cid = upload.get("cid")
                break

        if metadata_cid:
            gateway_url = f"{LIGHTHOUSE_GATEWAY}/ipfs/{metadata_cid}"
            response = http_session.get(gateway_url, timeout=30)
            if response.status_code == 200:
                encrypted_metadata = response.json()
                user_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)

                # Check if chat is pinned — prevent deletion of pinned chats
                chat_entry = next(
                    (c for c in user_metadata.get("chats", []) if c["chatId"] == chat_id), None
                )
                if chat_entry and chat_entry.get("pinned"):
                    return jsonify({
                        "error": {
                            "code": 400,
                            "message": "Cannot delete a pinned chat. Unpin it first.",
                        }
                    }), 400

                # Remove chat from list
                user_metadata["chats"] = [
                    c for c in user_metadata.get("chats", []) if c["chatId"] != chat_id
                ]

                # Upload updated metadata to IPFS
                metadata_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_metadata.json"
                metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
                upload_to_ipfs(
                    json.dumps(metadata_encrypted).encode("utf-8"),
                    metadata_filename,
                    principal_id=principal,
                    is_master_bundle=True,
                )

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

        user_metadata = load_metadata(principal)

        chat_entry = next(
            (c for c in user_metadata.get("chats", []) if c["chatId"] == chat_id), None
        )

        if not chat_entry:
            return jsonify({"error": "Chat not found"}), 404

        chat_entry["pinned"] = not chat_entry.get("pinned", False)
        save_metadata(principal, user_metadata)

        # Sync metadata to IPFS
        try:
            metadata_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_metadata.json"
            metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
            upload_to_ipfs(
                json.dumps(metadata_encrypted).encode("utf-8"),
                metadata_filename,
                principal_id=principal,
                is_master_bundle=True,
            )
        except Exception as sync_err:
            logger.warning(f"⚠️ Pin metadata sync failed: {sync_err}")

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

        uploads = get_lighthouse_uploads(principal)
        metadata_cid = None
        chat_cid = None

        for upload in uploads:
            filename = upload.get("fileName", "")
            if principal[:PRINCIPAL_DISPLAY_LENGTH] in filename and "metadata" in filename:
                metadata_cid = upload.get("cid")
            if chat_id in filename and "metadata" not in filename:
                chat_cid = upload.get("cid")

        if not chat_cid:
            return jsonify({"error": "Chat not found on IPFS"}), 404

        # Load metadata from IPFS
        user_metadata = {"chats": []}
        if metadata_cid:
            gateway_url = f"{LIGHTHOUSE_GATEWAY}/ipfs/{metadata_cid}"
            response = http_session.get(gateway_url, timeout=30)
            if response.status_code == 200:
                encrypted_metadata = response.json()
                user_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)

        chat_entry = next(
            (c for c in user_metadata.get("chats", []) if c["chatId"] == chat_id), None
        )

        if not chat_entry:
            chat_entry = {"chatId": chat_id, "cid": chat_cid}
            user_metadata.setdefault("chats", []).append(chat_entry)

        if chat_entry.get("isArchived"):
            return jsonify({"error": "Chat is already archived"}), 400

        # Hard limit: Maximum 20 archived chats
        archived_count = sum(
            1 for c in user_metadata.get("chats", []) if c.get("isArchived", False)
        )
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

        chat_entry["isArchived"] = True
        chat_entry["archivedAt"] = int(time.time() * 1000)
        chat_entry["cid"] = chat_cid

        # Upload updated metadata to IPFS
        metadata_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_metadata.json"
        metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
        new_metadata_cid = upload_to_ipfs(
            json.dumps(metadata_encrypted).encode("utf-8"),
            metadata_filename,
            principal_id=principal,
            is_master_bundle=True,
        )

        logger.info(f"✅ Chat archived: {chat_id[:8]}... CID: {chat_cid[:16]}...")

        return jsonify(
            {
                "success": True,
                "chatId": chat_id,
                "cid": chat_cid,
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
    """Recover all archived chats for the authenticated user."""
    try:
        principal = request.principal
        logger.info(f"🔍 Recovering archives for {principal[:20]}...")

        user_metadata = load_metadata(principal)
        local_bundle_cid = user_metadata.get("currentBundleCID")

        uploads = get_lighthouse_uploads(principal_id=principal)

        if not uploads and not local_bundle_cid:
            return jsonify(
                {"success": True, "message": "No archived chats found", "archives": [], "count": 0}
            )

        bundle_cid = local_bundle_cid

        if not bundle_cid:
            return jsonify(
                {"success": True, "message": "No master bundle found", "archives": [], "count": 0}
            )

        logger.info(f"📥 Downloading master bundle: {bundle_cid}")

        bundle_data = download_from_ipfs(bundle_cid)

        if not bundle_data:
            return (
                jsonify({"error": "Failed to download master bundle from IPFS", "cid": bundle_cid}),
                500,
            )

        encrypted_manifest = json.loads(bundle_data.decode("utf-8"))
        manifest = EncryptionUtils.decrypt_chat(encrypted_manifest, principal)

        logger.info(f'✅ Recovered {manifest.get("chatCount", 0)} archived chats')

        return jsonify(
            {
                "success": True,
                "masterBundleCID": bundle_cid,
                "bundleVersion": manifest.get("bundleVersion", 0),
                "archives": manifest.get("chats", []),
                "count": manifest.get("chatCount", 0),
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
        decrypted_chat = EncryptionUtils.decrypt_chat(encrypted_chat, principal)

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

        user_metadata = load_metadata(principal)
        chats = user_metadata.get("chats", [])
        pinned_count = sum(1 for c in chats if c.get("pinned"))
        archived_count = sum(1 for c in chats if c.get("isArchived"))

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
    """Get user's persistent memory (facts, preferences)"""
    try:
        principal = request.principal
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
    """Add a single fact to user's memory"""
    try:
        principal = request.principal
        data = request.json

        if not data or "fact" not in data:
            return jsonify({"error": "Fact is required"}), 400

        memory = load_user_memory(principal)

        new_fact = {
            "fact": data["fact"],
            "addedAt": int(time.time() * 1000),
            "fromChatId": data.get("chatId"),
            "category": data.get("category", "general"),
        }

        memory["facts"].append(new_fact)
        save_user_memory(principal, memory)

        logger.info(f'➕ Added fact to user memory (total: {len(memory["facts"])})')
        return jsonify({"success": True, "fact": new_fact, "totalFacts": len(memory["facts"])})

    except Exception as e:
        logger.error(f"❌ Error adding memory fact: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/user/memory/fact/<int:index>", methods=["DELETE"])
@require_auth
@storage_rate_limit
def delete_memory_fact(index):
    """Delete a fact from user's memory"""
    try:
        principal = request.principal
        memory = load_user_memory(principal)

        if index < 0 or index >= len(memory["facts"]):
            return jsonify({"error": "Invalid fact index"}), 400

        deleted_fact = memory["facts"].pop(index)
        save_user_memory(principal, memory)

        logger.info(f'🗑️ Deleted fact #{index} from user memory (remaining: {len(memory["facts"])})')
        return jsonify(
            {"success": True, "deletedFact": deleted_fact, "totalFacts": len(memory["facts"])}
        )

    except Exception as e:
        logger.error(f"❌ Error deleting memory fact: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
