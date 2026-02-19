"""
Backwards-compatibility shim — re-exports from ingestion_worker.

Old callers (admin.py, tests) that import from ``services.memory_ingestion``
are redirected to the new ``services.ingestion_worker`` module transparently.
"""

from services.ingestion_worker import (  # noqa: F401
    enqueue_ingestion,
    get_ingestion_stats,
    start_ingestion_worker,
    _maybe_update_summary as _maybe_update_conversation_summary,  # noqa: F401
    _process_job,  # noqa: F401
)
