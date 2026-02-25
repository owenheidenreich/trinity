"""Conversation summary operations mixin."""

from typing import Dict, Optional

from services.state_store._base import _now_ms


class SummaryStoreMixin:

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
