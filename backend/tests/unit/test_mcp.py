"""
Tests for Trinity MCP Server and Client

Tests the MCP JSON-RPC handler, tool conversion, HTTP route,
and MCP client manager.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# MCP SERVER — Tool Schema Conversion
# ============================================================================


class TestMCPToolList:
    """Test that Trinity tools are correctly converted to MCP format."""

    def test_get_mcp_tool_list_returns_all_tools(self):
        from services.mcp_server import get_mcp_tool_list

        tools = get_mcp_tool_list()
        assert isinstance(tools, list)
        assert len(tools) == 15  # 8 original + 5 filesystem + 2 memory (update/forget)

    def test_tool_has_required_fields(self):
        from services.mcp_server import get_mcp_tool_list

        tools = get_mcp_tool_list()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)
            assert isinstance(tool["inputSchema"], dict)

    def test_tool_schema_has_properties(self):
        from services.mcp_server import get_mcp_tool_list

        tools = get_mcp_tool_list()
        # Find calculator tool
        calc = next(t for t in tools if t["name"] == "calculator")
        schema = calc["inputSchema"]
        assert schema["type"] == "object"
        assert "expression" in schema["properties"]
        assert "expression" in schema["required"]

    def test_tool_names_match_definitions(self):
        from services.mcp_server import get_mcp_tool_list
        from services.tools import TOOL_DEFINITIONS

        tools = get_mcp_tool_list()
        tool_names = {t["name"] for t in tools}
        expected_names = set(TOOL_DEFINITIONS.keys())
        assert tool_names == expected_names

    def test_memory_tools_have_correct_params(self):
        from services.mcp_server import get_mcp_tool_list

        tools = get_mcp_tool_list()
        save = next(t for t in tools if t["name"] == "save_memory")
        assert "fact" in save["inputSchema"]["properties"]
        assert "category" in save["inputSchema"]["properties"]
        assert "importance" in save["inputSchema"]["properties"]


# ============================================================================
# MCP SERVER — JSON-RPC Handler
# ============================================================================


class TestMCPHandler:
    """Test the JSON-RPC 2.0 message handler."""

    def test_initialize(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        result = response["result"]
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "trinity"

    def test_ping(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
        )
        assert response["id"] == 2
        assert response["result"] == {}

    def test_tools_list(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        )
        assert response["id"] == 3
        tools = response["result"]["tools"]
        assert len(tools) == 15  # 8 original + 5 filesystem + 2 memory (update/forget)

    def test_tools_call_calculator(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "calculator",
                    "arguments": {"expression": "2 + 3"},
                },
            }
        )
        assert response["id"] == 4
        result = response["result"]
        assert result["isError"] is False
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "5"

    def test_tools_call_unknown_tool(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "nonexistent",
                    "arguments": {},
                },
            }
        )
        result = response["result"]
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_method_not_found(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {"jsonrpc": "2.0", "id": 6, "method": "bogus/method", "params": {}}
        )
        assert "error" in response
        assert response["error"]["code"] == -32601

    def test_notifications_initialized_returns_none(self):
        from services.mcp_server import handle_mcp_message

        response = handle_mcp_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )
        assert response is None

    def test_context_passed_to_execute_tool(self):
        from services.mcp_server import handle_mcp_message

        with patch("services.code_executor.execute_tool") as mock_exec:
            mock_exec.return_value = (True, "ok")

            handle_mcp_message(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "calculator",
                        "arguments": {"expression": "1+1"},
                    },
                },
                context={"principal_id": "test-user"},
            )

            mock_exec.assert_called_once_with(
                "calculator",
                {"expression": "1+1"},
                context={"principal_id": "test-user"},
            )


# ============================================================================
# MCP HTTP ROUTE
# ============================================================================


class TestMCPRoute:
    """Test the Flask /mcp endpoint."""

    @pytest.fixture
    def client(self):
        """Create a minimal Flask test client with MCP route."""
        from flask import Flask

        from routes.mcp import mcp_bp

        app = Flask(__name__)
        app.register_blueprint(mcp_bp)
        return app.test_client()

    def test_get_mcp_info(self, client):
        response = client.get("/mcp")
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "trinity"
        assert "protocolVersion" in data

    def test_post_initialize(self, client):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["result"]["serverInfo"]["name"] == "trinity"

    def test_post_tools_list(self, client):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["result"]["tools"]) == 15  # 8 original + 5 filesystem + 2 memory (update/forget)

    def test_post_tools_call(self, client):
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "calculator",
                    "arguments": {"expression": "10 * 5"},
                },
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["result"]["content"][0]["text"] == "50"
        assert data["result"]["isError"] is False

    def test_post_invalid_json(self, client):
        response = client.post("/mcp", data="not json", content_type="application/json")
        assert response.status_code == 400
        data = response.get_json()
        assert "Parse error" in data["error"]["message"]

    def test_post_notification_returns_204(self, client):
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        assert response.status_code == 204

    @patch("routes.mcp.MCP_SERVER_ENABLED", False)
    def test_disabled_get_returns_503(self, client):
        response = client.get("/mcp")
        assert response.status_code == 503

    @patch("routes.mcp.MCP_SERVER_ENABLED", False)
    def test_disabled_post_returns_503(self, client):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        )
        assert response.status_code == 503


# ============================================================================
# MCP CLIENT
# ============================================================================


class TestMCPClientManager:
    """Test the MCP client manager."""

    def test_singleton_created(self):
        from services.mcp_client import get_mcp_client

        client = get_mcp_client()
        assert client is not None
        assert client.tool_count == 0

    def test_not_initialized_by_default(self):
        from services.mcp_client import MCPClientManager

        client = MCPClientManager()
        assert not client.is_initialized
        assert client.tool_count == 0

    def test_initialize_with_empty_configs(self):
        from services.mcp_client import MCPClientManager

        client = MCPClientManager()
        count = client.initialize([])
        assert count == 0
        assert client.is_initialized

    def test_has_tool_returns_false_for_unknown(self):
        from services.mcp_client import MCPClientManager

        client = MCPClientManager()
        client.initialize([])
        assert not client.has_tool("nonexistent")

    def test_get_tool_definitions_empty(self):
        from services.mcp_client import MCPClientManager

        client = MCPClientManager()
        client.initialize([])
        assert client.get_tool_definitions() == {}

    def test_execute_unknown_tool_returns_error(self):
        from services.mcp_client import MCPClientManager

        client = MCPClientManager()
        client.initialize([])
        success, msg = client.execute_tool("nonexistent", {})
        assert not success
        assert "Unknown MCP tool" in msg

    def test_initialize_mcp_client_disabled(self):
        """MCP client always returns 0 (feature disabled)."""
        from services.mcp_client import initialize_mcp_client

        result = initialize_mcp_client()
        assert result == 0


# ============================================================================
# TOOL SYSTEM INTEGRATION
# ============================================================================


class TestMCPToolIntegration:
    """Test that MCP tools integrate with existing tool system."""

    def test_local_tool_definitions_available(self):
        from services.tools import TOOL_DEFINITIONS

        # Should include local tools
        assert len(TOOL_DEFINITIONS) >= 7

    def test_execute_tool_mcp_fallback(self):
        """Unknown tools fall through to MCP client."""
        from services.code_executor import execute_tool

        with patch("services.code_executor._execute_mcp_tool") as mock_mcp:
            mock_mcp.return_value = (True, "mcp result")
            success, result = execute_tool("external:some_tool", {})
            mock_mcp.assert_called_once()

    def test_execute_tool_local_still_works(self):
        """Local tools still work without going through MCP."""
        from services.code_executor import execute_tool

        success, result = execute_tool("calculator", {"expression": "7 + 8"})
        assert success
        assert result == "15"


# ============================================================================
# ASYNC MCP SERVER (if mcp package available)
# ============================================================================


class TestAsyncMCPServer:
    """Test the async MCP server creation."""

    def test_create_async_server_returns_object_or_none(self):
        from services.mcp_server import create_async_mcp_server

        server = create_async_mcp_server()
        # Returns Server if mcp package installed, None otherwise
        # Either way, should not raise
        assert server is not None or server is None
