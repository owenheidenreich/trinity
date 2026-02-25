"""
Canonical per-principal encrypted state store.

This package is the backend source of truth for chats, messages, memory facts,
conversation summaries, graph triples, embeddings, and ingestion jobs.

PrincipalStateStore is assembled from domain-specific mixins:
  _base.py        — schema, encryption, connection management
  _chats.py       — chat CRUD + auto-archiving
  _messages.py    — message append/retrieve/search
  _facts.py       — memory fact CRUD + bulk replace
  _summaries.py   — conversation summary CRUD
  _graph.py       — graph triple insert/list/search
  _embeddings.py  — embedding storage + similarity search
  _ingestion.py   — ingestion job queue
  _sync.py        — checkpoint + export/import
"""

import logging
import threading
from collections import OrderedDict
from pathlib import Path

from config import CHATS_DIR, MAX_STATE_STORES  # noqa: F401 — CHATS_DIR re-exported for test patching
from services.state_store._base import StateStoreBase, _quarantine_db_family
from services.state_store._chats import ChatStoreMixin
from services.state_store._embeddings import EmbeddingStoreMixin
from services.state_store._facts import FactStoreMixin
from services.state_store._graph import GraphStoreMixin
from services.state_store._ingestion import IngestionStoreMixin
from services.state_store._messages import MessageStoreMixin
from services.state_store._summaries import SummaryStoreMixin
from services.state_store._sync import SyncStoreMixin

logger = logging.getLogger(__name__)


class PrincipalStateStore(
    ChatStoreMixin,
    MessageStoreMixin,
    FactStoreMixin,
    SummaryStoreMixin,
    GraphStoreMixin,
    EmbeddingStoreMixin,
    IngestionStoreMixin,
    SyncStoreMixin,
    StateStoreBase,
):
    """Canonical state store for one principal — assembled from domain mixins."""
    pass


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
                _state_stores.move_to_end(principal_id)
        if store is None:
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
