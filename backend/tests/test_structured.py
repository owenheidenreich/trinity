"""
Tests for services/structured.py — Structured Output Service

Tests schema definitions, JSON validation, generate_with_schema,
and safe_structured_generate fallback logic.
"""

import json

import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def understanding_schema():
    from services.structured import SCHEMAS
    return SCHEMAS["understanding"]


@pytest.fixture
def plan_schema():
    from services.structured import SCHEMAS
    return SCHEMAS["plan"]


@pytest.fixture
def critique_schema():
    from services.structured import SCHEMAS
    return SCHEMAS["critique"]


@pytest.fixture
def tool_call_schema():
    from services.structured import SCHEMAS
    return SCHEMAS["tool_call"]


# =============================================================================
# SCHEMAS TESTS
# =============================================================================


class TestSchemas:
    """Test pre-defined schema definitions."""

    def test_all_schemas_present(self):
        from services.structured import SCHEMAS

        assert "understanding" in SCHEMAS
        assert "plan" in SCHEMAS
        assert "critique" in SCHEMAS
        assert "tool_call" in SCHEMAS

    def test_understanding_schema_valid(self, understanding_schema):
        assert understanding_schema["type"] == "object"
        assert "question_type" in understanding_schema["properties"]
        assert "complexity" in understanding_schema["properties"]
        assert "question_type" in understanding_schema["required"]
        assert "complexity" in understanding_schema["required"]

    def test_plan_schema_valid(self, plan_schema):
        assert "goal" in plan_schema["required"]
        assert "steps" in plan_schema["required"]
        steps_items = plan_schema["properties"]["steps"]["items"]
        assert "step_number" in steps_items["required"]
        assert "action" in steps_items["required"]

    def test_critique_schema_valid(self, critique_schema):
        assert "score" in critique_schema["required"]
        assert "needs_refinement" in critique_schema["required"]
        score_props = critique_schema["properties"]["score"]
        assert score_props["minimum"] == 1
        assert score_props["maximum"] == 10

    def test_tool_call_schema_valid(self, tool_call_schema):
        assert "tool" in tool_call_schema["required"]
        assert "parameters" in tool_call_schema["required"]
        # Verify enum values
        tool_enum = tool_call_schema["properties"]["tool"]["enum"]
        assert "calculator" in tool_enum
        assert "web_search" in tool_enum


# =============================================================================
# check_outlines_available TESTS
# =============================================================================


class TestCheckOutlinesAvailable:
    """Test Outlines availability detection."""

    def test_check_outlines_returns_bool(self):
        from services.structured import check_outlines_available

        # Reset cached value
        import services.structured
        services.structured._outlines_available = None

        result = check_outlines_available()
        assert isinstance(result, bool)

    def test_check_outlines_caches_result(self):
        from services.structured import check_outlines_available
        import services.structured

        services.structured._outlines_available = None
        first = check_outlines_available()
        second = check_outlines_available()
        assert first == second


# =============================================================================
# validate_json_output TESTS
# =============================================================================


class TestValidateJsonOutput:
    """Test JSON extraction and validation from text."""

    def test_valid_json_with_required_fields(self, understanding_schema):
        from services.structured import validate_json_output

        text = 'Here is the result: {"question_type": "factual", "complexity": 3}'
        result = validate_json_output(text, understanding_schema)

        assert result is not None
        assert result["question_type"] == "factual"
        assert result["complexity"] == 3

    def test_valid_json_missing_required_field(self, understanding_schema):
        from services.structured import validate_json_output

        # Missing "complexity" which is required
        text = '{"question_type": "factual"}'
        result = validate_json_output(text, understanding_schema)

        assert result is None

    def test_no_json_in_text(self, understanding_schema):
        from services.structured import validate_json_output

        text = "This is just plain text with no JSON at all."
        result = validate_json_output(text, understanding_schema)

        assert result is None

    def test_invalid_json_syntax(self, understanding_schema):
        from services.structured import validate_json_output

        text = '{"question_type": "factual", complexity: 3}'  # Missing quotes
        result = validate_json_output(text, understanding_schema)

        assert result is None

    def test_schema_with_no_required_fields(self):
        from services.structured import validate_json_output

        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        text = '{"x": 42}'
        result = validate_json_output(text, schema)

        assert result is not None
        assert result["x"] == 42

    def test_json_embedded_in_markdown(self, understanding_schema):
        from services.structured import validate_json_output

        text = '```json\n{"question_type": "code", "complexity": 7}\n```'
        result = validate_json_output(text, understanding_schema)

        assert result is not None
        assert result["question_type"] == "code"
        assert result["complexity"] == 7


# =============================================================================
# generate_with_schema TESTS
# =============================================================================


class TestGenerateWithSchema:
    """Test schema-based generation."""

    def test_unknown_schema_returns_none(self):
        from services.structured import generate_with_schema

        result = generate_with_schema("test prompt", "nonexistent_schema")
        assert result is None

    def test_valid_schema_calls_generate_structured(self):
        from services.structured import generate_with_schema

        expected = {"question_type": "factual", "complexity": 5}

        with patch("services.structured.generate_structured", return_value=expected) as mock_gen:
            result = generate_with_schema("Analyze this query", "understanding")

        assert result == expected
        mock_gen.assert_called_once()

    def test_all_schema_names_work(self):
        from services.structured import generate_with_schema, SCHEMAS

        with patch("services.structured.generate_structured", return_value={"ok": True}):
            for name in SCHEMAS:
                result = generate_with_schema("test", name)
                assert result is not None


# =============================================================================
# generate_structured TESTS
# =============================================================================


class TestGenerateStructured:
    """Test structured generation with Outlines."""

    def test_outlines_not_available_returns_none(self):
        from services.structured import generate_structured
        import services.structured

        services.structured._outlines_available = False

        result = generate_structured("test", {"type": "object"})
        assert result is None

        # Reset
        services.structured._outlines_available = None

    def test_outlines_available_calls_model(self):
        from services.structured import generate_structured
        import services.structured

        services.structured._outlines_available = True

        mock_model = MagicMock()
        mock_generator = MagicMock(return_value={"answer": 42})

        mock_outlines = MagicMock()
        mock_outlines.models.openai.return_value = mock_model
        mock_outlines.generate.json.return_value = mock_generator

        import sys
        sys.modules["outlines"] = mock_outlines

        try:
            result = generate_structured("What is 6*7?", {"type": "object"})
            assert result == {"answer": 42}
        finally:
            del sys.modules["outlines"]
            services.structured._outlines_available = None


# =============================================================================
# safe_structured_generate TESTS
# =============================================================================


class TestSafeStructuredGenerate:
    """Test the fallback chain: structured -> unstructured + parse."""

    def test_structured_succeeds_no_fallback(self):
        from services.structured import safe_structured_generate

        schema = {"type": "object", "required": ["x"]}
        expected = {"x": 1}

        with patch("services.structured.generate_structured", return_value=expected):
            result = safe_structured_generate("test", schema)

        assert result == expected

    def test_structured_fails_falls_back_to_parsing(self):
        from services.structured import safe_structured_generate

        schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}

        with patch("services.structured.generate_structured", return_value=None):
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"response": 'Here is the JSON: {"x": 99}'}
                mock_post.return_value = mock_resp

                result = safe_structured_generate("test", schema)

        assert result is not None
        assert result["x"] == 99

    def test_structured_fails_and_parsing_fails_returns_none(self):
        from services.structured import safe_structured_generate

        schema = {"type": "object", "required": ["x"]}

        with patch("services.structured.generate_structured", return_value=None):
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"response": "No JSON here!"}
                mock_post.return_value = mock_resp

                result = safe_structured_generate("test", schema)

        assert result is None

    def test_custom_fallback_parser(self):
        from services.structured import safe_structured_generate

        schema = {"type": "object", "required": ["x"]}

        def custom_parser(text):
            return {"x": int(text.strip())}

        with patch("services.structured.generate_structured", return_value=None):
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"response": "42"}
                mock_post.return_value = mock_resp

                result = safe_structured_generate("test", schema, fallback_parser=custom_parser)

        assert result == {"x": 42}

    def test_network_error_returns_none(self):
        from services.structured import safe_structured_generate
        import requests as req_lib

        schema = {"type": "object", "required": ["x"]}

        with patch("services.structured.generate_structured", return_value=None):
            with patch("requests.post", side_effect=req_lib.ConnectionError):
                result = safe_structured_generate("test", schema)

        assert result is None
