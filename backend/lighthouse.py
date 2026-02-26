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
