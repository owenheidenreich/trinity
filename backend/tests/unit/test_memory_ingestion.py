from unittest.mock import MagicMock, patch


class TestMemoryIngestion:
    @patch("services.ingestion_worker.MEMORY_INGESTION_ENABLED", True)
    def test_enqueue_user_message(self):
        from services.memory_ingestion import enqueue_ingestion

        mock_store = MagicMock()
        mock_store.get_messages.return_value = []
        mock_store.append_message.return_value = 42
        mock_store.enqueue_ingestion_job.return_value = 7
        mock_store.count_pending_jobs.return_value = 0

        with patch("services.state_store.get_state_store", return_value=mock_store), \
             patch("services.ingestion_worker.start_ingestion_worker"), \
             patch("services.ingestion_worker._remember_principal"):
            ok = enqueue_ingestion("principal-1", "my name is owen", source="user", chat_id="chat-1")

        assert ok is True
        mock_store.append_message.assert_called_once_with("chat-1", "user", "my name is owen")
        mock_store.enqueue_ingestion_job.assert_called_once_with(42, "user")

    @patch("services.ingestion_worker.MEMORY_INGESTION_ENABLED", True)
    def test_enqueue_rejects_empty(self):
        from services.memory_ingestion import enqueue_ingestion

        assert enqueue_ingestion("", "hello", source="user") is False
        assert enqueue_ingestion("principal-1", "", source="user") is False

    def test_process_job_uses_unified_extraction(self):
        from services.memory_ingestion import _process_job

        mock_store = MagicMock()
        mock_store.get_message_by_id.return_value = {
            "message_id": 12,
            "chat_id": "chat-1",
            "role": "user",
            "content": "I work at Acme with my cofounder Sarah",
        }

        with patch("services.state_store.get_state_store", return_value=mock_store), \
             patch("services.ingestion_worker._index_message") as mock_index, \
             patch("services.ingestion_worker._extract_and_save") as mock_extract, \
             patch("services.ingestion_worker._maybe_update_summary") as mock_summary:

            _process_job("principal-1", {"message_id": 12, "source": "user"})

        mock_index.assert_called_once()
        mock_extract.assert_called_once_with("principal-1", "I work at Acme with my cofounder Sarah", source="user")
        mock_summary.assert_called_once_with("principal-1", "chat-1")


class TestConversationSummaries:
    def test_summary_skipped_when_not_enough_new_messages(self):
        from services.memory_ingestion import _maybe_update_conversation_summary

        mock_store = MagicMock()
        mock_store.get_conversation_summary.return_value = {
            "summary": "Existing summary",
            "last_message_id": 5,
        }
        mock_store.get_messages_since.return_value = [
            {"message_id": 6, "role": "user", "content": "one"},
            {"message_id": 7, "role": "assistant", "content": "two"},
        ]

        with patch("services.state_store.get_state_store", return_value=mock_store), \
             patch("services.ingestion_worker._summarize_incremental") as mock_summarize:
            _maybe_update_conversation_summary("principal-1", "chat-1")

        mock_summarize.assert_not_called()
        mock_store.upsert_conversation_summary.assert_not_called()

    def test_summary_persists_incremental_updates(self):
        from services.memory_ingestion import _maybe_update_conversation_summary

        mock_store = MagicMock()
        mock_store.get_conversation_summary.return_value = {
            "summary": "Old summary",
            "last_message_id": 1,
        }
        new_messages = [
            {
                "message_id": i,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"msg {i}",
            }
            for i in range(2, 13)
        ]
        mock_store.get_messages_since.return_value = new_messages

        with patch("services.state_store.get_state_store", return_value=mock_store), \
             patch("services.ingestion_worker._summarize_incremental", return_value="Updated summary"):
            _maybe_update_conversation_summary("principal-1", "chat-1")

        mock_store.upsert_conversation_summary.assert_called_once_with("chat-1", "Updated summary", 12)
