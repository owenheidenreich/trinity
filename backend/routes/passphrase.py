"""
Passphrase management endpoints.
Routes: /api/passphrase/setup, /api/passphrase/unlock, /api/passphrase/change, /api/passphrase/lock
"""

import json
import logging
import threading
from typing import Dict, Optional

from flask import Blueprint, jsonify, request

from encryption import EncryptionUtils
from icp_auth import require_auth
from lighthouse import download_from_ipfs, get_lighthouse_uploads, upload_to_ipfs
from middleware import rate_limit
from services.session_manager import (
    clear_session,
    get_session_passphrase,
    has_passphrase,
    set_session_passphrase,
)

logger = logging.getLogger(__name__)

passphrase_bp = Blueprint("passphrase", __name__)

CANARY_FILENAME_SUFFIX = "_canary.json"


def _canary_filename(principal_id: str) -> str:
    return f"{principal_id[:20]}{CANARY_FILENAME_SUFFIX}"


def _find_canary_on_ipfs(principal_id: str) -> Optional[Dict]:
    """Search Lighthouse uploads for this user's passphrase canary."""
    try:
        filename = _canary_filename(principal_id)
        uploads = get_lighthouse_uploads(principal_id)

        for upload in uploads:
            if upload.get("fileName") == filename:
                cid = upload.get("cid")
                if not cid:
                    continue
                raw = download_from_ipfs(cid)
                if raw:
                    return json.loads(raw.decode("utf-8"))
        return None
    except Exception as e:
        logger.error(f"Canary search failed for {principal_id[:20]}: {e}")
        return None


@passphrase_bp.route("/api/passphrase/setup", methods=["POST"])
@require_auth
def setup_passphrase():
    """First-time passphrase setup. Creates and uploads canary blob."""
    principal = request.principal
    data = request.get_json()

    if not data or not data.get("passphrase"):
        return jsonify({"success": False, "error": "Passphrase required"}), 400

    passphrase = data["passphrase"]

    if len(passphrase) < 8:
        return jsonify({"success": False, "error": "Passphrase must be at least 8 characters"}), 400

    # Check if canary already exists
    existing = _find_canary_on_ipfs(principal)
    if existing:
        return jsonify({"success": False, "error": "Passphrase already set. Use /api/passphrase/change to update."}), 409

    # Create and upload canary
    canary = EncryptionUtils.create_passphrase_canary(passphrase)
    canary_data = json.dumps(canary).encode("utf-8")
    filename = _canary_filename(principal)
    cid = upload_to_ipfs(canary_data, filename, principal_id=principal)

    if not cid:
        # Degraded mode: Lighthouse unavailable/quota exceeded.
        # Keep the user unblocked for this server session even if canary persistence failed.
        set_session_passphrase(principal, passphrase)
        logger.warning(
            "Passphrase canary upload failed for %s; continuing in local-session-only mode",
            principal[:20],
        )
        return jsonify({
            "success": True,
            "canary_cid": None,
            "storage": "local_session_only",
            "warning": "IPFS unavailable. Passphrase is unlocked for this server session only.",
        })

    # Store passphrase in session
    set_session_passphrase(principal, passphrase)

    logger.info(f"Passphrase setup complete for {principal[:20]}, canary CID: {cid[:16]}")
    return jsonify({"success": True, "canary_cid": cid})


@passphrase_bp.route("/api/passphrase/unlock", methods=["POST"])
@require_auth
@rate_limit
def unlock_passphrase():
    """Unlock session with passphrase. Verifies against stored canary."""
    principal = request.principal
    data = request.get_json()

    if not data or not data.get("passphrase"):
        return jsonify({"success": False, "error": "Passphrase required"}), 400

    passphrase = data["passphrase"]

    # Already unlocked?
    if has_passphrase(principal):
        return jsonify({"success": True, "message": "Already unlocked"})

    # Find canary on IPFS
    canary = _find_canary_on_ipfs(principal)
    if not canary:
        return jsonify({"success": False, "error": "No passphrase configured. Use /api/passphrase/setup first."}), 404

    # Verify passphrase
    if not EncryptionUtils.verify_passphrase_canary(canary, passphrase):
        logger.warning(f"Bad passphrase attempt for {principal[:20]}")
        return jsonify({"success": False, "error": "Incorrect passphrase"}), 403

    # Store in session
    set_session_passphrase(principal, passphrase)

    # Kick off canonical state checkpoint restore in background.
    # Runtime source of truth remains local state.db; IPFS is checkpoint/archive.
    def _restore_checkpoint_async():
        try:
            from services.state_checkpoint import restore_state_checkpoint_from_ipfs

            restore_state_checkpoint_from_ipfs(principal)
        except Exception as e:
            logger.debug("Checkpoint restore skipped for %s: %s", principal[:20], e)

    threading.Thread(
        target=_restore_checkpoint_async,
        daemon=True,
        name=f"state-restore-{principal[:12]}",
    ).start()

    logger.info(f"Passphrase unlocked for {principal[:20]}")
    return jsonify({"success": True})


@passphrase_bp.route("/api/passphrase/change", methods=["POST"])
@require_auth
def change_passphrase():
    """Change passphrase. Re-encrypts canary with new passphrase."""
    principal = request.principal
    data = request.get_json()

    if not data or not data.get("old_passphrase") or not data.get("new_passphrase"):
        return jsonify({"success": False, "error": "old_passphrase and new_passphrase required"}), 400

    old_passphrase = data["old_passphrase"]
    new_passphrase = data["new_passphrase"]

    if len(new_passphrase) < 8:
        return jsonify({"success": False, "error": "New passphrase must be at least 8 characters"}), 400

    # Verify old passphrase
    canary = _find_canary_on_ipfs(principal)
    if not canary:
        return jsonify({"success": False, "error": "No passphrase configured"}), 404

    if not EncryptionUtils.verify_passphrase_canary(canary, old_passphrase):
        return jsonify({"success": False, "error": "Incorrect old passphrase"}), 403

    # Create new canary with new passphrase
    new_canary = EncryptionUtils.create_passphrase_canary(new_passphrase)
    canary_data = json.dumps(new_canary).encode("utf-8")
    filename = _canary_filename(principal)
    cid = upload_to_ipfs(canary_data, filename, principal_id=principal)

    if not cid:
        # Degraded mode mirrors setup(): do not brick active users when IPFS is down.
        set_session_passphrase(principal, new_passphrase)
        logger.warning(
            "Passphrase re-encryption upload failed for %s; updated session only",
            principal[:20],
        )
        return jsonify({
            "success": True,
            "canary_cid": None,
            "storage": "local_session_only",
            "warning": "IPFS unavailable. New passphrase is active for this server session only.",
        })

    # Update session
    set_session_passphrase(principal, new_passphrase)

    # TODO (Milestone 1 Step 6): Trigger background re-encryption of all IPFS artifacts
    logger.info(f"Passphrase changed for {principal[:20]}, new canary CID: {cid[:16]}")
    return jsonify({"success": True, "canary_cid": cid})


@passphrase_bp.route("/api/passphrase/lock", methods=["POST"])
@require_auth
def lock_passphrase():
    """Clear passphrase from session (logout)."""
    principal = request.principal
    clear_session(principal)
    logger.info(f"Session locked for {principal[:20]}")
    return jsonify({"success": True})


@passphrase_bp.route("/api/passphrase/status", methods=["GET"])
@require_auth
def passphrase_status():
    """Check if user has a passphrase configured and if session is unlocked."""
    principal = request.principal

    canary = _find_canary_on_ipfs(principal)

    return jsonify({
        "success": True,
        "has_passphrase": canary is not None,
        "session_unlocked": has_passphrase(principal),
    })
