"""Tests for routes/diagnostic.py — Diagnostic probe and status endpoints.

Note: The diagnostic blueprint is registered in conftest.py's app fixture
so it's available before any test request triggers Flask's setup-finished lock.
"""

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
# GET /diagnostic/status
# =============================================================================


class TestDiagnosticStatus:
    def test_returns_403_when_disabled(self, client):
        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", False):
            resp = client.get("/diagnostic/status")
        assert resp.status_code == 403
        assert resp.get_json()["enabled"] is False

    def test_returns_info_when_enabled(self, client):
        mock_provider = MagicMock()
        mock_provider.check_connection.return_value = True

        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", True), \
             patch("routes.diagnostic.MODEL_NAME", "qwen3:32b"), \
             patch("routes.diagnostic.MODEL_BACKEND", "llama-server"), \
             patch("services.provider_factory.get_provider", return_value=mock_provider):
            resp = client.get("/diagnostic/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is True
        assert data["model"] == "qwen3:32b"
        assert data["backend"] == "llama-server"
        assert data["llm_connected"] is True


# =============================================================================
# POST /diagnostic/probe
# =============================================================================


class TestDiagnosticProbe:
    def test_returns_403_when_disabled(self, client):
        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", False):
            resp = client.post("/diagnostic/probe", json={"prompt": "test"})
        assert resp.status_code == 403

    def test_missing_prompt_returns_400(self, client):
        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", True):
            resp = client.post("/diagnostic/probe", json={})
        assert resp.status_code == 400

    def test_empty_prompt_returns_400(self, client):
        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", True):
            resp = client.post("/diagnostic/probe", json={"prompt": ""})
        assert resp.status_code == 400

    def test_skip_context_direct_call(self, client):
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "<think>reasoning</think>The answer is 42."

        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", True), \
             patch("services.provider_factory.get_provider", return_value=mock_provider):
            resp = client.post("/diagnostic/probe", json={
                "prompt": "What is the meaning of life?",
                "skip_context": True,
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["pipeline"]["context_level"] == "SKIP"
        assert data["llm"]["raw_response"] == "<think>reasoning</think>The answer is 42."
        assert "reasoning" not in data["llm"]["filtered_response"]
        assert "42" in data["llm"]["filtered_response"]
        assert data["think_blocks"]["count"] == 1
        assert data["think_blocks"]["all_closed"] is True
        assert "timing" in data

    def test_messages_override(self, client):
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Direct response."

        custom_messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]

        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", True), \
             patch("services.provider_factory.get_provider", return_value=mock_provider):
            resp = client.post("/diagnostic/probe", json={
                "prompt": "Hi",
                "messages": custom_messages,
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["pipeline"]["context_level"] == "OVERRIDE"
        assert data["prompt"]["message_count"] == 2

    def test_llm_error_returns_500(self, client):
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = Exception("LLM connection timeout")

        with patch("routes.diagnostic.DIAGNOSTIC_ENABLED", True), \
             patch("services.provider_factory.get_provider", return_value=mock_provider):
            resp = client.post("/diagnostic/probe", json={
                "prompt": "test",
                "skip_context": True,
            })

        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


# =============================================================================
# Helper functions (no Flask client needed)
# =============================================================================


class TestAnalyzeThinkBlocks:
    def test_extracts_single_block(self):
        from routes.diagnostic import _analyze_think_blocks
        result = _analyze_think_blocks("<think>reasoning here</think>answer")
        assert result["count"] == 1
        assert result["all_closed"] is True
        assert result["total_chars"] > 0
        assert "reasoning here" in result["content"][0]

    def test_multiple_blocks(self):
        from routes.diagnostic import _analyze_think_blocks
        raw = "<think>first</think>middle<think>second</think>end"
        result = _analyze_think_blocks(raw)
        assert result["count"] == 2
        assert result["all_closed"] is True

    def test_unclosed_block(self):
        from routes.diagnostic import _analyze_think_blocks
        result = _analyze_think_blocks("<think>never closed")
        assert result["count"] == 1
        assert result["all_closed"] is False

    def test_no_blocks(self):
        from routes.diagnostic import _analyze_think_blocks
        result = _analyze_think_blocks("plain text no blocks")
        assert result["count"] == 0
        assert result["all_closed"] is True


class TestAnalyzeToolCalls:
    def test_extracts_tool_call(self):
        from routes.diagnostic import _analyze_tool_calls
        raw = '<tool_call name="calculator"><expression>2+2</expression></tool_call>'
        result = _analyze_tool_calls(raw)
        assert result["count"] == 1
        assert result["unclosed_tags"] == 0
        assert result["calls"][0]["name"] == "calculator"
        assert result["calls"][0]["params"]["expression"] == "2+2"

    def test_no_tool_calls(self):
        from routes.diagnostic import _analyze_tool_calls
        result = _analyze_tool_calls("just plain text")
        assert result["count"] == 0

    def test_unclosed_tool_call(self):
        from routes.diagnostic import _analyze_tool_calls
        raw = '<tool_call name="web_search"><query>test</query>'
        result = _analyze_tool_calls(raw)
        assert result["unclosed_tags"] == 1


class TestStripThinkBlocks:
    def test_strips_blocks(self):
        from routes.diagnostic import _strip_think_blocks
        result = _strip_think_blocks("<think>hidden</think>visible")
        assert result == "visible"

    def test_no_blocks(self):
        from routes.diagnostic import _strip_think_blocks
        result = _strip_think_blocks("plain text")
        assert result == "plain text"
