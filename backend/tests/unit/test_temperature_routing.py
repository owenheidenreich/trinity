"""Tests for temperature routing (Phase 1 of MicroGPT overhaul).

Verifies that query classification maps to appropriate sampling temperatures
and that temperature flows through the pipeline to the LLM provider.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.query_classifier import (
    classify_temperature,
)


# ---------------------------------------------------------------------------
# classify_temperature() unit tests
# ---------------------------------------------------------------------------


class TestClassifyTemperature:
    """Test temperature classification for different query types."""

    def test_code_query_gets_low_temperature(self):
        temp = classify_temperature(
            "write a python function to sort a list",
        )
        assert temp == 0.1

    def test_code_flag_overrides(self):
        temp = classify_temperature(
            "help me with this",
            is_code=True,
        )
        assert temp == 0.1

    def test_tool_query_gets_factual_temperature(self):
        temp = classify_temperature(
            "what's the weather",
            tools_needed=["web_search"],
        )
        assert temp == 0.3

    def test_memory_recall_gets_factual_temperature(self):
        temp = classify_temperature(
            "what do you remember about me",
        )
        assert temp == 0.3

    def test_conversational_query_gets_default_temperature(self):
        temp = classify_temperature(
            "explain quantum computing to me",
        )
        assert temp == 0.7

    def test_smalltalk_gets_conversational_temperature(self):
        temp = classify_temperature(
            "hello there",
        )
        assert temp == 0.7

    def test_code_takes_priority_over_tools(self):
        temp = classify_temperature(
            "write a python script",
            is_code=True,
            tools_needed=["code_display"],
        )
        assert temp == 0.1

    def test_tools_take_priority_over_conversational(self):
        temp = classify_temperature(
            "search for the latest news",
            tools_needed=["web_search"],
        )
        assert temp == 0.3

    def test_empty_tools_list_is_conversational(self):
        temp = classify_temperature(
            "tell me about history",
            tools_needed=[],
        )
        assert temp == 0.7

    def test_none_tools_is_conversational(self):
        temp = classify_temperature(
            "tell me about history",
            tools_needed=None,
        )
        assert temp == 0.7


# ---------------------------------------------------------------------------
# RequestContext temperature field
# ---------------------------------------------------------------------------


class TestRequestContextTemperature:
    """Test that temperature is computed during context loading."""

    def test_request_context_has_temperature_field(self):
        from services.context_loader import RequestContext

        ctx = RequestContext()
        assert ctx.temperature == 0.7  # Default

    def test_request_context_temperature_can_be_set(self):
        from services.context_loader import RequestContext

        ctx = RequestContext(temperature=0.1)
        assert ctx.temperature == 0.1

    def test_request_context_no_level_field(self):
        """RequestContext no longer has a 'level' field — context is always full."""
        from services.context_loader import RequestContext
        ctx = RequestContext()
        assert not hasattr(ctx, 'level')


# ---------------------------------------------------------------------------
# Pipeline temperature threading
# ---------------------------------------------------------------------------


class TestPipelineTemperature:
    """Test that temperature flows through the pipeline to the LLM provider."""

    def test_direct_streaming_passes_temperature(self):
        """Verify chat_stream receives the temperature kwarg."""
        from services.pipeline import StreamingPipeline

        mock_provider = MagicMock()
        mock_provider.chat_stream.return_value = iter(
            ["Hello", {"__done_reason": "stop"}]
        )

        pipeline = StreamingPipeline(provider=mock_provider)

        events = list(
            pipeline.process_streaming(
                question="test query",
                messages=[{"role": "user", "content": "test query"}],
                temperature=0.1,
            )
        )

        mock_provider.chat_stream.assert_called_once()
        _, kwargs = mock_provider.chat_stream.call_args
        assert kwargs["temperature"] == 0.1

    def test_smalltalk_still_calls_llm(self):
        """All queries go through the LLM — no fast-path."""
        from services.pipeline import StreamingPipeline

        mock_provider = MagicMock()
        mock_provider.chat_stream.return_value = iter(
            [{"choices": [{"delta": {"content": "Hey!"}}]}]
        )
        pipeline = StreamingPipeline(provider=mock_provider)

        events = list(
            pipeline.process_streaming(
                question="hello",
                messages=[{"role": "user", "content": "hello"}],
                temperature=0.7,
            )
        )

        # LLM should have been called
        mock_provider.chat_stream.assert_called_once()
        tokens = [e["token"] for e in events if "token" in e]
        assert len(tokens) > 0


# ---------------------------------------------------------------------------
# Config constants
# ---------------------------------------------------------------------------


class TestTemperatureConfig:
    """Test that temperature config constants exist and have correct defaults."""

    def test_config_constants_exist(self):
        from config import (
            TEMPERATURE_CODE,
            TEMPERATURE_FACTUAL,
            TEMPERATURE_CONVERSATIONAL,
        )

        assert TEMPERATURE_CODE == 0.1
        assert TEMPERATURE_FACTUAL == 0.3
        assert TEMPERATURE_CONVERSATIONAL == 0.7

    def test_config_constants_are_floats(self):
        from config import (
            TEMPERATURE_CODE,
            TEMPERATURE_FACTUAL,
            TEMPERATURE_CONVERSATIONAL,
        )

        assert isinstance(TEMPERATURE_CODE, float)
        assert isinstance(TEMPERATURE_FACTUAL, float)
        assert isinstance(TEMPERATURE_CONVERSATIONAL, float)
