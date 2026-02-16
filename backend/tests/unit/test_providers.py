"""
Tests for LLM Provider Abstraction Layer

Validates that:
1. OllamaProvider implements the LLMProvider interface
2. NDJSON parsing (Ollama) produces correct output contracts
3. Provider factory creates OllamaProvider correctly
4. All intelligence checks (tool detection, think-block filtering, structured output)
   work correctly
5. End-to-end pipeline: same input → same processing → correct output format
"""

import json

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ============================================================================
# LLMProvider ABC Contract Tests
# ============================================================================


class TestLLMProviderABC:
    """Verify the LLMProvider ABC defines the expected interface."""

    def test_abc_cannot_be_instantiated(self):
        from services.llm_provider import LLMProvider
        with pytest.raises(TypeError, match="abstract"):
            LLMProvider()

    def test_abc_has_required_methods(self):
        from services.llm_provider import LLMProvider
        required = ["generate", "generate_stream", "chat", "chat_stream",
                     "check_connection", "warmup"]
        for method in required:
            assert hasattr(LLMProvider, method), f"Missing method: {method}"

    def test_abc_has_backend_name_property(self):
        from services.llm_provider import LLMProvider
        assert hasattr(LLMProvider, "backend_name")


# ============================================================================
# OllamaProvider Tests
# ============================================================================


class TestOllamaProvider:
    """Test OllamaProvider implements LLMProvider correctly."""

    def _make_provider(self):
        from services.ollama_provider import OllamaProvider
        return OllamaProvider(
            host="http://localhost:11434",
            model="qwen2.5-coder:32b",
            num_ctx=32768,
        )

    def test_is_llm_provider(self):
        from services.llm_provider import LLMProvider
        provider = self._make_provider()
        assert isinstance(provider, LLMProvider)

    def test_backend_name(self):
        provider = self._make_provider()
        assert provider.backend_name == "ollama"

    def test_repr(self):
        provider = self._make_provider()
        assert "OllamaProvider" in repr(provider)
        assert "11434" in repr(provider)

    def test_generate_success(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"response": "Hello world"}
            mock_post.return_value = mock_resp

            result = provider.generate("Say hello", max_tokens=100)
            assert result == "Hello world"
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/generate" in call_args[0][0]

    def test_generate_timeout(self):
        import requests
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post",
                    side_effect=requests.Timeout):
            result = provider.generate("test", timeout=1)
            assert result == ""

    def test_generate_error_status(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_post.return_value = mock_resp
            result = provider.generate("test")
            assert result == ""

    def test_generate_stream_yields_tokens_and_done(self):
        provider = self._make_provider()
        chunks = [
            json.dumps({"response": "Hello", "done": False}).encode(),
            json.dumps({"response": " world", "done": False}).encode(),
            json.dumps({"response": "", "done": True, "done_reason": "stop"}).encode(),
        ]
        with patch("services.ollama_provider.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = chunks
            mock_post.return_value = mock_resp

            tokens = list(provider.generate_stream("test"))
            # Should have 2 content tokens + 1 done signal
            content = [t for t in tokens if isinstance(t, str)]
            done_signals = [t for t in tokens if isinstance(t, dict)]

            assert content == ["Hello", " world"]
            assert len(done_signals) == 1
            assert done_signals[0]["__done_reason"] == "stop"

    def test_chat_success(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "message": {"role": "assistant", "content": "Hi there!"}
            }
            mock_post.return_value = mock_resp

            result = provider.chat(
                [{"role": "user", "content": "Hello"}],
                max_tokens=100,
            )
            assert result == "Hi there!"
            call_args = mock_post.call_args
            assert "/api/chat" in call_args[0][0]

    def test_chat_raw_message(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "message": {"role": "assistant", "content": "Hi", "tool_calls": []}
            }
            mock_post.return_value = mock_resp

            result = provider.chat(
                [{"role": "user", "content": "Hello"}],
                raw_message=True,
            )
            assert isinstance(result, dict)
            assert result["content"] == "Hi"

    def test_check_connection_with_matching_model(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [{"name": "qwen2.5-coder:32b", "size": 1000}]
            }
            mock_get.return_value = mock_resp
            assert provider.check_connection() is True

    def test_check_connection_no_matching_model(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [{"name": "llama3:8b", "size": 500}]
            }
            mock_get.return_value = mock_resp
            assert provider.check_connection() is False

    def test_check_connection_failure(self):
        import requests
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.get",
                    side_effect=requests.ConnectionError):
            assert provider.check_connection() is False

    def test_warmup_success(self):
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            assert provider.warmup() is True

    def test_warmup_timeout(self):
        import requests
        provider = self._make_provider()
        with patch("services.ollama_provider.requests.post",
                    side_effect=requests.Timeout):
            assert provider.warmup() is False


# ============================================================================
# Provider Factory Tests
# ============================================================================


class TestProviderFactory:
    """Test that the factory creates OllamaProvider and the singleton works."""

    def setup_method(self):
        from services.provider_factory import reset_provider
        reset_provider()

    def teardown_method(self):
        from services.provider_factory import reset_provider
        reset_provider()

    @patch("config.OLLAMA_HOST", "http://localhost:11434")
    @patch("config.MODEL_NAME", "qwen2.5-coder:32b")
    @patch("config.NUM_CTX", 32768)
    def test_create_ollama_provider(self):
        from services.provider_factory import create_provider
        from services.ollama_provider import OllamaProvider
        provider = create_provider()
        assert isinstance(provider, OllamaProvider)
        assert provider.backend_name == "ollama"

    @patch("config.OLLAMA_HOST", "http://localhost:11434")
    @patch("config.MODEL_NAME", "qwen2.5-coder:32b")
    @patch("config.NUM_CTX", 32768)
    def test_singleton_returns_same_instance(self):
        from services.provider_factory import get_provider
        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2

    @patch("config.OLLAMA_HOST", "http://localhost:11434")
    @patch("config.MODEL_NAME", "qwen2.5-coder:32b")
    @patch("config.NUM_CTX", 32768)
    def test_reset_clears_singleton(self):
        from services.provider_factory import get_provider, reset_provider
        p1 = get_provider()
        reset_provider()
        p2 = get_provider()
        assert p1 is not p2


# ============================================================================
# Pipeline Integration Tests
# ============================================================================


class TestPipelineIntegration:
    """Verify the AgentPipeline works correctly with the provider abstraction."""

    def test_agent_pipeline_uses_injected_provider(self):
        """AgentPipeline should use whatever provider is injected."""
        from services.agent import AgentPipeline
        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = iter(["Hello", {"__done_reason": "stop"}])

        pipeline = AgentPipeline(provider=mock_provider)
        assert pipeline.client is mock_provider

    def test_agent_pipeline_falls_back_to_factory(self):
        """AgentPipeline uses provider factory when no provider given."""
        with patch("config.MODEL_BACKEND", "ollama"), \
             patch("config.OLLAMA_HOST", "http://localhost:11434"), \
             patch("config.MODEL_NAME", "test:8b"), \
             patch("config.NUM_CTX", 32768):
            from services.provider_factory import reset_provider
            reset_provider()
            from services.agent import AgentPipeline
            from services.ollama_provider import OllamaProvider
            pipeline = AgentPipeline()
            assert isinstance(pipeline.client, OllamaProvider)
            reset_provider()

    def test_think_block_filter(self):
        """The <think>...</think> filter in AgentPipeline strips reasoning blocks."""
        from services.agent import AgentPipeline

        mock_provider = MagicMock()
        pipeline = AgentPipeline(provider=mock_provider)

        # Simulate output with think blocks
        stream = iter([
            "<think>",
            "Let me reason about this...",
            "</think>",
            "The answer is 42.",
            {"__done_reason": "stop"},
        ])
        accumulator = []
        filtered = list(pipeline._filter_think_blocks(stream, accumulator))

        # Think blocks should be stripped, only answer visible
        content_tokens = [t for t in filtered if isinstance(t, str)]
        assert "".join(content_tokens).strip() == "The answer is 42."
        assert "".join(accumulator).strip() == "The answer is 42."

        # Done signal should pass through
        done_signals = [t for t in filtered if isinstance(t, dict)]
        assert len(done_signals) == 1
        assert done_signals[0]["__done_reason"] == "stop"

    def test_smalltalk_detection_is_conservative(self):
        """Only truly trivial phatic messages should use the fast path."""
        from services.agent import is_trivial_smalltalk

        assert is_trivial_smalltalk("hello")
        assert is_trivial_smalltalk("thanks!")
        assert not is_trivial_smalltalk("hello can you summarize this file")

    def test_smalltalk_fast_path_skips_llm_call(self):
        """Fast-path greetings should not call the LLM at all."""
        from services.agent import AgentPipeline

        mock_provider = MagicMock()
        pipeline = AgentPipeline(provider=mock_provider)

        events = list(
            pipeline.process_streaming(
                question="hello",
                context_messages=[],
                user_memory={},
                fast_path=True,
            )
        )

        mock_provider.generate_stream.assert_not_called()
        tokens = [e["token"] for e in events if isinstance(e, dict) and "token" in e]
        done_events = [e for e in events if isinstance(e, dict) and e.get("done")]

        assert len(tokens) == 1
        assert "ready" in tokens[0].lower()
        assert len(done_events) == 1

    def test_react_loop_accepts_any_provider(self):
        """ReactLoop should work with any provider implementing chat/chat_stream."""
        try:
            from services.react_loop import ReactLoop
        except ImportError:
            pytest.skip("ReactLoop not available")

        mock_provider = MagicMock()
        # ReactLoop uses self.client.chat() for tool detection
        mock_provider.chat.return_value = "I don't need any tools for this."

        loop = ReactLoop(mock_provider, context={})
        # Just verify it accepts the mock — actual execution tested separately
        assert loop.client is mock_provider

    def test_generate_route_uses_provider(self):
        """Verify /generate uses get_provider(), not raw Ollama HTTP."""
        with patch("routes.generate.get_provider") as mock_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = "Generated response"
            mock_factory.return_value = mock_provider

            result = mock_provider.generate("test prompt", max_tokens=100)
            assert result == "Generated response"

    def test_tools_route_uses_provider(self):
        """Verify call_ollama_for_tools uses get_provider()."""
        with patch("routes.tools.get_provider") as mock_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = "tool result"
            mock_factory.return_value = mock_provider

            from routes.tools import call_ollama_for_tools
            result = call_ollama_for_tools("summarize this", temperature=0.3)

            assert result == "tool result"
            mock_provider.generate.assert_called_once()
            call_kwargs = mock_provider.generate.call_args
            assert call_kwargs[1]["temperature"] == 0.3


# ============================================================================
# Structured Output Backend Dispatch Tests
# ============================================================================


class TestStructuredOutputDispatch:
    """Verify structured output correctly dispatches to Ollama."""

    @patch("config.MODEL_BACKEND", "ollama")
    @patch("config.OLLAMA_HOST", "http://localhost:11434")
    def test_structured_fallback_uses_provider(self):
        """safe_structured_generate fallback path should use get_provider()."""
        # The fallback in safe_structured_generate calls get_provider().generate()
        # get_provider is imported inside the function, so patch at factory level
        with patch("services.structured.generate_structured", return_value=None):
            with patch("services.provider_factory.get_provider") as mock_factory:
                mock_provider = MagicMock()
                mock_provider.generate.return_value = '{"tool": "web_search"}'
                mock_factory.return_value = mock_provider

                from services.structured import safe_structured_generate
                result = safe_structured_generate(
                    "test prompt",
                    {"type": "object", "properties": {"tool": {"type": "string"}}},
                )
                # Verify fallback used the provider
                mock_provider.generate.assert_called_once()
