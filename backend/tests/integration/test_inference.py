"""
Integration Tests — Real Ollama Inference
==========================================
These tests hit a real Ollama instance. They validate the full request pipeline:
  - Flask routing → request parsing → Ollama API call → response formatting.

Skip conditions:
  - Ollama not running → entire file skipped
  - No model available → entire file skipped

Run with:
    pytest tests/integration/test_inference.py -v --timeout=120
"""

import json
import time

import pytest

pytestmark = pytest.mark.integration


class TestBasicGeneration:
    """Test the core /generate endpoint with real Ollama."""

    def test_health_check(self, client, ollama_available):
        """Health endpoint should return 200 and model info."""
        resp = client.get("/health")
        data = resp.get_json()
        assert resp.status_code in (200, 503)  # 503 if Ollama still loading
        assert "status" in data
        assert "model" in data
        assert "provider_id" in data

    def test_simple_generate(self, client, ollama_available, test_model):
        """Simple generate should return a response from Ollama."""
        resp = client.post("/generate/simple", json={
            "prompt": "What is 2+2? Answer with just the number.",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True
        assert len(data.get("response", "")) > 0

    def test_empty_prompt_rejected(self, client, ollama_available):
        """Empty prompt should return 400."""
        resp = client.post("/generate/simple", json={"prompt": ""})
        assert resp.status_code == 400

    def test_generate_with_options(self, client, ollama_available, test_model):
        """Generate with custom temperature and max_length."""
        resp = client.post("/generate/simple", json={
            "prompt": "Say hello in one word.",
            "max_length": 10,
            "temperature": 0.1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True


class TestStreamingGeneration:
    """Test SSE streaming endpoints."""

    def test_simple_stream(self, client, ollama_available, test_model):
        """Simple stream should return SSE events."""
        resp = client.post("/generate/simple/stream", json={
            "prompt": "Say hello",
            "max_length": 20,
        })
        assert resp.status_code == 200
        assert "text/event-stream" in resp.content_type

        # Parse SSE events
        events = []
        for line in resp.data.decode().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        # Should have at least one token event and a done event
        assert len(events) > 0
        assert any(e.get("done") for e in events)


class TestEndpointValidation:
    """Test request validation on real endpoints."""

    def test_prompt_length_limit(self, client, ollama_available):
        """Prompts exceeding MAX_PROMPT_LENGTH should be rejected."""
        from config import MAX_PROMPT_LENGTH
        long_prompt = "a" * (MAX_PROMPT_LENGTH + 1)
        resp = client.post("/generate", json={
            "prompt": long_prompt,
        }, headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 400

    def test_origin_validation(self, client, ollama_available):
        """Bad origins should be rejected on POST."""
        resp = client.post("/generate", json={"prompt": "test"},
                          headers={"Origin": "https://evil.com"})
        assert resp.status_code == 403

    def test_metrics_endpoint(self, client, ollama_available):
        """Metrics should return Prometheus format."""
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_tools_status(self, client, ollama_available):
        """Tools status endpoint should work."""
        resp = client.get("/tools/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "ollama_connected" in data
        assert "tools" in data
