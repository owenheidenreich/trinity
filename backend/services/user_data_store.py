"""
Trinity Backend - Checkpoint / Archive Data Store
=================================================

Runtime source of truth is canonical per-principal `state.db`.
This module provides checkpoint/archive services to IPFS, plus
legacy compatibility helpers while old artifacts are phased out.
"""

import json
import logging
import threading
import time
import hashlib
import base64
from pathlib import Path
from typing import Dict, List, Optional

from config import (
    CHAT_CHECKPOINT_DEBOUNCE_SECONDS,
    CHAT_CHECKPOINT_MAX_WAIT_SECONDS,
    CHATS_DIR,
    PRINCIPAL_DISPLAY_LENGTH,
)
from encryption import EncryptionUtils
from lighthouse import (
    download_from_ipfs,
    get_lighthouse_uploads,
    upload_to_ipfs,
)
from services.session_manager import get_session_passphrase

logger = logging.getLogger(__name__)


def encrypt_for_user(data: dict, principal_id: str) -> dict:
    """Encrypt data using passphrase if available, else fall back to principal-based."""
    passphrase = get_session_passphrase(principal_id)
    if passphrase:
        return EncryptionUtils.encrypt_with_passphrase(data, passphrase)
    return EncryptionUtils.encrypt_chat(data, principal_id)


def decrypt_for_user(encrypted: dict, principal_id: str) -> dict:
    """Decrypt data. Tries passphrase for v2.0 data, falls back to principal-based."""
    passphrase = get_session_passphrase(principal_id)
    return EncryptionUtils.decrypt_auto(encrypted, passphrase=passphrase, principal_id=principal_id)

# Track which principals have been restored this session
_restored_principals: set = set()
_restore_lock = threading.Lock()
_restore_inflight: set = set()

# Debounce state for vector DB uploads
_vector_sync_counters: Dict[str, int] = {}
_vector_sync_timestamps: Dict[str, float] = {}
VECTOR_SYNC_INTERVAL = 60  # seconds between auto-syncs
VECTOR_SYNC_MESSAGE_THRESHOLD = 10  # messages indexed before auto-sync

# Debounce state for profile uploads
_profile_sync_timers: Dict[str, threading.Timer] = {}
_profile_sync_latest: Dict[str, Dict] = {}
_profile_sync_lock = threading.Lock()
PROFILE_SYNC_DEBOUNCE_SECONDS = 15

# Debounce state for graph uploads
_graph_sync_timers: Dict[str, threading.Timer] = {}
_graph_sync_lock = threading.Lock()
GRAPH_SYNC_DEBOUNCE_SECONDS = 30

# Debounce state for chat manifest uploads
_manifest_sync_timers: Dict[str, threading.Timer] = {}
_manifest_sync_latest: Dict[str, Dict] = {}
_manifest_sync_lock = threading.Lock()
MANIFEST_SYNC_DEBOUNCE_SECONDS = 5

# Debounce state for chat blob uploads
_chat_sync_timers: Dict[tuple, threading.Timer] = {}
_chat_sync_latest: Dict[tuple, Dict] = {}
_chat_sync_started_at: Dict[tuple, float] = {}
_chat_sync_lock = threading.Lock()

# =============================================================================
# RETRY LOGIC — at-least-once IPFS delivery
# =============================================================================

# Pending syncs: {(principal_id, artifact_type): {data for retry}}
_pending_syncs: Dict[tuple, Dict] = {}
_pending_syncs_lock = threading.Lock()
_pending_retry_inflight: set = set()
_pending_retry_lock = threading.Lock()

# Sync status tracking per principal
_sync_status: Dict[str, Dict] = {}
_sync_status_lock = threading.Lock()

# Retry configuration
IPFS_RETRY_ATTEMPTS = 3
IPFS_RETRY_DELAYS = [1, 4, 16]  # seconds — exponential backoff

# Content-hash dedupe cache for IPFS uploads.
_upload_dedupe: Dict[tuple, str] = {}
_upload_latest: Dict[tuple, Dict] = {}
_upload_dedupe_lock = threading.Lock()


def _upload_with_retry(file_data: bytes, filename: str, principal_id: str = None,
                       is_master_bundle: bool = False) -> Optional[str]:
    """
    Upload to IPFS with exponential-backoff retry.
    Returns CID on success, None on failure after all retries.
    """
    digest = hashlib.sha256(file_data).hexdigest()
    if principal_id:
        file_key = (principal_id, filename)
        dedupe_key = (principal_id, filename, digest)
        with _upload_dedupe_lock:
            cached_cid = _upload_dedupe.get(dedupe_key)
            latest = _upload_latest.get(file_key)
        if cached_cid:
            logger.debug("♻️ IPFS dedupe hit for %s", filename)
            return cached_cid
        if latest and latest.get("hash") == digest and latest.get("cid"):
            logger.debug("♻️ IPFS unchanged payload for %s", filename)
            return latest["cid"]

    last_error = None
    for attempt in range(IPFS_RETRY_ATTEMPTS):
        try:
            cid = upload_to_ipfs(file_data, filename, principal_id=principal_id,
                                 is_master_bundle=is_master_bundle)
            if cid:
                if principal_id:
                    with _upload_dedupe_lock:
                        _upload_dedupe[(principal_id, filename, digest)] = cid
                        _upload_latest[(principal_id, filename)] = {
                            "hash": digest,
                            "cid": cid,
                            "updated_at": int(time.time() * 1000),
                        }
                try:
                    from services.slo_metrics import record_ipfs_write

                    if principal_id:
                        record_ipfs_write(principal_id)
                except Exception:
                    pass
                return cid
            last_error = "upload_to_ipfs returned None"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"⚠️ IPFS upload attempt {attempt + 1}/{IPFS_RETRY_ATTEMPTS} failed: {e}")

        if attempt < IPFS_RETRY_ATTEMPTS - 1:
            delay = IPFS_RETRY_DELAYS[attempt]
            logger.info(f"⏳ Retrying IPFS upload in {delay}s...")
            time.sleep(delay)

    logger.error(f"❌ IPFS upload failed after {IPFS_RETRY_ATTEMPTS} attempts: {last_error}")
    return None


def _record_sync_status(principal_id: str, artifact_type: str, success: bool,
                        cid: str = None, error: str = None):
    """Record sync status for monitoring endpoint."""
    with _sync_status_lock:
        if principal_id not in _sync_status:
            _sync_status[principal_id] = {}
        _sync_status[principal_id][artifact_type] = {
            "lastAttempt": int(time.time() * 1000),
            "success": success,
            "cid": cid,
            "error": error,
        }
        if success:
            _sync_status[principal_id][f"{artifact_type}_lastSuccess"] = int(time.time() * 1000)


def _add_pending_sync(principal_id: str, artifact_type: str, sync_func, sync_args: tuple):
    """Queue a failed sync for retry on next user request."""
    with _pending_syncs_lock:
        key = (principal_id, artifact_type)
        _pending_syncs[key] = {
            "func": sync_func,
            "args": sync_args,
            "failed_at": int(time.time() * 1000),
        }
        logger.info(f"📋 Queued pending sync: {artifact_type} for {principal_id[:16]}")


def retry_pending_syncs(principal_id: str):
    """Retry any pending syncs for this principal. Called on each request."""
    with _pending_syncs_lock:
        keys_to_retry = [k for k in _pending_syncs if k[0] == principal_id]

    for key in keys_to_retry:
        with _pending_syncs_lock:
            pending = _pending_syncs.pop(key, None)
        if pending:
            artifact_type = key[1]
            logger.info(f"🔄 Retrying pending {artifact_type} sync for {principal_id[:16]}...")
            try:
                pending["func"](*pending["args"])
            except Exception as e:
                logger.warning(f"⚠️ Pending sync retry failed for {artifact_type}: {e}")
                # Re-queue if still failing
                _add_pending_sync(principal_id, artifact_type, pending["func"], pending["args"])


def _retry_pending_syncs_async(principal_id: str):
    """Run pending-sync retries in background so request latency stays predictable."""
    with _pending_retry_lock:
        if principal_id in _pending_retry_inflight:
            return
        _pending_retry_inflight.add(principal_id)

    def _run():
        try:
            retry_pending_syncs(principal_id)
        finally:
            with _pending_retry_lock:
                _pending_retry_inflight.discard(principal_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def get_all_sync_status() -> Dict:
    """Return sync status for all users (for admin endpoint)."""
    with _sync_status_lock:
        return dict(_sync_status)

def get_pending_sync_count() -> int:
    """Return number of pending syncs."""
    with _chat_sync_lock:
        queued_chat_checkpoints = len(_chat_sync_latest)
    with _pending_syncs_lock:
        return len(_pending_syncs) + queued_chat_checkpoints


# =============================================================================
# USER MANIFEST
# =============================================================================

def _default_manifest(principal_id: str) -> Dict:
    """Return an empty user manifest."""
    return {
        "version": 2,
        "manifestVersion": 1,
        "currentManifestCid": None,
        "manifestHistory": [],
        "principal": principal_id,
        "profile": {
            "cid": None,
            "lastUpdated": None,
            "factCount": 0,
        },
        "memoryIndex": {
            "cid": None,
            "lastUpdated": None,
            "messageCount": 0,
        },
        "graphIndex": {
            "cid": None,
            "lastUpdated": None,
            "tripleCount": 0,
        },
        "chats": [],
        "totalBytes": 0,
        "createdAt": int(time.time() * 1000),
        "lastUpdated": int(time.time() * 1000),
    }


def _get_manifest_path(principal_id: str) -> Path:
    """Get local cache path for user manifest."""
    from storage import get_user_dir
    return get_user_dir(principal_id) / "manifest.json"


def _manifest_filename(principal_id: str) -> str:
    """IPFS filename for the user manifest."""
    return f"{principal_id[:PRINCIPAL_DISPLAY_LENGTH]}_manifest.json"


def load_manifest(principal_id: str) -> Dict:
    """Load user manifest from local cache."""
    path = _get_manifest_path(principal_id)
    if path.exists():
        try:
            with open(path, "r") as f:
                encrypted = json.load(f)
            if isinstance(encrypted, dict) and "encryption" in encrypted:
                return decrypt_for_user(encrypted, principal_id)
            # Legacy unencrypted — return as-is
            return encrypted
        except Exception as e:
            logger.error(f"Failed to load manifest for {principal_id[:20]}: {e}")
    return _default_manifest(principal_id)


def save_manifest(principal_id: str, manifest: Dict):
    """Save user manifest to local cache (encrypted)."""
    manifest["lastUpdated"] = int(time.time() * 1000)
    encrypted = encrypt_for_user(manifest, principal_id)
    path = _get_manifest_path(principal_id)
    with open(path, "w") as f:
        json.dump(encrypted, f)


def sync_manifest_to_ipfs(principal_id: str, manifest: Dict) -> Optional[str]:
    """Encrypt and upload manifest to IPFS with retry. Returns CID or None."""
    try:
        previous_cid = manifest.get("currentManifestCid")
        previous_version = int(manifest.get("manifestVersion", 1))
        encrypted = encrypt_for_user(manifest, principal_id)
        data = json.dumps(encrypted).encode("utf-8")
        filename = _manifest_filename(principal_id)
        cid = _upload_with_retry(data, filename, principal_id=principal_id, is_master_bundle=True)
        if cid:
            if previous_cid and previous_cid != cid:
                history = manifest.get("manifestHistory", [])
                history.append({
                    "version": previous_version,
                    "cid": previous_cid,
                    "updatedAt": int(time.time() * 1000),
                })
                manifest["manifestHistory"] = history[-20:]
            manifest["currentManifestCid"] = cid
            manifest["manifestVersion"] = previous_version + 1
            save_manifest(principal_id, manifest)
            logger.info(f"📋 Manifest synced to IPFS: {cid[:16]}...")
            _record_sync_status(principal_id, "manifest", True, cid=cid)
        else:
            _record_sync_status(principal_id, "manifest", False, error="upload returned None")
            _add_pending_sync(principal_id, "manifest", sync_manifest_to_ipfs, (principal_id, manifest))
        return cid
    except Exception as e:
        logger.error(f"❌ Manifest IPFS sync failed: {e}")
        _record_sync_status(principal_id, "manifest", False, error=str(e))
        _add_pending_sync(principal_id, "manifest", sync_manifest_to_ipfs, (principal_id, manifest))
        return None


def find_manifest_on_ipfs(principal_id: str) -> Optional[Dict]:
    """
    Search Lighthouse uploads for the user's latest manifest.
    Download, decrypt, and return it. Returns None if not found.
    """
    try:
        filename = _manifest_filename(principal_id)
        uploads = get_lighthouse_uploads(principal_id)

        for upload in uploads:
            if upload.get("fileName") == filename:
                cid = upload.get("cid")
                if not cid:
                    continue
                raw = download_from_ipfs(cid)
                if raw:
                    encrypted = json.loads(raw.decode("utf-8"))
                    return decrypt_for_user(encrypted, principal_id)

        return None
    except Exception as e:
        logger.error(f"❌ Manifest search failed for {principal_id[:20]}: {e}")
        return None


def rollback_manifest(principal_id: str, target_version: Optional[int] = None) -> bool:
    """
    Roll back local manifest to a previous manifest CID checkpoint.

    Args:
        principal_id: User principal.
        target_version: Optional target manifestVersion from history.

    Returns:
        True on successful rollback.
    """
    manifest = load_manifest(principal_id)
    history = manifest.get("manifestHistory", [])
    if not history:
        return False

    target = None
    if target_version is None:
        target = history[-1]
    else:
        for entry in reversed(history):
            if int(entry.get("version", -1)) == int(target_version):
                target = entry
                break
    if not target:
        return False

    cid = target.get("cid")
    if not cid:
        return False

    raw = download_from_ipfs(cid)
    if not raw:
        return False

    try:
        encrypted = json.loads(raw.decode("utf-8"))
        restored = decrypt_for_user(encrypted, principal_id)
        save_manifest(principal_id, restored)
        return True
    except Exception as e:
        logger.error(f"❌ Manifest rollback failed for {principal_id[:20]}: {e}")
        return False


# =============================================================================
# PROFILE (USER MEMORY) SYNC
# =============================================================================

def _profile_filename(principal_id: str) -> str:
    """IPFS filename for user profile."""
    return f"{principal_id[:PRINCIPAL_DISPLAY_LENGTH]}_profile.json"


def sync_profile_to_ipfs(principal_id: str, memory: Dict = None) -> Optional[str]:
    """
    Encrypt user profile and upload to IPFS.
    Updates manifest with new CID.

    Args:
        principal_id: User principal
        memory: Profile dict (loads from disk if not provided)

    Returns:
        CID on success, None on failure
    """
    try:
        if memory is None:
            from storage import load_user_memory
            memory = load_user_memory(principal_id)

        # Encrypt and upload with retry
        encrypted = encrypt_for_user(memory, principal_id)
        data = json.dumps(encrypted).encode("utf-8")
        filename = _profile_filename(principal_id)
        cid = _upload_with_retry(data, filename, principal_id=principal_id)

        if not cid:
            logger.error(f"❌ Profile IPFS upload failed for {principal_id[:20]}")
            _record_sync_status(principal_id, "profile", False, error="upload returned None")
            _add_pending_sync(principal_id, "profile", sync_profile_to_ipfs, (principal_id, memory))
            return None

        logger.info(f"👤 Profile synced to IPFS: {cid[:16]}... ({len(memory.get('facts', []))} facts)")
        _record_sync_status(principal_id, "profile", True, cid=cid)

        # Update manifest
        manifest = load_manifest(principal_id)
        old_cid = manifest["profile"].get("cid")
        manifest["profile"]["cid"] = cid
        manifest["profile"]["lastUpdated"] = int(time.time() * 1000)
        manifest["profile"]["factCount"] = len(memory.get("facts", []))
        save_manifest(principal_id, manifest)
        sync_manifest_to_ipfs(principal_id, manifest)

        # Unpin old profile CID
        if old_cid and old_cid != cid:
            unpin_cid(old_cid)

        return cid

    except Exception as e:
        logger.error(f"❌ Profile sync failed: {e}", exc_info=True)
        _record_sync_status(principal_id, "profile", False, error=str(e))
        _add_pending_sync(principal_id, "profile", sync_profile_to_ipfs, (principal_id, memory))
        return None


def restore_profile_from_ipfs(principal_id: str, manifest: Dict = None) -> bool:
    """
    Restore user profile from IPFS if not present locally.

    Args:
        principal_id: User principal
        manifest: Pre-loaded manifest (loads if not provided)

    Returns:
        True if profile is available (local or restored)
    """
    from storage import get_user_memory_path, save_user_memory

    local_path = get_user_memory_path(principal_id)
    if local_path.exists():
        return True

    try:
        if manifest is None:
            manifest = load_manifest(principal_id)

        profile_cid = manifest.get("profile", {}).get("cid")
        if not profile_cid:
            logger.info(f"No profile CID in manifest for {principal_id[:20]} — new user")
            return True

        raw = download_from_ipfs(profile_cid)
        if not raw:
            logger.error(f"❌ Failed to download profile from IPFS: {profile_cid}")
            return False

        encrypted = json.loads(raw.decode("utf-8"))
        memory = decrypt_for_user(encrypted, principal_id)
        save_user_memory(principal_id, memory)

        fact_count = len(memory.get("facts", []))
        logger.info(f"✅ Profile restored from IPFS: {fact_count} facts for {principal_id[:20]}")
        return True

    except Exception as e:
        logger.error(f"❌ Profile restore failed: {e}", exc_info=True)
        return False


# =============================================================================
# VECTOR DB (MEMORY INDEX) SYNC
# =============================================================================

def _vector_filename(principal_id: str) -> str:
    """IPFS filename for encrypted vector DB."""
    return f"{principal_id[:PRINCIPAL_DISPLAY_LENGTH]}_vectors_enc.db"


def sync_vector_db_to_ipfs(principal_id: str) -> Optional[str]:
    """
    Export, encrypt, and upload the vector database to IPFS.
    Updates manifest with new CID.

    Returns:
        CID on success, None on failure
    """
    try:
        from services.vector_store import get_vector_store

        store = get_vector_store(principal_id)
        db_data = store.export_for_ipfs()

        if not db_data:
            logger.warning(f"No vector data to upload for {principal_id[:20]}")
            return None

        # Encrypt the raw SQLite bytes
        # We wrap in a dict for EncryptionUtils compatibility
        import base64
        wrapper = {"type": "vector_db", "data": base64.b64encode(db_data).decode("utf-8")}
        encrypted = encrypt_for_user(wrapper, principal_id)
        data = json.dumps(encrypted).encode("utf-8")

        filename = _vector_filename(principal_id)
        cid = _upload_with_retry(data, filename, principal_id=principal_id)

        if not cid:
            logger.error(f"❌ Vector DB IPFS upload failed for {principal_id[:20]}")
            _record_sync_status(principal_id, "vectorDb", False, error="upload returned None")
            _add_pending_sync(principal_id, "vectorDb", sync_vector_db_to_ipfs, (principal_id,))
            return None

        stats = store.get_stats()
        msg_count = stats.get("message_embeddings", 0)
        logger.info(f"🧠 Vector DB synced to IPFS: {cid[:16]}... ({msg_count} embeddings, {len(db_data)} bytes)")
        _record_sync_status(principal_id, "vectorDb", True, cid=cid)

        # Update manifest
        manifest = load_manifest(principal_id)
        old_cid = manifest["memoryIndex"].get("cid")
        manifest["memoryIndex"]["cid"] = cid
        manifest["memoryIndex"]["lastUpdated"] = int(time.time() * 1000)
        manifest["memoryIndex"]["messageCount"] = msg_count
        save_manifest(principal_id, manifest)
        sync_manifest_to_ipfs(principal_id, manifest)

        # Unpin old vector CID
        if old_cid and old_cid != cid:
            unpin_cid(old_cid)

        return cid

    except Exception as e:
        logger.error(f"❌ Vector DB sync failed: {e}", exc_info=True)
        _record_sync_status(principal_id, "vectorDb", False, error=str(e))
        _add_pending_sync(principal_id, "vectorDb", sync_vector_db_to_ipfs, (principal_id,))
        return None


def restore_vector_db_from_ipfs(principal_id: str, manifest: Dict = None) -> bool:
    """
    Restore vector database from IPFS if not present locally.

    Returns:
        True if vector DB is available (local or restored)
    """
    try:
        local_db = Path(CHATS_DIR) / principal_id / "vectors.db"
        if local_db.exists() and local_db.stat().st_size > 0:
            return True

        if manifest is None:
            manifest = load_manifest(principal_id)

        vector_cid = manifest.get("memoryIndex", {}).get("cid")
        if not vector_cid:
            # Try legacy unencrypted format from old lighthouse.py
            return _try_legacy_vector_restore(principal_id)

        raw = download_from_ipfs(vector_cid)
        if not raw:
            logger.error(f"❌ Failed to download vector DB from IPFS: {vector_cid}")
            return _try_legacy_vector_restore(principal_id)

        # Decrypt
        import base64
        encrypted = json.loads(raw.decode("utf-8"))
        wrapper = decrypt_for_user(encrypted, principal_id)
        db_data = base64.b64decode(wrapper["data"])

        from services.vector_store import get_vector_store
        store = get_vector_store(principal_id)
        success = store.import_from_ipfs(db_data)

        if success:
            logger.info(f"✅ Vector DB restored from IPFS (encrypted): {vector_cid[:16]}...")
        return success

    except Exception as e:
        logger.error(f"❌ Vector DB restore failed: {e}", exc_info=True)
        return _try_legacy_vector_restore(principal_id)


def _try_legacy_vector_restore(principal_id: str) -> bool:
    """
    Fallback: try restoring from the old unencrypted vector DB format
    used by the original lighthouse.py sync_vector_db_on_login().
    """
    try:
        from lighthouse import sync_vector_db_on_login
        return sync_vector_db_on_login(principal_id)
    except Exception:
        return True  # No vectors is OK for new users


# =============================================================================
# GRAPH MEMORY SYNC
# =============================================================================

def _graph_filename(principal_id: str) -> str:
    return f"{principal_id[:PRINCIPAL_DISPLAY_LENGTH]}_identity_graph.json"


def sync_graph_db_to_ipfs(principal_id: str) -> Optional[str]:
    """
    Sync graph memory artifacts (identity.kuzu + triples sidecar) to IPFS.
    """
    try:
        user_dir = Path(CHATS_DIR) / principal_id
        graph_db_path = user_dir / "identity.kuzu"
        triples_path = user_dir / "identity_triples.json"
        triples = []
        if triples_path.exists():
            try:
                with open(triples_path, "r") as f:
                    triples = json.load(f) or []
            except Exception:
                triples = []

        graph_db_bytes = b""
        if graph_db_path.exists():
            with open(graph_db_path, "rb") as f:
                graph_db_bytes = f.read()

        payload = {
            "type": "identity_graph",
            "graph_db_b64": base64.b64encode(graph_db_bytes).decode("utf-8"),
            "triples": triples,
            "updatedAt": int(time.time() * 1000),
        }
        encrypted = encrypt_for_user(payload, principal_id)
        cid = _upload_with_retry(
            json.dumps(encrypted).encode("utf-8"),
            _graph_filename(principal_id),
            principal_id=principal_id,
        )
        if not cid:
            _record_sync_status(principal_id, "graphDb", False, error="upload returned None")
            _add_pending_sync(principal_id, "graphDb", sync_graph_db_to_ipfs, (principal_id,))
            return None

        _record_sync_status(principal_id, "graphDb", True, cid=cid)
        manifest = load_manifest(principal_id)
        old_cid = manifest.get("graphIndex", {}).get("cid")
        manifest["graphIndex"]["cid"] = cid
        manifest["graphIndex"]["lastUpdated"] = int(time.time() * 1000)
        manifest["graphIndex"]["tripleCount"] = len(triples)
        save_manifest(principal_id, manifest)
        sync_manifest_to_ipfs(principal_id, manifest)
        if old_cid and old_cid != cid:
            unpin_cid(old_cid)
        return cid
    except Exception as e:
        logger.error(f"❌ Graph DB sync failed: {e}", exc_info=True)
        _record_sync_status(principal_id, "graphDb", False, error=str(e))
        _add_pending_sync(principal_id, "graphDb", sync_graph_db_to_ipfs, (principal_id,))
        return None


def restore_graph_db_from_ipfs(principal_id: str, manifest: Dict = None) -> bool:
    """Restore graph memory artifacts from IPFS if present."""
    try:
        user_dir = Path(CHATS_DIR) / principal_id
        user_dir.mkdir(parents=True, exist_ok=True)
        graph_db_path = user_dir / "identity.kuzu"
        triples_path = user_dir / "identity_triples.json"

        if manifest is None:
            manifest = load_manifest(principal_id)
        graph_cid = manifest.get("graphIndex", {}).get("cid")
        if not graph_cid:
            return True

        raw = download_from_ipfs(graph_cid)
        if not raw:
            return False

        encrypted = json.loads(raw.decode("utf-8"))
        payload = decrypt_for_user(encrypted, principal_id)
        graph_db_b64 = payload.get("graph_db_b64", "")
        if graph_db_b64:
            with open(graph_db_path, "wb") as f:
                f.write(base64.b64decode(graph_db_b64))
        triples = payload.get("triples", [])
        with open(triples_path, "w") as f:
            json.dump(triples if isinstance(triples, list) else [], f)
        return True
    except Exception as e:
        logger.error(f"❌ Graph DB restore failed: {e}", exc_info=True)
        return False


# =============================================================================
# AUTO-SYNC TRIGGERS
# =============================================================================

def notify_message_indexed(principal_id: str):
    """
    Called after a message is indexed into the vector store.
    Triggers debounced vector DB sync to IPFS.

    Sync triggers when EITHER:
    - VECTOR_SYNC_MESSAGE_THRESHOLD messages have been indexed since last sync, OR
    - VECTOR_SYNC_INTERVAL seconds have passed since last sync
    """
    counter = _vector_sync_counters.get(principal_id, 0) + 1
    _vector_sync_counters[principal_id] = counter

    last_sync = _vector_sync_timestamps.get(principal_id, 0)
    now = time.time()
    elapsed = now - last_sync

    should_sync = (
        counter >= VECTOR_SYNC_MESSAGE_THRESHOLD or
        (elapsed >= VECTOR_SYNC_INTERVAL and counter > 0)
    )

    if should_sync:
        _vector_sync_counters[principal_id] = 0
        _vector_sync_timestamps[principal_id] = now
        # Run sync in background thread to not block the request
        thread = threading.Thread(
            target=sync_vector_db_to_ipfs,
            args=(principal_id,),
            daemon=True,
        )
        thread.start()
        logger.info(f"🔄 Vector DB auto-sync triggered for {principal_id[:20]} (count={counter}, elapsed={elapsed:.0f}s)")


def notify_profile_changed(principal_id: str, memory: Dict):
    """
    Called after user profile (facts/preferences) is saved locally.
    Debounces sync to avoid uploading on every tiny memory mutation burst.
    """
    def _flush_profile_sync(pid: str):
        with _profile_sync_lock:
            latest_memory = _profile_sync_latest.pop(pid, None)
            _profile_sync_timers.pop(pid, None)

        if latest_memory is None:
            return

        sync_profile_to_ipfs(pid, latest_memory)

    with _profile_sync_lock:
        _profile_sync_latest[principal_id] = memory

        existing = _profile_sync_timers.get(principal_id)
        if existing and existing.is_alive():
            existing.cancel()

        timer = threading.Timer(
            PROFILE_SYNC_DEBOUNCE_SECONDS,
            _flush_profile_sync,
            args=(principal_id,),
        )
        timer.daemon = True
        _profile_sync_timers[principal_id] = timer
        timer.start()


def notify_graph_changed(principal_id: str):
    """Debounce graph DB sync to avoid upload churn during message bursts."""
    def _flush_graph_sync(pid: str):
        with _graph_sync_lock:
            _graph_sync_timers.pop(pid, None)
        sync_graph_db_to_ipfs(pid)

    with _graph_sync_lock:
        existing = _graph_sync_timers.get(principal_id)
        if existing and existing.is_alive():
            existing.cancel()
        timer = threading.Timer(
            GRAPH_SYNC_DEBOUNCE_SECONDS,
            _flush_graph_sync,
            args=(principal_id,),
        )
        timer.daemon = True
        _graph_sync_timers[principal_id] = timer
        timer.start()


def _debounce_manifest_sync(principal_id: str, manifest: Dict):
    """Debounce manifest uploads to reduce IPFS churn during autosave bursts."""
    def _flush_manifest_sync(pid: str):
        with _manifest_sync_lock:
            latest_manifest = _manifest_sync_latest.pop(pid, None)
            _manifest_sync_timers.pop(pid, None)

        if latest_manifest is None:
            return

        sync_manifest_to_ipfs(pid, latest_manifest)

    with _manifest_sync_lock:
        _manifest_sync_latest[principal_id] = manifest

        existing = _manifest_sync_timers.get(principal_id)
        if existing and existing.is_alive():
            existing.cancel()

        timer = threading.Timer(
            MANIFEST_SYNC_DEBOUNCE_SECONDS,
            _flush_manifest_sync,
            args=(principal_id,),
        )
        timer.daemon = True
        _manifest_sync_timers[principal_id] = timer
        timer.start()


# =============================================================================
# CHAT CHECKPOINT SYNC
# =============================================================================

def _chat_filename(principal_id: str, chat_id: str) -> str:
    """IPFS filename for a single encrypted chat blob."""
    return f"{principal_id[:PRINCIPAL_DISPLAY_LENGTH]}_{chat_id}.json"


def sync_chat_to_ipfs(
    principal_id: str,
    chat_id: str,
    chat_data: Dict,
    title: str = "Untitled",
    message_count: int = 0,
    archived: bool = False,
    pinned: bool = False,
) -> Optional[str]:
    """
    Encrypt and upload a chat snapshot to IPFS, then update manifest.

    This is used by the debounced autosave checkpoint queue.
    """
    try:
        encrypted = encrypt_for_user(chat_data, principal_id)
        payload = json.dumps(encrypted).encode("utf-8")
        cid = _upload_with_retry(
            payload,
            _chat_filename(principal_id, chat_id),
            principal_id=principal_id,
        )

        if not cid:
            _record_sync_status(principal_id, "chat", False, error="upload returned None")
            _add_pending_sync(
                principal_id,
                f"chat:{chat_id}",
                sync_chat_to_ipfs,
                (principal_id, chat_id, chat_data, title, message_count, archived, pinned),
            )
            return None

        _record_sync_status(principal_id, "chat", True, cid=cid)
        update_chat_in_manifest(
            principal_id=principal_id,
            chat_id=chat_id,
            cid=cid,
            title=title,
            message_count=message_count,
            archived=archived,
            pinned=pinned,
        )
        logger.info(
            "💬 Chat checkpoint synced to IPFS: %s (%s msgs)",
            chat_id[:12],
            message_count,
        )
        return cid
    except Exception as e:
        logger.error("❌ Chat checkpoint sync failed for %s: %s", chat_id[:12], e, exc_info=True)
        _record_sync_status(principal_id, "chat", False, error=str(e))
        _add_pending_sync(
            principal_id,
            f"chat:{chat_id}",
            sync_chat_to_ipfs,
            (principal_id, chat_id, chat_data, title, message_count, archived, pinned),
        )
        return None


def _flush_chat_sync(principal_id: str, chat_id: str) -> Optional[str]:
    """Flush the latest queued chat checkpoint for a principal/chat pair."""
    key = (principal_id, chat_id)
    with _chat_sync_lock:
        payload = _chat_sync_latest.pop(key, None)
        _chat_sync_timers.pop(key, None)
        _chat_sync_started_at.pop(key, None)

    if not payload:
        return None

    return sync_chat_to_ipfs(**payload)


def queue_chat_sync(
    principal_id: str,
    chat_id: str,
    chat_data: Dict,
    title: str = "Untitled",
    message_count: int = 0,
    archived: bool = False,
    pinned: bool = False,
):
    """
    Queue a debounced chat checkpoint sync to IPFS.

    Repeated autosaves for the same chat coalesce into one upload.
    """
    key = (principal_id, chat_id)
    now = time.time()

    with _chat_sync_lock:
        _chat_sync_latest[key] = {
            "principal_id": principal_id,
            "chat_id": chat_id,
            "chat_data": chat_data,
            "title": title,
            "message_count": message_count,
            "archived": archived,
            "pinned": pinned,
        }

        started = _chat_sync_started_at.setdefault(key, now)
        pending_age = now - started
        delay_seconds = CHAT_CHECKPOINT_DEBOUNCE_SECONDS
        if pending_age >= CHAT_CHECKPOINT_MAX_WAIT_SECONDS:
            # Don't delay forever during very active chats.
            delay_seconds = 0.05

        existing = _chat_sync_timers.get(key)
        if existing and existing.is_alive():
            existing.cancel()

        timer = threading.Timer(delay_seconds, _flush_chat_sync, args=(principal_id, chat_id))
        timer.daemon = True
        _chat_sync_timers[key] = timer
        timer.start()


def flush_chat_sync_now(principal_id: str, chat_id: str) -> Optional[str]:
    """Immediately flush any queued chat checkpoint for this chat."""
    key = (principal_id, chat_id)
    with _chat_sync_lock:
        existing = _chat_sync_timers.get(key)
        if existing and existing.is_alive():
            existing.cancel()
    return _flush_chat_sync(principal_id, chat_id)


def discard_queued_chat_sync(principal_id: str, chat_id: str):
    """Cancel and drop any queued autosave checkpoint for a deleted chat."""
    key = (principal_id, chat_id)
    with _chat_sync_lock:
        existing = _chat_sync_timers.pop(key, None)
        if existing and existing.is_alive():
            existing.cancel()
        _chat_sync_latest.pop(key, None)
        _chat_sync_started_at.pop(key, None)


# =============================================================================
# RESTORE-ON-LOGIN
# =============================================================================

def ensure_user_data_restored(principal_id: str) -> bool:
    """
    Ensure all user data is restored from IPFS.
    Called on first authenticated request per session.

    This is idempotent — multiple calls for the same principal are no-ops.

    Returns:
        True if data is available (or user is new)
    """
    # Retry any pending syncs in background to avoid request-path stalls.
    _retry_pending_syncs_async(principal_id)

    with _restore_lock:
        if principal_id in _restored_principals:
            return True
        # Don't add yet — only add after successful restore
        pass

    logger.info(f"🔄 Restoring user data for {principal_id[:20]}...")

    # Try to find manifest on IPFS
    manifest = load_manifest(principal_id)
    if manifest.get("profile", {}).get("cid") is None:
        # Local manifest has no CIDs — try IPFS
        remote_manifest = find_manifest_on_ipfs(principal_id)
        if remote_manifest:
            manifest = remote_manifest
            save_manifest(principal_id, manifest)
            logger.info(f"📋 Manifest restored from IPFS for {principal_id[:20]}")

    # Restore each artifact
    profile_ok = restore_profile_from_ipfs(principal_id, manifest)
    vector_ok = restore_vector_db_from_ipfs(principal_id, manifest)
    graph_ok = restore_graph_db_from_ipfs(principal_id, manifest)

    if profile_ok and vector_ok and graph_ok:
        logger.info(f"✅ User data restore complete for {principal_id[:20]}")
        with _restore_lock:
            _restored_principals.add(principal_id)
    elif profile_ok:
        # Profile is the critical artifact — mark as restored even if vectors fail
        logger.warning(
            f"⚠️ Partial restore for {principal_id[:20]}: profile={profile_ok}, vectors={vector_ok}, graph={graph_ok}"
        )
        with _restore_lock:
            _restored_principals.add(principal_id)
    else:
        # Profile failed — do NOT mark as restored so next request retries
        logger.error(
            f"❌ Restore failed for {principal_id[:20]}: profile={profile_ok}, vectors={vector_ok}, graph={graph_ok}"
        )

    return profile_ok


def hydrate_user_data_async(principal_id: str):
    """
    Kick off restore/hydration in background without blocking request latency.
    Safe to call on every request.
    """
    with _restore_lock:
        if principal_id in _restored_principals or principal_id in _restore_inflight:
            return
        _restore_inflight.add(principal_id)

    def _run():
        try:
            ensure_user_data_restored(principal_id)
        finally:
            with _restore_lock:
                _restore_inflight.discard(principal_id)

    threading.Thread(target=_run, daemon=True).start()


# =============================================================================
# CHAT MANIFEST TRACKING
# =============================================================================

def update_chat_in_manifest(
    principal_id: str,
    chat_id: str,
    cid: str,
    title: str = "Untitled",
    message_count: int = 0,
    archived: bool = False,
    pinned: bool = False,
):
    """
    Update a chat entry in the user manifest after autosave.

    Args:
        principal_id: User principal
        chat_id: Chat identifier
        cid: IPFS CID of the encrypted chat blob
        title: Chat title
        message_count: Number of messages
        archived: Whether chat is archived
        pinned: Whether chat is pinned
    """
    manifest = load_manifest(principal_id)

    # Find or create chat entry
    chat_entry = next((c for c in manifest["chats"] if c["chatId"] == chat_id), None)
    if not chat_entry:
        chat_entry = {
            "chatId": chat_id,
            "createdAt": int(time.time() * 1000),
        }
        manifest["chats"].append(chat_entry)

    old_cid = chat_entry.get("cid")
    chat_entry["cid"] = cid
    chat_entry["title"] = title
    chat_entry["lastUpdated"] = int(time.time() * 1000)
    chat_entry["messageCount"] = message_count
    chat_entry["archived"] = archived
    chat_entry["pinned"] = pinned

    save_manifest(principal_id, manifest)
    _debounce_manifest_sync(principal_id, manifest)

    # Unpin old chat CID (debounced — don't unpin on every autosave keystroke)
    if old_cid and old_cid != cid:
        unpin_cid(old_cid)


def remove_chat_from_manifest(principal_id: str, chat_id: str):
    """Remove a chat entry from the manifest (on delete)."""
    manifest = load_manifest(principal_id)
    manifest["chats"] = [c for c in manifest["chats"] if c["chatId"] != chat_id]
    save_manifest(principal_id, manifest)
    sync_manifest_to_ipfs(principal_id, manifest)


# =============================================================================
# CID CLEANUP
# =============================================================================

def unpin_cid(cid: str):
    """
    Remove pinning for a superseded CID on Lighthouse.
    This frees storage quota. Content may still be available on IPFS
    but will eventually be garbage-collected without a pin.
    """
    try:
        from config import LIGHTHOUSE_API_KEY, LIGHTHOUSE_API, http_session

        if not LIGHTHOUSE_API_KEY:
            return

        headers = {"Authorization": f"Bearer {LIGHTHOUSE_API_KEY}"}
        response = http_session.delete(
            f"{LIGHTHOUSE_API}/api/data/remove",
            headers=headers,
            json={"cid": cid},
            timeout=15,
        )

        if response.status_code == 200:
            logger.debug(f"🗑️ Unpinned old CID: {cid[:16]}...")
        else:
            logger.debug(f"Unpin response for {cid[:16]}: {response.status_code}")

    except Exception as e:
        # Non-critical — log and move on
        logger.debug(f"Unpin failed for {cid[:16]}: {e}")


# =============================================================================
# STORAGE BUDGET
# =============================================================================

def get_storage_stats(principal_id: str) -> Dict:
    """
    Get storage usage stats for a user.

    Returns:
        Dict with artifact counts and estimated IPFS usage
    """
    manifest = load_manifest(principal_id)

    chat_count = len(manifest.get("chats", []))
    has_profile = manifest.get("profile", {}).get("cid") is not None
    has_vectors = manifest.get("memoryIndex", {}).get("cid") is not None
    has_graph = manifest.get("graphIndex", {}).get("cid") is not None
    fact_count = manifest.get("profile", {}).get("factCount", 0)
    msg_count = manifest.get("memoryIndex", {}).get("messageCount", 0)
    triple_count = manifest.get("graphIndex", {}).get("tripleCount", 0)

    return {
        "principal": principal_id[:PRINCIPAL_DISPLAY_LENGTH],
        "chatCount": chat_count,
        "hasProfile": has_profile,
        "hasVectors": has_vectors,
        "hasGraph": has_graph,
        "factCount": fact_count,
        "messageEmbeddings": msg_count,
        "graphTriples": triple_count,
        "lastUpdated": manifest.get("lastUpdated"),
        # CID count = 1 manifest + 1 profile + 1 vectors + 1 graph + N chats
        "activeCids": (1 if has_profile else 0) + (1 if has_vectors else 0) + (1 if has_graph else 0) + chat_count + 1,
    }
