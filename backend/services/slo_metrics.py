"""
SLO Metrics
===========
Tracks runtime SLO signals for conversational quality and storage behavior.
"""

import statistics
import threading
import time
from collections import defaultdict, deque
from typing import Dict

_lock = threading.Lock()

_first_token_latencies_ms = deque(maxlen=5000)
_unsolicited_total = 0
_unsolicited_hits = 0
_ipfs_write_events = deque(maxlen=20000)  # (ts_seconds, principal)
_ipfs_by_user = defaultdict(deque)  # principal -> deque[timestamp]

_PERSONAL_QUERY_MARKERS = (
    "what do you know about me",
    "what do you remember about me",
    "what is my name",
    "what's my name",
    "who am i",
)
_UNSOLICITED_RESPONSE_MARKERS = (
    "i remember",
    "you told me",
    "welcome back",
    "as you mentioned before",
)


def _percentile(values, pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    index = int(round((len(values) - 1) * pct))
    index = max(0, min(len(values) - 1, index))
    return float(sorted(values)[index])


def record_first_token_latency(ms: float):
    with _lock:
        _first_token_latencies_ms.append(float(ms))


def record_ipfs_write(principal_id: str):
    now = time.time()
    with _lock:
        _ipfs_write_events.append((now, principal_id))
        _ipfs_by_user[principal_id].append(now)


def record_unsolicited_personal_reference(query: str, response: str):
    q = (query or "").lower()
    r = (response or "").lower()
    is_personal_query = any(marker in q for marker in _PERSONAL_QUERY_MARKERS)
    hit = (not is_personal_query) and any(marker in r for marker in _UNSOLICITED_RESPONSE_MARKERS)

    with _lock:
        global _unsolicited_total, _unsolicited_hits
        _unsolicited_total += 1
        if hit:
            _unsolicited_hits += 1


def _hour_window(values):
    cutoff = time.time() - 3600
    return [v for v in values if v >= cutoff]


def get_slo_snapshot() -> Dict:
    with _lock:
        latencies = list(_first_token_latencies_ms)
        unsolicited_total = _unsolicited_total
        unsolicited_hits = _unsolicited_hits
        write_events = list(_ipfs_write_events)
        user_events = {k: list(v) for k, v in _ipfs_by_user.items()}

    first_token = {
        "samples": len(latencies),
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_ms": round(_percentile(latencies, 0.50), 2) if latencies else 0.0,
        "p95_ms": round(_percentile(latencies, 0.95), 2) if latencies else 0.0,
    }

    unsolicited_rate = (
        float(unsolicited_hits) / float(unsolicited_total) if unsolicited_total > 0 else 0.0
    )

    cutoff = time.time() - 3600
    writes_last_hour = [event for event in write_events if event[0] >= cutoff]
    active_users = 0
    for principal, timestamps in user_events.items():
        last_hour_user = [ts for ts in timestamps if ts >= cutoff]
        if last_hour_user:
            active_users += 1

    writes_per_active_user_hour = (
        len(writes_last_hour) / active_users if active_users > 0 else 0.0
    )

    # Memory precision/recall come from deterministic policy eval (offline-safe).
    memory_precision = 0.0
    memory_recall = 0.0
    try:
        from services.memory_eval import evaluate_memory_policy

        eval_result = evaluate_memory_policy()
        memory_precision = float(eval_result.get("precision", 0.0))
        memory_recall = float(eval_result.get("recall", 0.0))
    except Exception:
        pass

    return {
        "first_token_latency": first_token,
        "memory_precision_recall": {
            "precision": round(memory_precision, 4),
            "recall": round(memory_recall, 4),
        },
        "unsolicited_personal_reference_rate": round(unsolicited_rate, 6),
        "ipfs_writes_per_active_user_hour": round(writes_per_active_user_hour, 6),
        "ipfs_writes_last_hour": len(writes_last_hour),
        "active_users_last_hour": active_users,
    }
