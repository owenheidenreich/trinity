"""
Graph Memory Service
====================
Per-user relationship graph backed by Kuzu when available.
Sidecar JSON keeps retrieval resilient even if Kuzu is unavailable.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List

from config import CHATS_DIR, GRAPH_MEMORY_TOP_K

logger = logging.getLogger(__name__)

try:
    import kuzu  # type: ignore

    _KUZU_AVAILABLE = True
except Exception:
    kuzu = None  # type: ignore
    _KUZU_AVAILABLE = False


def _normalize_node_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or ""))[:96].strip("_")


def _tokenize(text: str) -> List[str]:
    lowered = (text or "").lower()
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
    return [tok for tok in cleaned.split() if len(tok) > 2]


class GraphMemory:
    """User-scoped graph memory facade."""

    def __init__(self, principal_id: str):
        self.principal_id = principal_id
        self.user_dir = Path(CHATS_DIR) / principal_id
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.graph_path = self.user_dir / "identity.kuzu"
        self.sidecar_path = self.user_dir / "identity_triples.json"
        self._lock = threading.Lock()
        self._kuzu_ready = False
        self._conn = None
        self._init_graph_store()

    def _init_graph_store(self):
        # Always ensure identity.kuzu path exists as the canonical graph substrate path.
        self.graph_path.touch(exist_ok=True)
        if not _KUZU_AVAILABLE:
            return

        try:
            db = kuzu.Database(str(self.graph_path))
            self._conn = kuzu.Connection(db)
            self._ensure_schema()
            self._kuzu_ready = True
        except Exception as e:
            logger.warning("⚠️ Kuzu graph init failed for %s: %s", self.principal_id[:16], e)
            self._kuzu_ready = False

    def _ensure_schema(self):
        if not self._conn:
            return
        statements = [
            "CREATE NODE TABLE UserNode(id STRING, label STRING, PRIMARY KEY(id));",
            "CREATE NODE TABLE EntityNode(id STRING, label STRING, kind STRING, PRIMARY KEY(id));",
            "CREATE REL TABLE Related(FROM UserNode TO EntityNode, predicate STRING, source STRING, updated_at INT64);",
        ]
        for statement in statements:
            try:
                self._conn.execute(statement)
            except Exception:
                # Table probably already exists; continue.
                pass

    def _load_sidecar(self) -> List[Dict]:
        if not self.sidecar_path.exists():
            return []
        try:
            with open(self.sidecar_path, "r") as f:
                rows = json.load(f)
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def _save_sidecar(self, triples: List[Dict]):
        with open(self.sidecar_path, "w") as f:
            json.dump(triples, f)

    def _upsert_kuzu(self, triple: Dict):
        if not self._kuzu_ready or not self._conn:
            return

        sid = _normalize_node_id(triple.get("subject", "user")) or "user"
        oid = _normalize_node_id(triple.get("object", "unknown")) or "unknown"
        subject_label = str(triple.get("subject", "user")).replace("'", " ")
        object_label = str(triple.get("object", "unknown")).replace("'", " ")
        object_kind = str(triple.get("object_kind", "entity")).replace("'", " ")
        predicate = str(triple.get("predicate", "related_to")).replace("'", " ")
        source = str(triple.get("source", "user")).replace("'", " ")
        now_ms = int(time.time() * 1000)

        queries = [
            f"MERGE (u:UserNode {{id: '{sid}'}}) SET u.label = '{subject_label}'",
            f"MERGE (e:EntityNode {{id: '{oid}'}}) SET e.label = '{object_label}', e.kind = '{object_kind}'",
            (
                "MATCH (u:UserNode {id: '"
                + sid
                + "'}), (e:EntityNode {id: '"
                + oid
                + "'}) "
                + "MERGE (u)-[r:Related {predicate: '"
                + predicate
                + "'}]->(e) "
                + "SET r.source = '"
                + source
                + "', r.updated_at = "
                + str(now_ms)
            ),
        ]
        for query in queries:
            try:
                self._conn.execute(query)
            except Exception:
                # Best-effort Kuzu write; sidecar remains authoritative fallback.
                pass

    def ingest_triples(self, triples: List[Dict], source: str = "user", chat_id: str = None) -> int:
        """Ingest triples into sidecar and Kuzu."""
        if not triples:
            return 0
        now_ms = int(time.time() * 1000)
        added = 0
        with self._lock:
            rows = self._load_sidecar()
            existing = {
                (
                    r.get("subject", "").lower(),
                    r.get("predicate", "").lower(),
                    r.get("object", "").lower(),
                )
                for r in rows
            }
            for triple in triples:
                key = (
                    str(triple.get("subject", "")).lower(),
                    str(triple.get("predicate", "")).lower(),
                    str(triple.get("object", "")).lower(),
                )
                if key in existing:
                    continue
                row = dict(triple)
                row["source"] = source
                row["chat_id"] = chat_id
                row["created_at"] = now_ms
                rows.append(row)
                existing.add(key)
                added += 1
                self._upsert_kuzu(row)
            self._save_sidecar(rows)
        if added > 0:
            try:
                from services.user_data_store import notify_graph_changed

                notify_graph_changed(self.principal_id)
            except Exception:
                pass
        return added

    def retrieve_relevant(self, query: str, limit: int = GRAPH_MEMORY_TOP_K) -> List[Dict]:
        """Retrieve relevant triples by lexical overlap scoring."""
        tokens = set(_tokenize(query))
        if not tokens:
            return []

        with self._lock:
            rows = self._load_sidecar()

        scored = []
        for triple in rows:
            triple_text = " ".join(
                [
                    str(triple.get("subject", "")),
                    str(triple.get("predicate", "")),
                    str(triple.get("object", "")),
                    str(triple.get("object_kind", "")),
                ]
            )
            triple_tokens = set(_tokenize(triple_text))
            if not triple_tokens:
                continue
            overlap = 0
            for query_tok in tokens:
                for triple_tok in triple_tokens:
                    if query_tok == triple_tok:
                        overlap += 1
                        break
                    if query_tok.startswith(triple_tok) or triple_tok.startswith(query_tok):
                        overlap += 1
                        break
            if overlap <= 0:
                continue

            recency = 1.0
            created_at = int(triple.get("created_at") or int(time.time() * 1000))
            age_days = max(0.0, (int(time.time() * 1000) - created_at) / (1000 * 86400))
            recency = max(0.0, 1.0 - (age_days / 30.0))
            confidence = float(triple.get("confidence", 0.6))
            score = overlap + (confidence * 0.5) + (recency * 0.35)
            scored.append((score, triple))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, triple in scored[: max(1, limit)]:
            enriched = dict(triple)
            enriched["score"] = round(score, 4)
            enriched["text"] = (
                f"{triple.get('subject', 'user')} "
                f"{triple.get('predicate', 'related_to')} "
                f"{triple.get('object', '')}"
            )
            results.append(enriched)
        return results

    def get_stats(self) -> Dict:
        with self._lock:
            rows = self._load_sidecar()
        return {
            "triple_count": len(rows),
            "kuzu_available": _KUZU_AVAILABLE,
            "kuzu_ready": self._kuzu_ready,
            "graph_path": str(self.graph_path),
        }


_instances: Dict[str, GraphMemory] = {}
_instances_lock = threading.Lock()


def get_graph_memory(principal_id: str) -> GraphMemory:
    with _instances_lock:
        instance = _instances.get(principal_id)
        if instance is None:
            instance = GraphMemory(principal_id)
            _instances[principal_id] = instance
        return instance
