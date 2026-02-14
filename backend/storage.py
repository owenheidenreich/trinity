"""
Trinity Backend - File Storage Module
User directory, metadata, and memory management
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict

from config import CHATS_DIR
from encryption import EncryptionUtils

logger = logging.getLogger(__name__)


def get_user_dir(principal_id: str) -> Path:
    """
    Get user's chat directory with path traversal protection.

    Security: Prevents malicious principal IDs containing '..' or other
    path manipulation characters from escaping the CHATS_DIR sandbox.
    Even if a principal somehow contains '../../../etc/passwd', the
    resolved path check ensures we stay within CHATS_DIR.
    """
    # Sanitize: remove any path traversal attempts
    safe_principal = (
        principal_id.replace("..", "").replace("\x00", "").replace("/", "").replace("\\", "")
    )

    # Construct the path
    chats_base = Path(CHATS_DIR).resolve()
    user_dir = chats_base / safe_principal

    # CRITICAL: Ensure resolved path is still under CHATS_DIR
    # This catches any edge cases the sanitization might miss
    if not user_dir.resolve().is_relative_to(chats_base):
        logger.error(f"🚨 PATH TRAVERSAL ATTEMPT: {principal_id}")
        raise ValueError("Invalid principal: path traversal detected")

    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_metadata_path(principal_id: str) -> Path:
    """Get metadata file path for user"""
    return get_user_dir(principal_id) / "metadata.json"


def get_user_memory_path(principal_id: str) -> Path:
    """Get user memory file path"""
    return get_user_dir(principal_id) / "user_memory.json"


def _normalize_facts(memory: Dict) -> Dict:
    """Normalize legacy fact schemas to canonical format.

    Canonical: {"text": str, "category": str, "importance": int, "embedding": list|None, "created_at": int}
    Legacy A (REST API): {"fact": "...", "addedAt": ..., "category": "..."}
    Legacy B (plain strings): "some fact"

    This migration is idempotent — already-normalized facts pass through unchanged.
    """
    facts = memory.get("facts", [])
    if not facts:
        return memory

    normalized = []
    changed = False
    for fact in facts:
        if isinstance(fact, str):
            normalized.append({
                "text": fact,
                "category": "general",
                "importance": 3,
                "embedding": None,
                "created_at": int(time.time() * 1000),
            })
            changed = True
        elif isinstance(fact, dict):
            if "text" in fact:
                # Already canonical (or close) — ensure all fields present
                fact.setdefault("category", "general")
                fact.setdefault("importance", 3)
                fact.setdefault("embedding", None)
                fact.setdefault("created_at", fact.get("addedAt", int(time.time() * 1000)))
                normalized.append(fact)
            elif "fact" in fact:
                # Legacy REST API format
                normalized.append({
                    "text": fact["fact"],
                    "category": fact.get("category", "general"),
                    "importance": fact.get("importance", 3),
                    "embedding": fact.get("embedding"),
                    "created_at": fact.get("addedAt", fact.get("created_at", int(time.time() * 1000))),
                })
                changed = True
            else:
                # Unknown dict format — skip
                logger.warning(f"Skipping unrecognized fact format: {list(fact.keys())}")
                changed = True
        else:
            changed = True  # drop non-string, non-dict entries

    if changed:
        memory["facts"] = normalized
    return memory


def load_user_memory(principal_id: str) -> Dict:
    """Load user's persistent memory (encrypted on disk)"""
    path = get_user_memory_path(principal_id)
    if path.exists():
        with open(path, "r") as f:
            raw = f.read()

        # Try to decrypt (new encrypted format)
        try:
            encrypted_data = json.loads(raw)
            # Check if it's encrypted format (has 'encryption' key)
            if isinstance(encrypted_data, dict) and "encryption" in encrypted_data:
                return _normalize_facts(EncryptionUtils.decrypt_chat(encrypted_data, principal_id))
            else:
                # Legacy unencrypted JSON - return as-is, will be encrypted on next save
                logger.warning(f"⚠️ Legacy unencrypted user memory found for {principal_id[:20]}...")
                return _normalize_facts(encrypted_data)
        except (json.JSONDecodeError, ValueError, KeyError):
            # If it's not valid JSON or can't decrypt, return default
            logger.error(f"❌ Failed to load user memory for {principal_id[:20]}...")
            return _default_user_memory(principal_id)

    return _default_user_memory(principal_id)


def _default_user_memory(principal_id: str) -> Dict:
    """Return default user memory structure"""
    return {
        "principalId": principal_id,
        "version": "1.0",
        "facts": [],
        "preferences": {},
        "createdAt": int(time.time() * 1000),
        "lastUpdated": int(time.time() * 1000),
    }


def save_user_memory(principal_id: str, memory: Dict):
    """Save user's persistent memory (encrypted with AES-256-GCM)"""
    memory["lastUpdated"] = int(time.time() * 1000)
    encrypted = EncryptionUtils.encrypt_chat(memory, principal_id)
    with open(get_user_memory_path(principal_id), "w") as f:
        json.dump(encrypted, f)


def load_metadata(principal_id: str) -> Dict:
    """Load user's metadata"""
    path = get_metadata_path(principal_id)
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {
        "principalId": principal_id,
        "version": "1.0",
        "chats": [],
        "createdAt": int(time.time() * 1000),
        "lastLogin": int(time.time() * 1000),
        "currentBundleCID": None,
        "lastBundleVersion": 0,
        "lastSyncedAt": None,
    }


def save_metadata(principal_id: str, metadata: Dict):
    """Save user's metadata"""
    metadata["lastLogin"] = int(time.time() * 1000)
    with open(get_metadata_path(principal_id), "w") as f:
        json.dump(metadata, f, indent=2)
