"""
Tests for services/ollama.py — Ollama LLM Service

Tests connection check, warmup, generate, streaming — all with mocked HTTP.
"""

import json

import pytest
from unittest.mock import patch, MagicMock


FAKE_MODEL = "qwen2.5-coder:32b"
FAKE_HOST = "http://localhost:11434"


@pytest.fixture(autouse=True)
def mock_config():
    """Provide consistent config for all tests."""
    with patch("services.ollama.MODEL_NAME", FAKE_MODEL), \
         patch("services.ollama.OLLAMA_HOST", FAKE_HOST):
        yield


# =============================================================================
# check_ollama_connection TESTS
# =============================================================================


class TestCheckOllamaConnection:
    """Test Ollama connectivity check."""

    def test_connection_success_with_model(self):
        from services.ollama import check_ollama_connection

        with patch("services.ollama.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [
                    {"name": f"{FAKE_MODEL}", "size": 1000000},
                ]
            }
            mock_get.return_value = mock_resp

            assert check_ollama_connection() is True
            mock_get.assert_called_once_with(f"{FAKE_HOST}/api/tags", timeout=5)

    def test_connection_success_no_matching_model(self):
        from services.ollama import check_ollama_connection

        with patch("services.ollama.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [{"name": "other-model:7b", "size": 500}]
            }
            mock_get.return_value = mock_resp

            assert check_ollama_connection() is False

    def test_connection_failure(self):
        from services.ollama import check_ollama_connection
        import requests

        with patch("services.ollama.requests.get", side_effect=requests.ConnectionError):
            assert check_ollama_connection() is False

    def test_connection_timeout(self):
        from services.ollama import check_ollama_connection
        import requests

        with patch("services.ollama.requests.get", side_effect=requests.Timeout):
            assert check_ollama_connection() is False

    def test_connection_non_200(self):
        from services.ollama import check_ollama_connection

        with patch("services.ollama.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_get.return_value = mock_resp

            assert check_ollama_connection() is False


# =============================================================================
# warmup_model TESTS
# =============================================================================


class TestWarmupModel:
    """Test model warmup."""

    def test_warmup_success(self):
        from services.ollama import warmup_model

        with patch("services.ollama.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            assert warmup_model() is True
            # Verify it uses a short prompt with few tokens
            call_json = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json"))
            assert call_json["options"]["num_predict"] == 10

    def test_warmup_failure(self):
        from services.ollama import warmup_model

        with patch("services.ollama.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_post.return_value = mock_resp

            assert warmup_model() is False

    def test_warmup_timeout(self):
        from services.ollama import warmup_model
        import requests

        with patch("services.ollama.requests.post", side_effect=requests.Timeout):
            assert warmup_model() is False


# =============================================================================
# call_ollama TESTS
# =============================================================================


class TestCallOllama:
    """Test LLM generation."""

    def test_basic_generate(self):
        from services.ollama import call_ollama

        with patch("services.ollama.requests.post") as mock_post, \
             patch("services.ollama._get_token_tracker", return_value=None):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "response": "Hello! I'm here to help.",
                "done": True,
                "prompt_eval_count": 25,
                "eval_count": 10,
            }
            mock_post.return_value = mock_resp

            result = call_ollama("Hello")

        assert result["response"] == "Hello! I'm here to help."

    def test_generate_with_token_tracking(self):
        from services.ollama import call_ollama

        mock_tracker = MagicMock()
        mock_usage = MagicMock()
        mock_usage.estimated_cost_usd = 0.001
        mock_tracker.record.return_value = mock_usage

        with patch("services.ollama.requests.post") as mock_post, \
             patch("services.ollama._get_token_tracker", return_value=mock_tracker):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "response": "Test",
                "done": True,
                "prompt_eval_count": 50,
                "eval_count": 100,
            }
            mock_post.return_value = mock_resp

            result = call_ollama("Test", user_id="user-123")

        assert "token_usage" in result
        assert result["token_usage"]["prompt_tokens"] == 50
        assert result["token_usage"]["completion_tokens"] == 100
        assert result["token_usage"]["total_tokens"] == 150
        mock_tracker.record.assert_called_once()

    def test_generate_custom_params(self):
        from services.ollama import call_ollama

        with patch("services.ollama.requests.post") as mock_post, \
             patch("services.ollama._get_token_tracker", return_value=None):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"response": "ok", "done": True}
            mock_post.return_value = mock_resp

            call_ollama("Test", max_tokens=1000, temperature=0.2)

        call_json = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json"))
        assert call_json["options"]["num_predict"] == 1000
        assert call_json["options"]["temperature"] == 0.2

    def test_generate_timeout(self):
        from services.ollama import call_ollama
        import requests

        with patch("services.ollama.requests.post", side_effect=requests.Timeout):
            result = call_ollama("Test")

        assert "error" in result
        assert "timed out" in result["error"].lower()

    def test_generate_server_error(self):
        from services.ollama import call_ollama

        with patch("services.ollama.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_post.return_value = mock_resp

            result = call_ollama("Test")

        assert "error" in result

    def test_generate_connection_error(self):
        from services.ollama import call_ollama
        import requests

        with patch("services.ollama.requests.post", side_effect=requests.ConnectionError("refused")):
            result = call_ollama("Test")

        assert "error" in result


# =============================================================================
# call_ollama_stream TESTS
# =============================================================================


class TestCallOllamaStream:
    """Test streaming generation."""

    def test_stream_success(self):
        from services.ollama import call_ollama_stream

        chunks = [
            json.dumps({"response": "Hello", "done": False}).encode(),
            json.dumps({"response": " world", "done": True}).encode(),
        ]

        with patch("services.ollama.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = chunks
            mock_post.return_value = mock_resp

            results = list(call_ollama_stream("Hi"))

        assert len(results) == 2
        assert json.loads(results[0])["response"] == "Hello"
        assert json.loads(results[1])["response"] == " world"

    def test_stream_error_status(self):
        from services.ollama import call_ollama_stream

        with patch("services.ollama.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_post.return_value = mock_resp

            results = list(call_ollama_stream("Hi"))

        assert len(results) == 1
        assert "error" in results[0]

    def test_stream_timeout(self):
        from services.ollama import call_ollama_stream
        import requests

        with patch("services.ollama.requests.post", side_effect=requests.Timeout):
            results = list(call_ollama_stream("Hi"))

        assert len(results) == 1
        assert "timed out" in results[0].lower()

    def test_stream_sends_correct_params(self):
        from services.ollama import call_ollama_stream

        with patch("services.ollama.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = []
            mock_post.return_value = mock_resp

            list(call_ollama_stream("Test", max_tokens=200, temperature=0.5))

        call_kwargs = mock_post.call_args
        call_json = call_kwargs.kwargs.get("json", call_kwargs[1].get("json"))
        assert call_json["stream"] is True
        assert call_json["options"]["num_predict"] == 200
        assert call_json["options"]["temperature"] == 0.5
