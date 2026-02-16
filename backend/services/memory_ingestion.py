"""
Memory Ingestion Worker
=======================
Single async ingestion queue for profile facts and graph triples.
"""

import logging
import queue
import threading
from typing import Dict

from config import (
    AUTO_EXTRACT_ASSISTANT_MEMORY,
    GRAPH_MEMORY_ENABLED,
    MEMORY_INGESTION_ENABLED,
    MEMORY_INGESTION_QUEUE_MAXSIZE,
)

logger = logging.getLogger(__name__)

_ingestion_queue: "queue.Queue[Dict]" = queue.Queue(maxsize=MEMORY_INGESTION_QUEUE_MAXSIZE)
_worker_lock = threading.Lock()
_worker_started = False
_stats = {
    "enqueued": 0,
    "processed": 0,
    "dropped": 0,
    "errors": 0,
}


def _process_task(task: Dict):
    principal_id = task["principal_id"]
    message = task["message"]
    source = task.get("source", "user")
    chat_id = task.get("chat_id")

    from services.profile_extractor import auto_extract_and_save

    # Profile extraction: user source always, assistant source only when explicitly enabled.
    if source == "user" or (source == "assistant" and AUTO_EXTRACT_ASSISTANT_MEMORY):
        auto_extract_and_save(message, principal_id, source=source)

    if GRAPH_MEMORY_ENABLED and source == "user":
        from services.graph_extractor import extract_graph_triples
        from services.graph_memory import get_graph_memory

        triples = extract_graph_triples(message, source=source)
        if triples:
            graph = get_graph_memory(principal_id)
            graph.ingest_triples(triples, source=source, chat_id=chat_id)


def _worker_loop():
    while True:
        task = _ingestion_queue.get()
        if task is None:
            _ingestion_queue.task_done()
            continue
        try:
            _process_task(task)
            _stats["processed"] += 1
        except Exception as e:
            _stats["errors"] += 1
            logger.warning("⚠️ Memory ingestion task failed: %s", e)
        finally:
            _ingestion_queue.task_done()


def start_ingestion_worker():
    """Start the ingestion worker once."""
    global _worker_started
    if not MEMORY_INGESTION_ENABLED:
        return

    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, daemon=True, name="memory-ingestion-worker")
        thread.start()
        _worker_started = True
        logger.info("🧵 Memory ingestion worker started")


def enqueue_ingestion(principal_id: str, message: str, source: str = "user", chat_id: str = None) -> bool:
    """Queue a message for async profile/graph ingestion."""
    if not MEMORY_INGESTION_ENABLED:
        return False
    if not principal_id or not message:
        return False

    start_ingestion_worker()
    task = {
        "principal_id": principal_id,
        "message": message,
        "source": source,
        "chat_id": chat_id,
    }
    try:
        _ingestion_queue.put_nowait(task)
        _stats["enqueued"] += 1
        return True
    except queue.Full:
        _stats["dropped"] += 1
        logger.warning("⚠️ Memory ingestion queue full; dropping task for %s", principal_id[:16])
        return False


def get_ingestion_stats() -> Dict:
    return {
        **_stats,
        "queue_depth": _ingestion_queue.qsize(),
        "enabled": MEMORY_INGESTION_ENABLED,
        "worker_started": _worker_started,
    }
