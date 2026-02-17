"""
Trinity Backend - IPFS Storage Module
IPFS pinning via Lighthouse (plan-dependent quotas)

v4.0: Added vector database sync for persistence across Akash redeployments
v4.1: Migrated to pooled http_session with retry adapter; added timing instrumentation
"""

import logging
import time
from typing import Optional

from config import (
    LIGHTHOUSE_API,
    LIGHTHOUSE_API_KEY,
    LIGHTHOUSE_GATEWAY,
    LIGHTHOUSE_NODE,
    http_session,
)

logger = logging.getLogger(__name__)

_LIST_MAX_PAGES = 200


def _created_at_key(upload: dict) -> int:
    """Normalize createdAt values for stable sorting."""
    try:
        return int(upload.get("createdAt", 0) or 0)
    except (TypeError, ValueError):
        return 0


def upload_to_ipfs(
    file_data: bytes, filename: str, principal_id: str = None, is_master_bundle: bool = False
) -> Optional[str]:
    """
    Upload file to IPFS via Lighthouse.

    Content is available immediately via IPFS gateways.

    Args:
        file_data: The encrypted data to upload
        filename: Name for the file (used for tracking)
        principal_id: User's principal ID (for logging)
        is_master_bundle: If True, marks this as the user's master bundle

    Returns:
        CID string on success, None on failure
    """
    if not LIGHTHOUSE_API_KEY:
        logger.warning("Lighthouse API key not configured - skipping archive")
        return None

    t0 = time.monotonic()
    try:
        endpoint = f"{LIGHTHOUSE_NODE}/api/v0/add"

        headers = {"Authorization": f"Bearer {LIGHTHOUSE_API_KEY}"}

        files = {"file": (filename, file_data, "application/json")}

        logger.info(f"📤 Uploading to Lighthouse: {filename} ({len(file_data)} bytes)")

        response = http_session.post(endpoint, headers=headers, files=files, timeout=60)

        elapsed = time.monotonic() - t0
        if response.status_code == 200:
            result = response.json()
            cid = result.get("Hash")
            size = result.get("Size", len(file_data))

            logger.info(f"✅ Uploaded to Lighthouse/IPFS: {cid} ({elapsed:.2f}s)")
            logger.info(f"   Size: {size} bytes")
            logger.info(f"   Principal: {principal_id}")
            logger.info(f"   Gateway: {LIGHTHOUSE_GATEWAY}/ipfs/{cid}")

            return cid
        else:
            logger.error(
                f"❌ Lighthouse upload failed: {response.status_code} - {response.text} ({elapsed:.2f}s)"
            )
            return None

    except Exception as e:
        elapsed = time.monotonic() - t0
        if "timeout" in str(type(e).__name__).lower() or "timeout" in str(e).lower():
            logger.error(f"❌ Lighthouse upload timed out ({elapsed:.2f}s)")
        else:
            logger.error(f"❌ Lighthouse upload error ({elapsed:.2f}s): {e}", exc_info=True)
        return None


def get_lighthouse_uploads(principal_id: str = None, file_type: str = None) -> list:
    """
    Get list of files uploaded to Lighthouse for this API key.

    Args:
        principal_id: User's principal ID (for logging)
        file_type: Optional filter (not used in API, filter locally)

    Returns:
        List of upload records sorted by upload time (newest first)
    """
    if not LIGHTHOUSE_API_KEY:
        logger.warning("Lighthouse API key not configured")
        return []

    t0 = time.monotonic()
    try:
        headers = {"Authorization": f"Bearer {LIGHTHOUSE_API_KEY}"}
        url = f"{LIGHTHOUSE_API}/api/user/files_uploaded"
        files = []
        last_key = None

        for page_idx in range(_LIST_MAX_PAGES):
            params = {}
            if last_key:
                params["lastKey"] = last_key

            response = http_session.get(url, headers=headers, params=params, timeout=30)

            if response.status_code != 200:
                elapsed = time.monotonic() - t0
                logger.error(
                    f"Lighthouse listing failed: {response.status_code} - {response.text} ({elapsed:.2f}s)"
                )
                return []

            result = response.json() or {}
            page_files = result.get("fileList", []) or []
            files.extend(page_files)

            next_key = result.get("lastKey")
            if not page_files or not next_key or next_key == last_key:
                break
            last_key = next_key

            if page_idx == _LIST_MAX_PAGES - 1:
                logger.warning("Reached Lighthouse listing page cap (%s pages)", _LIST_MAX_PAGES)

        elapsed = time.monotonic() - t0
        files.sort(key=_created_at_key, reverse=True)

        logger.info(f"📦 Found {len(files)} files in Lighthouse storage ({elapsed:.2f}s)")
        return files

    except Exception as e:
        elapsed = time.monotonic() - t0
        if "timeout" in str(type(e).__name__).lower() or "timeout" in str(e).lower():
            logger.error(f"Lighthouse listing timed out ({elapsed:.2f}s)")
        else:
            logger.error(f"Lighthouse listing error ({elapsed:.2f}s): {e}", exc_info=True)
        return []


def download_from_ipfs(cid: str) -> Optional[bytes]:
    """
    Download file from IPFS via multiple gateways for redundancy.

    Tries Lighthouse gateway first since we upload there, then falls back
    to other public IPFS gateways for redundancy.
    """
    if not cid:
        return None

    t0 = time.monotonic()
    try:
        gateways = [
            f"{LIGHTHOUSE_GATEWAY}/ipfs/{cid}",
            f"https://ipfs.io/ipfs/{cid}",
            f"https://dweb.link/ipfs/{cid}",
            f"https://cloudflare-ipfs.com/ipfs/{cid}",
        ]

        for idx, gateway in enumerate(gateways):
            gw_t0 = time.monotonic()
            try:
                logger.info(f"Attempting download from: {gateway}")
                response = http_session.get(gateway, timeout=30)

                gw_elapsed = time.monotonic() - gw_t0
                if response.status_code == 200:
                    total_elapsed = time.monotonic() - t0
                    logger.info(
                        f"✅ File downloaded from IPFS: {cid} "
                        f"(gateway {idx + 1}/{len(gateways)}, {gw_elapsed:.2f}s, total {total_elapsed:.2f}s)"
                    )
                    return response.content
                else:
                    logger.warning(
                        f"Gateway {gateway} returned {response.status_code} ({gw_elapsed:.2f}s)"
                    )
            except Exception as gw_e:
                gw_elapsed = time.monotonic() - gw_t0
                if "timeout" in str(type(gw_e).__name__).lower() or "timeout" in str(gw_e).lower():
                    logger.warning(f"Gateway {gateway} timed out ({gw_elapsed:.2f}s)")
                else:
                    logger.warning(f"Gateway {gateway} error ({gw_elapsed:.2f}s): {gw_e}")
                continue

        total_elapsed = time.monotonic() - t0
        logger.error(f"❌ All gateways failed for CID: {cid} ({total_elapsed:.2f}s)")
        return None
    except Exception as e:
        total_elapsed = time.monotonic() - t0
        logger.error(f"❌ IPFS download error ({total_elapsed:.2f}s): {e}", exc_info=True)
        return None


# ============================================================================
# VECTOR DATABASE SYNC (v4.0)
# ============================================================================


def upload_vector_db(principal_id: str) -> Optional[str]:
    """
    Upload user's vector database to IPFS for persistence.

    Called after significant updates to ensure vectors survive
    Akash redeployments.

    Args:
        principal_id: User's principal ID

    Returns:
        CID of uploaded database, or None on failure
    """
    try:
        from services.vector_store import get_vector_store

        store = get_vector_store(principal_id)
        db_data = store.export_for_ipfs()

        if not db_data:
            logger.warning(f"No vector data to upload for {principal_id}")
            return None

        filename = f"{principal_id}_vectors.db"
        cid = upload_to_ipfs(db_data, filename, principal_id)

        if cid:
            logger.info(f"📦 Vector DB uploaded: {cid} ({len(db_data)} bytes)")

        return cid

    except ImportError:
        logger.warning("Vector store not available")
        return None
    except Exception as e:
        logger.error(f"❌ Vector DB upload failed: {e}")
        return None


def download_vector_db(principal_id: str, cid: str) -> bool:
    """
    Download and restore user's vector database from IPFS.

    Called on user login to restore vectors after Akash redeployment.

    Args:
        principal_id: User's principal ID
        cid: IPFS CID of the vector database

    Returns:
        True on success
    """
    try:
        from services.vector_store import get_vector_store

        db_data = download_from_ipfs(cid)

        if not db_data:
            logger.error(f"Failed to download vector DB: {cid}")
            return False

        store = get_vector_store(principal_id)
        success = store.import_from_ipfs(db_data)

        if success:
            logger.info(f"✅ Vector DB restored from IPFS: {cid}")

        return success

    except ImportError:
        logger.warning("Vector store not available")
        return False
    except Exception as e:
        logger.error(f"❌ Vector DB download failed: {e}")
        return False


def get_user_vector_cid(principal_id: str) -> Optional[str]:
    """
    Get the latest vector DB CID for a user from Lighthouse.

    Searches uploads for the most recent vectors.db file.

    Args:
        principal_id: User's principal ID

    Returns:
        CID if found, None otherwise
    """
    try:
        uploads = get_lighthouse_uploads(principal_id)

        # Look for vector DB files
        vector_filename = f"{principal_id}_vectors.db"
        for upload in uploads:
            if upload.get("fileName") == vector_filename:
                return upload.get("cid")

        return None

    except Exception as e:
        logger.error(f"❌ Error finding vector CID: {e}")
        return None


def sync_vector_db_on_login(principal_id: str) -> bool:
    """
    Sync vector database on user login.

    Checks if local DB exists, if not, tries to restore from IPFS.

    Args:
        principal_id: User's principal ID

    Returns:
        True if DB is available (local or restored)
    """
    try:
        from pathlib import Path

        from config import CHATS_DIR

        # Check if local DB exists
        local_db = Path(CHATS_DIR) / principal_id / "vectors.db"

        if local_db.exists() and local_db.stat().st_size > 0:
            logger.info(f"📦 Local vector DB exists for {principal_id}")
            return True

        # Try to restore from IPFS
        cid = get_user_vector_cid(principal_id)
        if cid:
            logger.info(f"🔄 Restoring vector DB from IPFS: {cid}")
            return download_vector_db(principal_id, cid)

        # No local or remote DB - user is new or has no vectors
        logger.info(f"📦 No vector DB found for {principal_id} - will create on first use")
        return True

    except Exception as e:
        logger.error(f"❌ Vector DB sync failed: {e}")
        return False
