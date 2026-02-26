"""
Trinity — Ingestion Worker

Unified background worker for all post-message async work:
  1. Index messages into vec_knowledge for semantic retrieval
  2. Extract profile facts + graph triples via ingestion LLM
  3. Update rolling conversation summaries

Replaces:
  - memory_ingestion.py's polling loop
  - generate.py's fire-and-forget _index_semantic_async threads
  - memory.py's SemanticMemory.index_message (now uses KnowledgeStore)

Architecture:
  - Single daemon thread drains jobs from state_store's ingestion_jobs table
  - ThreadPoolExecutor bounds concurrent LLM calls (default: 2 workers)
  - Event-driven wakeup (no polling delay on hot path)
  - Atomic stats via threading
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Dict, List, Optional, Set

from config import (
    AUTO_EXTRACT_ASSISTANT_MEMORY,
    CHATS_DIR,
    MEMORY_INGESTION_ENABLED,
    MEMORY_INGESTION_QUEUE_MAXSIZE,
    LLM_TIMEOUT_TOOLS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker state
# ---------------------------------------------------------------------------

_worker_lock = threading.Lock()
_worker_started = False
_wakeup = threading.Event()

_known_principals_lock = threading.Lock()
_known_principals: Set[str] = set()

_summary_locks: Dict[str, threading.Lock] = {}
_summary_locks_guard = threading.Lock()

# bounded executor for LLM extraction calls
_executor: Optional[ThreadPoolExecutor] = None
_EXECUTOR_WORKERS = 2

# Atomic stats
_stats_lock = threading.Lock()
_stats = {
    "enqueued": 0,
    "processed": 0,
    "dropped": 0,
    "rejected_queue_full": 0,
    "errors": 0,
    "indexed": 0,
}

# Atomic backpressure counter — avoids O(N) DB queries on every enqueue
_pending_count = 0
_pending_lock = threading.Lock()

# Summary configuration
SUMMARY_TRIGGER_MESSAGES = 10
SUMMARY_MAX_TOKENS = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inc_stat(name: str, n: int = 1):
    with _stats_lock:
        _stats[name] = _stats.get(name, 0) + n


def _inc_pending(n: int = 1):
    global _pending_count
    with _pending_lock:
        _pending_count += n


def _dec_pending(n: int = 1):
    global _pending_count
    with _pending_lock:
        _pending_count = max(0, _pending_count - n)


def _get_pending() -> int:
    with _pending_lock:
        return _pending_count


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


def _all_principals() -> List[str]:
    with _known_principals_lock:
        return list(_known_principals)


def _discover_principals() -> List[str]:
    try:
        root = Path(CHATS_DIR)
        if not root.exists():
            return []
        return [
            child.name
            for child in root.iterdir()
            if child.is_dir() and (child / "state.db").exists()
        ]
    except Exception:
        return []


def _bootstrap_known_principals():
    """One-time discovery so jobs from previous process lifetimes are still drained."""
    for pid in _discover_principals():
        _remember_principal(pid)


# ---------------------------------------------------------------------------
# Message indexing (replaces generate.py _index_semantic_async)
# ---------------------------------------------------------------------------

def _index_message(principal_id: str, chat_id: str, message_id: int, role: str, content: str):
    """Index a single message into KnowledgeStore for semantic retrieval."""
    if not content or not content.strip():
        return

    try:
        from services.state_store import get_state_store
        from services.knowledge_store import KnowledgeStore

        store = get_state_store(principal_id)
        ks = KnowledgeStore(store)
        ks.index_message(
            chat_id=chat_id,
            message_id=message_id,
            role=role,
            content=content,
        )
        _inc_stat("indexed")
    except Exception as e:
        logger.debug("Message indexing failed (msg=%s): %s", message_id, e)


# ---------------------------------------------------------------------------
# Fact extraction
# ---------------------------------------------------------------------------

def _extract_and_save(principal_id: str, message_text: str, source: str):
    """Run LLM extraction and save results via KnowledgeStore."""
    from services.profile_extractor import extract_memory_candidates
    from services.memory_tools import tool_save_memory

    extracted = extract_memory_candidates(message_text, source=source)

    # Save facts
    for candidate in extracted.get("facts", []):
        try:
            success, result = tool_save_memory(candidate, principal_id)
            if success and ("Saved:" in result or "Updated" in result):
                logger.info("📝 Auto-extracted (%s): %s", source, candidate.get("fact", ""))
        except Exception as e:
            logger.debug("Fact save failed: %s", e)



# ---------------------------------------------------------------------------
# Conversation summary
# ---------------------------------------------------------------------------

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
    rendered = _build_summary_input(new_messages)
    if not rendered:
        return ""

    prompt = (
        "Update the rolling conversation summary.\n\n"
        f"Previous summary:\n{previous_summary or 'None'}\n\n"
        f"New messages:\n{rendered}\n\n"
        "Return a concise summary focused on:\n"
        "- Main topics and context\n"
        "- Decisions or commitments\n"
        "- Open/unresolved questions\n"
        "Keep the summary compact and factual."
    )

    from services.provider_factory import get_ingest_provider

    provider = get_ingest_provider()
    content = provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=SUMMARY_MAX_TOKENS,
        temperature=0.1,
        timeout=LLM_TIMEOUT_TOOLS,
    )
    return (content or "").strip()


def _maybe_update_summary(principal_id: str, chat_id: Optional[str]):
    if not chat_id:
        return

    from services.state_store import get_state_store

    store = get_state_store(principal_id)
    lock = _get_summary_lock(principal_id)
    with lock:
        current = store.get_conversation_summary(chat_id) or {}
        last_msg_id = int(current.get("last_message_id", 0) or 0)

        new_messages = store.get_messages_since(
            chat_id=chat_id, after_message_id=last_msg_id
        )
        if len(new_messages) <= SUMMARY_TRIGGER_MESSAGES:
            return

        updated = _summarize_incremental(
            current.get("summary", ""), new_messages
        )
        if not updated:
            return

        latest_id = int(new_messages[-1].get("message_id", last_msg_id))
        store.upsert_conversation_summary(chat_id, updated, latest_id)
        logger.info(
            "🧾 Summary updated: principal=%s chat=%s upto=%s",
            principal_id[:16],
            str(chat_id)[:12],
            latest_id,
        )


# ---------------------------------------------------------------------------
# Job processing
# ---------------------------------------------------------------------------

def _process_job(principal_id: str, job: Dict):
    """Process a single ingestion job: index + extract + summarize."""
    from services.state_store import get_state_store

    store = get_state_store(principal_id)
    message_id = int(job["message_id"])
    source = job.get("source", "user")

    record = store.get_message_by_id(message_id)
    if not record:
        raise ValueError(f"Message not found for ingestion job: {message_id}")

    chat_id = record.get("chat_id")
    content = record.get("content", "")
    role = record.get("role", source)

    # Step 1: Index message embedding into KnowledgeStore
    _index_message(principal_id, chat_id, message_id, role, content)

    # Step 2: Extract facts + triples via LLM
    _extract_and_save(principal_id, content, source=source)

    # Step 3: Maybe update conversation summary
    try:
        _maybe_update_summary(principal_id, chat_id)
    except Exception as e:
        logger.warning(
            "⚠️ Summary update failed: principal=%s chat=%s: %s",
            principal_id[:16],
            str(chat_id)[:12],
            e,
        )


def _drain_principal(principal_id: str) -> bool:
    """Drain all due jobs for one principal. Returns True if any work was done."""
    from services.state_store import get_state_store

    store = get_state_store(principal_id)
    due = store.fetch_due_jobs(limit=20)
    if not due:
        return False

    processed = False
    futures: List[Future] = []

    for job in due:
        job_id = int(job["job_id"])
        if not store.claim_job(job_id):
            continue

        def _run(jid=job_id, j=job):
            try:
                _process_job(principal_id, j)
                store.complete_job(jid)
                _inc_stat("processed")
                _dec_pending()
            except Exception as e:
                _inc_stat("errors")
                _dec_pending()
                store.fail_job(jid, str(e))
                logger.warning("⚠️ Ingestion job failed (job=%s): %s", jid, e)

        if _executor is not None:
            futures.append(_executor.submit(_run))
        else:
            _run()
        processed = True

    # Wait for all futures in this batch
    for f in futures:
        try:
            f.result(timeout=120)
        except Exception:
            pass

    return processed


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _worker_loop():
    """Main loop: drain all principals, then wait for wakeup signal."""
    while True:
        did_work = False
        for pid in _all_principals():
            try:
                if _drain_principal(pid):
                    did_work = True
            except Exception as e:
                logger.debug("Ingestion scan error for %s: %s", pid[:16], e)

        if did_work:
            continue

        _wakeup.wait(timeout=2.0)
        _wakeup.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_ingestion_worker():
    """Start the ingestion worker thread (idempotent)."""
    global _worker_started, _executor

    if not MEMORY_INGESTION_ENABLED:
        return

    with _worker_lock:
        if _worker_started:
            return

        _bootstrap_known_principals()
        _executor = ThreadPoolExecutor(
            max_workers=_EXECUTOR_WORKERS,
            thread_name_prefix="ingest-exec",
        )
        thread = threading.Thread(
            target=_worker_loop, daemon=True, name="ingestion-worker"
        )
        thread.start()
        _worker_started = True
        logger.info("🧵 Ingestion worker started (workers=%d)", _EXECUTOR_WORKERS)


def enqueue_ingestion(
    principal_id: str,
    message: str = "",
    source: str = "user",
    chat_id: Optional[str] = None,
    message_id: Optional[int] = None,
) -> bool:
    """Enqueue a message for background ingestion.

    Parameters match the old memory_ingestion.enqueue_ingestion() signature
    for backwards compatibility.
    """
    if not MEMORY_INGESTION_ENABLED:
        return False
    if not principal_id:
        return False
    if source != "user" and not (source == "assistant" and AUTO_EXTRACT_ASSISTANT_MEMORY):
        return False

    # Queue depth backpressure (atomic counter — O(1) instead of O(N) DB queries)
    queue_depth = _get_pending()

    if queue_depth >= MEMORY_INGESTION_QUEUE_MAXSIZE:
        _inc_stat("dropped")
        _inc_stat("rejected_queue_full")
        logger.warning(
            "⚠️ Ingestion queue full (%d/%d), dropping job for %s",
            queue_depth,
            MEMORY_INGESTION_QUEUE_MAXSIZE,
            principal_id[:16],
        )
        return False

    from services.state_store import get_state_store

    store = get_state_store(principal_id)
    _remember_principal(principal_id)

    resolved_id = message_id

    # Legacy compatibility: resolve message_id from text if not provided
    if resolved_id is None:
        if chat_id and message:
            recent = store.get_messages(chat_id=chat_id, limit=6)
            for msg in reversed(recent):
                if (
                    msg.get("role") == source
                    and (msg.get("content") or "").strip() == message.strip()
                ):
                    resolved_id = int(msg["message_id"])
                    break
        if resolved_id is None and message:
            target_chat = chat_id or store.create_chat(title="New Chat")
            resolved_id = store.append_message(target_chat, source, message)

    if resolved_id is None:
        _inc_stat("dropped")
        return False

    job_id = store.enqueue_ingestion_job(int(resolved_id), source)
    if job_id is None:
        _inc_stat("dropped")
        return False

    _inc_stat("enqueued")
    _inc_pending()
    start_ingestion_worker()
    _wakeup.set()
    return True


def get_ingestion_stats() -> Dict:
    """Return current ingestion worker stats."""
    queue_depth = _get_pending()

    with _stats_lock:
        stats_copy = dict(_stats)

    return {
        **stats_copy,
        "queue_depth": queue_depth,
        "queue_max": MEMORY_INGESTION_QUEUE_MAXSIZE,
        "enabled": MEMORY_INGESTION_ENABLED,
        "worker_started": _worker_started,
    }
