"""Security tests for protected /tools endpoints."""

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    from middleware.rate_limit import request_counts, storage_request_counts

    request_counts.clear()
    storage_request_counts.clear()
    yield
    request_counts.clear()
    storage_request_counts.clear()


def test_document_query_requires_auth(client):
    response = client.post("/tools/documents/query", json={"query": "hello"})
    assert response.status_code == 401


def test_document_query_allows_authenticated_request(client, auth_headers):
    headers = auth_headers("/tools/documents/query")
    response = client.post("/tools/documents/query", json={}, headers=headers)
    assert response.status_code == 400
