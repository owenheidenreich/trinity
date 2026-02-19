"""
Memory ingestion worker.

Durable job queue backed by canonical state_store ingestion_jobs.
Extraction/summarization runs on ingestion model capacity and never blocks
user-facing generation streams.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from config import (
    AUTO_EXTRACT_ASSISTANT_MEMORY,
    CHATS_DIR,
    GRAPH_MEMORY_ENABLED,
    MEMORY_INGESTION_ENABLED,
    MEMORY_INGESTION_QUEUE_MAXSIZE,
    OLLAMA_INGEST_HOST,
    OLLAMA_INGEST_MODEL,
    OLLAMA_TIMEOUT_TOOLS,
    http_session,
)
from services.state_store import get_state_store

logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_worker_started = False
_wakeup_event = threading.Event()

_known_principals_lock = threading.Lock()
_known_principals: Set[str] = set()

_summary_locks: Dict[str, threading.Lock] = {}
_summary_locks_guard = threading.Lock()

_stats = {
    "enqueued": 0,
    "processed": 0,
    "dropped": 0,
    "rejected_queue_full": 0,
    "errors": 0,
}

SUMMARY_TRIGGER_MESSAGES = 10
SUMMARY_MAX_TOKENS = 500


def _get_summary_lock(principal_id: str) -> threading.Lock:
    with _summary_locks_guard:
        lock = _summary_locks.get(principal_id)
        if lock is None:
            lock = threading.Lock()
            _summary_locks[principal_id] = lock
        return lock


def _remember_principal(principal_id: str):
    with _known_principals_lock:
        _known_principals.add(principal_id)


def _discover_principals() -> List[str]:
    try:
        root = Path(CHATS_DIR)
        if not root.exists():
            return []
        found = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if (child / "state.db").exists():
                found.append(child.name)
        return found
    except Exception:
        return []


def _all_principals() -> List[str]:
    with _known_principals_lock:
        return list(_known_principals)


def _bootstrap_known_principals():
    """One-time discovery so jobs from previous process lifetimes are still drained."""
    for principal_id in _discover_principals():
        _remember_principal(principal_id)


def _build_summary_input(messages: List[Dict]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 1400:
            content = content[:1400] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _summarize_incremental(previous_summary: str, new_messages: List[Dict]) -> str:
    rendered_messages = _build_summary_input(new_messages)
    if not rendered_messages:
        return ""

    prompt = (
        "Update the rolling conversation summary.\n\n"
        f"Previous summary:\n{previous_summary or 'None'}\n\n"
        f"New messages:\n{rendered_messages}\n\n"
        "Return a concise summary focused on:\n"
        "- Main topics and context\n"
        "- Decisions or commitments\n"
        "- Open/unresolved questions\n"
        "Keep the summary compact and factual."
    )

    payload = {
        "model": OLLAMA_INGEST_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_predict": SUMMARY_MAX_TOKENS,
        },
    }

    response = http_session.post(
        f"{OLLAMA_INGEST_HOST}/api/chat",
        json=payload,
        timeout=OLLAMA_TIMEOUT_TOOLS,
    )
    if response.status_code != 200:
        raise ValueError(f"Ollama status {response.status_code}")
    content = response.json().get("message", {}).get("content", "")
    return (content or "").strip()


def _save_extracted_facts(facts: List[Dict], principal_id: str, source: str):
    if not facts:
        return

    from services.memory_tools import tool_save_memory

    for candidate in facts:
        success, result = tool_save_memory(candidate, principal_id)
        if success and ("Saved:" in result or "Updated" in result):
            logger.info("📝 Auto-extracted (%s): %s", source, candidate.get("fact", ""))


def _ingest_graph_triples(triples: List[Dict], principal_id: str, source_message_id: int):
    if not GRAPH_MEMORY_ENABLED or not triples:
        return

    store = get_state_store(principal_id)
    store.insert_graph_triples(triples, source_message_id=source_message_id)


def _maybe_update_conversation_summary(principal_id: str, chat_id: Optional[str]):
    if not chat_id:
        return

    store = get_state_store(principal_id)
    lock = _get_summary_lock(principal_id)
    with lock:
        current = store.get_conversation_summary(chat_id) or {}
        last_message_id = int(current.get("last_message_id", 0) or 0)

        new_messages = store.get_messages_since(chat_id=chat_id, after_message_id=last_message_id)
        if len(new_messages) <= SUMMARY_TRIGGER_MESSAGES:
            return

        updated_summary = _summarize_incremental(current.get("summary", ""), new_messages)
        if not updated_summary:
            return

        latest_id = int(new_messages[-1].get("message_id", last_message_id))
        store.upsert_conversation_summary(chat_id, updated_summary, latest_id)
        logger.info(
            "🧾 Conversation summary updated: principal=%s chat=%s upto=%s",
            principal_id[:16],
            str(chat_id)[:12],
            latest_id,
        )


def _process_job(principal_id: str, job: Dict):
    from services.profile_extractor import extract_memory_candidates

    store = get_state_store(principal_id)
    message_id = int(job["message_id"])
    source = job.get("source", "user")

    record = store.get_message_by_id(message_id)
    if not record:
        raise ValueError(f"Message not found for ingestion job: {message_id}")

    chat_id = record.get("chat_id")
    message_text = record.get("content", "")
    extracted = extract_memory_candidates(message_text, source=source)

    facts = extracted.get("facts", [])
    triples = extracted.get("triples", [])

    if facts:
        _save_extracted_facts(facts, principal_id, source=source)
    if triples:
        _ingest_graph_triples(triples, principal_id, source_message_id=message_id)

    try:
        _maybe_update_conversation_summary(principal_id, chat_id)
    except Exception as summary_error:
        logger.warning(
            "⚠️ Summary update failed for principal=%s chat=%s: %s",
            principal_id[:16],
            str(chat_id)[:12],
            summary_error,
        )


def _drain_principal_jobs(principal_id: str) -> bool:
    processed_any = False
    store = get_state_store(principal_id)
    due = store.fetch_due_jobs(limit=20)

    for job in due:
        job_id = int(job["job_id"])
        if not store.claim_job(job_id):
            continue
        try:
            _process_job(principal_id, job)
            store.complete_job(job_id)
            _stats["processed"] += 1
            processed_any = True
        except Exception as e:
            _stats["errors"] += 1
            store.fail_job(job_id, str(e))
            logger.warning("⚠️ Memory ingestion task failed (job=%s): %s", job_id, e)

    return processed_any


def _worker_loop():
    while True:
        did_work = False
        principals = _all_principals()

        for principal_id in principals:
            try:
                if _drain_principal_jobs(principal_id):
                    did_work = True
            except Exception as e:
                logger.debug("Ingestion scan error for %s: %s", principal_id[:16], e)

        if did_work:
            continue

        _wakeup_event.wait(timeout=2.0)
        _wakeup_event.clear()


def start_ingestion_worker():
    """Start the ingestion worker once."""
    global _worker_started
    if not MEMORY_INGESTION_ENABLED:
        return

    with _worker_lock:
        if _worker_started:
            return
        _bootstrap_known_principals()
        thread = threading.Thread(target=_worker_loop, daemon=True, name="memory-ingestion-worker")
        thread.start()
        _worker_started = True
        logger.info("🧵 Memory ingestion worker started")


def enqueue_ingestion(
    principal_id: str,
    message: str = "",
    source: str = "user",
    chat_id: Optional[str] = None,
    message_id: Optional[int] = None,
) -> bool:
    """Queue canonical ingestion by message_id (legacy text fallback supported)."""
    if not MEMORY_INGESTION_ENABLED:
        return False
    if not principal_id:
        return False
    if not (source == "user" or (source == "assistant" and AUTO_EXTRACT_ASSISTANT_MEMORY)):
        return False

    # Global queue backpressure guard.
    queue_depth = 0
    for principal in _all_principals():
        try:
            pending = get_state_store(principal).count_pending_jobs()
            if isinstance(pending, (int, float)):
                queue_depth += int(pending)
        except Exception:
            pass
    if queue_depth >= MEMORY_INGESTION_QUEUE_MAXSIZE:
        _stats["dropped"] += 1
        _stats["rejected_queue_full"] += 1
        logger.warning(
            "⚠️ Ingestion queue full (%s/%s), dropping job for principal=%s source=%s",
            queue_depth,
            MEMORY_INGESTION_QUEUE_MAXSIZE,
            principal_id[:16],
            source,
        )
        return False

    store = get_state_store(principal_id)
    _remember_principal(principal_id)

    resolved_message_id = message_id

    # Legacy compatibility: resolve or persist message if caller didn't provide message_id.
    if resolved_message_id is None:
        if chat_id and message:
            recent = store.get_messages(chat_id=chat_id, limit=6)
            for msg in reversed(recent):
                if msg.get("role") == source and (msg.get("content") or "").strip() == message.strip():
                    resolved_message_id = int(msg["message_id"])
                    break
        if resolved_message_id is None and message:
            target_chat_id = chat_id or store.create_chat(title="New Chat")
            resolved_message_id = store.append_message(target_chat_id, source, message)

    if resolved_message_id is None:
        _stats["dropped"] += 1
        return False

    job_id = store.enqueue_ingestion_job(int(resolved_message_id), source)
    if job_id is None:
        _stats["dropped"] += 1
        return False

    _stats["enqueued"] += 1
    start_ingestion_worker()
    _wakeup_event.set()
    return True


def get_ingestion_stats() -> Dict:
    queue_depth = 0
    for principal in _all_principals():
        try:
            pending = get_state_store(principal).count_pending_jobs()
            if isinstance(pending, (int, float)):
                queue_depth += int(pending)
        except Exception:
            pass

    return {
        **_stats,
        "queue_depth": queue_depth,
        "queue_max": MEMORY_INGESTION_QUEUE_MAXSIZE,
        "enabled": MEMORY_INGESTION_ENABLED,
        "worker_started": _worker_started,
    }
