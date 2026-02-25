"""
Tests for regex fallback when tiny classifiers are unavailable or low-confidence.

These tests mock the classifier to always return ("general", 0.0) / [],
forcing the regex fallback path in both query_classifier.py and tools.py.

After the classifier simplification, the only classifier that matters for
pipeline behavior is tool detection. Query-level classification (smalltalk,
disclosure, etc.) is stripped — every query gets full context and an LLM call.
"""

import sys
from unittest.mock import patch

import pytest


# ============================================================================
# 1. QUERY CLASSIFIER — Regex fallback for disclosure + memory detection
# ============================================================================


class TestPersonalDisclosureDetection:
    """Personal disclosure detection still matters for memory filtering."""

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_disclosure_my_name_detected(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("my name is Owen") is True

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_disclosure_i_work_at_detected(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("I work at a startup") is True

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_disclosure_i_like_dogs(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("i like dogs") is True

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_disclosure_question_not_detected(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("What is my name?") is False

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_disclosure_request_not_detected(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("Can you help me write code") is False


class TestPersonalMemoryDetection:
    """Memory recall detection drives include_personal in memory_eval."""

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_memory_what_is_my_name_detected(self, mock_cls):
        from services.query_classifier import requests_personal_memory
        assert requests_personal_memory("what is my name?") is True

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_memory_do_you_remember_detected(self, mock_cls):
        from services.query_classifier import requests_personal_memory
        assert requests_personal_memory("do you remember me?") is True

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_memory_what_do_you_know_detected(self, mock_cls):
        from services.query_classifier import requests_personal_memory
        assert requests_personal_memory("what do you know about me") is True

    @patch("services.query_classifier._classify", return_value=("general", 0.0))
    def test_generic_not_detected(self, mock_cls):
        from services.query_classifier import requests_personal_memory
        assert requests_personal_memory("what is the speed of light") is False


# ============================================================================
# 2. DEPRECATED FUNCTIONS — verify stubs return safe defaults
# ============================================================================


class TestDeprecatedStubs:
    """Deprecated functions should return inert values."""

    def test_is_trivial_smalltalk_always_false(self):
        from services.query_classifier import is_trivial_smalltalk
        assert is_trivial_smalltalk("hello") is False
        assert is_trivial_smalltalk("hey there") is False
        assert is_trivial_smalltalk("thanks") is False

    def test_smalltalk_fast_response_returns_empty(self):
        from services.query_classifier import smalltalk_fast_response
        assert smalltalk_fast_response("hello") == ""

    def test_classify_context_level_always_full(self):
        from services.query_classifier import classify_context_level, ContextLevel
        assert classify_context_level("hello") == ContextLevel.FULL
        assert classify_context_level("explain quantum physics") == ContextLevel.FULL
        assert classify_context_level("my name is Owen") == ContextLevel.FULL


# ============================================================================
# 3. TOOL DETECTION — Regex fallback (the one classifier that earns its keep)
# ============================================================================


class TestToolDetectionRegexFallback:
    """When tiny classifier returns [], regex heuristics should catch tools."""

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_math_triggers_calculator(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is 2 + 2?")
        assert "calculator" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_calculate_triggers_calculator(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("calculate 847 * 293")
        assert "calculator" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_web_search_bitcoin(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Search the web for today's Bitcoin price.")
        assert "web_search" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_web_search_latest_news(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is the latest news?")
        assert "web_search" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_memory_recall_what_do_you_know(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What do you know about me? Check your memory.")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_memory_recall_whats_my_name(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("what is my name?")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_memory_recall_do_you_remember(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("do you remember my preferences?")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_forget_memory(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("forget that I told you my name")
        assert "forget_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_greeting_no_tools(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Hello, how are you today?")
        assert tools == []

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_generic_question_no_tools(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Explain what water is in one sentence.")
        assert tools == []


# ============================================================================
# 4. CLASSIFIER-FIRST: verify classifier wins when confident
# ============================================================================


class TestClassifierTakesPrecedence:
    """When classifier is confident, it should win over regex for tool detection."""

    @patch("services.tiny_classifier.detect_tools", return_value=["calculator"])
    def test_confident_classifier_tool_wins(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is 2 + 2?")
        assert tools == ["calculator"]

    @patch("services.query_classifier._classify", return_value=("disclosure", 0.95))
    def test_confident_disclosure_detected(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("i like dogs") is True

    @patch("services.query_classifier._classify", return_value=("memory_recall", 0.90))
    def test_confident_memory_recall_detected(self, mock_cls):
        from services.query_classifier import requests_personal_memory
        assert requests_personal_memory("what do you know about me") is True


# ============================================================================
# 5. CLASSIFIER EXCEPTION: verify regex catches when classifier throws
# ============================================================================


class TestClassifierExceptionFallback:
    """When the classifier raises an exception, regex should still work."""

    @patch("services.query_classifier._classify", side_effect=Exception("model unavailable"))
    def test_exception_falls_to_regex_disclosure(self, mock_cls):
        from services.query_classifier import is_personal_disclosure
        assert is_personal_disclosure("my name is Owen") is True

    @patch("services.query_classifier._classify", side_effect=Exception("model unavailable"))
    def test_exception_falls_to_regex_memory(self, mock_cls):
        from services.query_classifier import requests_personal_memory
        assert requests_personal_memory("what do you know about me") is True

    def test_tool_detection_exception_falls_to_regex(self):
        with patch("services.tiny_classifier.detect_tools", side_effect=Exception("model crash")):
            from services.tools import detect_tools_needed
            tools = detect_tools_needed("calculate 25 * 38")
            assert "calculator" in tools


# ============================================================================
# 6. EXACT DIAGNOSTIC FAILURES — match the failing tests from diag run
# ============================================================================


class TestDiagnosticFailures:
    """Reproduce the exact queries that failed in diag_20260220_012632.json."""

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_basic_001_math_2_plus_2(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is 2 + 2?")
        assert "calculator" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_tool_001_calculator_pipeline(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is 847 * 293? Use your calculator tool.")
        assert "calculator" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_tool_002_web_search_pipeline(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Search the web for today's Bitcoin price.")
        assert "web_search" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_tool_003_memory_save_pipeline(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Remember that my favorite programming language is Rust.")
        assert "save_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_tool_004_memory_recall_pipeline(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What do you know about me? Check your memory.")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_fmt_008_natural_math(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("If I have 3 apples and give away 1, how many do I have?")
        assert "calculator" in tools


# ============================================================================
# 7. DIAGNOSTIC GAP TESTS — specific regex pattern gaps
# ============================================================================


class TestDiagnosticGapFixes:
    """Test the specific regex pattern gaps identified from diagnostic analysis."""

    # --- save_memory patterns ---

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_save_memory_remember_that(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Remember that I like Python")
        assert "save_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_save_memory_remember_my(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Remember my favorite editor is vim")
        assert "save_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_save_memory_save_fact(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Save the fact that I work at Google")
        assert "save_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_save_memory_keep_in_mind(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Keep in mind that I prefer dark mode")
        assert "save_memory" in tools

    # --- recall_memory expanded noun list ---

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_recall_favorite_color(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is my favorite color?")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_recall_what_do_i_do(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What do I do for work?")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_recall_who_am_i(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("Who am I?")
        assert "recall_memory" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_recall_whats_my_project(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What's my project?")
        assert "recall_memory" in tools

    # --- natural-language math ---

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_calc_apples_give_away(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("If I have 3 apples and give away 1, how many do I have?")
        assert "calculator" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_calc_natural_plus(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("What is 5 plus 3?")
        assert "calculator" in tools

    @patch("services.tiny_classifier.detect_tools", return_value=[])
    def test_calc_how_much(self, mock_detect):
        from services.tools import detect_tools_needed
        tools = detect_tools_needed("How much is 100 divided by 7?")
        assert "calculator" in tools
