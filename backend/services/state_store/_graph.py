"""Graph triple operations mixin."""

from typing import Dict, List, Optional

from services.state_store._base import _now_ms


class GraphStoreMixin:

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
