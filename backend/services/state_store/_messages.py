"""Message storage operations mixin."""

from typing import Dict, List, Optional

from services.state_store._base import _now_ms


class MessageStoreMixin:

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
