"""
Canonical state DB checkpoint/archive service.

Runtime source of truth is local per-principal `state.db`.
IPFS is checkpoint/archive only.
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

from config import CHATS_DIR, PRINCIPAL_DISPLAY_LENGTH
from encryption import EncryptionUtils
from lighthouse import download_from_ipfs, get_lighthouse_uploads, upload_to_ipfs
from services.session_manager import get_session_passphrase
from services.state_store import get_state_store

logger = logging.getLogger(__name__)


def _state_checkpoint_filename(principal_id: str) -> str:
    return f"{principal_id[:PRINCIPAL_DISPLAY_LENGTH]}_state_checkpoint.json"


def _encrypt_for_user(data: dict, principal_id: str) -> dict:
    passphrase = get_session_passphrase(principal_id)
    if passphrase:
        return EncryptionUtils.encrypt_with_passphrase(data, passphrase)
    return EncryptionUtils.encrypt_chat(data, principal_id)


def _decrypt_for_user(encrypted: dict, principal_id: str) -> dict:
    passphrase = get_session_passphrase(principal_id)
    return EncryptionUtils.decrypt_auto(
        encrypted,
        passphrase=passphrase,
        principal_id=principal_id,
    )


def sync_state_checkpoint_to_ipfs(principal_id: str) -> Optional[str]:
    """Upload encrypted canonical state.db checkpoint to IPFS."""
    try:
        store = get_state_store(principal_id)
        db_bytes = store.export_db_bytes()
        if not db_bytes:
            return None

        payload = {
            "type": "state_db",
            "updatedAt": int(time.time() * 1000),
            "db_b64": base64.b64encode(db_bytes).decode("utf-8"),
        }
        encrypted = _encrypt_for_user(payload, principal_id)
        cid = upload_to_ipfs(
            json.dumps(encrypted).encode("utf-8"),
            _state_checkpoint_filename(principal_id),
            principal_id=principal_id,
            is_master_bundle=True,
        )
        if not cid:
            return None

        store.set_sync_checkpoint(
            last_ipfs_cid=cid,
            last_synced_message_id=store.get_latest_message_id(),
            last_sync_at=int(time.time() * 1000),
        )
        logger.info("💽 Canonical state checkpoint synced: %s -> %s", principal_id[:16], cid[:16])
        return cid
    except Exception as e:
        logger.error("❌ Canonical state checkpoint sync failed for %s: %s", principal_id[:16], e)
        return None


def restore_state_checkpoint_from_ipfs(principal_id: str) -> bool:
    """
    Restore canonical state.db from latest valid IPFS checkpoint.

    Safety: validates checkpoint DB schema before import and skips invalid blobs.
    """
    filename = _state_checkpoint_filename(principal_id)
    uploads = get_lighthouse_uploads(principal_id)
    candidates = [u for u in uploads if u.get("fileName") == filename and u.get("cid")]
    if not candidates:
        return False

    store = get_state_store(principal_id)

    for upload in candidates:
        cid = upload.get("cid")
        try:
            raw = download_from_ipfs(cid)
            if not raw:
                continue

            encrypted = json.loads(raw.decode("utf-8"))
            payload = _decrypt_for_user(encrypted, principal_id)
            if payload.get("type") != "state_db":
                logger.warning(
                    "Skipping checkpoint %s for %s: unexpected payload type=%s",
                    str(cid)[:16],
                    principal_id[:16],
                    payload.get("type"),
                )
                continue

            db_b64 = payload.get("db_b64")
            if not db_b64:
                logger.warning(
                    "Skipping checkpoint %s for %s: missing db_b64",
                    str(cid)[:16],
                    principal_id[:16],
                )
                continue

            db_bytes = base64.b64decode(db_b64)
            store.import_db_bytes(db_bytes)
            store.set_sync_checkpoint(
                last_ipfs_cid=cid,
                last_synced_message_id=store.get_latest_message_id(),
                last_sync_at=int(time.time() * 1000),
            )
            logger.info("✅ Canonical state checkpoint restored for %s from %s", principal_id[:16], str(cid)[:16])
            return True
        except Exception as e:
            logger.warning(
                "⚠️ Skipping invalid state checkpoint %s for %s: %s",
                str(cid)[:16],
                principal_id[:16],
                e,
            )

    return False


def checkpoint_all_state_stores(max_users: int = 100):
    """Best-effort periodic checkpoint for all principals with canonical state DBs."""
    root = Path(CHATS_DIR)
    if not root.exists():
        return

    processed = 0
    for child in root.iterdir():
        if processed >= max_users:
            break
        if not child.is_dir():
            continue
        principal_id = child.name
        if not (child / "state.db").exists():
            continue
        try:
            sync_state_checkpoint_to_ipfs(principal_id)
            processed += 1
        except Exception as e:
            logger.debug("state checkpoint skip for %s: %s", principal_id[:16], e)
