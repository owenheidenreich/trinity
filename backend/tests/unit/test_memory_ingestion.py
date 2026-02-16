from unittest.mock import patch


class TestMemoryIngestion:
    @patch("services.memory_ingestion.MEMORY_INGESTION_ENABLED", True)
    def test_enqueue_user_message(self):
        with patch("services.memory_ingestion._process_task", return_value=None):
            from services.memory_ingestion import enqueue_ingestion, get_ingestion_stats

            ok = enqueue_ingestion("principal-1", "my name is owen", source="user", chat_id="chat-1")
            assert ok is True
            stats = get_ingestion_stats()
            assert stats["enqueued"] >= 1

    @patch("services.memory_ingestion.MEMORY_INGESTION_ENABLED", True)
    def test_enqueue_rejects_empty(self):
        from services.memory_ingestion import enqueue_ingestion

        assert enqueue_ingestion("", "hello", source="user") is False
        assert enqueue_ingestion("principal-1", "", source="user") is False
