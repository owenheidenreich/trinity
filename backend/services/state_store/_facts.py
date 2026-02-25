"""Memory fact CRUD operations mixin."""

from typing import Dict, List, Optional

from services.state_store._base import _blob_to_vector, _now_ms, _vector_to_blob


class FactStoreMixin:

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
