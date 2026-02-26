"""
Base class for PrincipalStateStore — schema, encryption, connection management.
"""

import json
import logging
import sqlite3
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from config import ARCHIVE_AFTER_DAYS, CHATS_DIR, MAX_STATE_STORES
from encryption import EncryptionUtils
from services.session_manager import get_session_passphrase

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _vector_to_blob(vector) -> Optional[bytes]:
    if vector is None:
        return None
    arr = np.array(vector, dtype=np.float32)
    return arr.tobytes()


def _blob_to_vector(blob: Optional[bytes]):
    if not blob:
        return None
    try:
        return np.frombuffer(blob, dtype=np.float32).tolist()
    except Exception:
        return None


def _quarantine_db_family(db_path: Path):
    """Move a corrupt DB and its WAL sidecars out of the live runtime path."""
    timestamp = _now_ms()
    parent = db_path.parent
    targets = [
        (db_path, f"state.corrupt.{timestamp}.db"),
        (Path(str(db_path) + "-wal"), f"state.corrupt.{timestamp}.db-wal"),
        (Path(str(db_path) + "-shm"), f"state.corrupt.{timestamp}.db-shm"),
    ]
    for source, backup_name in targets:
        if not source.exists():
            continue
        try:
            source.rename(parent / backup_name)
        except Exception:
            pass


class StateStoreBase:
    """Base providing schema init, encryption, and connection management."""

    REQUIRED_CORE_TABLES = {
        "chats",
        "messages",
        "memory_facts",
        "conversation_summaries",
        "ingestion_jobs",
        "sync_checkpoints",
    }

    def __init__(self, principal_id: str):
        self.principal_id = principal_id
        self._lock = threading.RLock()
        self._last_quick_check_ms = 0
        self._last_archive_check: float = 0.0
        self.user_dir = self._user_dir_for_principal(principal_id)
        self.db_path = self.user_dir / "state.db"
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._configure_connection(self.conn)
        self._init_schema()

    @staticmethod
    def _user_dir_for_principal(principal_id: str) -> Path:
        safe_principal = (
            principal_id.replace("..", "").replace("\x00", "").replace("/", "").replace("\\", "")
        )
        # Late import to support test patching via services.state_store.CHATS_DIR
        import services.state_store as _pkg
        base = Path(getattr(_pkg, 'CHATS_DIR', CHATS_DIR)).resolve()
        user_dir = base / safe_principal
        if not user_dir.resolve().is_relative_to(base):
            raise ValueError("Invalid principal: path traversal detected")
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _init_schema(self):
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    title_enc TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_chats_principal_updated
                    ON chats(principal_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    principal_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content_enc TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_msg
                    ON messages(principal_id, chat_id, message_id DESC);

                CREATE TABLE IF NOT EXISTS memory_facts (
                    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    principal_id TEXT NOT NULL,
                    text_enc TEXT NOT NULL,
                    category TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    deleted_at INTEGER,
                    valid_at INTEGER,
                    invalid_at INTEGER,
                    source_message_id INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_memory_facts_principal
                    ON memory_facts(principal_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    chat_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    summary_enc TEXT NOT NULL,
                    last_message_id INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, principal_id),
                    FOREIGN KEY(chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
                );

                -- Additive migration: source_chat_id for tier-aware retrieval --
                """
            )
            # Additive column migration (idempotent — fails silently if column exists)
            try:
                self.conn.execute(
                    "ALTER TABLE memory_facts ADD COLUMN source_chat_id TEXT DEFAULT NULL"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

            self.conn.executescript(
                """

                CREATE TABLE IF NOT EXISTS embeddings_messages (
                    message_id INTEGER PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(message_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_embeddings_messages_principal
                    ON embeddings_messages(principal_id);

                CREATE TABLE IF NOT EXISTS embeddings_facts (
                    fact_id INTEGER PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    FOREIGN KEY(fact_id) REFERENCES memory_facts(fact_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_embeddings_facts_principal
                    ON embeddings_facts(principal_id);

                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    principal_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(principal_id, message_id, source)
                );
                CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_due
                    ON ingestion_jobs(principal_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS sync_checkpoints (
                    principal_id TEXT PRIMARY KEY,
                    last_ipfs_cid TEXT,
                    last_sync_at INTEGER,
                    last_synced_message_id INTEGER
                );
                """
            )
            self.conn.commit()

            # Create sqlite-vec virtual tables for ANN search (if sqlite-vec is available)
            from services.db import create_vec_tables

            create_vec_tables(self.conn)

    def _configure_connection(self, conn: sqlite3.Connection):
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.create_function("cosine_sim", 2, self._sqlite_cosine_similarity)

    @classmethod
    def _missing_core_tables_on_conn(cls, conn: sqlite3.Connection) -> List[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        existing = {str(row[0]) for row in rows}
        return sorted(cls.REQUIRED_CORE_TABLES - existing)

    def ensure_required_schema(self):
        with self._lock:
            now_ms = _now_ms()
            if (now_ms - int(self._last_quick_check_ms or 0)) > 60_000:
                quick = self.conn.execute("PRAGMA quick_check").fetchone()
                quick_status = str(quick[0]).strip().lower() if quick else ""
                if quick_status != "ok":
                    raise RuntimeError(f"State DB integrity check failed: {quick_status or 'unknown'}")
                self._last_quick_check_ms = now_ms
            missing = self._missing_core_tables_on_conn(self.conn)
            if not missing:
                return
            self._init_schema()
            missing_after = self._missing_core_tables_on_conn(self.conn)
            if missing_after:
                raise RuntimeError(
                    f"State DB schema still missing required tables: {', '.join(missing_after)}"
                )

    def _validate_checkpoint_bytes(self, data: bytes):
        if not data:
            raise ValueError("Empty checkpoint payload")

        with tempfile.NamedTemporaryFile(prefix="state-import-", suffix=".db", delete=True) as tmp:
            tmp.write(data)
            tmp.flush()
            candidate = sqlite3.connect(tmp.name)
            try:
                quick = candidate.execute("PRAGMA quick_check").fetchone()
                quick_status = str(quick[0]).strip().lower() if quick else ""
                if quick_status != "ok":
                    raise ValueError(f"Checkpoint integrity check failed: {quick_status or 'unknown'}")

                missing = self._missing_core_tables_on_conn(candidate)
                if missing:
                    raise ValueError(
                        f"Checkpoint missing required tables: {', '.join(missing)}"
                    )
            finally:
                candidate.close()

    def _encrypt_text(self, value: str) -> str:
        payload = {"v": value or ""}
        passphrase = get_session_passphrase(self.principal_id)
        if passphrase:
            envelope = EncryptionUtils.encrypt_with_passphrase(payload, passphrase)
        else:
            envelope = EncryptionUtils.encrypt_chat(payload, self.principal_id)
        return json.dumps(envelope, separators=(",", ":"))

    def _decrypt_text(self, value: Optional[str]) -> str:
        if value is None:
            return ""
        try:
            envelope = json.loads(value)
            passphrase = get_session_passphrase(self.principal_id)
            payload = EncryptionUtils.decrypt_auto(
                envelope,
                passphrase=passphrase,
                principal_id=self.principal_id,
            )
            return str(payload.get("v", ""))
        except Exception:
            return str(value)

    @staticmethod
    def _sqlite_cosine_similarity(a_blob, b_blob) -> float:
        if not a_blob or not b_blob:
            return 0.0
        try:
            a = np.frombuffer(a_blob, dtype=np.float32)
            b = np.frombuffer(b_blob, dtype=np.float32)
            if a.size == 0 or b.size == 0 or a.size != b.size:
                return 0.0
            na = np.linalg.norm(a)
            nb = np.linalg.norm(b)
            if na == 0.0 or nb == 0.0:
                return 0.0
            return float(np.dot(a, b) / (na * nb))
        except Exception:
            return 0.0

    @staticmethod
    def _derive_title(content: str) -> str:
        text = (content or "").strip().replace("\n", " ")
        if not text:
            return "New Chat"
        if len(text) <= 60:
            return text
        return text[:57].rstrip() + "..."

    def close(self):
        with self._lock:
            if self.conn:
                self.conn.close()
