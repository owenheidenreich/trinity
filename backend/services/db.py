"""
Trinity Backend — Database Connection Factory

Provides sqlcipher-encrypted, sqlite-vec-enabled connections for each principal.
Replaces raw sqlite3.connect() calls in state_store.py.

Architecture:
  - Whole-DB encryption via sqlcipher (replaces per-field AES-256-GCM)
  - sqlite-vec extension loaded for ANN vector search
  - Read/write connection separation (WAL mode allows concurrent reads)
  - Connection pool with lazy init and eviction

Migration path:
  Old: sqlite3.connect() + per-field encrypt/decrypt via EncryptionUtils
  New: sqlcipher PRAGMA key + plaintext columns + vec0 virtual tables
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from config import CHATS_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flags — graceful fallback when native extensions not available
# ---------------------------------------------------------------------------

_SQLCIPHER_AVAILABLE = False
_SQLITE_VEC_AVAILABLE = False
_sqlite_vec_path: Optional[str] = None

try:
    # pysqlcipher3 provides a drop-in sqlite3 replacement with encryption
    import pysqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]

    _SQLCIPHER_AVAILABLE = True
    logger.info("🔐 sqlcipher available — whole-DB encryption enabled")
except ImportError:
    sqlcipher = None  # type: ignore[assignment]
    logger.warning("⚠️ pysqlcipher3 not installed — falling back to plain sqlite3")

try:
    import sqlite_vec  # type: ignore[import-untyped]

    _SQLITE_VEC_AVAILABLE = True
    _sqlite_vec_path = sqlite_vec.loadable_path()
    logger.info("🔍 sqlite-vec available — ANN vector search enabled")
except ImportError:
    logger.warning("⚠️ sqlite-vec not installed — falling back to brute-force vector search")


# ---------------------------------------------------------------------------
# Encryption key derivation
# ---------------------------------------------------------------------------


def _derive_db_key(principal_id: str) -> str:
    """
    Derive a sqlcipher encryption key from the principal and session passphrase.

    Uses the session passphrase if available (runtime), otherwise falls back
    to a deterministic key derived from the principal ID (startup/migration).
    """
    try:
        from services.session_manager import get_session_passphrase

        passphrase = get_session_passphrase(principal_id)
        if passphrase:
            return passphrase
    except ImportError:
        pass

    # Fallback: HMAC-based key from principal_id + server-level secret
    import hashlib
    import hmac

    server_secret = os.getenv("TRINITY_DB_SECRET", "trinity-default-dev-key")
    return hmac.new(
        server_secret.encode(), principal_id.encode(), hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def _user_dir_for_principal(principal_id: str) -> Path:
    """Resolve the safe directory path for a principal."""
    safe_principal = (
        principal_id.replace("..", "")
        .replace("\x00", "")
        .replace("/", "")
        .replace("\\", "")
    )
    base = Path(CHATS_DIR).resolve()
    user_dir = base / safe_principal
    if not user_dir.resolve().is_relative_to(base):
        raise ValueError("Invalid principal: path traversal detected")
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def open_connection(
    principal_id: str,
    db_name: str = "state.db",
    readonly: bool = False,
) -> sqlite3.Connection:
    """
    Open a sqlcipher-encrypted, sqlite-vec-enabled connection.

    Args:
        principal_id: The principal whose database to open.
        db_name: Database filename (default state.db).
        readonly: If True, opens in read-only mode for concurrent access.

    Returns:
        A configured sqlite3.Connection (or sqlcipher Connection).
    """
    user_dir = _user_dir_for_principal(principal_id)
    db_path = user_dir / db_name

    if _SQLCIPHER_AVAILABLE and sqlcipher is not None:
        uri = f"file:{db_path}"
        if readonly:
            uri += "?mode=ro"
        conn = sqlcipher.connect(uri, uri=True, check_same_thread=False)
        key = _derive_db_key(principal_id)
        conn.execute(f"PRAGMA key = '{key}'")
    else:
        if readonly:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)

    # Configure connection
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    # Load sqlite-vec extension for ANN search
    if _SQLITE_VEC_AVAILABLE and _sqlite_vec_path:
        try:
            conn.enable_load_extension(True)
            conn.load_extension(_sqlite_vec_path)
            conn.enable_load_extension(False)
        except Exception as e:
            logger.warning(f"⚠️ Failed to load sqlite-vec: {e}")

    return conn


# ---------------------------------------------------------------------------
# Connection pool — one read + one write connection per principal
# ---------------------------------------------------------------------------


class _ConnectionPool:
    """
    Per-principal connection pool.

    - One write connection (serialized via RLock)
    - One read connection (WAL allows concurrent reads while writer is active)
    - Lazy init, evictable
    """

    def __init__(self, principal_id: str):
        self.principal_id = principal_id
        self._write_conn: Optional[sqlite3.Connection] = None
        self._read_conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.RLock()
        self._read_lock = threading.RLock()

    @property
    def writer(self) -> sqlite3.Connection:
        """Get or create the write connection."""
        if self._write_conn is None:
            with self._write_lock:
                if self._write_conn is None:
                    self._write_conn = open_connection(
                        self.principal_id, readonly=False
                    )
        return self._write_conn

    @property
    def reader(self) -> sqlite3.Connection:
        """Get or create the read connection."""
        if self._read_conn is None:
            with self._read_lock:
                if self._read_conn is None:
                    self._read_conn = open_connection(
                        self.principal_id, readonly=True
                    )
        return self._read_conn

    def close(self):
        """Close both connections."""
        for conn in (self._write_conn, self._read_conn):
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        self._write_conn = None
        self._read_conn = None


# Module-level pool registry
_pools: dict[str, _ConnectionPool] = {}
_pools_lock = threading.Lock()


def get_pool(principal_id: str) -> _ConnectionPool:
    """Get or create the connection pool for a principal."""
    pool = _pools.get(principal_id)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(principal_id)
        if pool is None:
            pool = _ConnectionPool(principal_id)
            _pools[principal_id] = pool
        return pool


def close_pool(principal_id: str):
    """Close and evict a principal's connection pool."""
    with _pools_lock:
        pool = _pools.pop(principal_id, None)
    if pool:
        pool.close()


def close_all_pools():
    """Close all connection pools. Called on shutdown."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def create_vec_tables(conn: sqlite3.Connection):
    """
    Create sqlite-vec virtual tables for ANN search.

    Only works when sqlite-vec is available. Falls back silently otherwise.
    The vec0 virtual table provides KNN search via:
        SELECT * FROM vec_knowledge WHERE embedding MATCH ? AND k = 10
    """
    if not _SQLITE_VEC_AVAILABLE:
        logger.debug("sqlite-vec not available — skipping vec table creation")
        return

    try:
        conn.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_knowledge USING vec0(
                embedding float[384],
                +item_id integer,
                +item_type text,
                +principal_id text,
                +category text
            );
            """
        )
        conn.commit()
        logger.debug("✅ vec_knowledge virtual table ready")
    except Exception as e:
        logger.warning(f"⚠️ Failed to create vec tables: {e}")


# ---------------------------------------------------------------------------
# Public API summary
# ---------------------------------------------------------------------------

__all__ = [
    "open_connection",
    "get_pool",
    "close_pool",
    "close_all_pools",
    "create_vec_tables",
    "SQLCIPHER_AVAILABLE",
    "SQLITE_VEC_AVAILABLE",
]

SQLCIPHER_AVAILABLE = _SQLCIPHER_AVAILABLE
SQLITE_VEC_AVAILABLE = _SQLITE_VEC_AVAILABLE
