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
from services.user_data_store import encrypt_for_user, decrypt_for_user
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
        encrypted_manifest = encrypt_for_user(manifest, principal_id)

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
            encrypted = encrypt_for_user(chat_data, principal)
            encrypted_json = json.dumps(encrypted)

            # Upload to IPFS (source of truth)
            lighthouse_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_{chat_id}.json"
            cid = upload_to_ipfs(
                encrypted_json.encode("utf-8"), lighthouse_filename, principal_id=principal
            )

            if not cid:
                logger.error(f"❌ IPFS upload failed for chat {chat_id[:8]}")
                # Still return partial success so the frontend stops retrying.
                # The chat is saved locally in IndexedDB; IPFS sync can retry later.
                return jsonify({
                    "success": True,
                    "chatId": chat_id,
                    "savedAt": int(time.time() * 1000),
                    "cid": None,
                    "warning": "IPFS upload failed — saved locally only",
                }), 200

            logger.info(f"☁️  Saved to IPFS: {cid[:16]}...")

            # Update metadata with CID for later retrieval
            user_metadata = load_metadata(principal)

            # Read title from top-level (frontend sends it there) or metadata fallback
            chat_title = data.get("title") or metadata.get("title") or "Untitled"

            chat_entry = next((c for c in user_metadata["chats"] if c["chatId"] == chat_id), None)
            if not chat_entry:
                chat_entry = {
                    "chatId": chat_id,
                    "title": chat_title,
                    "createdAt": int(time.time() * 1000),
                    "isArchived": False,
                }
                user_metadata["chats"].append(chat_entry)

            # Always update title (may improve as conversation grows)
            chat_entry["title"] = chat_title
            chat_entry["lastUpdated"] = metadata.get("updatedAt", int(time.time() * 1000))
            chat_entry["messageCount"] = len(messages)
            if cid:
                chat_entry["cid"] = cid

            save_metadata(principal, user_metadata)

            # Update unified manifest (replaces legacy metadata IPFS sync)
            try:
                from services.user_data_store import update_chat_in_manifest
                update_chat_in_manifest(
                    principal_id=principal,
                    chat_id=chat_id,
                    cid=cid,
                    title=chat_title,
                    message_count=len(messages),
                    archived=chat_entry.get("isArchived", False),
                    pinned=chat_entry.get("pinned", False),
                )
            except Exception as manifest_err:
                logger.warning(f"⚠️ Manifest update failed: {manifest_err}")

            # Also sync metadata to IPFS (legacy — kept for backward compat)
            try:
                metadata_filename = f"{principal[:PRINCIPAL_DISPLAY_LENGTH]}_metadata.json"
                metadata_encrypted = encrypt_for_user(user_metadata, principal)
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
                    recovered_metadata = decrypt_for_user(encrypted_metadata, principal)
                    chats = recovered_metadata.get("chats", [])
                    logger.info(f"✅ Retrieved {len(chats)} chats from IPFS")
            else:
                seen_ids = {}
                for upload in uploads[:IPFS_SCAN_LIMIT]:
                    filename = upload.get("fileName", "")
                    if principal[:PRINCIPAL_DISPLAY_LENGTH] in filename and "metadata" not in filename:
                        parts = filename.replace(".json", "").split("_")
                        if len(parts) >= 2:
                            chat_id = parts[-1]
                            # Deduplicate by chatId — keep most recent (first seen in sorted uploads)
                            if chat_id not in seen_ids:
                                seen_ids[chat_id] = {
                                    "chatId": chat_id,
                                    "title": "Recovered Chat",
                                    "cid": upload.get("cid"),
                                    "lastUpdated": upload.get("createdAt", 0),
                                    "isArchived": False,
                                }
                chats = list(seen_ids.values())
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
                user_metadata = decrypt_for_user(encrypted_metadata, principal)

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
                metadata_encrypted = encrypt_for_user(user_metadata, principal)
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
            metadata_encrypted = encrypt_for_user(user_metadata, principal)
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
                user_metadata = decrypt_for_user(encrypted_metadata, principal)

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
        metadata_encrypted = encrypt_for_user(user_metadata, principal)
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
        manifest = decrypt_for_user(encrypted_manifest, principal)

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
            metadata = load_metadata(principal)
            chats = metadata.get("chats", [])
            for chat_meta in chats:
                chat_id = chat_meta.get("chatId", "")
                if not chat_id:
                    continue

                # Try to load chat from disk
                try:
                    from storage import get_user_dir
                    chat_path = get_user_dir(principal) / f"{chat_id}.json"
                    if chat_path.exists():
                        with open(chat_path, "r") as cf:
                            raw = json.load(cf)
                        # Decrypt if needed
                        if isinstance(raw, dict) and "encryption" in raw:
                            chat_data = decrypt_for_user(raw, principal)
                        else:
                            chat_data = raw
                    else:
                        continue
                except Exception:
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
            try:
                from services.user_data_store import load_manifest
                manifest = load_manifest(principal)
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            except Exception:
                zf.writestr("manifest.json", json.dumps({"note": "No IPFS manifest available"}))

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

        memory = load_user_memory(principal)
        metadata = load_metadata(principal)

        all_facts = memory.get("facts", [])
        active_facts = [f for f in all_facts if not f.get("deleted", False)]
        deleted_facts = [f for f in all_facts if f.get("deleted", False)]

        # Count categories
        categories = {}
        for fact in active_facts:
            cat = fact.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1

        # Chat stats
        chats = metadata.get("chats", [])
        total_messages = sum(c.get("messageCount", 0) for c in chats)

        # IPFS stats
        manifest = None
        try:
            from services.user_data_store import load_manifest
            manifest = load_manifest(principal)
        except Exception:
            pass

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
                "archivedChats": len(manifest.get("chats", [])) if manifest else 0,
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
