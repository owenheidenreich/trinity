"""
Trinity Backend - File Storage Module
User directory, metadata, and memory management
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

from config import CHATS_DIR
from encryption import EncryptionUtils
from services.session_manager import get_session_passphrase

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


def _normalize_fact(fact) -> Optional[Dict]:
    """Normalize a single fact to canonical format. Returns None for invalid entries.

    Canonical: {"text": str, "category": str, "importance": int,
                "embedding": list|None, "created_at": int, "deleted": bool,
                "source_chat_id": str|None, "last_mentioned": int|None,
                "valid_at": int|None, "invalid_at": int|None}
    """
    now_ms = int(time.time() * 1000)

    if isinstance(fact, str):
        return {
            "text": fact, "category": "general", "importance": 3,
            "embedding": None, "created_at": now_ms, "deleted": False,
            "source_chat_id": None, "last_mentioned": None,
            "valid_at": now_ms, "invalid_at": None,
        }
    elif isinstance(fact, dict):
        if "text" in fact:
            fact.setdefault("category", "general")
            fact.setdefault("importance", 3)
            fact.setdefault("embedding", None)
            fact.setdefault("created_at", fact.get("addedAt", now_ms))
            fact.setdefault("deleted", False)
            fact.setdefault("source_chat_id", None)
            fact.setdefault("last_mentioned", None)
            fact.setdefault("valid_at", fact.get("created_at", now_ms))
            fact.setdefault("invalid_at", None)
            return fact
        elif "fact" in fact:
            created = fact.get("addedAt", fact.get("created_at", now_ms))
            return {
                "text": fact["fact"],
                "category": fact.get("category", "general"),
                "importance": fact.get("importance", 3),
                "embedding": fact.get("embedding"),
                "created_at": created,
                "deleted": False, "source_chat_id": None, "last_mentioned": None,
                "valid_at": created, "invalid_at": None,
            }
        else:
            logger.warning(f"Skipping unrecognized fact format: {list(fact.keys())}")
            return None
    return None


def _classify_fact_category(text: str) -> str:
    """Heuristic classification of a fact into a profile category.

    Used during migration to sort flat facts into structured profile categories.
    """
    text_lower = text.lower()

    identity_patterns = ["my name is", "i am ", "i'm ", "i live in", "from ",
                         "years old", "born in", "native language", "speak "]
    work_patterns = ["i work", "my job", "my role", "i'm a ", "i am a ",
                     "my company", "my team", "my project", "building ",
                     "developing", "tech stack", "use python", "use javascript",
                     "use typescript", "use rust", "use go", "coding", "engineer",
                     "developer", "designer", "manager", "founder"]
    interest_patterns = ["interested in", "hobby", "i like", "i love",
                         "i enjoy", "passion", "my goal", "want to learn",
                         "learning about", "studying", "reading about"]
    preference_patterns = ["i prefer", "i want", "i like when", "don't like",
                           "favorite", "rather ", "style", "format"]
    relationship_patterns = ["my friend", "my partner", "my wife", "my husband",
                             "my boss", "my colleague", "my team", "my dog",
                             "my cat", "my child", "my son", "my daughter"]

    for p in identity_patterns:
        if p in text_lower:
            return "identity"
    for p in work_patterns:
        if p in text_lower:
            return "work"
    for p in interest_patterns:
        if p in text_lower:
            return "interests"
    for p in preference_patterns:
        if p in text_lower:
            return "preferences"
    for p in relationship_patterns:
        if p in text_lower:
            return "relationships"
    return "general"


def _migrate_to_structured_profile(memory: Dict) -> Dict:
    """Migrate flat fact list to structured profile format (v2.0).

    Idempotent — already-migrated profiles pass through unchanged.
    Returns memory dict at version 2.0 with structured profile field.
    """
    version = memory.get("version", "1.0")

    # Already migrated
    if version == "2.0" and "profile" in memory:
        # Still normalize any raw facts that may have come in via REST
        facts = memory.get("facts", [])
        if facts:
            normalized = []
            for f in facts:
                nf = _normalize_fact(f)
                if nf:
                    normalized.append(nf)
            memory["facts"] = normalized
        if not isinstance(memory.get("conversation_summaries"), dict):
            memory["conversation_summaries"] = {}
        return memory

    # Build structured profile from existing flat facts
    profile = {
        "identity": {},
        "work": {},
        "interests": {},
        "preferences": {},
        "relationships": {},
    }

    facts = memory.get("facts", [])
    normalized_facts = []
    for f in facts:
        nf = _normalize_fact(f)
        if nf:
            # Reclassify if still "general"
            if nf["category"] == "general":
                nf["category"] = _classify_fact_category(nf["text"])
            normalized_facts.append(nf)

    memory["facts"] = normalized_facts
    memory["profile"] = profile
    if not isinstance(memory.get("conversation_summaries"), dict):
        memory["conversation_summaries"] = {}
    memory["version"] = "2.0"

    # Carry forward preferences dict (was dead code, now part of profile)
    old_prefs = memory.get("preferences", {})
    if old_prefs:
        profile["preferences"] = old_prefs

    return memory


def load_user_memory(principal_id: str) -> Dict:
    """Load user memory from canonical state store (fallback: legacy file)."""
    from services.state_store import get_state_store

    store = get_state_store(principal_id)
    facts = store.list_facts(include_deleted=True, include_invalid=True, with_embeddings=True)
    summaries = store.list_conversation_summaries()

    if facts or summaries:
        return {
            **_default_user_memory(principal_id),
            "facts": facts,
            "conversation_summaries": summaries,
            "lastUpdated": int(time.time() * 1000),
        }

    # Fresh store but legacy file exists: migrate once.
    path = get_user_memory_path(principal_id)
    if not path.exists():
        return _default_user_memory(principal_id)

    try:
        with open(path, "r") as f:
            raw = f.read()
        encrypted_data = json.loads(raw)
        if isinstance(encrypted_data, dict) and "encryption" in encrypted_data:
            passphrase = get_session_passphrase(principal_id)
            memory = EncryptionUtils.decrypt_auto(
                encrypted_data,
                passphrase=passphrase,
                principal_id=principal_id,
            )
        else:
            memory = encrypted_data
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.error(f"❌ Failed to load legacy user memory for {principal_id[:20]}...")
        return _default_user_memory(principal_id)

    migrated = _migrate_to_structured_profile(memory)
    save_user_memory(principal_id, migrated)
    return {
        **_default_user_memory(principal_id),
        "facts": store.list_facts(include_deleted=True, include_invalid=True, with_embeddings=True),
        "conversation_summaries": store.list_conversation_summaries(),
    }


def _default_user_memory(principal_id: str) -> Dict:
    """Return default v2.0 user memory structure with empty profile."""
    return {
        "principalId": principal_id,
        "version": "2.0",
        "facts": [],
        "profile": {
            "identity": {},
            "work": {},
            "interests": {},
            "preferences": {},
            "relationships": {},
        },
        "conversation_summaries": {},
        "createdAt": int(time.time() * 1000),
        "lastUpdated": int(time.time() * 1000),
    }


def get_active_facts(memory: Dict) -> list:
    """Return only non-deleted, currently-valid facts from user memory.
    Facts with invalid_at set are treated as superseded/expired."""
    return [
        f for f in memory.get("facts", [])
        if (isinstance(f, dict) and not f.get("deleted", False) and not f.get("invalid_at"))
        or isinstance(f, str)
    ]


def save_user_memory(principal_id: str, memory: Dict):
    """Persist memory payload into canonical state store."""
    from services.state_store import get_state_store

    memory["lastUpdated"] = int(time.time() * 1000)
    store = get_state_store(principal_id)
    store.replace_facts_from_memory_payload(memory.get("facts", []))

    summaries = memory.get("conversation_summaries", {})
    if isinstance(summaries, dict):
        for chat_id, entry in summaries.items():
            if not isinstance(entry, dict):
                continue
            summary = str(entry.get("summary", "")).strip()
            if not summary:
                continue
            last_idx = entry.get("last_message_id", entry.get("last_summarized_index", 0))
            try:
                last_message_id = int(last_idx)
            except (TypeError, ValueError):
                last_message_id = 0
            store.upsert_conversation_summary(chat_id, summary, last_message_id)


def _default_metadata(principal_id: str) -> Dict:
    """Return fresh default metadata for a principal."""
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


def load_metadata(principal_id: str) -> Dict:
    """Load user's metadata (supports both encrypted and legacy plaintext).

    Resilient: returns default metadata if decryption fails (e.g. missing
    passphrase after container restart) rather than raising an exception.
    """
    path = get_metadata_path(principal_id)
    if path.exists():
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            # Check if encrypted (new format)
            if isinstance(raw, dict) and "encryption" in raw:
                passphrase = get_session_passphrase(principal_id)
                try:
                    return EncryptionUtils.decrypt_auto(
                        raw, passphrase=passphrase, principal_id=principal_id
                    )
                except ValueError as ve:
                    # Passphrase required but not in session (e.g. container restart)
                    # Return defaults so autosave can still append new chats.
                    # Existing chats remain safely encrypted on disk.
                    logger.warning(
                        f"⚠️ Cannot decrypt metadata for {principal_id[:20]}: {ve}. "
                        "Returning defaults — unlock passphrase to restore history."
                    )
                    return _default_metadata(principal_id)
            # Legacy plaintext — return as-is, will be encrypted on next save
            return raw
        except Exception as e:
            logger.error(f"Failed to load metadata for {principal_id[:20]}: {e}")
    return _default_metadata(principal_id)


def save_metadata(principal_id: str, metadata: Dict):
    """Save user's metadata (encrypted on disk with AES-256-GCM)"""
    metadata["lastLogin"] = int(time.time() * 1000)
    passphrase = get_session_passphrase(principal_id)
    if passphrase:
        encrypted = EncryptionUtils.encrypt_with_passphrase(metadata, passphrase)
    else:
        encrypted = EncryptionUtils.encrypt_chat(metadata, principal_id)
    with open(get_metadata_path(principal_id), "w") as f:
        json.dump(encrypted, f)
