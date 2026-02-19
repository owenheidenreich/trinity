from unittest.mock import MagicMock, patch


class TestMemoryIngestion:
    @patch("services.memory_ingestion.MEMORY_INGESTION_ENABLED", True)
    def test_enqueue_user_message(self):
        from services.memory_ingestion import enqueue_ingestion

        mock_store = MagicMock()
        mock_store.get_messages.return_value = []
        mock_store.append_message.return_value = 42
        mock_store.enqueue_ingestion_job.return_value = 7

        with patch("services.memory_ingestion.get_state_store", return_value=mock_store), \
             patch("services.memory_ingestion.start_ingestion_worker"), \
             patch("services.memory_ingestion._remember_principal"):
            ok = enqueue_ingestion("principal-1", "my name is owen", source="user", chat_id="chat-1")

        assert ok is True
        mock_store.append_message.assert_called_once_with("chat-1", "user", "my name is owen")
        mock_store.enqueue_ingestion_job.assert_called_once_with(42, "user")

    @patch("services.memory_ingestion.MEMORY_INGESTION_ENABLED", True)
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

        with patch("services.memory_ingestion.get_state_store", return_value=mock_store), \
             patch("services.profile_extractor.extract_memory_candidates") as mock_extract, \
             patch("services.memory_ingestion._save_extracted_facts") as mock_save_facts, \
             patch("services.memory_ingestion._ingest_graph_triples") as mock_graph, \
             patch("services.memory_ingestion._maybe_update_conversation_summary") as mock_summary:
            mock_extract.return_value = {
                "facts": [{"fact": "User works at Acme", "category": "work", "importance": 4}],
                "triples": [{"subject": "user", "predicate": "works_at", "object": "Acme"}],
            }

            _process_job("principal-1", {"message_id": 12, "source": "user"})

        mock_extract.assert_called_once_with("I work at Acme with my cofounder Sarah", source="user")
        mock_save_facts.assert_called_once()
        mock_graph.assert_called_once_with(mock_extract.return_value["triples"], "principal-1", source_message_id=12)
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

        with patch("services.memory_ingestion.get_state_store", return_value=mock_store), \
             patch("services.memory_ingestion._summarize_incremental") as mock_summarize:
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

        with patch("services.memory_ingestion.get_state_store", return_value=mock_store), \
             patch("services.memory_ingestion._summarize_incremental", return_value="Updated summary"):
            _maybe_update_conversation_summary("principal-1", "chat-1")

        mock_store.upsert_conversation_summary.assert_called_once_with("chat-1", "Updated summary", 12)
