"""Chat CRUD operations mixin."""

import time
import uuid
from typing import Dict, List, Optional

from config import ARCHIVE_AFTER_DAYS
from services.state_store._base import _now_ms, logger


class ChatStoreMixin:

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
        self.auto_archive_stale_chats()

        with self._lock:
            query = (
                "SELECT chat_id, title_enc, pinned, archived, created_at, updated_at, message_count "
                "FROM chats WHERE principal_id = ? "
            )
            params: List = [self.principal_id]
            if not include_archived:
                query += "AND archived = 0 "
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
