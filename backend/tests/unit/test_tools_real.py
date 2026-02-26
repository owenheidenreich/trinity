"""
Trinity Backend - Real Tool Implementation Tests
=================================================
Tests for the real implementations of web_search, fact_check, and document_search
tools in code_executor.execute_tool().

All external dependencies (Brave API, vector store, embeddings) are mocked.
"""

import numpy as np
from unittest.mock import MagicMock, patch

from services.code_executor import execute_tool
from services.fact_check import format_fact_check
from services.search import SearchResponse, SearchResult


# ============================================================================
# Web Search Tool
# ============================================================================


class TestWebSearchTool:
    """Test execute_tool('web_search', ...) with mocked Brave Search."""

    @patch("services.search.search_web")
    @patch("services.search.format_search_context")
    def test_web_search_success(self, mock_format, mock_search):
        """Successful web search returns formatted results."""
        mock_search.return_value = SearchResponse(
            query="bitcoin price",
            results=[SearchResult(title="BTC", url="https://example.com", snippet="$100k")],
        )
        mock_format.return_value = "Web search results for 'bitcoin price':\n\n1. **BTC**\n   $100k"

        success, result = execute_tool("web_search", {"query": "bitcoin price"})

        assert success is True
        assert "BTC" in result

    @patch("services.search.search_web")
    def test_web_search_error(self, mock_search):
        """Search API error is reported."""
        mock_search.return_value = SearchResponse(
            query="test", results=[], error="API key invalid"
        )

        success, result = execute_tool("web_search", {"query": "test"})

        assert success is False
        assert "API key invalid" in result

    def test_web_search_empty_query(self):
        """Empty query returns error without calling API."""
        success, result = execute_tool("web_search", {"query": ""})

        assert success is False
        assert "Empty" in result

    @patch("services.search.search_web")
    @patch("services.search.format_search_context")
    def test_web_search_no_results(self, mock_format, mock_search):
        """No results returns informative message."""
        mock_search.return_value = SearchResponse(query="obscure query", results=[])
        mock_format.return_value = ""

        success, result = execute_tool("web_search", {"query": "obscure query"})

        assert success is True
        assert "No results" in result


# ============================================================================
# Fact Check Tool
# ============================================================================


class TestFactCheckTool:
    """Test execute_tool('fact_check', ...) and the fact_check module."""

    @patch("services.fact_check.search_web")
    def test_fact_check_success(self, mock_search):
        """Successful fact check returns formatted evidence."""
        mock_search.return_value = SearchResponse(
            query="Earth is round",
            results=[SearchResult(title="NASA", url="https://nasa.gov", snippet="Confirmed")],
        )

        success, result = execute_tool("fact_check", {"claim": "Earth is round"})

        assert success is True
        assert "Evidence found" in result
        assert "NASA" in result

    def test_fact_check_empty_claim(self):
        """Empty claim returns error."""
        success, result = execute_tool("fact_check", {"claim": ""})

        assert success is False
        assert "No claim" in result

    def test_format_fact_check_with_results(self):
        """format_fact_check produces readable output with results."""
        supporting = SearchResponse(
            query="Earth is round",
            results=[SearchResult(title="NASA", url="https://nasa.gov", snippet="Earth is an oblate spheroid")],
        )
        verification = SearchResponse(
            query="is it true that Earth is round",
            results=[SearchResult(title="Science", url="https://sci.org", snippet="Confirmed by photos")],
        )

        output = format_fact_check("Earth is round", supporting, verification)

        assert "Earth is round" in output
        assert "Evidence found" in output
        assert "NASA" in output
        assert "Verification search" in output
        assert "Science" in output

    def test_format_fact_check_no_results(self):
        """format_fact_check handles empty results gracefully."""
        supporting = SearchResponse(query="test", results=[])
        verification = SearchResponse(query="test", results=[])

        output = format_fact_check("some claim", supporting, verification)

        assert "No results found" in output

    def test_format_fact_check_with_errors(self):
        """format_fact_check handles search errors."""
        supporting = SearchResponse(query="test", results=[], error="Timeout")
        verification = SearchResponse(query="test", results=[], error="API error")

        output = format_fact_check("some claim", supporting, verification)

        assert "Timeout" in output
        assert "API error" in output


# ============================================================================
# Document Search Tool
# ============================================================================



# ============================================================================
# Context Passing
# ============================================================================


class TestContextPassing:
    """Verify context dict flows through execute_tool correctly."""

    def test_calculator_works_without_context(self):
        """Calculator doesn't need context."""
        success, result = execute_tool("calculator", {"expression": "2 + 2"})

        assert success is True
        assert result == "4"

    def test_unknown_tool_returns_error(self):
        """Unknown tool name returns error."""
        success, result = execute_tool("nonexistent_tool", {})

        assert success is False
        assert "Unknown tool" in result

    def test_memory_tools_need_context(self):
        """Memory tools fail gracefully without principal_id."""
        for tool in ("save_memory", "recall_memory", "search_memory"):
            success, result = execute_tool(tool, {"query": "test"})
            assert success is False
            assert "principal_id" in result.lower() or "context" in result.lower() or "unavailable" in result.lower()
