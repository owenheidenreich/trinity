"""
Canonical per-principal encrypted state store.

This service is the backend source of truth for chats, messages, memory facts,
conversation summaries, graph triples, embeddings, and ingestion jobs.
"""

import json
import logging
import sqlite3
import threading
import tempfile
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from config import ARCHIVE_AFTER_DAYS
from config import CHATS_DIR
from config import MAX_STATE_STORES
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
    """
    Move a corrupt DB and its WAL sidecars out of the live runtime path.
    """
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


class PrincipalStateStore:
    """Canonical state store for one principal."""

    REQUIRED_CORE_TABLES = {
        "chats",
        "messages",
        "memory_facts",
        "conversation_summaries",
        "graph_triples",
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
        base = Path(CHATS_DIR).resolve()
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

                CREATE TABLE IF NOT EXISTS graph_triples (
                    triple_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    principal_id TEXT NOT NULL,
                    subject_enc TEXT NOT NULL,
                    predicate_enc TEXT NOT NULL,
                    object_enc TEXT NOT NULL,
                    source_message_id INTEGER,
                    created_at INTEGER NOT NULL,
                    invalid_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_graph_triples_principal
                    ON graph_triples(principal_id, created_at DESC);

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
        # Prevent SQLITE_BUSY when the ingestion worker holds a write lock;
        # the connection will retry for up to 5 seconds before raising.
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
            # Back-compat with plaintext rows.
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

    # ---------------------------------------------------------------------
    # Chat / message operations
    # ---------------------------------------------------------------------

    def auto_archive_stale_chats(self, days: Optional[int] = None) -> int:
        """Archive chats whose updated_at is older than *days* days.

        Pinned chats are exempt.  Returns the number of chats archived.
        Throttled to run at most once per hour via ``_last_archive_check``.
        """
        now = time.time()
        if now - self._last_archive_check < 3600:
            return 0
        self._last_archive_check = now

        threshold_days = days if days is not None else ARCHIVE_AFTER_DAYS
        cutoff_ms = _now_ms() - (threshold_days * 86_400_000)

        with self._lock:
            cursor = self.conn.execute(
                """
                UPDATE chats
                SET archived = 1, updated_at = ?
                WHERE principal_id = ?
                  AND archived = 0
                  AND pinned = 0
                  AND updated_at < ?
                """,
                (_now_ms(), self.principal_id, cutoff_ms),
            )
            count = cursor.rowcount
            if count:
                self.conn.commit()
                logger.info(
                    "Auto-archived %d stale chat(s) for principal %s",
                    count,
                    self.principal_id[:12],
                )
        return count

    def create_chat(self, chat_id: Optional[str] = None, title: str = "New Chat") -> str:
        with self._lock:
            now = _now_ms()
            resolved_chat_id = chat_id or f"chat-{now}-{uuid.uuid4().hex[:8]}"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO chats
                (chat_id, principal_id, title_enc, pinned, archived, created_at, updated_at, message_count)
                VALUES (?, ?, ?, 0, 0, ?, ?, 0)
                """,
                (
                    resolved_chat_id,
                    self.principal_id,
                    self._encrypt_text(title or "New Chat"),
                    now,
                    now,
                ),
            )
            self.conn.commit()
            return resolved_chat_id

    def ensure_chat(self, chat_id: str, default_title: str = "New Chat") -> str:
        if not chat_id:
            return self.create_chat(title=default_title)
        return self.create_chat(chat_id=chat_id, title=default_title)

    def list_chats(self, include_archived: bool = True, limit: int = 200) -> List[Dict]:
        # Lazily archive stale chats (throttled to once/hour)
        self.auto_archive_stale_chats()

        with self._lock:
            query = (
                "SELECT chat_id, title_enc, pinned, archived, created_at, updated_at, message_count "
                "FROM chats WHERE principal_id = ? "
            )
            params: List = [self.principal_id]
            if not include_archived:
                query += "AND archived = 0 "
            # Deterministic ordering prevents UI jitter when timestamps tie.
            query += "ORDER BY pinned DESC, updated_at DESC, created_at DESC, chat_id DESC LIMIT ?"
            params.append(int(limit))
            rows = self.conn.execute(query, tuple(params)).fetchall()

        return [
            {
                "chatId": row["chat_id"],
                "title": self._decrypt_text(row["title_enc"]),
                "pinned": bool(row["pinned"]),
                "archived": bool(row["archived"]),
                "isArchived": bool(row["archived"]),
                "createdAt": int(row["created_at"]),
                "lastUpdated": int(row["updated_at"]),
                "messageCount": int(row["message_count"] or 0),
            }
            for row in rows
        ]

    def get_chat(self, chat_id: str) -> Optional[Dict]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT chat_id, title_enc, pinned, archived, created_at, updated_at, message_count
                FROM chats
                WHERE principal_id = ? AND chat_id = ?
                """,
                (self.principal_id, chat_id),
            ).fetchone()
        if not row:
            return None
        return {
            "chatId": row["chat_id"],
            "title": self._decrypt_text(row["title_enc"]),
            "pinned": bool(row["pinned"]),
            "archived": bool(row["archived"]),
            "isArchived": bool(row["archived"]),
            "createdAt": int(row["created_at"]),
            "lastUpdated": int(row["updated_at"]),
            "messageCount": int(row["message_count"] or 0),
        }

    def update_chat(
        self,
        chat_id: str,
        *,
        title: Optional[str] = None,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
    ) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT chat_id FROM chats WHERE principal_id = ? AND chat_id = ?",
                (self.principal_id, chat_id),
            ).fetchone()
            if not row:
                return False

            fields = []
            params: List = []
            if title is not None:
                fields.append("title_enc = ?")
                params.append(self._encrypt_text(title))
            if pinned is not None:
                fields.append("pinned = ?")
                params.append(1 if pinned else 0)
            if archived is not None:
                fields.append("archived = ?")
                params.append(1 if archived else 0)

            fields.append("updated_at = ?")
            params.append(_now_ms())
            params.extend([self.principal_id, chat_id])

            self.conn.execute(
                f"UPDATE chats SET {', '.join(fields)} WHERE principal_id = ? AND chat_id = ?",
                tuple(params),
            )
            self.conn.commit()
            return True

    def delete_chat(self, chat_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM chats WHERE principal_id = ? AND chat_id = ?",
                (self.principal_id, chat_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def append_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        token_count: int = 0,
        created_at: Optional[int] = None,
    ) -> int:
        with self._lock:
            now = created_at or _now_ms()
            resolved_chat_id = self.ensure_chat(chat_id)

            self.conn.execute(
                """
                INSERT INTO messages (principal_id, chat_id, role, content_enc, created_at, token_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.principal_id,
                    resolved_chat_id,
                    role,
                    self._encrypt_text(content),
                    now,
                    int(token_count or 0),
                ),
            )
            message_id = int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            # Update chat counters + title evolution.
            chat_row = self.conn.execute(
                "SELECT title_enc, message_count FROM chats WHERE principal_id = ? AND chat_id = ?",
                (self.principal_id, resolved_chat_id),
            ).fetchone()
            current_title = self._decrypt_text(chat_row["title_enc"]) if chat_row else "New Chat"
            next_count = int(chat_row["message_count"] or 0) + 1 if chat_row else 1

            title_enc = chat_row["title_enc"] if chat_row else self._encrypt_text("New Chat")
            if role == "user" and (current_title == "New Chat" or next_count <= 1):
                title_enc = self._encrypt_text(self._derive_title(content))

            self.conn.execute(
                """
                UPDATE chats
                SET title_enc = ?, updated_at = ?, message_count = ?
                WHERE principal_id = ? AND chat_id = ?
                """,
                (title_enc, now, next_count, self.principal_id, resolved_chat_id),
            )

            self.conn.commit()
            return message_id

    def get_messages(
        self,
        chat_id: str,
        before_message_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict]:
        with self._lock:
            if before_message_id is not None:
                rows = self.conn.execute(
                    """
                    SELECT message_id, chat_id, role, content_enc, created_at, token_count
                    FROM messages
                    WHERE principal_id = ? AND chat_id = ? AND message_id < ?
                    ORDER BY message_id DESC
                    LIMIT ?
                    """,
                    (self.principal_id, chat_id, int(before_message_id), int(limit)),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT message_id, chat_id, role, content_enc, created_at, token_count
                    FROM messages
                    WHERE principal_id = ? AND chat_id = ?
                    ORDER BY message_id DESC
                    LIMIT ?
                    """,
                    (self.principal_id, chat_id, int(limit)),
                ).fetchall()

        output = []
        for row in reversed(rows):
            output.append(
                {
                    "id": int(row["message_id"]),
                    "message_id": int(row["message_id"]),
                    "chatId": row["chat_id"],
                    "chat_id": row["chat_id"],
                    "role": row["role"],
                    "content": self._decrypt_text(row["content_enc"]),
                    "createdAt": int(row["created_at"]),
                    "created_at": int(row["created_at"]),
                    "token_count": int(row["token_count"] or 0),
                    "status": "persisted",
                }
            )
        return output

    def get_messages_since(
        self,
        chat_id: str,
        after_message_id: int = 0,
        limit: int = 0,
    ) -> List[Dict]:
        with self._lock:
            if limit and limit > 0:
                rows = self.conn.execute(
                    """
                    SELECT message_id, chat_id, role, content_enc, created_at, token_count
                    FROM messages
                    WHERE principal_id = ? AND chat_id = ? AND message_id > ?
                    ORDER BY message_id ASC
                    LIMIT ?
                    """,
                    (self.principal_id, chat_id, int(after_message_id), int(limit)),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT message_id, chat_id, role, content_enc, created_at, token_count
                    FROM messages
                    WHERE principal_id = ? AND chat_id = ? AND message_id > ?
                    ORDER BY message_id ASC
                    """,
                    (self.principal_id, chat_id, int(after_message_id)),
                ).fetchall()

        output = []
        for row in rows:
            output.append(
                {
                    "id": int(row["message_id"]),
                    "message_id": int(row["message_id"]),
                    "chatId": row["chat_id"],
                    "chat_id": row["chat_id"],
                    "role": row["role"],
                    "content": self._decrypt_text(row["content_enc"]),
                    "createdAt": int(row["created_at"]),
                    "created_at": int(row["created_at"]),
                    "token_count": int(row["token_count"] or 0),
                    "status": "persisted",
                }
            )
        return output

    def get_last_message_id(self, chat_id: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT MAX(message_id) AS max_id FROM messages WHERE principal_id = ? AND chat_id = ?",
                (self.principal_id, chat_id),
            ).fetchone()
            if not row or row["max_id"] is None:
                return 0
            return int(row["max_id"])

    def get_latest_message_id(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT MAX(message_id) AS max_id FROM messages WHERE principal_id = ?",
                (self.principal_id,),
            ).fetchone()
            if not row or row["max_id"] is None:
                return 0
            return int(row["max_id"])

    # ---------------------------------------------------------------------
    # Facts / memory operations
    # ---------------------------------------------------------------------

    def list_facts(
        self,
        include_deleted: bool = True,
        include_invalid: bool = True,
        with_embeddings: bool = False,
    ) -> List[Dict]:
        where = ["f.principal_id = ?"]
        params: List = [self.principal_id]
        if not include_deleted:
            where.append("f.deleted_at IS NULL")
        if not include_invalid:
            where.append("f.invalid_at IS NULL")

        select = (
            "f.fact_id, f.text_enc, f.category, f.importance, f.created_at, f.updated_at, "
            "f.deleted_at, f.valid_at, f.invalid_at, f.source_message_id, f.source_chat_id"
        )
        join = ""
        if with_embeddings:
            select += ", e.vector AS vector"
            join = " LEFT JOIN embeddings_facts e ON e.fact_id = f.fact_id AND e.principal_id = f.principal_id "

        query = (
            f"SELECT {select} FROM memory_facts f {join}"
            f"WHERE {' AND '.join(where)} ORDER BY f.updated_at DESC"
        )

        with self._lock:
            rows = self.conn.execute(query, tuple(params)).fetchall()

        result = []
        for row in rows:
            item = {
                "fact_id": int(row["fact_id"]),
                "text": self._decrypt_text(row["text_enc"]),
                "category": row["category"],
                "importance": int(row["importance"] or 3),
                "created_at": int(row["created_at"]),
                "updated_at": int(row["updated_at"]),
                "deleted_at": int(row["deleted_at"]) if row["deleted_at"] is not None else None,
                "deleted": row["deleted_at"] is not None,
                "valid_at": int(row["valid_at"]) if row["valid_at"] is not None else None,
                "invalid_at": int(row["invalid_at"]) if row["invalid_at"] is not None else None,
                "source_message_id": row["source_message_id"],
                "source_chat_id": row["source_chat_id"] if "source_chat_id" in row.keys() else None,
                "last_mentioned": int(row["updated_at"]),
            }
            if with_embeddings:
                item["embedding"] = _blob_to_vector(row["vector"])
            result.append(item)
        return result

    def get_fact(self, fact_id: int, with_embedding: bool = False) -> Optional[Dict]:
        facts = self.list_facts(include_deleted=True, include_invalid=True, with_embeddings=with_embedding)
        for fact in facts:
            if int(fact.get("fact_id", -1)) == int(fact_id):
                return fact
        return None

    def create_fact(
        self,
        *,
        text: str,
        category: str,
        importance: int,
        source_message_id: Optional[int] = None,
        source_chat_id: Optional[str] = None,
        valid_at: Optional[int] = None,
        invalid_at: Optional[int] = None,
        deleted_at: Optional[int] = None,
        embedding=None,
    ) -> int:
        with self._lock:
            now = _now_ms()
            self.conn.execute(
                """
                INSERT INTO memory_facts
                (principal_id, text_enc, category, importance, created_at, updated_at,
                 deleted_at, valid_at, invalid_at, source_message_id, source_chat_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.principal_id,
                    self._encrypt_text(text),
                    category,
                    int(importance),
                    now,
                    now,
                    deleted_at,
                    valid_at if valid_at is not None else now,
                    invalid_at,
                    source_message_id,
                    source_chat_id,
                ),
            )
            fact_id = int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            if embedding is not None:
                blob = _vector_to_blob(embedding)
                if blob is not None:
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO embeddings_facts (fact_id, principal_id, vector)
                        VALUES (?, ?, ?)
                        """,
                        (fact_id, self.principal_id, blob),
                    )
            self.conn.commit()
            return fact_id

    def update_fact(self, fact_id: int, updates: Dict) -> bool:
        allowed = {
            "text",
            "category",
            "importance",
            "deleted_at",
            "valid_at",
            "invalid_at",
            "source_message_id",
            "source_chat_id",
            "embedding",
        }
        clean = {k: v for k, v in updates.items() if k in allowed}
        if not clean:
            return False

        with self._lock:
            row = self.conn.execute(
                "SELECT fact_id FROM memory_facts WHERE principal_id = ? AND fact_id = ?",
                (self.principal_id, int(fact_id)),
            ).fetchone()
            if not row:
                return False

            fields = []
            params: List = []
            if "text" in clean:
                fields.append("text_enc = ?")
                params.append(self._encrypt_text(str(clean["text"])))
            if "category" in clean:
                fields.append("category = ?")
                params.append(str(clean["category"]))
            if "importance" in clean:
                fields.append("importance = ?")
                params.append(int(clean["importance"]))
            if "deleted_at" in clean:
                fields.append("deleted_at = ?")
                params.append(clean["deleted_at"])
            if "valid_at" in clean:
                fields.append("valid_at = ?")
                params.append(clean["valid_at"])
            if "invalid_at" in clean:
                fields.append("invalid_at = ?")
                params.append(clean["invalid_at"])
            if "source_message_id" in clean:
                fields.append("source_message_id = ?")
                params.append(clean["source_message_id"])
            if "source_chat_id" in clean:
                fields.append("source_chat_id = ?")
                params.append(clean["source_chat_id"])

            fields.append("updated_at = ?")
            params.append(_now_ms())
            params.extend([self.principal_id, int(fact_id)])

            self.conn.execute(
                f"UPDATE memory_facts SET {', '.join(fields)} WHERE principal_id = ? AND fact_id = ?",
                tuple(params),
            )

            if "embedding" in clean:
                blob = _vector_to_blob(clean["embedding"])
                if blob is not None:
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO embeddings_facts (fact_id, principal_id, vector)
                        VALUES (?, ?, ?)
                        """,
                        (int(fact_id), self.principal_id, blob),
                    )
                else:
                    self.conn.execute(
                        "DELETE FROM embeddings_facts WHERE fact_id = ? AND principal_id = ?",
                        (int(fact_id), self.principal_id),
                    )

            self.conn.commit()
            return True

    def soft_delete_fact(self, fact_id: int) -> bool:
        return self.update_fact(int(fact_id), {"deleted_at": _now_ms()})

    def replace_facts_from_memory_payload(self, facts: List[Dict]):
        """Compatibility helper for storage.save_user_memory()."""
        existing_by_id = {
            int(item.get("fact_id")): item
            for item in self.list_facts(include_deleted=True, include_invalid=True, with_embeddings=True)
            if item.get("fact_id") is not None
        }
        existing_by_signature = {}
        for item in existing_by_id.values():
            signature = (
                str(item.get("text", "")).strip().lower(),
                str(item.get("category", "general")).strip().lower(),
            )
            if signature[0]:
                existing_by_signature[signature] = int(item.get("fact_id"))

        for fact in facts or []:
            if isinstance(fact, str):
                fact = {
                    "text": fact,
                    "category": "general",
                    "importance": 3,
                }
            if not isinstance(fact, dict):
                continue

            fact_id = fact.get("fact_id") or fact.get("id")
            payload = {
                "text": fact.get("text") or fact.get("fact") or "",
                "category": fact.get("category", "general"),
                "importance": int(fact.get("importance", 3)),
                "deleted_at": (
                    fact.get("deleted_at")
                    if fact.get("deleted_at") is not None
                    else (_now_ms() if fact.get("deleted") else None)
                ),
                "valid_at": fact.get("valid_at"),
                "invalid_at": fact.get("invalid_at"),
                "source_message_id": fact.get("source_message_id"),
                "embedding": fact.get("embedding"),
            }
            if not payload["text"]:
                continue

            if fact_id:
                existing = existing_by_id.get(int(fact_id))
                if not existing:
                    self.create_fact(**payload)
                    continue

                current_deleted_at = existing.get("deleted_at")
                target_deleted_at = payload.get("deleted_at")
                current_embedding = existing.get("embedding")
                target_embedding = payload.get("embedding")
                embedding_changed = False
                if current_embedding is None and target_embedding is None:
                    embedding_changed = False
                elif current_embedding is None or target_embedding is None:
                    embedding_changed = True
                else:
                    embedding_changed = list(current_embedding) != list(target_embedding)

                unchanged = (
                    str(existing.get("text", "")) == str(payload.get("text", ""))
                    and str(existing.get("category", "general")) == str(payload.get("category", "general"))
                    and int(existing.get("importance", 3)) == int(payload.get("importance", 3))
                    and current_deleted_at == target_deleted_at
                    and existing.get("valid_at") == payload.get("valid_at")
                    and existing.get("invalid_at") == payload.get("invalid_at")
                    and existing.get("source_message_id") == payload.get("source_message_id")
                    and not embedding_changed
                )
                if unchanged:
                    continue

                self.update_fact(int(fact_id), payload)
            else:
                signature = (
                    str(payload.get("text", "")).strip().lower(),
                    str(payload.get("category", "general")).strip().lower(),
                )
                matched_fact_id = existing_by_signature.get(signature)
                if matched_fact_id:
                    self.update_fact(int(matched_fact_id), payload)
                    continue

                created_fact_id = self.create_fact(**payload)
                if signature[0]:
                    existing_by_signature[signature] = created_fact_id

    # ---------------------------------------------------------------------
    # Conversation summary operations
    # ---------------------------------------------------------------------

    def get_conversation_summary(self, chat_id: str) -> Optional[Dict]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT summary_enc, last_message_id, updated_at
                FROM conversation_summaries
                WHERE principal_id = ? AND chat_id = ?
                """,
                (self.principal_id, chat_id),
            ).fetchone()
        if not row:
            return None
        return {
            "summary": self._decrypt_text(row["summary_enc"]),
            "last_summarized_index": int(row["last_message_id"]),
            "last_message_id": int(row["last_message_id"]),
            "updated_at": int(row["updated_at"]),
        }

    def list_conversation_summaries(self) -> Dict[str, Dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT chat_id, summary_enc, last_message_id, updated_at
                FROM conversation_summaries
                WHERE principal_id = ?
                ORDER BY updated_at DESC
                """,
                (self.principal_id,),
            ).fetchall()
        summaries: Dict[str, Dict] = {}
        for row in rows:
            chat_id = row["chat_id"]
            summaries[chat_id] = {
                "summary": self._decrypt_text(row["summary_enc"]),
                "last_summarized_index": int(row["last_message_id"]),
                "last_message_id": int(row["last_message_id"]),
                "updated_at": int(row["updated_at"]),
            }
        return summaries

    def upsert_conversation_summary(self, chat_id: str, summary: str, last_message_id: int):
        with self._lock:
            now = _now_ms()
            self.conn.execute(
                """
                INSERT INTO conversation_summaries
                (chat_id, principal_id, summary_enc, last_message_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, principal_id)
                DO UPDATE SET
                    summary_enc = excluded.summary_enc,
                    last_message_id = excluded.last_message_id,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    self.principal_id,
                    self._encrypt_text(summary),
                    int(last_message_id),
                    now,
                ),
            )
            self.conn.commit()

    # ---------------------------------------------------------------------
    # Graph operations
    # ---------------------------------------------------------------------

    def insert_graph_triples(self, triples: List[Dict], source_message_id: Optional[int] = None):
        if not triples:
            return
        with self._lock:
            now = _now_ms()
            for triple in triples:
                subject = str(triple.get("subject", "user") or "user")
                predicate = str(triple.get("predicate", "related_to") or "related_to")
                obj = str(triple.get("object", "") or "")
                if not obj:
                    continue
                self.conn.execute(
                    """
                    INSERT INTO graph_triples
                    (principal_id, subject_enc, predicate_enc, object_enc, source_message_id, created_at, invalid_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        self.principal_id,
                        self._encrypt_text(subject),
                        self._encrypt_text(predicate),
                        self._encrypt_text(obj),
                        source_message_id,
                        now,
                    ),
                )
            self.conn.commit()

    def list_graph_triples(self, limit: int = 100, include_invalid: bool = False) -> List[Dict]:
        where = "principal_id = ?"
        if not include_invalid:
            where += " AND invalid_at IS NULL"
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT triple_id, subject_enc, predicate_enc, object_enc, source_message_id, created_at, invalid_at
                FROM graph_triples
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.principal_id, int(limit)),
            ).fetchall()
        triples = []
        for row in rows:
            triples.append(
                {
                    "triple_id": int(row["triple_id"]),
                    "subject": self._decrypt_text(row["subject_enc"]),
                    "predicate": self._decrypt_text(row["predicate_enc"]),
                    "object": self._decrypt_text(row["object_enc"]),
                    "source_message_id": row["source_message_id"],
                    "created_at": int(row["created_at"]),
                    "invalid_at": row["invalid_at"],
                }
            )
        return triples

    def search_graph_triples(self, query: str, limit: int = 6) -> List[Dict]:
        """Retrieve graph triples relevant to a user query from canonical store."""
        query_text = str(query or "").strip().lower()
        if not query_text:
            return []

        def _tokenize(text: str) -> List[str]:
            cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in (text or "").lower())
            return [tok for tok in cleaned.split() if len(tok) > 2]

        query_tokens = set(_tokenize(query_text))
        if not query_tokens:
            return []

        triples = self.list_graph_triples(limit=500, include_invalid=False)
        now_ms = _now_ms()
        scored = []
        for triple in triples:
            triple_text = " ".join(
                [
                    str(triple.get("subject", "")),
                    str(triple.get("predicate", "")),
                    str(triple.get("object", "")),
                ]
            )
            triple_tokens = set(_tokenize(triple_text))
            if not triple_tokens:
                continue

            overlap = 0
            for qtok in query_tokens:
                for ttok in triple_tokens:
                    if qtok == ttok or qtok.startswith(ttok) or ttok.startswith(qtok):
                        overlap += 1
                        break
            if overlap <= 0:
                continue

            created_at = int(triple.get("created_at") or now_ms)
            age_days = max(0.0, (now_ms - created_at) / (1000 * 86400))
            recency = max(0.0, 1.0 - (age_days / 30.0))
            score = overlap + (recency * 0.35)
            enriched = dict(triple)
            enriched["score"] = round(score, 4)
            enriched["text"] = (
                f"{triple.get('subject', 'user')} "
                f"{triple.get('predicate', 'related_to')} "
                f"{triple.get('object', '')}"
            )
            scored.append((score, enriched))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[: max(1, int(limit))]]

    # ---------------------------------------------------------------------
    # Embedding operations (SQL-side similarity)
    # ---------------------------------------------------------------------

    def set_message_embedding(self, message_id: int, embedding) -> bool:
        blob = _vector_to_blob(embedding)
        if blob is None:
            return False
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO embeddings_messages (message_id, principal_id, vector)
                VALUES (?, ?, ?)
                """,
                (int(message_id), self.principal_id, blob),
            )
            self.conn.commit()
            return True

    def search_message_embeddings(
        self,
        query_embedding,
        chat_id: Optional[str] = None,
        k: int = 8,
        recency_weight: float = 0.3,
    ) -> List[Dict]:
        blob = _vector_to_blob(query_embedding)
        if blob is None:
            return []

        now = _now_ms()
        week_ms = 7 * 24 * 60 * 60 * 1000
        recency_weight = max(0.0, min(1.0, float(recency_weight)))
        sim_weight = 1.0 - recency_weight

        where = "m.principal_id = ?"
        params: List = [blob, sim_weight, recency_weight, now, week_ms, blob, self.principal_id]
        if chat_id:
            where += " AND m.chat_id = ?"
            params.append(chat_id)
        params.append(int(k))

        query = f"""
            SELECT
                m.message_id,
                m.chat_id,
                m.role,
                m.content_enc,
                m.created_at,
                cosine_sim(e.vector, ?) AS similarity,
                (
                    (? * cosine_sim(e.vector, ?)) +
                    (? * MAX(0.0, 1.0 - ((? - m.created_at) * 1.0 / ?)))
                ) AS score
            FROM embeddings_messages e
            JOIN messages m ON m.message_id = e.message_id
            WHERE {where}
            ORDER BY score DESC
            LIMIT ?
        """

        with self._lock:
            rows = self.conn.execute(query, tuple(params)).fetchall()

        out = []
        for row in rows:
            out.append(
                {
                    "message_id": int(row["message_id"]),
                    "chat_id": row["chat_id"],
                    "role": row["role"],
                    "content": self._decrypt_text(row["content_enc"]),
                    "timestamp": int(row["created_at"]),
                    "similarity": float(row["similarity"] or 0.0),
                    "score": float(row["score"] or 0.0),
                }
            )
        return out

    def get_embedding_stats(self) -> Dict[str, int]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM embeddings_messages WHERE principal_id = ?) AS message_embeddings,
                    (SELECT COUNT(*) FROM embeddings_facts WHERE principal_id = ?) AS fact_embeddings
                """,
                (self.principal_id, self.principal_id),
            ).fetchone()
        if not row:
            return {"message_embeddings": 0, "fact_embeddings": 0}
        return {
            "message_embeddings": int(row["message_embeddings"] or 0),
            "fact_embeddings": int(row["fact_embeddings"] or 0),
        }

    # ---------------------------------------------------------------------
    # Ingestion job queue operations
    # ---------------------------------------------------------------------

    def enqueue_ingestion_job(self, message_id: int, source: str) -> Optional[int]:
        with self._lock:
            now = _now_ms()
            self.conn.execute(
                """
                INSERT INTO ingestion_jobs
                (principal_id, message_id, source, status, attempts, last_error, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', 0, NULL, ?, ?)
                ON CONFLICT(principal_id, message_id, source)
                DO NOTHING
                """,
                (self.principal_id, int(message_id), source, now, now),
            )
            row = self.conn.execute(
                """
                SELECT job_id FROM ingestion_jobs
                WHERE principal_id = ? AND message_id = ? AND source = ?
                """,
                (self.principal_id, int(message_id), source),
            ).fetchone()
            self.conn.commit()
            return int(row["job_id"]) if row else None

    def fetch_due_jobs(self, limit: int = 25) -> List[Dict]:
        with self._lock:
            now = _now_ms()
            rows = self.conn.execute(
                """
                SELECT job_id, message_id, source, status, attempts, created_at, updated_at
                FROM ingestion_jobs
                WHERE principal_id = ?
                  AND status IN ('queued', 'retry')
                  AND updated_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (self.principal_id, now, int(limit)),
            ).fetchall()

        return [dict(row) for row in rows]

    def list_recent_ingestion_jobs(self, limit: int = 25) -> List[Dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT job_id, message_id, source, status, attempts, last_error, created_at, updated_at
                FROM ingestion_jobs
                WHERE principal_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (self.principal_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_pending_jobs(self) -> int:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM ingestion_jobs
                WHERE principal_id = ?
                  AND status IN ('queued', 'retry', 'processing')
                """,
                (self.principal_id,),
            ).fetchone()
        return int(row["c"] or 0) if row else 0

    def claim_job(self, job_id: int) -> bool:
        with self._lock:
            now = _now_ms()
            cur = self.conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'processing', attempts = attempts + 1, updated_at = ?
                WHERE principal_id = ? AND job_id = ? AND status IN ('queued', 'retry')
                """,
                (now, self.principal_id, int(job_id)),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def complete_job(self, job_id: int):
        with self._lock:
            self.conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'done', last_error = NULL, updated_at = ?
                WHERE principal_id = ? AND job_id = ?
                """,
                (_now_ms(), self.principal_id, int(job_id)),
            )
            self.conn.commit()

    def fail_job(self, job_id: int, error: str, max_attempts: int = 5):
        with self._lock:
            row = self.conn.execute(
                """
                SELECT attempts FROM ingestion_jobs
                WHERE principal_id = ? AND job_id = ?
                """,
                (self.principal_id, int(job_id)),
            ).fetchone()
            if not row:
                return

            attempts = int(row["attempts"] or 0)
            now = _now_ms()
            if attempts >= max_attempts:
                status = "dead_letter"
                next_at = now
            else:
                status = "retry"
                delay_ms = int((2 ** max(0, attempts - 1)) * 1000)
                next_at = now + delay_ms

            self.conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE principal_id = ? AND job_id = ?
                """,
                (status, str(error)[:4000], next_at, self.principal_id, int(job_id)),
            )
            self.conn.commit()

    def get_message_by_id(self, message_id: int) -> Optional[Dict]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT message_id, chat_id, role, content_enc, created_at
                FROM messages
                WHERE principal_id = ? AND message_id = ?
                """,
                (self.principal_id, int(message_id)),
            ).fetchone()
        if not row:
            return None
        return {
            "message_id": int(row["message_id"]),
            "chat_id": row["chat_id"],
            "role": row["role"],
            "content": self._decrypt_text(row["content_enc"]),
            "created_at": int(row["created_at"]),
        }

    # ---------------------------------------------------------------------
    # Checkpoint operations
    # ---------------------------------------------------------------------

    def set_sync_checkpoint(
        self,
        last_ipfs_cid: Optional[str],
        last_synced_message_id: Optional[int],
        last_sync_at: Optional[int] = None,
    ):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO sync_checkpoints (principal_id, last_ipfs_cid, last_sync_at, last_synced_message_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(principal_id)
                DO UPDATE SET
                    last_ipfs_cid = excluded.last_ipfs_cid,
                    last_sync_at = excluded.last_sync_at,
                    last_synced_message_id = excluded.last_synced_message_id
                """,
                (
                    self.principal_id,
                    last_ipfs_cid,
                    int(last_sync_at or _now_ms()),
                    last_synced_message_id,
                ),
            )
            self.conn.commit()

    def get_sync_checkpoint(self) -> Dict:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT last_ipfs_cid, last_sync_at, last_synced_message_id
                FROM sync_checkpoints WHERE principal_id = ?
                """,
                (self.principal_id,),
            ).fetchone()
        if not row:
            return {
                "last_ipfs_cid": None,
                "last_sync_at": None,
                "last_synced_message_id": None,
            }
        return {
            "last_ipfs_cid": row["last_ipfs_cid"],
            "last_sync_at": row["last_sync_at"],
            "last_synced_message_id": row["last_synced_message_id"],
        }

    # ---------------------------------------------------------------------
    # Export / import
    # ---------------------------------------------------------------------

    def export_db_bytes(self) -> bytes:
        with self._lock:
            self.conn.commit()
            with tempfile.NamedTemporaryFile(prefix="state-backup-", suffix=".db", delete=True) as tmp:
                backup_conn = sqlite3.connect(tmp.name)
                try:
                    self.conn.backup(backup_conn)
                    backup_conn.commit()
                finally:
                    backup_conn.close()
                tmp.seek(0)
                return tmp.read()

    def import_db_bytes(self, data: bytes):
        self._validate_checkpoint_bytes(data)

        with self._lock:
            self.conn.close()
            for sidecar in (Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
                try:
                    if sidecar.exists():
                        sidecar.unlink()
                except Exception:
                    pass
            with open(self.db_path, "wb") as f:
                f.write(data)
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._configure_connection(self.conn)
            # Ensures forward-compatible additive schema migrations after restore.
            self._init_schema()

    def close(self):
        with self._lock:
            if self.conn:
                self.conn.close()


_state_store_lock = threading.Lock()
_state_stores: OrderedDict[str, PrincipalStateStore] = OrderedDict()


def get_state_store(principal_id: str) -> PrincipalStateStore:
    with _state_store_lock:
        expected_dir = PrincipalStateStore._user_dir_for_principal(principal_id)
        expected_db = Path(expected_dir) / "state.db"
        store = _state_stores.get(principal_id)
        if store is not None:
            if Path(store.user_dir).resolve() != Path(expected_dir).resolve():
                try:
                    store.close()
                except Exception:
                    pass
                _state_stores.pop(principal_id, None)
                store = None
            else:
                # Mark as recently used (move to end of OrderedDict)
                _state_stores.move_to_end(principal_id)
        if store is None:
            # Evict oldest entries if at capacity
            while len(_state_stores) >= MAX_STATE_STORES:
                evicted_pid, evicted_store = _state_stores.popitem(last=False)
                try:
                    evicted_store.close()
                    logger.debug("LRU-evicted state store for principal %s", evicted_pid[:16])
                except Exception:
                    pass
            store = PrincipalStateStore(principal_id)
            _state_stores[principal_id] = store
        try:
            store.ensure_required_schema()
        except Exception as schema_error:
            logger.error(
                "State DB schema invalid for %s, recreating empty canonical DB: %s",
                principal_id[:16],
                schema_error,
            )
            try:
                store.close()
            except Exception:
                pass

            _state_stores.pop(principal_id, None)
            _quarantine_db_family(expected_db)
            store = PrincipalStateStore(principal_id)
            _state_stores[principal_id] = store
        return store


def close_all_state_stores():
    with _state_store_lock:
        stores = list(_state_stores.values())
        _state_stores.clear()
    for store in stores:
        try:
            store.close()
        except Exception:
            pass
