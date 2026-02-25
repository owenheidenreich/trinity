"""Embedding operations mixin (SQL-side similarity)."""

from typing import Dict, List, Optional

from services.state_store._base import _now_ms, _vector_to_blob


class EmbeddingStoreMixin:

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
