"""
Integration Test Configuration
================================
Fixtures shared across integration tests. These tests require a running
llama-server instance and are skipped automatically if it's unavailable.

Run integration tests:
    pytest tests/integration/ -v --timeout=120

IMPORTANT:
    - These tests hit real llama-server (not mocked)
    - Ensure llama-server is running locally on port 8081
    - A model must be loaded
"""

import os
import sys
import time

import pytest
import requests


@pytest.fixture(scope="session")
def llm_available():
    """Skip the entire integration test session if llama-server is not running."""
    try:
        resp = requests.get("http://localhost:8081/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                return True
        pytest.skip("llama-server running but not healthy")
    except (requests.ConnectionError, requests.Timeout):
        pytest.skip("llama-server not available — skipping integration tests")


@pytest.fixture(scope="session")
def app():
    """Create Flask app for integration testing."""
    # Set environment before importing
    os.environ.setdefault("CHATS_DIR", "/tmp/trinity/integration_tests")

    from inference_server import app
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client for integration tests."""
    return app.test_client()
