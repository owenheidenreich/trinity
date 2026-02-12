"""
Integration Test Configuration
================================
Fixtures shared across integration tests. These tests require a running Ollama
instance and are skipped automatically if Ollama is unavailable.

Run integration tests:
    pytest tests/integration/ -v --timeout=120

IMPORTANT:
    - These tests hit real Ollama (not mocked)
    - Ensure `ollama serve` is running locally
    - At least qwen2.5:3b should be pulled
"""

import os
import sys
import time

import pytest
import requests


@pytest.fixture(scope="session")
def ollama_available():
    """Skip the entire integration test session if Ollama is not running."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            if models:
                return models
        pytest.skip("Ollama running but no models available")
    except (requests.ConnectionError, requests.Timeout):
        pytest.skip("Ollama not available — skipping integration tests")


@pytest.fixture(scope="session")
def test_model(ollama_available):
    """Return the first available model name for testing."""
    return ollama_available[0]


@pytest.fixture(scope="session")
def app():
    """Create Flask app for integration testing."""
    # Set environment before importing
    os.environ.setdefault("CHATS_DIR", "/tmp/trinity/integration_tests")
    os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")

    from inference_server import app
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client for integration tests."""
    return app.test_client()
