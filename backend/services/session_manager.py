"""
Trinity Backend - Session Passphrase Manager

Holds user passphrases in memory for the duration of their session.
Never persisted to disk, never logged, never sent over the wire.
"""

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_sessions: Dict[str, str] = {}  # principal_id -> passphrase


def set_session_passphrase(principal_id: str, passphrase: str) -> None:
    """Store passphrase in memory for this session."""
    with _lock:
        _sessions[principal_id] = passphrase
    logger.info(f"Session passphrase set for {principal_id[:8]}...")


def get_session_passphrase(principal_id: str) -> Optional[str]:
    """Retrieve passphrase for this session, or None if not unlocked."""
    with _lock:
        return _sessions.get(principal_id)


def has_passphrase(principal_id: str) -> bool:
    """Check if the user has an active passphrase session."""
    with _lock:
        return principal_id in _sessions


def clear_session(principal_id: str) -> None:
    """Wipe passphrase from memory (logout)."""
    with _lock:
        _sessions.pop(principal_id, None)
    logger.info(f"Session cleared for {principal_id[:8]}...")


def clear_all_sessions() -> None:
    """Wipe all sessions (server restart)."""
    with _lock:
        _sessions.clear()
