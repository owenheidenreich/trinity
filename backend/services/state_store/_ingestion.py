"""Ingestion job queue operations mixin."""

from typing import Dict, List, Optional

from services.state_store._base import _now_ms


class IngestionStoreMixin:

    def enqueue_ingestion_job(self, message_id: int, source: str) -> Optional[int]:
        with self._lock:
            now = _now_ms()
            self.conn.execute(
                """
                INSERT INTO ingestion_jobs
                (principal_id, message_id, source, status, attempts, last_error, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', 0, NULL, ?, ?)
                ON CONFLICT(principal_id, message_id, source)
                DO NOTHING
                """,
                (self.principal_id, int(message_id), source, now, now),
            )
            row = self.conn.execute(
                """
                SELECT job_id FROM ingestion_jobs
                WHERE principal_id = ? AND message_id = ? AND source = ?
                """,
                (self.principal_id, int(message_id), source),
            ).fetchone()
            self.conn.commit()
            return int(row["job_id"]) if row else None

    def fetch_due_jobs(self, limit: int = 25) -> List[Dict]:
        with self._lock:
            now = _now_ms()
            rows = self.conn.execute(
                """
                SELECT job_id, message_id, source, status, attempts, created_at, updated_at
                FROM ingestion_jobs
                WHERE principal_id = ?
                  AND status IN ('queued', 'retry')
                  AND updated_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (self.principal_id, now, int(limit)),
            ).fetchall()

        return [dict(row) for row in rows]

    def list_recent_ingestion_jobs(self, limit: int = 25) -> List[Dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT job_id, message_id, source, status, attempts, last_error, created_at, updated_at
                FROM ingestion_jobs
                WHERE principal_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (self.principal_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_pending_jobs(self) -> int:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM ingestion_jobs
                WHERE principal_id = ?
                  AND status IN ('queued', 'retry', 'processing')
                """,
                (self.principal_id,),
            ).fetchone()
        return int(row["c"] or 0) if row else 0

    def claim_job(self, job_id: int) -> bool:
        with self._lock:
            now = _now_ms()
            cur = self.conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'processing', attempts = attempts + 1, updated_at = ?
                WHERE principal_id = ? AND job_id = ? AND status IN ('queued', 'retry')
                """,
                (now, self.principal_id, int(job_id)),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def complete_job(self, job_id: int):
        with self._lock:
            self.conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'done', last_error = NULL, updated_at = ?
                WHERE principal_id = ? AND job_id = ?
                """,
                (_now_ms(), self.principal_id, int(job_id)),
            )
            self.conn.commit()

    def fail_job(self, job_id: int, error: str, max_attempts: int = 5):
        with self._lock:
            row = self.conn.execute(
                """
                SELECT attempts FROM ingestion_jobs
                WHERE principal_id = ? AND job_id = ?
                """,
                (self.principal_id, int(job_id)),
            ).fetchone()
            if not row:
                return

            attempts = int(row["attempts"] or 0)
            now = _now_ms()
            if attempts >= max_attempts:
                status = "dead_letter"
                next_at = now
            else:
                status = "retry"
                delay_ms = int((2 ** max(0, attempts - 1)) * 1000)
                next_at = now + delay_ms

            self.conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE principal_id = ? AND job_id = ?
                """,
                (status, str(error)[:4000], next_at, self.principal_id, int(job_id)),
            )
            self.conn.commit()
