"""Tests for routes/user.py — User status, stats, and export endpoints."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    from middleware.rate_limit import request_counts, storage_request_counts
    request_counts.clear()
    storage_request_counts.clear()
    yield
    request_counts.clear()
    storage_request_counts.clear()


# =============================================================================
# Authentication
# =============================================================================


class TestUserAuth:
    def test_status_requires_auth(self, client):
        resp = client.get("/user/status")
        assert resp.status_code == 401

    def test_export_requires_auth(self, client):
        resp = client.get("/user/export")
        assert resp.status_code == 401

    def test_stats_requires_auth(self, client):
        resp = client.get("/user/stats")
        assert resp.status_code == 401


# =============================================================================
# GET /user/status
# =============================================================================


class TestGetUserStatus:
    def test_returns_storage_and_token_info(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_chats.return_value = [
            {"chatId": "c1", "pinned": True, "archived": False},
            {"chatId": "c2", "pinned": False, "archived": True},
            {"chatId": "c3", "pinned": False, "archived": False},
        ]

        with patch("routes.user.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/status")
            resp = client.get("/user/status", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["storage"]["chats_used"] == 3
        assert data["storage"]["pinned_count"] == 1
        assert data["storage"]["archived_count"] == 1
        assert "tokens" in data

    def test_empty_account_returns_zero_counts(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_chats.return_value = []

        with patch("routes.user.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/status")
            resp = client.get("/user/status", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["storage"]["chats_used"] == 0
        assert data["storage"]["pinned_count"] == 0


# =============================================================================
# GET /user/export
# =============================================================================


class TestExportUserData:
    def test_returns_full_export(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_chats.return_value = [{"chatId": "c1", "title": "My Chat"}]
        mock_store.list_facts.return_value = [{"id": 1, "text": "A fact"}]
        mock_store.list_conversation_summaries.return_value = []
        mock_store.list_recent_ingestion_jobs.return_value = []

        with patch("routes.user.get_state_store", return_value=mock_store), \
             patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/export")
            resp = client.get("/user/export", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert "principalId" in data
        assert "generatedAt" in data
        assert "chats" in data
        assert "memory" in data
        assert len(data["chats"]) == 1


# =============================================================================
# GET /user/stats
# =============================================================================


class TestGetUserStats:
    def test_returns_profile_and_chat_stats(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_chats.return_value = [
            {"chatId": "c1", "messageCount": 10},
            {"chatId": "c2", "messageCount": 5},
        ]
        mock_store.list_facts.return_value = [
            {"id": 1, "text": "Active", "deleted": False, "invalid_at": None},
            {"id": 2, "text": "Deleted", "deleted": True, "invalid_at": None},
        ]
        mock_store.list_conversation_summaries.return_value = []
        mock_store.list_recent_ingestion_jobs.return_value = []

        with patch("routes.user.get_state_store", return_value=mock_store), \
             patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/stats")
            resp = client.get("/user/stats", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profile"]["activeFacts"] == 1
        assert data["profile"]["deletedFacts"] == 1
        assert data["chats"]["count"] == 2
        assert data["chats"]["totalMessages"] == 15
        assert data["encryption"]["algorithm"] == "AES-256-GCM"

    def test_no_chats_no_facts(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_chats.return_value = []
        mock_store.list_facts.return_value = []
        mock_store.list_conversation_summaries.return_value = []
        mock_store.list_recent_ingestion_jobs.return_value = []

        with patch("routes.user.get_state_store", return_value=mock_store), \
             patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/stats")
            resp = client.get("/user/stats", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profile"]["activeFacts"] == 0
        assert data["chats"]["count"] == 0
        assert data["chats"]["totalMessages"] == 0
