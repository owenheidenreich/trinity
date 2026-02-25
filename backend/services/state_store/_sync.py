"""Checkpoint and export/import operations mixin."""

import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, Optional

from services.state_store._base import _now_ms


class SyncStoreMixin:

    def set_sync_checkpoint(
        self,
        last_ipfs_cid: Optional[str],
        last_synced_message_id: Optional[int],
        last_sync_at: Optional[int] = None,
    ):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO sync_checkpoints (principal_id, last_ipfs_cid, last_sync_at, last_synced_message_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(principal_id)
                DO UPDATE SET
                    last_ipfs_cid = excluded.last_ipfs_cid,
                    last_sync_at = excluded.last_sync_at,
                    last_synced_message_id = excluded.last_synced_message_id
                """,
                (
                    self.principal_id,
                    last_ipfs_cid,
                    int(last_sync_at or _now_ms()),
                    last_synced_message_id,
                ),
            )
            self.conn.commit()

    def get_sync_checkpoint(self) -> Dict:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT last_ipfs_cid, last_sync_at, last_synced_message_id
                FROM sync_checkpoints WHERE principal_id = ?
                """,
                (self.principal_id,),
            ).fetchone()
        if not row:
            return {
                "last_ipfs_cid": None,
                "last_sync_at": None,
                "last_synced_message_id": None,
            }
        return {
            "last_ipfs_cid": row["last_ipfs_cid"],
            "last_sync_at": row["last_sync_at"],
            "last_synced_message_id": row["last_synced_message_id"],
        }

    def export_db_bytes(self) -> bytes:
        with self._lock:
            self.conn.commit()
            with tempfile.NamedTemporaryFile(prefix="state-backup-", suffix=".db", delete=True) as tmp:
                backup_conn = sqlite3.connect(tmp.name)
                try:
                    self.conn.backup(backup_conn)
                    backup_conn.commit()
                finally:
                    backup_conn.close()
                tmp.seek(0)
                return tmp.read()

    def import_db_bytes(self, data: bytes):
        self._validate_checkpoint_bytes(data)

        with self._lock:
            self.conn.close()
            for sidecar in (Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
                try:
                    if sidecar.exists():
                        sidecar.unlink()
                except Exception:
                    pass
            with open(self.db_path, "wb") as f:
                f.write(data)
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._configure_connection(self.conn)
            self._init_schema()
