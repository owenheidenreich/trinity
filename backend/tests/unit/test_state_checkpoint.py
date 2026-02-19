import base64
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from encryption import EncryptionUtils
from services.state_checkpoint import restore_state_checkpoint_from_ipfs
from services.state_store import close_all_state_stores, get_state_store


def _build_sqlite_bytes(db_path: Path, schema_sql: str) -> bytes:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    return db_path.read_bytes()


class TestStateCheckpointSafety:
    def test_import_rejects_db_without_required_tables(self, tmp_path):
        principal = "checkpoint-test-user-a"

        close_all_state_stores()
        with patch("services.state_store.CHATS_DIR", str(tmp_path)):
            store = get_state_store(principal)
            store.create_chat(chat_id="chat-1", title="Baseline")
            assert len(store.list_chats(include_archived=True)) == 1

            invalid_bytes = _build_sqlite_bytes(
                tmp_path / "invalid.db",
                "CREATE TABLE not_canonical (id INTEGER PRIMARY KEY);",
            )
            with pytest.raises(ValueError, match="missing required tables"):
                store.import_db_bytes(invalid_bytes)

            # Existing canonical DB must remain usable after failed import.
            chats = store.list_chats(include_archived=True)
            assert len(chats) == 1
            assert chats[0]["chatId"] == "chat-1"
        close_all_state_stores()

    def test_restore_skips_invalid_checkpoint_then_uses_valid_one(self, tmp_path):
        principal = "checkpoint-test-user-b"

        close_all_state_stores()
        with patch("services.state_store.CHATS_DIR", str(tmp_path)), patch(
            "services.state_checkpoint.CHATS_DIR", str(tmp_path)
        ):
            store = get_state_store(principal)
            store.create_chat(chat_id="chat-restore", title="Restore Target")
            valid_db_bytes = store.export_db_bytes()
            invalid_db_bytes = _build_sqlite_bytes(
                tmp_path / "invalid-restore.db",
                "CREATE TABLE wrong_table (id INTEGER PRIMARY KEY);",
            )

            def _encode_payload(db_bytes: bytes) -> bytes:
                payload = {
                    "type": "state_db",
                    "updatedAt": int(time.time() * 1000),
                    "db_b64": base64.b64encode(db_bytes).decode("utf-8"),
                }
                encrypted = EncryptionUtils.encrypt_chat(payload, principal)
                return json.dumps(encrypted).encode("utf-8")

            raw_by_cid = {
                "cid-invalid": _encode_payload(invalid_db_bytes),
                "cid-valid": _encode_payload(valid_db_bytes),
            }
            filename = f"{principal[:16]}_state_checkpoint.json"

            with patch(
                "services.state_checkpoint.get_lighthouse_uploads",
                return_value=[
                    {"fileName": filename, "cid": "cid-invalid", "createdAt": 2},
                    {"fileName": filename, "cid": "cid-valid", "createdAt": 1},
                ],
            ), patch(
                "services.state_checkpoint.download_from_ipfs",
                side_effect=lambda cid: raw_by_cid.get(cid),
            ):
                assert restore_state_checkpoint_from_ipfs(principal) is True

            chats = store.list_chats(include_archived=True)
            assert any(chat["chatId"] == "chat-restore" for chat in chats)
        close_all_state_stores()
