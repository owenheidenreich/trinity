"""Tests for routes/memory.py — Memory fact CRUD endpoints."""

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


class TestMemoryAuth:
    def test_get_memory_requires_auth(self, client):
        resp = client.get("/user/memory")
        assert resp.status_code == 401

    def test_add_fact_requires_auth(self, client):
        resp = client.post("/user/memory/fact", json={"fact": "test"})
        assert resp.status_code == 401

    def test_edit_fact_requires_auth(self, client):
        resp = client.patch("/user/memory/fact/1", json={"text": "updated"})
        assert resp.status_code == 401

    def test_delete_fact_requires_auth(self, client):
        resp = client.delete("/user/memory/fact/1")
        assert resp.status_code == 401


# =============================================================================
# GET /user/memory
# =============================================================================


class TestGetUserMemory:
    def test_returns_memory_payload(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_facts.return_value = [
            {"id": 1, "text": "Likes Python", "category": "preferences"},
        ]
        mock_store.list_conversation_summaries.return_value = []
        mock_store.list_recent_ingestion_jobs.return_value = []

        with patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/memory")
            resp = client.get("/user/memory", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["version"] == "3.0"
        assert len(data["facts"]) == 1
        assert data["facts"][0]["text"] == "Likes Python"

    def test_raw_flag_includes_graph_triples(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.list_facts.return_value = []
        mock_store.list_conversation_summaries.return_value = []
        mock_store.list_recent_ingestion_jobs.return_value = []
        mock_store.list_graph_triples.return_value = [{"s": "User", "p": "likes", "o": "Python"}]
        mock_store.get_sync_checkpoint.return_value = None

        with patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/memory")
            resp = client.get("/user/memory?raw=true", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert "graph_triples" in data
        assert len(data["graph_triples"]) == 1


# =============================================================================
# POST /user/memory (retired)
# =============================================================================


class TestUpdateUserMemoryRetired:
    def test_returns_410_gone(self, client, auth_headers):
        with patch("routes.memory.get_state_store"):
            headers = auth_headers("/user/memory")
            resp = client.post("/user/memory", json={"facts": []}, headers=headers)

        assert resp.status_code == 410
        data = resp.get_json()
        assert "retired" in data["error"].lower() or "Route retired" in data["error"]


# =============================================================================
# POST /user/memory/fact
# =============================================================================


class TestAddMemoryFact:
    def test_creates_fact_successfully(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.create_fact.return_value = 42
        mock_store.get_fact.return_value = {
            "id": 42, "text": "Loves coding", "category": "preferences",
        }

        with patch("routes.memory.get_state_store", return_value=mock_store), \
             patch("services.embeddings.embed_text", return_value=None):
            headers = auth_headers("/user/memory/fact")
            resp = client.post("/user/memory/fact", json={"fact": "Loves coding"}, headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["fact_id"] == 42

    def test_empty_text_returns_400(self, client, auth_headers):
        with patch("routes.memory.get_state_store"):
            headers = auth_headers("/user/memory/fact")
            resp = client.post("/user/memory/fact", json={"fact": ""}, headers=headers)

        assert resp.status_code == 400

    def test_missing_text_returns_400(self, client, auth_headers):
        with patch("routes.memory.get_state_store"):
            headers = auth_headers("/user/memory/fact")
            resp = client.post("/user/memory/fact", json={}, headers=headers)

        assert resp.status_code == 400

    def test_accepts_text_key(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.create_fact.return_value = 1
        mock_store.get_fact.return_value = {"id": 1, "text": "Via text key"}

        with patch("routes.memory.get_state_store", return_value=mock_store), \
             patch("services.embeddings.embed_text", return_value=None):
            headers = auth_headers("/user/memory/fact")
            resp = client.post("/user/memory/fact", json={"text": "Via text key"}, headers=headers)

        assert resp.status_code == 200

    def test_importance_clamped_to_range(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.create_fact.return_value = 1
        mock_store.get_fact.return_value = {"id": 1, "text": "test"}

        with patch("routes.memory.get_state_store", return_value=mock_store), \
             patch("services.embeddings.embed_text", return_value=None):
            headers = auth_headers("/user/memory/fact")
            resp = client.post(
                "/user/memory/fact",
                json={"fact": "test", "importance": 99},
                headers=headers,
            )

        assert resp.status_code == 200
        call_kwargs = mock_store.create_fact.call_args
        assert call_kwargs.kwargs.get("importance", call_kwargs[1].get("importance")) <= 5


# =============================================================================
# PATCH /user/memory/fact/<id>
# =============================================================================


class TestEditMemoryFact:
    def test_updates_fact_text(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.update_fact.return_value = True
        mock_store.get_fact.return_value = {"id": 1, "text": "Updated text"}

        with patch("routes.memory.get_state_store", return_value=mock_store), \
             patch("services.embeddings.embed_text", return_value=None):
            headers = auth_headers("/user/memory/fact/1")
            resp = client.patch("/user/memory/fact/1", json={"text": "Updated text"}, headers=headers)

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_empty_text_returns_400(self, client, auth_headers):
        with patch("routes.memory.get_state_store"):
            headers = auth_headers("/user/memory/fact/1")
            resp = client.patch("/user/memory/fact/1", json={"text": ""}, headers=headers)

        assert resp.status_code == 400

    def test_no_updates_returns_400(self, client, auth_headers):
        with patch("routes.memory.get_state_store"):
            headers = auth_headers("/user/memory/fact/1")
            resp = client.patch("/user/memory/fact/1", json={}, headers=headers)

        assert resp.status_code == 400

    def test_fact_not_found_returns_404(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.update_fact.return_value = False

        with patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/memory/fact/999")
            resp = client.patch("/user/memory/fact/999", json={"text": "new"}, headers=headers)

        assert resp.status_code == 404


# =============================================================================
# DELETE /user/memory/fact/<id>
# =============================================================================


class TestDeleteMemoryFact:
    def test_soft_deletes_fact(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.soft_delete_fact.return_value = True

        with patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/memory/fact/1")
            resp = client.delete("/user/memory/fact/1", headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["fact_id"] == 1
        assert "deletedAt" in data

    def test_nonexistent_fact_returns_404(self, client, auth_headers):
        mock_store = MagicMock()
        mock_store.soft_delete_fact.return_value = False

        with patch("routes.memory.get_state_store", return_value=mock_store):
            headers = auth_headers("/user/memory/fact/999")
            resp = client.delete("/user/memory/fact/999", headers=headers)

        assert resp.status_code == 404
